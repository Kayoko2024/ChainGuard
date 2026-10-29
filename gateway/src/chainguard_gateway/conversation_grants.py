"""Versioned LOW conversation signatures and independent persistent execution gates."""
import contextlib
import json
import secrets
import time
from eth_account.messages import encode_typed_data
from eth_utils import keccak
from .canonical import canonical,validate
from .session_grants import ToolPolicy,hash_json,recover,sign,TYPES,MESSAGE_TYPES,fn
from chainguard_sandbox.protocol import ToolError

# These are NEW types. The task-bound SessionGrant and original protocol stay byte-identical.
NEW_TYPES={
 'ConversationGrant':[('requester','address'),('agent','address'),('sessionId','bytes32'),('toolsHash','bytes32'),('nonce','uint64'),('issuedAt','uint64'),('expiresAt','uint64'),('maxCalls','uint32')],
 'ConversationBinding':[('sessionId','bytes32'),('taskId','bytes32'),('grantDigest','bytes32'),('expiresAt','uint64')],
 'ConversationClose':[('sessionId','bytes32'),('grantDigest','bytes32'),('closedAt','uint64')],
}
# Extend the shared serializer with distinct primary types, never replacing V1.
for _kind,_fields in NEW_TYPES.items():
    MESSAGE_TYPES[_kind]=[{'name':n,'type':t} for n,t in _fields]

ABI=[fn('publisher',[],['address']),fn('policyRegistry',[],['address']),
 fn('latest',['bytes32'],['uint64']),fn('checkpoints',['bytes32','uint64'],['bytes32','uint32','uint64','bool']),
 fn('anchor',['bytes32','uint64','bytes32','uint32','bytes32','bool'],mutability='nonpayable')]

def domain(config):return dict(name='ChainGuard ConversationSessionRegistry',version='1',chainId=config['deployment']['chainId'],verifyingContract=config['conversation']['address'])
def digest(kind,message,d):
    m=encode_typed_data(domain_data=d,message_types={kind:MESSAGE_TYPES[kind]},message_data=message)
    return '0x'+keccak(b'\x19'+m.version+m.header+m.body).hex()

def builtin_revision(name):
    from .default_tools import functions,READ_TOOLS
    if name not in READ_TOOLS:raise ToolError('UNKNOWN_TOOL')
    return hash_json(dict(kind='builtin-low-v1',name=name,schema=functions([name])[0]['function']['parameters']))

class ConversationPolicy(ToolPolicy):
    def __init__(self,config,urls):super().__init__(config,urls);self.domain=domain(config)
    def snapshot(self):
        from .chain_rpc import Contract
        snapshot=super().snapshot();block=hex(int(snapshot['number']))
        for node in self.chain.nodes:
            item=self.config['conversation'];code=node.call('eth_getCode',[item['address'],block])
            if code=='0x' or '0x'+keccak(bytes.fromhex(code[2:])).hex()!=item['codeHash']:raise ToolError('CHAIN_UNAVAILABLE')
            if Contract('ConversationSessionRegistry',item['address'],node,ABI).call('policyRegistry',block=block)!=self.chain.policy.address:raise ToolError('POLICY_REVOKED')
        return snapshot
    def verify(self,envelope,live=True):
        try:
            if set(envelope)!={'message','scopes','signature'}:raise ValueError()
            m=envelope['message'];scopes=envelope['scopes']
            if set(m)!={n for n,_ in NEW_TYPES['ConversationGrant']} or not isinstance(scopes,list) or not 1<=len(scopes)<=24:raise ValueError()
            validate('Bytes32',m['sessionId'])
            if m['sessionId']=='0x'+'00'*32:raise ValueError()
            validate('Address',m['requester']);validate('Address',m['agent'])
            if any(type(m[k]) is not int for k in ['nonce','issuedAt','expiresAt','maxCalls']) or not 0<=m['nonce']<=2**53-1 or not 0<=m['issuedAt']<m['expiresAt']<=2**53-1 or not 1<=m['maxCalls']<=10000:raise ValueError()
            if len({s['name'] for s in scopes})!=len(scopes):raise ValueError()
            for s in scopes:
                if set(s)!={'name','revision','allowed_keys','generation'} or not isinstance(s['allowed_keys'],list) or not s['allowed_keys']:raise ValueError()
                from .default_tools import READ_TOOLS
                if s['name'] not in READ_TOOLS and not s['name'].startswith('custom.'):raise ValueError()
                validate('Bytes32',s['revision'])
                if any(type(k) is not str for k in s['allowed_keys']) or len(set(s['allowed_keys']))!=len(s['allowed_keys']) or type(s['generation']) is not int:raise ValueError()
                if s['name'] in READ_TOOLS and s['revision']!=builtin_revision(s['name']):raise ValueError()
            if hash_json(scopes)!=m['toolsHash'] or recover('ConversationGrant',m,self.domain,envelope['signature'])!=m['requester'].lower():raise ValueError()
            now=int(time.time())
            if m['issuedAt']>now or not 0<m['expiresAt']-m['issuedAt']<=86400 or live and m['expiresAt']<=now:raise ToolError('SESSION_EXPIRED')
            self.identity(m['requester'],m['agent'])
            return m,scopes
        except (ValueError,KeyError,TypeError,AttributeError):raise ToolError('APPROVAL_INVALID') from None

DDL='''
CREATE TABLE IF NOT EXISTS conversation_grants(digest TEXT PRIMARY KEY,session_id TEXT,requester TEXT,nonce INTEGER,data BLOB,used INTEGER DEFAULT 0,UNIQUE(requester,nonce));
CREATE TABLE IF NOT EXISTS conversation_bindings(task_id TEXT PRIMARY KEY,session_id TEXT,grant_digest TEXT,data BLOB);
CREATE TABLE IF NOT EXISTS conversation_closed(session_id TEXT PRIMARY KEY,data BLOB);
CREATE TABLE IF NOT EXISTS conversation_calls(id TEXT PRIMARY KEY,request_hash TEXT,state TEXT,data BLOB);
CREATE TABLE IF NOT EXISTS conversation_low_logs(session_id TEXT,sequence INTEGER,call_id TEXT UNIQUE,data TEXT,PRIMARY KEY(session_id,sequence));
CREATE TABLE IF NOT EXISTS conversation_checkpoints(id TEXT PRIMARY KEY,session_id TEXT,data TEXT,raw BLOB,tx_hash TEXT,state TEXT);
CREATE TABLE IF NOT EXISTS conversation_active(session_id TEXT PRIMARY KEY,grant_digest TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS conversation_epochs(digest TEXT PRIMARY KEY,session_id TEXT NOT NULL,start_sequence INTEGER NOT NULL,end_sequence INTEGER);
'''

class ConversationAccess:
    def __init__(self,store,policy):
        self.store,self.policy=store,policy
        with self.connect() as db:db.executescript(DDL)
    @contextlib.contextmanager
    def connect(self):
        with self.store.connect() as db:
            try:yield db;db.commit()
            except BaseException:db.rollback();raise
    def seal(self,id,data):return self.store.seal('conversation/'+id,data)
    def open(self,id,data):return self.store.unseal('conversation/'+id,data)
    def bound(self,task):
        with self.connect() as db:return db.execute('SELECT 1 FROM conversation_bindings WHERE task_id=?',(task,)).fetchone() is not None
    def install(self,envelope):
        m,scopes=self.policy.verify(envelope,live=False);id=digest('ConversationGrant',m,self.policy.domain)
        for scope in scopes:
            a=self.policy.admission(scope['revision'])
            if a['risk_level']!='LOW' or a['generation']!=scope['generation']:raise ToolError('POLICY_REVOKED')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM conversation_closed WHERE session_id=?',(m['sessionId'],)).fetchone():raise ToolError('CONVERSATION_CLOSED')
            old=db.execute('SELECT * FROM conversation_grants WHERE requester=? AND nonce=?',(m['requester'].lower(),m['nonce'])).fetchone()
            if old:
                if old['digest']!=id or self.open(id,old['data'])!=envelope:raise ToolError('REPLAY_BLOCKED')
            else:db.execute('INSERT INTO conversation_grants(digest,session_id,requester,nonce,data) VALUES (?,?,?,?,?)',(id,m['sessionId'],m['requester'].lower(),m['nonce'],self.seal(id,envelope)))
        return {'grant_digest':id}
    def bind(self,value):
        if set(value)!={'message','signature'} or set(value['message'])!={n for n,_ in NEW_TYPES['ConversationBinding']}:raise ToolError('APPROVAL_INVALID')
        m=value['message'];task=m['taskId'];validate('Bytes32',task)
        with self.connect() as db:
            row=db.execute('SELECT * FROM conversation_grants WHERE digest=?',(m['grantDigest'],)).fetchone()
            if not row:raise ToolError('APPROVAL_INVALID')
            envelope=self.open(row['digest'],row['data'])
        grant,_=self.policy.verify(envelope,live=False)
        if m['sessionId']!=grant['sessionId'] or m['expiresAt']>grant['expiresAt'] or recover('ConversationBinding',m,self.policy.domain,value['signature'])!=grant['requester'].lower():raise ToolError('APPROVAL_INVALID')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE');old=db.execute('SELECT * FROM conversation_bindings WHERE task_id=?',(task,)).fetchone()
            if old:
                if self.open(task,old['data'])!=value:raise ToolError('REPLAY_BLOCKED')
            else:db.execute('INSERT INTO conversation_bindings VALUES (?,?,?,?)',(task,m['sessionId'],m['grantDigest'],self.seal(task,value)))
        return {'bound':True}

    def preflight(self,envelope):
        """Authoritative read only check; actual calls still atomically charge quota."""
        m,scopes=self.policy.verify(envelope)
        id=digest('ConversationGrant',m,self.policy.domain)
        for scope in scopes:
            a=self.policy.admission(scope['revision'])
            if a['risk_level']!='LOW' or a['generation']!=scope['generation']:raise ToolError('POLICY_REVOKED')
        with self.connect() as db:
            row=db.execute('SELECT * FROM conversation_grants WHERE digest=?',(id,)).fetchone()
            if not row or self.open(id,row['data'])!=envelope:raise ToolError('SESSION_NOT_INSTALLED')
            if db.execute('SELECT 1 FROM conversation_closed WHERE session_id=?',(m['sessionId'],)).fetchone():raise ToolError('CONVERSATION_CLOSED')
            active=db.execute('SELECT grant_digest FROM conversation_active WHERE session_id=?',(m['sessionId'],)).fetchone()
            if active and active[0]!=id:raise ToolError('SESSION_REPLACED')
            if row['used']>=m['maxCalls']:raise ToolError('SESSION_EXHAUSTED')
        return dict(status='ACTIVE',grant_digest=id,used=row['used'],max_calls=m['maxCalls'],expires_at=m['expiresAt'])

    def activate(self,value):
        """Trusted control plane rotation. Historical bindings and quotas stay intact."""
        envelope=value['envelope'];previous=value['previous_digest']
        m,_=self.policy.verify(envelope,live=False)
        id=self.install(envelope)['grant_digest'];sid=m['sessionId']
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            active=db.execute('SELECT grant_digest FROM conversation_active WHERE session_id=?',(sid,)).fetchone()
            if active and active[0]==id:return dict(grant_digest=id,active=True)
            if active and active[0]!=previous:raise ToolError('STATE_CONFLICT')
            from .conversation_audit import unfinished
            if unfinished(self,db,sid):raise ToolError('EXECUTION_UNKNOWN')
            count=db.execute('SELECT COALESCE(MAX(sequence),0) FROM conversation_low_logs WHERE session_id=?',(sid,)).fetchone()[0]
            if previous:
                old=db.execute('SELECT session_id FROM conversation_grants WHERE digest=?',(previous,)).fetchone()
                if not old or old[0]!=sid:raise ToolError('APPROVAL_INVALID')
                db.execute('INSERT OR IGNORE INTO conversation_epochs VALUES (?,?,1,NULL)',(previous,sid))
                db.execute('UPDATE conversation_epochs SET end_sequence=? WHERE digest=?',(count,previous))
            db.execute('INSERT OR IGNORE INTO conversation_epochs VALUES (?,?,?,NULL)',(id,sid,count+1))
            db.execute('INSERT INTO conversation_active VALUES (?,?) ON CONFLICT(session_id) DO UPDATE SET grant_digest=excluded.grant_digest',(sid,id))
        return dict(grant_digest=id,active=True)
    def close(self,value):
        if set(value)!={'message','signature'} or set(value['message'])!={n for n,_ in NEW_TYPES['ConversationClose']}:raise ToolError('APPROVAL_INVALID')
        m=value['message'];sid=m['sessionId']
        if type(m['closedAt']) is not int or m['closedAt']>time.time():raise ToolError('APPROVAL_INVALID')
        with self.connect() as db:row=db.execute('SELECT * FROM conversation_grants WHERE digest=?',(m['grantDigest'],)).fetchone()
        if not row or row['session_id']!=sid or recover('ConversationClose',m,self.policy.domain,value['signature'])!=row['requester']:raise ToolError('APPROVAL_INVALID')
        with self.connect() as db:db.execute('INSERT OR IGNORE INTO conversation_closed VALUES (?,?)',(sid,self.seal(sid,value)))
        return {'closed':True}
    def execute(self,request,id,dispatch,requester=None,*,strong=False):
        validate('Bytes32',id);request_hash=hash_json(request);task=request['task_id']
        with self.connect() as db:
            binding=db.execute('SELECT * FROM conversation_bindings WHERE task_id=?',(task,)).fetchone()
            if not binding:raise ToolError('APPROVAL_INVALID')
            row=db.execute('SELECT * FROM conversation_grants WHERE digest=?',(binding['grant_digest'],)).fetchone()
            envelope=self.open(row['digest'],row['data']);bound=self.open(task,binding['data'])['message']
        m,scopes=self.policy.verify(envelope,live=False)
        if m['agent'].lower()!=request['agent'].lower() or requester and m['requester'].lower()!=requester.lower():raise ToolError('FORBIDDEN')
        scope=next((s for s in scopes if s['name']==request['tool_name']),None)
        if not scope:raise ToolError('UNAUTHORIZED_SCOPE')
        a=self.policy.admission(scope['revision'])
        if a['risk_level']!='LOW' or a['generation']!=scope['generation']:raise ToolError('POLICY_REVOKED')
        from .default_tools import READ_TOOLS
        if request['tool_name'] not in READ_TOOLS and (request.get('revision')!=scope['revision'] or request['arguments'].get('query') not in scope['allowed_keys']):raise ToolError('UNAUTHORIZED_SCOPE')
        if request['tool_name']=='doc.read' and request['arguments'].get('doc_id') not in scope['allowed_keys']:raise ToolError('UNAUTHORIZED_SCOPE')
        if request['tool_name'] in READ_TOOLS and builtin_revision(request['tool_name'])!=scope['revision']:raise ToolError('PARAMS_MISMATCH')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old=db.execute('SELECT * FROM conversation_calls WHERE id=?',(id,)).fetchone()
            if old:
                if old['request_hash']!=request_hash:raise ToolError('IDEMPOTENCY_CONFLICT')
                return self.open(id,old['data'])['result'] if old['state']=='DONE' else {'status':'UNKNOWN','error_code':'EXECUTION_UNKNOWN'}
            if not strong and (m['expiresAt']<=time.time() or bound['expiresAt']<=time.time()):raise ToolError('SESSION_EXPIRED')
            active=db.execute('SELECT grant_digest FROM conversation_active WHERE session_id=?',(m['sessionId'],)).fetchone()
            if not strong and active and active[0]!=row['digest']:raise ToolError('SESSION_REPLACED')
            if db.execute('SELECT 1 FROM conversation_closed WHERE session_id=?',(m['sessionId'],)).fetchone():raise ToolError('CONVERSATION_CLOSED')
            if not strong:
                if db.execute('SELECT used FROM conversation_grants WHERE digest=?',(row['digest'],)).fetchone()[0]>=m['maxCalls']:raise ToolError('SESSION_EXHAUSTED')
                db.execute('UPDATE conversation_grants SET used=used+1 WHERE digest=?',(row['digest'],))
            salt=secrets.token_hex(32)
            db.execute('INSERT INTO conversation_calls VALUES (?,?,?,?)',(id,request_hash,'STARTED',self.seal(id,dict(session_id=m['sessionId'],request=request,params_salt=salt))))
        try:
            result=dispatch()
            final=self.policy.admission(scope['revision'])
            if final['risk_level']!='LOW' or final['generation']!=scope['generation']:raise ToolError('POLICY_REVOKED')
            if not isinstance(result,dict):raise ToolError('EXECUTION_UNKNOWN')
            if request['tool_name'] in READ_TOOLS and result.get('trust')=='untrusted':
                data=result.get('data',{})
                if any(v['doc_id'] not in scope['allowed_keys'] for v in data.get('documents',[])) or any(v['recipient'] not in scope['allowed_keys'] for v in data.get('messages',[])):raise ToolError('UNAUTHORIZED_SCOPE')
        except Exception:
            self.log(m,id,request,scope,salt,{'status':'UNKNOWN'})
            raise
        self.log(m,id,request,scope,salt,result)
        with self.connect() as db:db.execute("UPDATE conversation_calls SET state='DONE' WHERE id=?",(id,))
        return result
    def log(self,m,id,request,scope,salt,result):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM conversation_low_logs WHERE call_id=?',(id,)).fetchone():return
            seq=db.execute('SELECT COALESCE(MAX(sequence),0)+1 FROM conversation_low_logs WHERE session_id=?',(m['sessionId'],)).fetchone()[0]
            log=dict(schema=3,grant_digest=digest('ConversationGrant',m,self.policy.domain),session_id=m['sessionId'],sequence=seq,call_id=id,task_id=request['task_id'],agent_id=m['agent'],tool_id=scope['revision'],tool_name=scope['name'],risk_level='LOW',params_hash=hash_json(dict(salt=salt,arguments=request['arguments'])),timestamp=int(time.time()),outcome='OK' if result.get('trust')=='untrusted' else result.get('status','UNKNOWN'),result_hash=hash_json(dict(salt=salt,result=result)))
            db.execute('INSERT INTO conversation_low_logs VALUES (?,?,?,?)',(m['sessionId'],seq,id,canonical(log).decode()))
            row=db.execute('SELECT data FROM conversation_calls WHERE id=?',(id,)).fetchone();private=self.open(id,row['data']);private.update(result=result,result_salt=salt)
            db.execute('UPDATE conversation_calls SET data=? WHERE id=?',(self.seal(id,private),id))
    def status(self,sid):
        with self.connect() as db:
            grants=[dict(digest=r['digest'],used=r['used'],message=self.open(r['digest'],r['data'])['message']) for r in db.execute('SELECT * FROM conversation_grants WHERE session_id=?',(sid,))]
            logs=[json.loads(r[0]) for r in db.execute('SELECT data FROM conversation_low_logs WHERE session_id=? ORDER BY sequence',(sid,))]
            closed=db.execute('SELECT 1 FROM conversation_closed WHERE session_id=?',(sid,)).fetchone() is not None
            from .conversation_audit import unfinished
            pending=unfinished(self,db,sid)
            epochs=[dict(r) for r in db.execute('SELECT * FROM conversation_epochs WHERE session_id=? ORDER BY rowid',(sid,))]
        return dict(session_id=sid,grants=grants,logs=logs,closed=closed,pending_calls=pending,authorization_epochs=epochs)

def configured(store,urls):
    path=store.root/'tool-sessions.json'
    if not path.exists():return None
    c=json.loads(path.read_text())
    return ConversationAccess(store,ConversationPolicy(c,urls)) if c.get('conversation') else None
