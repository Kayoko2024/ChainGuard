"""Encrypted conversation history. Login sessions and execution actions stay separate."""
import hashlib
import hmac
import json
import secrets
import time
from .canonical import canonical,validate
from chainguard_sandbox.protocol import ToolError

ACTIVE = {'QUEUED','AGENT_RUNNING','AWAITING_APPROVAL','AWAITING_TOOL_APPROVAL','RESUMING','UNKNOWN','INTERRUPTED'}


class Conversations:
    def __init__(self,store):
        self.store=store
        with store.db() as db:db.executescript('''
        CREATE TABLE IF NOT EXISTS conversations(id TEXT PRIMARY KEY,owner TEXT NOT NULL,state TEXT NOT NULL,version INTEGER NOT NULL,data BLOB NOT NULL,created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS conversation_runs(id TEXT PRIMARY KEY,session_id TEXT NOT NULL,mac TEXT NOT NULL,ordinal INTEGER NOT NULL,lease TEXT,lease_until REAL DEFAULT 0,UNIQUE(session_id,ordinal));
        CREATE TABLE IF NOT EXISTS conversation_legacy(job_id TEXT PRIMARY KEY,session_id TEXT UNIQUE NOT NULL,owner TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS conversation_renewals(id TEXT PRIMARY KEY,session_id TEXT NOT NULL,request_mac TEXT NOT NULL,state TEXT NOT NULL,data BLOB NOT NULL);
        ''')

    def create(self,id,owner,scope):
        validate('Bytes32',id)
        value=dict(scope=scope,history=[],low_grant=None)
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE');old=db.execute('SELECT * FROM conversations WHERE id=?',(id,)).fetchone()
            if old:
                data=self.store.open('conversation/'+id,old['data'])
                if old['owner']!=owner or data['scope']!=scope:raise ToolError('IDEMPOTENCY_CONFLICT')
            else:db.execute('INSERT INTO conversations VALUES (?,?,?,?,?,?)',(id,owner,'OPEN',0,self.store.seal('conversation/'+id,value),time.time()))
        return self.get(id,owner)

    def get(self,id,owner=None):
        with self.store.db() as db:row=db.execute('SELECT * FROM conversations WHERE id=?',(id,)).fetchone()
        if not row:raise ToolError('NOT_FOUND')
        if owner is not None and row['owner']!=owner:raise ToolError('FORBIDDEN')
        return dict(id=id,owner=row['owner'],state=row['state'],version=row['version'],created=row['created'],**self.store.open('conversation/'+id,row['data']))

    def listing(self,owner,*,include_hidden=False):
        with self.store.db() as db:ids=[r[0] for r in db.execute('SELECT id FROM conversations WHERE owner=? ORDER BY created DESC',(owner,))]
        if not include_hidden:
            hidden=self.store.hidden(owner);ids=[id for id in ids if ('conversation',id) not in hidden]
        return [self.get(id,owner) for id in ids]

    def update(self,id,**fields):
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT * FROM conversations WHERE id=?',(id,)).fetchone()
            if not row:raise ToolError('NOT_FOUND')
            value=self.store.open('conversation/'+id,row['data']);value.update(fields)
            db.execute('UPDATE conversations SET data=? WHERE id=?',(self.store.seal('conversation/'+id,value),id))

    def accepted(self,id,owner,message_id,text):
        self.get(id,owner)
        validate('Bytes32',message_id)
        mac=hmac.digest(self.store.key,canonical(dict(session_id=id,text=text)),'sha256').hex()
        with self.store.db() as db:old=db.execute('SELECT * FROM conversation_runs WHERE id=?',(message_id,)).fetchone()
        if not old:return False
        if old['session_id']!=id or old['mac']!=mac:raise ToolError('IDEMPOTENCY_CONFLICT')
        return True

    def idle(self,db,id,data):
        rows=db.execute('SELECT j.state FROM conversation_runs r JOIN jobs j ON r.id=j.id WHERE r.session_id=?',(id,)).fetchall()
        if any(r[0] in ACTIVE for r in rows):raise ToolError('CONVERSATION_BUSY')
        legacy=data.get('legacy_job_id')
        if legacy and not data.get('legacy_resolved'):
            row=db.execute('SELECT state FROM jobs WHERE id=?',(legacy,)).fetchone()
            if row and row[0] in ACTIVE:raise ToolError('CONVERSATION_BUSY')

    def append(self,id,owner,message_id,text,expected_version,*,grant_digest=None):
        validate('Bytes32',message_id)
        if not isinstance(text,str) or not 1<=len(text.strip())<=8000 or type(expected_version) is not int:raise ToolError('SCHEMA_INVALID')
        mac=hmac.digest(self.store.key,canonical(dict(session_id=id,text=text)),'sha256').hex()
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT * FROM conversations WHERE id=?',(id,)).fetchone()
            if not row or row['owner']!=owner:raise ToolError('FORBIDDEN')
            old=db.execute('SELECT * FROM conversation_runs WHERE id=?',(message_id,)).fetchone()
            if old:
                if old['session_id']!=id or old['mac']!=mac:raise ToolError('IDEMPOTENCY_CONFLICT')
                return False
            if row['state']!='OPEN':raise ToolError('CONVERSATION_CLOSED')
            if row['version']!=expected_version:raise ToolError('STATE_CONFLICT')
            data=self.store.open('conversation/'+id,row['data'])
            self.idle(db,id,data)
            if data.get('pending_renewal'):raise ToolError('AUTH_RENEWAL_PENDING')
            if grant_digest is not None and (data.get('low_grant') or {}).get('digest')!=grant_digest:raise ToolError('STATE_CONFLICT')
            scope=data['scope']
            value=dict(scope,task_text=text)
            request_mac=hmac.digest(self.store.key,canonical(value),'sha256').hex()
            value.update(conversation_id=id,conversation_owner=owner)
            if grant_digest:value['conversation_grant_digest']=grant_digest
            db.execute('INSERT INTO jobs VALUES (?,?,?,?,?)',(message_id,request_mac,'QUEUED',self.store.seal(message_id,value),time.time()))
            db.execute('INSERT INTO conversation_runs(id,session_id,mac,ordinal) VALUES (?,?,?,?)',(message_id,id,mac,row['version']+1))
            db.execute('UPDATE conversations SET version=version+1 WHERE id=?',(id,))
        return True

    def attach_legacy(self,job_id,owner,scope,history):
        validate('Bytes32',job_id)
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            old=db.execute('SELECT * FROM conversation_legacy WHERE job_id=?',(job_id,)).fetchone()
            if old:
                if old['owner']!=owner:raise ToolError('FORBIDDEN')
                return old['session_id']
            sid='0x'+secrets.token_hex(32)
            value=dict(scope=scope,history=history,low_grant=None,legacy_job_id=job_id)
            db.execute('INSERT INTO conversations VALUES (?,?,?,?,?,?)',(sid,owner,'OPEN',0,self.store.seal('conversation/'+sid,value),time.time()))
            db.execute('INSERT INTO conversation_legacy VALUES (?,?,?)',(job_id,sid,owner))
        return sid

    def legacy_session(self,job_id):
        with self.store.db() as db:row=db.execute('SELECT session_id FROM conversation_legacy WHERE job_id=?',(job_id,)).fetchone()
        return row[0] if row else None

    def renewal(self,id):
        with self.store.db() as db:row=db.execute('SELECT * FROM conversation_renewals WHERE id=?',(id,)).fetchone()
        return dict(state=row['state'],**self.store.open('renewal/'+id,row['data'])) if row else None

    def begin_renewal(self,sid,owner,request_id,expected,options,message,scopes,digest):
        validate('Bytes32',request_id)
        request_mac=hmac.digest(self.store.key,canonical(dict(session_id=sid,expected=expected,options=options)),'sha256').hex()
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT * FROM conversations WHERE id=?',(sid,)).fetchone()
            if not row or row['owner']!=owner:raise ToolError('FORBIDDEN')
            prior=db.execute('SELECT * FROM conversation_renewals WHERE id=?',(request_id,)).fetchone()
            if prior:
                if prior['session_id']!=sid or prior['request_mac']!=request_mac:raise ToolError('IDEMPOTENCY_CONFLICT')
                return request_id
            if row['state']!='OPEN':raise ToolError('CONVERSATION_CLOSED')
            value=self.store.open('conversation/'+sid,row['data']);self.idle(db,sid,value)
            current=(value.get('low_grant') or {}).get('digest')
            if current!=expected:raise ToolError('STATE_CONFLICT')
            if value.get('pending_renewal'):
                pending=db.execute('SELECT * FROM conversation_renewals WHERE id=?',(value['pending_renewal'],)).fetchone()
                if pending['request_mac']!=request_mac:raise ToolError('AUTH_RENEWAL_PENDING')
                return pending['id']
            data=dict(message=message,scopes=scopes,digest=digest,options=options,previous_digest=expected)
            db.execute('INSERT INTO conversation_renewals VALUES (?,?,?,?,?)',(request_id,sid,request_mac,'PREPARED',self.store.seal('renewal/'+request_id,data)))
            value['pending_renewal']=request_id
            db.execute('UPDATE conversations SET data=? WHERE id=?',(self.store.seal('conversation/'+sid,value),sid))
        return request_id

    def save_renewal(self,id,envelope):
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT * FROM conversation_renewals WHERE id=?',(id,)).fetchone()
            value=self.store.open('renewal/'+id,row['data'])
            if value.get('envelope') and value['envelope']!=envelope:raise ToolError('IDEMPOTENCY_CONFLICT')
            if row['state']=='ACTIVE':return
            value['envelope']=envelope
            db.execute('UPDATE conversation_renewals SET state=?,data=? WHERE id=?',('SIGNED',self.store.seal('renewal/'+id,value),id))

    def activate_renewal(self,sid,id):
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT * FROM conversations WHERE id=?',(sid,)).fetchone()
            data=self.store.open('conversation/'+sid,row['data'])
            renewal=db.execute('SELECT * FROM conversation_renewals WHERE id=? AND session_id=?',(id,sid)).fetchone()
            if not renewal:raise ToolError('STATE_CONFLICT')
            value=self.store.open('renewal/'+id,renewal['data'])
            if renewal['state']=='ACTIVE':return
            if data.get('pending_renewal')!=id or row['state']!='OPEN':raise ToolError('STATE_CONFLICT')
            self.idle(db,sid,data)
            data.update(low_grant=value['envelope'],pending_renewal=None)
            data['auth_revision']=data.get('auth_revision',0)+1
            data['scope']['session_grant']=value['options']
            db.execute('UPDATE conversations SET data=? WHERE id=?',(self.store.seal('conversation/'+sid,data),sid))
            db.execute("UPDATE conversation_renewals SET state='ACTIVE' WHERE id=?",(id,))

    def remember_failure(self,run_id,lease):
        from .conversation_memory import from_job
        job=self.store.get(run_id)
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT * FROM conversation_runs WHERE id=? AND lease=?',(run_id,lease)).fetchone()
            if not row:raise ToolError('STATE_CONFLICT')
            conversation=db.execute('SELECT data FROM conversations WHERE id=?',(row['session_id'],)).fetchone()
            data=self.store.open('conversation/'+row['session_id'],conversation['data'])
            fallback=list(data['history'])
            if not job.get('runner_snapshot'):fallback.append(dict(role='user',content=job['task_text']))
            data['history']=from_job(job,self.store.events(run_id),fallback)
            db.execute('UPDATE conversations SET data=? WHERE id=?',(self.store.seal('conversation/'+row['session_id'],data),row['session_id']))

    def runs(self,id):
        with self.store.db() as db:return [r[0] for r in db.execute('SELECT id FROM conversation_runs WHERE session_id=? ORDER BY ordinal',(id,))]

    def claim(self,run_id):
        lease=secrets.token_hex(16)
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            changed=db.execute('UPDATE conversation_runs SET lease=?,lease_until=? WHERE id=? AND (lease IS NULL OR lease_until<?)',(lease,time.time()+180,run_id,time.time())).rowcount
        return lease if changed else None

    def checkpoint(self,run_id,lease,snapshot):
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT lease FROM conversation_runs WHERE id=?',(run_id,)).fetchone()
            if not row or row['lease']!=lease:raise ToolError('STATE_CONFLICT')
            job=db.execute('SELECT data FROM jobs WHERE id=?',(run_id,)).fetchone();value=self.store.open(run_id,job['data']);value['runner_snapshot']=snapshot
            db.execute('UPDATE jobs SET data=? WHERE id=?',(self.store.seal(run_id,value),run_id))
            db.execute('UPDATE conversation_runs SET lease_until=? WHERE id=?',(time.time()+180,run_id))

    def release(self,run_id,lease):
        with self.store.db() as db:db.execute('UPDATE conversation_runs SET lease=NULL,lease_until=0 WHERE id=? AND lease=?',(run_id,lease))

    def complete(self,run_id,lease,state,output,**fields):
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM conversation_runs WHERE id=? AND lease=?',(run_id,lease)).fetchone()
            if not row:raise ToolError('STATE_CONFLICT')
            job=db.execute('SELECT data FROM jobs WHERE id=?',(run_id,)).fetchone()
            value=self.store.open(run_id,job['data']);snapshot=value['runner_snapshot']
            if snapshot['phase']!='COMPLETED':raise ToolError('STATE_CONFLICT')
            value.update(agent_output=output,**fields)
            conversation=db.execute('SELECT data FROM conversations WHERE id=?',(row['session_id'],)).fetchone()
            data=self.store.open('conversation/'+row['session_id'],conversation['data']);data['history']=snapshot['messages']
            db.execute('UPDATE conversations SET data=? WHERE id=?',(self.store.seal('conversation/'+row['session_id'],data),row['session_id']))
            db.execute('UPDATE jobs SET state=?,data=? WHERE id=?',(state,self.store.seal(run_id,value),run_id))

    def close(self,id,owner):
        self.get(id,owner)
        with self.store.db() as db:db.execute("UPDATE conversations SET state='CLOSED' WHERE id=? AND owner=?",(id,owner))
        return self.get(id,owner)
