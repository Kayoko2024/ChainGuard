"""Additive session / exact-call approval gate. Never authorizes frozen R2/R3 tools.

Both gateway and tool use independent persistent databases and live chain reads.
Quota is consumed before dispatch; crashes remain UNKNOWN and never dispatch again.
"""
import json
import contextlib
import secrets
import time
from eth_account import Account
from eth_account.messages import encode_typed_data
from eth_utils import keccak
from .canonical import canonical
from .chain_rpc import Chain, Contract
from .crypto import label
from chainguard_sandbox.protocol import ToolError

TYPES = {
    'ToolReview': [('revision','bytes32'),('riskLevel','uint8'),('enabled','bool'),('nonce','uint64'),('epoch','uint64'),('issuedAt','uint64'),('expiresAt','uint64')],
    'SessionGrant': [('requester','address'),('agent','address'),('taskId','bytes32'),('toolsHash','bytes32'),('nonce','uint64'),('issuedAt','uint64'),('expiresAt','uint64'),('maxCalls','uint32')],
    'ToolUseApproval': [('callId','bytes32'),('requester','address'),('agent','address'),('taskId','bytes32'),('revision','bytes32'),('paramsHash','bytes32'),('generation','uint64'),('expiresAt','uint64')],
}
MESSAGE_TYPES={k:[{'name':n,'type':t} for n,t in v] for k,v in TYPES.items()}

def hash_json(value): return '0x'+keccak(canonical(value)).hex()
def typed(kind,value,domain):
    return encode_typed_data(domain_data=domain,message_types={kind:MESSAGE_TYPES[kind]},message_data=value)
def sign(kind,value,domain,key): return '0x'+Account.sign_message(typed(kind,value,domain),key).signature.hex()
def recover(kind,value,domain,signature):
    try:
        raw=bytes.fromhex(signature.removeprefix('0x'))
        if len(raw)!=65 or raw[-1] not in (27,28) or not 0<int.from_bytes(raw[32:64],'big')<=0x7fffffffffffffffffffffffffffffff5d576e7357a4501ddfe92f46681b20a0:
            raise ValueError()
        return Account.recover_message(typed(kind,value,domain),signature=raw).lower()
    except (ValueError,TypeError,KeyError,AttributeError): raise ToolError('APPROVAL_INVALID') from None

def fn(name,inputs,outputs=(),mutability='view'):
    return {'type':'function','name':name,'stateMutability':mutability,'inputs':[{'name':str(i),'type':t} for i,t in enumerate(inputs)],'outputs':[{'name':str(i),'type':t} for i,t in enumerate(outputs)]}

ADMISSION_ABI=[fn('policyRegistry',[],['address']),fn('reviewerOrganization',[],['bytes32']),fn('epoch',[],['uint64']),
    fn('tools',['bytes32'],['uint8','bool','uint64','address']),
    fn('review',[t for _,t in TYPES['ToolReview']]+['bytes'],mutability='nonpayable')]
ANCHOR_ABI=[fn('publisher',[],['address']),fn('batches',['bytes32'],['bytes32','uint32','uint64','uint64']),
    fn('anchor',['bytes32','bytes32','uint32','uint64','uint64'],mutability='nonpayable')]

class ToolPolicy:
    def __init__(self,config,urls):
        self.config=config;self.chain=Chain(config['deployment'],urls)
        self.domain=dict(name='ChainGuard ToolAdmissionRegistry',version='1',chainId=config['deployment']['chainId'],verifyingContract=config['registry']['address'])

    def snapshot(self):
        snapshot=self.chain.healthy();block=hex(int(snapshot['number']))
        for node in self.chain.nodes:
            for key in ['registry','anchor']:
                item=self.config[key];code=node.call('eth_getCode',[item['address'],block])
                if code=='0x' or '0x'+keccak(bytes.fromhex(code[2:])).hex()!=item['codeHash']:raise ToolError('CHAIN_UNAVAILABLE')
            registry=Contract('ToolAdmissionRegistry',self.config['registry']['address'],node,ADMISSION_ABI)
            if registry.call('policyRegistry',block=block)!=self.chain.policy.address:raise ToolError('POLICY_REVOKED')
        return snapshot

    def admission(self,revision):
        snapshot=self.snapshot();block=hex(int(snapshot['number']))
        if any(Contract('PolicyRegistry',self.chain.policy.address,n).call('paused',block=block) for n in self.chain.nodes):raise ToolError('POLICY_REVOKED')
        answers=[tuple(Contract('ToolAdmissionRegistry',self.config['registry']['address'],n,ADMISSION_ABI).call('tools',[revision],block)) for n in self.chain.nodes]
        if len(set(answers))!=1:raise ToolError('CHAIN_UNAVAILABLE')
        risk,active,generation,reviewer=answers[0]
        if not active or risk not in (1,2):raise ToolError('POLICY_REVOKED')
        return dict(risk_level='LOW' if risk==1 else 'HIGH',generation=generation,reviewer=reviewer,snapshot=snapshot)

    def role(self,address,role,snapshot):
        block=hex(int(snapshot['number']))
        values=[(Contract('PolicyRegistry',self.chain.policy.address,n).call('hasRole',[label('role',role),address],block),
            Contract('PolicyRegistry',self.chain.policy.address,n).call('isSignerRevoked',[address],block),
            Contract('PolicyRegistry',self.chain.policy.address,n).call('orgOf',[address],block)) for n in self.chain.nodes]
        if len(set(values))!=1:raise ToolError('CHAIN_UNAVAILABLE')
        allowed,revoked,org=values[0]
        if not allowed or revoked or org=='0x'+'00'*32:raise ToolError('APPROVAL_INVALID')
        return org

    def identity(self,requester,agent):
        snapshot=self.snapshot();self.role(requester,'REQUESTER',snapshot)
        block=hex(int(snapshot['number']))
        if any(Contract('PolicyRegistry',self.chain.policy.address,n).call('paused',block=block) for n in self.chain.nodes):raise ToolError('POLICY_REVOKED')
        if not all(Contract('PolicyRegistry',self.chain.policy.address,n).call('isAgentAuthorized',[requester,agent],block) for n in self.chain.nodes):raise ToolError('FORBIDDEN')
        return snapshot

    def verify_session(self,envelope,*,live=True):
        try:
            message=envelope['message'];scopes=envelope['scopes']
            if set(envelope)!={'message','scopes','signature'} or set(message)!={n for n,_ in TYPES['SessionGrant']}:raise ValueError()
            if type(scopes) is not list or not 1<=len(scopes)<=8 or len({g['revision'] for g in scopes})!=len(scopes):raise ValueError()
            for scope in scopes:
                if set(scope)!={'name','revision','allowed_keys','generation'} or not scope['name'].startswith('custom.') or not scope['allowed_keys']:raise ValueError()
            if hash_json(scopes)!=message['toolsHash']:raise ValueError()
            if recover('SessionGrant',message,self.domain,envelope['signature'])!=message['requester'].lower():raise ValueError()
            now=int(time.time());issued=int(message['issuedAt']);expires=int(message['expiresAt']);maximum=message['maxCalls']
            if type(maximum) is not int or not 1<=maximum<=10000 or issued>now or not 0<expires-issued<=86400 or live and expires<=now:raise ToolError('SESSION_EXPIRED')
            if type(message['nonce']) is not int or not 0<=message['nonce']<=2**53-1:raise ValueError()
            self.identity(message['requester'],message['agent'])
            return message,scopes
        except (ValueError,KeyError,TypeError,AttributeError):raise ToolError('APPROVAL_INVALID') from None


DDL='''
CREATE TABLE IF NOT EXISTS session_grants(task_id TEXT PRIMARY KEY,requester TEXT,nonce INTEGER,digest TEXT,data BLOB,used INTEGER DEFAULT 0,UNIQUE(requester,nonce));
CREATE TABLE IF NOT EXISTS session_calls(id TEXT PRIMARY KEY,request_hash TEXT,task_id TEXT,state TEXT,data BLOB);
CREATE TABLE IF NOT EXISTS session_logs(sequence INTEGER PRIMARY KEY AUTOINCREMENT,call_id TEXT UNIQUE,data TEXT,batch_id TEXT);
CREATE TABLE IF NOT EXISTS session_batches(id TEXT PRIMARY KEY,data TEXT,raw BLOB,tx_hash TEXT,state TEXT);
'''

class SessionAccess:
    def __init__(self,store,policy):
        self.store,self.policy=store,policy
        with self.connect() as db:db.executescript(DDL)
    @contextlib.contextmanager
    def connect(self):
        # ChainStore/Store.connect use autocommit and DO NOT commit explicit BEGIN.
        # Own the transaction here; do not depend on OperationsStore's test adapter.
        with self.store.connect() as db:
            try:
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise
    def seal(self,id,data):return self.store.seal('session/'+id,data)
    def open(self,id,data):return self.store.unseal('session/'+id,data)
    def install(self,envelope):
        m,scopes=self.policy.verify_session(envelope)
        for g in scopes:
            admitted=self.policy.admission(g['revision'])
            if admitted['risk_level']!='LOW' or admitted['generation']!=g['generation']:raise ToolError('POLICY_REVOKED')
        task=m['taskId'];digest=hash_json(envelope)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old=db.execute('SELECT * FROM session_grants WHERE task_id=? OR (requester=? AND nonce=?)',(task,m['requester'].lower(),m['nonce'])).fetchone()
            if old:
                if old['task_id']!=task or old['digest']!=digest:raise ToolError('REPLAY_BLOCKED')
            else:db.execute('INSERT INTO session_grants(task_id,requester,nonce,digest,data) VALUES (?,?,?,?,?)',(task,m['requester'].lower(),m['nonce'],digest,self.seal(task,envelope)))
        return {'installed':True,'task_id':task}
    def envelope(self,task):
        with self.connect() as db:row=db.execute('SELECT data FROM session_grants WHERE task_id=?',(task,)).fetchone()
        return self.open(task,row[0]) if row else None
    def call(self,id):
        with self.connect() as db:row=db.execute('SELECT * FROM session_calls WHERE id=?',(id,)).fetchone()
        if not row:raise ToolError('NOT_FOUND')
        return dict(self.open(id,row['data']),state=row['state'],call_id=id)
    def approve(self,id,signature):
        value=self.call(id)
        if value['state']!='AWAITING_TOOL_APPROVAL':raise ToolError('STATE_CONFLICT')
        approval=value['approval'];signer=recover('ToolUseApproval',approval,self.policy.domain,signature)
        snapshot=self.policy.snapshot()
        roles=[]
        for role in ['BUSINESS_APPROVER','SECURITY_APPROVER']:
            try:org=self.policy.role(signer,role,snapshot);roles.append((role,org))
            except ToolError as error:
                if error.code=='CHAIN_UNAVAILABLE':raise
        if not roles or signer in {approval['requester'].lower(),approval['agent'].lower()} or approval['expiresAt']<=time.time():raise ToolError('APPROVAL_INVALID')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT * FROM session_calls WHERE id=?',(id,)).fetchone();value=self.open(id,row['data'])
            if row['state']!='AWAITING_TOOL_APPROVAL':raise ToolError('STATE_CONFLICT')
            value['signatures'][signer]=signature
            db.execute('UPDATE session_calls SET data=? WHERE id=?',(self.seal(id,value),id))
        return {'call_id':id,'approvals':len(value['signatures'])}
    def complete_approvals(self,value):
        a=value['approval'];snapshot=self.policy.identity(a['requester'],a['agent'])
        if a['expiresAt']<=time.time():raise ToolError('APPROVAL_EXPIRED')
        choices=[]
        for signer,sig in value['signatures'].items():
            if signer in {a['requester'].lower(),a['agent'].lower()}:raise ToolError('APPROVAL_INVALID')
            if recover('ToolUseApproval',a,self.policy.domain,sig)!=signer:raise ToolError('APPROVAL_INVALID')
            for role in ['BUSINESS_APPROVER','SECURITY_APPROVER']:
                try:choices.append((signer,role,self.policy.role(signer,role,snapshot)))
                except ToolError as error:
                    if error.code=='CHAIN_UNAVAILABLE':raise
        return any(x[1]=='BUSINESS_APPROVER' and y[1]=='SECURITY_APPROVER' and x[0]!=y[0] and x[2]!=y[2] for x in choices for y in choices)

    def execute(self,request,id,dispatch,*,requester=None,authorization=None):
        from .canonical import validate
        validate('Bytes32',id);request_hash=hash_json(request)
        # Live admission applies even to cached results; chain outage never enables dispatch.
        admitted=self.policy.admission(request['revision'])
        envelope=self.envelope(request['task_id']);m=envelope['message'] if envelope else None
        if m and (m['agent'].lower()!=request['agent'].lower() or requester and m['requester'].lower()!=requester.lower()):raise ToolError('FORBIDDEN')
        if authorization:
            # Tool accepts signed exact-call approvals only; no gateway boolean can authorize it.
            if set(authorization)!={'approval','signatures','params_salt'}:raise ToolError('APPROVAL_INVALID')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE');old=db.execute('SELECT * FROM session_calls WHERE id=?',(id,)).fetchone()
            if old:
                if old['request_hash']!=request_hash:raise ToolError('IDEMPOTENCY_CONFLICT')
                value=self.open(id,old['data'])
                if old['state']=='DONE':return value['result']
                if old['state']=='STARTED':return {'status':'UNKNOWN','error_code':'EXECUTION_UNKNOWN','call_id':id}
            else:
                salt=secrets.token_hex(32)
                a=dict(callId=id,requester=requester or (m['requester'] if m else authorization['approval']['requester'] if authorization else '0x'+'00'*20),agent=request['agent'],taskId=request['task_id'],revision=request['revision'],paramsHash=hash_json({'salt':salt,'arguments':request['arguments']}),generation=admitted['generation'],expiresAt=int(time.time())+86400)
                if authorization:a=authorization['approval'];salt=None
                value=dict(request=request,approval=a,params_salt=salt,signatures={},result=None)
                db.execute('INSERT INTO session_calls VALUES (?,?,?,?,?)',(id,request_hash,request['task_id'],'AWAITING_TOOL_APPROVAL',self.seal(id,value)))
        reason='HIGH_RISK' if admitted['risk_level']=='HIGH' else 'SESSION_MISSING'
        allowed=False
        if admitted['risk_level']=='LOW' and envelope:
            try:
                _,scopes=self.policy.verify_session(envelope)
                if not any(g['revision']==request['revision'] and g['name']==request['tool_name'] and g['generation']==admitted['generation'] and request['arguments'].get('query') in g['allowed_keys'] for g in scopes):raise ToolError('UNAUTHORIZED_SCOPE')
                allowed=True
            except ToolError as error:
                if error.code not in {'SESSION_EXPIRED'}:raise
                reason=error.code
        if authorization:
            a=authorization['approval']
            if any(a[k]!=v for k,v in dict(callId=id,agent=request['agent'],taskId=request['task_id'],revision=request['revision'],generation=admitted['generation']).items()):raise ToolError('APPROVAL_INVALID')
            if hash_json({'salt':authorization['params_salt'],'arguments':request['arguments']})!=a['paramsHash']:raise ToolError('PARAMS_MISMATCH')
            # The salt is passed over mTLS only for the exact signed parameter commitment.
            value['approval']=a;value['signatures']=authorization['signatures'];value['params_salt']=authorization['params_salt']
        if value['approval']['generation']!=admitted['generation']:raise ToolError('POLICY_REVOKED')
        strong=self.complete_approvals(value) if value['signatures'] else False
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT state FROM session_calls WHERE id=?',(id,)).fetchone()
            if row['state']=='DONE':return self.call(id)['result']
            if row['state']=='STARTED':return {'status':'UNKNOWN','error_code':'EXECUTION_UNKNOWN','call_id':id}
            if allowed and not strong:
                grant=db.execute('SELECT used FROM session_grants WHERE task_id=?',(request['task_id'],)).fetchone()
                if grant['used']>=m['maxCalls']:allowed=False;reason='SESSION_EXHAUSTED'
                else:db.execute('UPDATE session_grants SET used=used+1 WHERE task_id=?',(request['task_id'],))
            if not allowed and not strong:
                return {'status':'AWAITING_TOOL_APPROVAL','error_code':reason,'call_id':id,'approval':value['approval'],'approvals':len(value['signatures'])}
            db.execute("UPDATE session_calls SET state='STARTED',data=? WHERE id=?",(self.seal(id,value),id))
        # Only the winner dispatches. A crash / lost response leaves STARTED => UNKNOWN permanently.
        auth={k:value[k] for k in ['approval','signatures','params_salt']} if strong else None
        try:result=dispatch(auth)
        except Exception:
            self.log(id,request,value,'UNKNOWN',{'status':'UNKNOWN'})
            raise
        if result.get('status')=='AWAITING_TOOL_APPROVAL':
            # The independent tool may expire/exhaust/reclassify after gateway validation.
            with self.connect() as db:db.execute("UPDATE session_calls SET state='AWAITING_TOOL_APPROVAL',data=? WHERE id=?",(self.seal(id,value),id))
            return dict(result,approval=value['approval'],approvals=len(value['signatures']))
        # Revocation during external I/O prevents release. No automatic retry.
        try:
            final=self.policy.admission(request['revision'])
            if final['generation']!=admitted['generation']:raise ToolError('POLICY_REVOKED')
        except ToolError:
            self.log(id,request,value,'UNKNOWN',{'status':'UNKNOWN','reason':'POST_DISPATCH_POLICY_CHECK_FAILED'})
            raise
        self.log(id,request,value,'OK' if result.get('trust')=='untrusted' else result.get('status','UNKNOWN'),result)
        value['result']=result
        with self.connect() as db:db.execute("UPDATE session_calls SET state='DONE',data=? WHERE id=?",(self.seal(id,value),id))
        return result

    def log(self,id,request,value,outcome,result):
        salt=secrets.token_hex(32);value['result_salt']=salt;value['audit_result']=result
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM session_logs WHERE call_id=?',(id,)).fetchone():return
            sequence=db.execute('SELECT COALESCE(MAX(sequence),0)+1 FROM session_logs').fetchone()[0]
            log=dict(schema=1,sequence=sequence,call_id=id,task_id=request['task_id'],agent_id=request['agent'],tool_id=request['revision'],
                params_hash=value['approval']['paramsHash'],timestamp=int(time.time()),outcome=outcome,result_hash=hash_json({'salt':salt,'result':result}))
            db.execute('INSERT INTO session_logs(sequence,call_id,data) VALUES (?,?,?)',(sequence,id,canonical(log).decode()))
            db.execute('UPDATE session_calls SET data=? WHERE id=?',(self.seal(id,value),id))

def configured_access(store,urls):
    from pathlib import Path
    path=store.root/'tool-sessions.json'
    if not path.exists():return None
    return SessionAccess(store,ToolPolicy(json.loads(path.read_text()),urls))
