"""C-group encrypted state plus durable write-ahead transaction journal."""
import json
import os
from pathlib import Path
import secrets

from eth_account import Account

from .central_store import CentralStore, DDL
from .canonical import canonical
from .crypto import random_id
from .policy import check_policy_freeze

CHAIN_DDL = """
CREATE TABLE chain_transactions(action_id TEXT NOT NULL,kind TEXT NOT NULL,nonce INTEGER NOT NULL UNIQUE,
 tx_hash TEXT NOT NULL UNIQUE,raw BLOB NOT NULL,state TEXT NOT NULL,PRIMARY KEY(action_id,kind));
CREATE TABLE chain_events(sequence INTEGER PRIMARY KEY,action_id TEXT,event TEXT NOT NULL,data BLOB NOT NULL);
"""


class ChainStore(CentralStore):
    @classmethod
    def create(cls, root):
        root = Path(root)
        root.mkdir(mode=0o700)
        for name in ("data.key","jwt.key","audit.key","admin.key","state.sqlite3"):
            descriptor = os.open(root/name,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
            with os.fdopen(descriptor,"wb") as stream:
                stream.write(b"" if name.endswith("sqlite3") else secrets.token_bytes(32))
        pinned = {"group":"C","policy_hash":check_policy_freeze(),"deployment_id":random_id(),
                  "audit_signer":Account.from_key((root/'audit.key').read_bytes()).address.lower()}
        (root/'deployment.json').write_bytes(canonical(pinned))
        os.chmod(root/'deployment.json',0o600)
        store = cls(root)
        with store.connect() as db:
            db.executescript(DDL+CHAIN_DDL)
            db.executemany("INSERT INTO meta VALUES (?,?)",[(k,json.dumps(v)) for k,v in pinned.items()])
        return store

    def save(self, db, action_id, state, data):
        db.execute("UPDATE actions SET state=?,data=? WHERE action_id=?",(state,self.seal('action/'+action_id,data),action_id))

    def event(self, db, action_id, event, data):
        db.execute("INSERT INTO chain_events(action_id,event,data) VALUES (?,?,?)",(action_id,event,canonical(data)))
