"""Centralized SQLite transactions and encrypted local data; no chain state."""

import contextlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import stat

from Crypto.Cipher import AES
from eth_account import Account

from .canonical import canonical, validate
from .crypto import random_id
from chainguard_sandbox.protocol import ToolError

DDL = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE actors (subject TEXT PRIMARY KEY, address TEXT NOT NULL UNIQUE, data BLOB NOT NULL);
CREATE TABLE tasks (task_id TEXT PRIMARY KEY, requester TEXT NOT NULL, agent TEXT NOT NULL,
 data BLOB NOT NULL, revoked INTEGER NOT NULL DEFAULT 0, used_actions INTEGER NOT NULL DEFAULT 0);
CREATE TABLE actions (action_id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(task_id),
 tool_name TEXT NOT NULL, state TEXT NOT NULL, data BLOB NOT NULL, result BLOB);
CREATE TABLE approvals (action_id TEXT NOT NULL REFERENCES actions(action_id), signer TEXT NOT NULL,
 signature BLOB NOT NULL, PRIMARY KEY(action_id,signer));
CREATE TABLE idempotency (subject TEXT NOT NULL, operation TEXT NOT NULL, key TEXT NOT NULL,
 request_mac TEXT NOT NULL, entity_id TEXT NOT NULL, PRIMARY KEY(subject,operation,key));
CREATE TABLE nonces (requester TEXT PRIMARY KEY, next_nonce TEXT NOT NULL);
CREATE TABLE audit (sequence INTEGER PRIMARY KEY, previous_hash TEXT NOT NULL, event_hash TEXT NOT NULL,
 event_json BLOB NOT NULL, signature TEXT);
"""


class CentralStore:
    @classmethod
    def create(cls, root, group, policy_hash, tool_root):
        if group not in {"A", "B"}:
            raise ValueError("Only the authorized central A/B groups exist")
        root = Path(root)
        root.mkdir(mode=0o700)
        for name in ("data.key", "jwt.key", "audit.key", "admin.key", "state.sqlite3"):
            content = b"" if name.endswith("sqlite3") else secrets.token_bytes(32)
            descriptor = os.open(root / name, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
        signer = Account.from_key((root / "audit.key").read_bytes()).address.lower()
        pinned = {"group": group, "policy_hash": policy_hash, "tool_root": str(tool_root),
                  "deployment_id": random_id(), "audit_signer": signer,
                  "domain": {"name": "ChainGuard ExecutionRegistry", "version": "1", "chainId": "0", "verifyingContract": signer}}
        descriptor = os.open(root / "deployment.json", os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(canonical(pinned))
        store = cls(root)
        with store.connect() as db:
            db.executescript(DDL)
            values = dict(pinned, policy_epoch=1, paused=False)
            db.executemany("INSERT INTO meta VALUES (?,?)", [(key, json.dumps(value)) for key, value in values.items()])
            if group == "B":
                db.executescript("""
CREATE TRIGGER audit_no_update BEFORE UPDATE ON audit BEGIN SELECT RAISE(ABORT,'append only'); END;
CREATE TRIGGER audit_no_delete BEFORE DELETE ON audit BEGIN SELECT RAISE(ABORT,'append only'); END;
""")
        return store

    def __init__(self, root):
        self.root = Path(root)
        if self.root.is_symlink() or not self.root.is_dir():
            raise ToolError("POLICY_DENY")
        for name in ("data.key", "jwt.key", "audit.key", "admin.key", "state.sqlite3", "deployment.json"):
            path = self.root / name
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ToolError("POLICY_DENY")
            if os.name == "posix" and (info.st_uid != os.geteuid() or info.st_mode & 0o077):
                raise ToolError("POLICY_DENY")
        self.deployment = json.loads((self.root / "deployment.json").read_text())

    def private(self, name):
        if name not in {"data.key", "jwt.key", "audit.key", "admin.key"}:
            raise ToolError("FORBIDDEN")
        path = self.root / name
        if path.is_symlink():
            raise ToolError("POLICY_DENY")
        return path.read_bytes()

    def admin(self, key):
        if type(key) is not bytes or not secrets.compare_digest(key, self.private("admin.key")):
            raise ToolError("FORBIDDEN")

    def seal(self, context, value):
        cipher = AES.new(self.private("data.key"), AES.MODE_GCM, nonce=secrets.token_bytes(12))
        cipher.update(context.encode())
        encrypted, tag = cipher.encrypt_and_digest(canonical(value))
        return cipher.nonce + tag + encrypted

    def unseal(self, context, data):
        try:
            cipher = AES.new(self.private("data.key"), AES.MODE_GCM, nonce=data[:12])
            cipher.update(context.encode())
            return json.loads(cipher.decrypt_and_verify(data[28:], data[12:28]))
        except (ValueError, TypeError):
            raise ToolError("STATE_CONFLICT") from None

    @contextlib.contextmanager
    def connect(self):
        if (self.root / "state.sqlite3").is_symlink():
            raise ToolError("POLICY_DENY")
        db = sqlite3.connect(self.root / "state.sqlite3", timeout=30, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA synchronous=FULL")
        try:
            yield db
        finally:
            db.close()

    @contextlib.contextmanager
    def transaction(self):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise

    def meta(self, db, key):
        row = db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        if row is None:
            raise ToolError("STATE_CONFLICT")
        value = json.loads(row[0])
        if key in self.deployment and value != self.deployment[key]:
            raise ToolError("POLICY_REVOKED")
        return value

    def register_actor(self, admin_key, actor):
        self.admin(admin_key)
        validate("Address", actor["address"])
        known_roles = json.loads((Path(__file__).resolve().parents[3] / "spec/identifiers.json").read_text())["roles"]
        if not actor["subject"] or not set(actor["roles"]) <= set(known_roles) or type(actor["active"]) is not bool:
            raise ToolError("SCHEMA_INVALID")
        with self.transaction() as db:
            db.execute("INSERT INTO actors VALUES (?,?,?) ON CONFLICT(subject) DO UPDATE SET address=excluded.address,data=excluded.data",
                       (actor["subject"], actor["address"], self.seal("actor/" + actor["subject"], actor)))

    def actor(self, db, subject=None, address=None):
        row = db.execute("SELECT * FROM actors WHERE " + ("subject=?" if subject is not None else "address=?"),
                         (subject if subject is not None else address,)).fetchone()
        return self.unseal("actor/" + row["subject"], row["data"]) if row else None

    def task(self, db, task_id):
        row = db.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        if row is None:
            raise ToolError("NOT_FOUND")
        return row, self.unseal("task/" + task_id, row["data"])

    def action(self, db, action_id):
        row = db.execute("SELECT * FROM actions WHERE action_id=?", (action_id,)).fetchone()
        if row is None:
            raise ToolError("NOT_FOUND")
        return row, self.unseal("action/" + action_id, row["data"])
