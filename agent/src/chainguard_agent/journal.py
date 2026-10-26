"""Agent-owned encrypted request journal and redacted observation log."""
from contextlib import contextmanager
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import sqlite3
import time

from Crypto.Cipher import AES
from chainguard_gateway.canonical import canonical
from chainguard_sandbox.protocol import ToolError


class Journal:
    def __init__(self,root):
        self.root=Path(root)
        self.root.mkdir(mode=0o700,parents=True,exist_ok=True)
        key=self.root/'journal.key'
        if not key.exists():
            fd=os.open(key,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
            with os.fdopen(fd,'wb') as f: f.write(secrets.token_bytes(32))
        self.key=key.read_bytes()
        with self.connect() as db:
            db.executescript('''
CREATE TABLE IF NOT EXISTS calls(run_id TEXT,call_id TEXT,task_id TEXT,request_mac TEXT,idempotency_key TEXT,
 action_id TEXT,data BLOB,PRIMARY KEY(run_id,call_id));
CREATE TABLE IF NOT EXISTS events(sequence INTEGER PRIMARY KEY,data TEXT NOT NULL);
''')

    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.root/'journal.sqlite3',timeout=30,isolation_level=None)
        db.row_factory=sqlite3.Row
        db.execute('PRAGMA synchronous=FULL')
        try: yield db
        finally: db.close()

    def seal(self,context,value):
        cipher=AES.new(self.key,AES.MODE_GCM,nonce=secrets.token_bytes(12)); cipher.update(context.encode())
        ciphertext,tag=cipher.encrypt_and_digest(canonical(value))
        return cipher.nonce+tag+ciphertext

    def unseal(self,context,value):
        try:
            cipher=AES.new(self.key,AES.MODE_GCM,nonce=value[:12]); cipher.update(context.encode())
            return json.loads(cipher.decrypt_and_verify(value[28:],value[12:28]))
        except ValueError: raise ToolError('STATE_CONFLICT') from None

    def claim(self,run_id,task_id,call):
        request={'task_id':task_id,'tool_name':call.name,'params':call.arguments}
        mac=hmac.digest(self.key,canonical(request),'sha256').hex()
        key='0x'+hmac.digest(self.key,canonical([run_id,call.id]),'sha256').hex()
        context=run_id+'/'+call.id
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM calls WHERE run_id=? AND call_id=?',(run_id,call.id)).fetchone()
            if row:
                if row['request_mac']!=mac: raise ToolError('IDEMPOTENCY_CONFLICT')
                return dict(row),self.unseal(context,row['data'])
            data={'request':request,'result':None}
            db.execute('INSERT INTO calls VALUES (?,?,?,?,?,?,?)',(run_id,call.id,task_id,mac,key,None,self.seal(context,data)))
            db.commit()
        return {'idempotency_key':key,'action_id':None},data

    def save(self,run_id,call_id,action_id,data):
        with self.connect() as db:
            db.execute('UPDATE calls SET action_id=?,data=? WHERE run_id=? AND call_id=?',
                (action_id,self.seal(run_id+'/'+call_id,data),run_id,call_id))

    def event(self,**data):
        value={'schema_version':1,'observed_at':str(int(time.time())),'agent_attempted_tool':False,
            'policy_verdict':None,'tool_executed':None,'attack_success':None,**data}
        # Fixed replay cannot establish an LLM attack-success outcome.
        if value.get('mode')=='fixed_trace': value['attack_success']=None
        with self.connect() as db: db.execute('INSERT INTO events(data) VALUES (?)',(canonical(value).decode(),))

    def events(self):
        with self.connect() as db: return [json.loads(r[0]) for r in db.execute('SELECT data FROM events ORDER BY sequence')]
