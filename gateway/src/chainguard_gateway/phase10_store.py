"""Encrypted local business state, durable idempotency, hashed expiring sessions."""
import contextlib
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import time
from Crypto.Cipher import AES
from .canonical import canonical
from chainguard_sandbox.protocol import ToolError


class OperationsStore:
    def __init__(self, root):
        self.root=Path(root); self.root.mkdir(parents=True,exist_ok=True)
        key=self.root/'operations.key'
        if not key.exists():
            with key.open('xb') as f: f.write(secrets.token_bytes(32))
        self.key=key.read_bytes()
        with self.db() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, request_mac TEXT NOT NULL,
                state TEXT NOT NULL, data BLOB NOT NULL, created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY,role TEXT NOT NULL,csrf TEXT NOT NULL,expires REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,job_id TEXT NOT NULL,data BLOB NOT NULL);
                CREATE TABLE IF NOT EXISTS controls(action_id TEXT PRIMARY KEY,hold INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS hidden_items(kind TEXT NOT NULL,id TEXT NOT NULL,owner TEXT NOT NULL,
                    is_hidden INTEGER NOT NULL DEFAULT 1,updated REAL NOT NULL,PRIMARY KEY(kind,id,owner));
                CREATE TABLE IF NOT EXISTS projections(id TEXT PRIMARY KEY,data BLOB NOT NULL,updated REAL NOT NULL);''')

    @contextlib.contextmanager
    def db(self):
        db=sqlite3.connect(self.root/'operations.sqlite3',timeout=30); db.row_factory=sqlite3.Row
        db.execute('PRAGMA synchronous=FULL')
        try:
            yield db; db.commit()
        except BaseException: db.rollback(); raise
        finally: db.close()

    def seal(self,context,value):
        # Private observational metadata includes measured floating point latency.
        # It is not an ActionIntent/commitment/request. Frozen protocol JSON still
        # goes through canonical()/validate() at every original /v1 boundary.
        cipher=AES.new(self.key,AES.MODE_GCM); cipher.update(context.encode())
        raw,tag=cipher.encrypt_and_digest(json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode('utf8'))
        return cipher.nonce+tag+raw

    def open(self,context,raw):
        cipher=AES.new(self.key,AES.MODE_GCM,nonce=raw[:16]); cipher.update(context.encode())
        return json.loads(cipher.decrypt_and_verify(raw[32:],raw[16:32]))

    def create(self,id,value):
        import hmac
        mac=hmac.digest(self.key,canonical(value),'sha256').hex()
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE'); old=db.execute('SELECT * FROM jobs WHERE id=?',(id,)).fetchone()
            if old:
                if old['request_mac']!=mac: raise ToolError('IDEMPOTENCY_CONFLICT')
                return False
            db.execute('INSERT INTO jobs VALUES (?,?,?,?,?)',(id,mac,'QUEUED',self.seal(id,value),time.time()))
        return True

    def get(self,id):
        with self.db() as db: row=db.execute('SELECT * FROM jobs WHERE id=?',(id,)).fetchone()
        if not row: raise ToolError('NOT_FOUND')
        return dict(id=id,state=row['state'],created=row['created'],**self.open(id,row['data']))

    def update(self,id,*,state=None,**fields):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE'); row=db.execute('SELECT * FROM jobs WHERE id=?',(id,)).fetchone()
            if not row: raise ToolError('NOT_FOUND')
            value=self.open(id,row['data']); value.update(fields)
            db.execute('UPDATE jobs SET state=?,data=? WHERE id=?',(state or row['state'],self.seal(id,value),id))

    def jobs(self):
        with self.db() as db: ids=[r[0] for r in db.execute('SELECT id FROM jobs ORDER BY created DESC')]
        return [self.get(id) for id in ids]

    def hide(self,kind,id,owner):
        table={'conversation':'conversations','task':'jobs'}.get(kind)
        if not table:raise ToolError('SCHEMA_INVALID')
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM '+table+' WHERE id=?',(id,)).fetchone()
            if not row:raise ToolError('NOT_FOUND')
            if kind=='conversation' and row['owner']!=owner:raise ToolError('FORBIDDEN')
            db.execute('INSERT INTO hidden_items VALUES (?,?,?,1,?) ON CONFLICT(kind,id,owner) DO UPDATE SET is_hidden=1,updated=excluded.updated',(kind,id,owner,time.time()))
        return dict(id=id,is_hidden=True)

    def hidden(self,owner):
        with self.db() as db:return {(r['kind'],r['id']) for r in db.execute('SELECT kind,id FROM hidden_items WHERE owner=? AND is_hidden=1',(owner,))}

    def visible_jobs(self,owner):
        hidden=self.hidden(owner)
        # Legacy jobs are referenced by a mapping, never rewritten on attachment.
        with self.db() as db:
            linked={r['job_id']:r['session_id'] for r in db.execute('SELECT job_id,session_id FROM conversation_legacy WHERE owner=?',(owner,))} if db.execute("SELECT 1 FROM sqlite_master WHERE name='conversation_legacy'").fetchone() else {}
        return [j for j in self.jobs() if ('task',j['id']) not in hidden and ('conversation',j.get('conversation_id') or linked.get(j['id'])) not in hidden]

    def cache(self,id,value):
        with self.db() as db:db.execute('INSERT INTO projections VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data,updated=excluded.updated',(id,self.seal('projection/'+id,value),time.time()))

    def cached(self,id,default=None):
        with self.db() as db:row=db.execute('SELECT data FROM projections WHERE id=?',(id,)).fetchone()
        return self.open('projection/'+id,row['data']) if row else default

    def event(self,id,value):
        with self.db() as db: db.execute('INSERT INTO events(job_id,data) VALUES (?,?)',(id,self.seal(id,value)))

    def events(self,id):
        with self.db() as db: rows=db.execute('SELECT data FROM events WHERE job_id=? ORDER BY id',(id,)).fetchall()
        return [self.open(id,r[0]) for r in rows]

    def login(self,role):
        token=secrets.token_urlsafe(32); csrf=secrets.token_urlsafe(32)
        with self.db() as db: db.execute('INSERT INTO sessions VALUES (?,?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),role,csrf,time.time()+3600))
        return token,csrf

    def session(self,token):
        with self.db() as db: row=db.execute('SELECT * FROM sessions WHERE token_hash=?',(hashlib.sha256((token or '').encode()).hexdigest(),)).fetchone()
        if not row or row['expires']<=time.time(): raise ToolError('AUTH_REQUIRED')
        return dict(row)


class PublicStore:
    def __init__(self,path):
        self.path=Path(path); self.path.parent.mkdir(parents=True,exist_ok=True)
        with sqlite3.connect(self.path) as db: db.execute('CREATE TABLE IF NOT EXISTS actions(entry_id TEXT PRIMARY KEY, data TEXT NOT NULL)')
    def publish(self,value):
        with sqlite3.connect(self.path) as db:
            db.execute('INSERT INTO actions VALUES (?,?) ON CONFLICT(entry_id) DO UPDATE SET data=excluded.data',(value['entry_id'],json.dumps(value)))
    def actions(self):
        with sqlite3.connect('file:'+self.path.as_posix()+'?mode=ro',uri=True) as db:
            return [json.loads(r[0]) for r in db.execute('SELECT data FROM actions ORDER BY rowid DESC')]
