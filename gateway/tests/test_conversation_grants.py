"""Conversation V2 gate fixtures; live acceptance is recorded separately."""
import copy
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
import pytest
from eth_account import Account
from chainguard_gateway.phase10_store import OperationsStore
from chainguard_gateway.conversation_grants import ConversationAccess,ConversationPolicy,digest,builtin_revision
from chainguard_gateway.session_grants import hash_json,sign
from chainguard_gateway.batch_audit import merkle
from chainguard_gateway.conversation_audit import check
from chainguard_sandbox.protocol import ToolError

USER=Account.from_key('0x'+'11'*32);AGENT='0x'+'14'*20
def key(n):return '0x'+format(n,'064x')
class Policy:
    domain=dict(name='ChainGuard ConversationSessionRegistry',version='1',chainId=31337,verifyingContract='0x'+'24'*20)
    verify=ConversationPolicy.verify
    risk='LOW';generation=1;online=True
    def identity(self,*args):
        if not self.online:raise ToolError('CHAIN_UNAVAILABLE')
    def admission(self,*args):self.identity();return dict(risk_level=self.risk,generation=self.generation)

def envelope(**changes):
    scopes=[dict(name='custom.contacts',revision=key(6),allowed_keys=['A'],generation=1)]
    now=int(time.time());m=dict(requester=USER.address.lower(),agent=AGENT,sessionId=key(1),toolsHash=hash_json(scopes),nonce=1,issuedAt=now,expiresAt=now+600,maxCalls=2);m.update(changes)
    return dict(message=m,scopes=scopes,signature=sign('ConversationGrant',m,Policy.domain,USER.key))

def access(path):
    s=OperationsStore(path);return ConversationAccess(SimpleNamespace(connect=s.db,seal=s.seal,unseal=s.open),Policy())
def bind(a,e,task=key(2)):
    m=dict(sessionId=e['message']['sessionId'],taskId=task,grantDigest=digest('ConversationGrant',e['message'],a.policy.domain),expiresAt=e['message']['expiresAt'])
    return a.bind(dict(message=m,signature=sign('ConversationBinding',m,a.policy.domain,USER.key)))
def request(task=key(2)):return dict(task_id=task,agent=AGENT,tool_name='custom.contacts',revision=key(6),arguments={'query':'A'})
def result():return dict(trust='untrusted',data={'id':'A'})

def test_signature_session_nonce_domain_and_scope_cannot_be_rewritten(tmp_path):
    a=access(tmp_path);e=envelope();a.install(e);bind(a,e)
    for field,val in [('sessionId',key(99)),('maxCalls',200),('agent','0x'+'99'*20)]:
        forged=copy.deepcopy(e);forged['message'][field]=val
        with pytest.raises(ToolError,match='APPROVAL_INVALID'):a.install(forged)
    with pytest.raises(ToolError,match='REPLAY_BLOCKED'):a.install(envelope(sessionId=key(9)))
    wrong=copy.deepcopy(e);wrong['signature']=sign('ConversationGrant',e['message'],dict(Policy.domain,name='ChainGuard ToolAdmissionRegistry'),USER.key)
    with pytest.raises(ToolError):a.install(wrong)
    with pytest.raises(ToolError,match='UNAUTHORIZED_SCOPE'):a.execute(dict(request(),arguments={'query':'B'}),key(20),result)
    with pytest.raises(ToolError,match='APPROVAL_INVALID'):a.execute(request(key(7)),key(20),result)

def test_quota_spans_turns_is_atomic_persistent_and_duplicate_does_not_dispatch(tmp_path):
    a=access(tmp_path);e=envelope(maxCalls=1);a.install(e);bind(a,e);bind(a,e,key(3));calls=[]
    def execute(i):
        try:return a.execute(request(key(2+i%2)),key(20+i),lambda:(calls.append(i) or result()))
        except ToolError as error:return error.code
    with ThreadPoolExecutor(max_workers=2) as pool:out=list(pool.map(execute,[0,1]))
    assert len(calls)==1 and 'SESSION_EXHAUSTED' in out
    b=access(tmp_path);winner=calls[0];assert b.execute(request(key(2+winner%2)),key(20+winner),lambda:pytest.fail('duplicate'))==result()
    assert b.status(key(1))['grants'][0]['used']==1

def test_expiration_reclassification_outage_and_close_fail_before_dispatch(tmp_path):
    a=access(tmp_path);e=envelope(issuedAt=int(time.time())-20,expiresAt=int(time.time())-1);a.install(e);bind(a,e)
    with pytest.raises(ToolError,match='SESSION_EXPIRED'):a.execute(request(),key(20),lambda:pytest.fail('expired'))
    e=envelope(nonce=2);a.install(e);bind(a,e,key(3));a.policy.risk='HIGH'
    with pytest.raises(ToolError,match='POLICY_REVOKED'):a.execute(request(key(3)),key(20),result)
    a.policy.risk='LOW';a.policy.online=False
    with pytest.raises(ToolError,match='CHAIN_UNAVAILABLE'):a.execute(request(key(3)),key(20),result)
    a.policy.online=True;m=dict(sessionId=key(1),grantDigest=digest('ConversationGrant',e['message'],a.policy.domain),closedAt=int(time.time()))
    a.close(dict(message=m,signature=sign('ConversationClose',m,a.policy.domain,USER.key)))
    with pytest.raises(ToolError,match='CONVERSATION_CLOSED'):a.execute(request(key(3)),key(20),lambda:pytest.fail('closed'))

def test_lost_response_remains_unknown_after_restart_and_is_logged(tmp_path):
    a=access(tmp_path);e=envelope();a.install(e);bind(a,e);calls=[]
    def lost():calls.append(1);raise ToolError('EXECUTION_UNKNOWN')
    with pytest.raises(ToolError):a.execute(request(),key(20),lost)
    assert access(tmp_path).execute(request(),key(20),lambda:pytest.fail('must not retry'))['status']=='UNKNOWN'
    assert calls==[1] and a.status(key(1))['logs'][0]['outcome']=='UNKNOWN'

def test_per_session_merkle_explicit_position_rejects_tampering_and_high():
    logs=[dict(schema=2,risk_level='LOW',tool_name='doc.read',session_id=key(1),sequence=i+1,value=i) for i in range(70)]
    root,proofs=merkle(logs);batch=dict(root=root,count=len(logs),session_id=key(1))
    assert all(check(log,p,batch) for log,p in zip(logs,proofs))
    for changed in [dict(logs[0],session_id=key(3)),dict(logs[0],risk_level='HIGH'),dict(logs[0],tool_name='mail.send'),dict(logs[0],sequence=2),dict(logs[0],value=9)]:assert not check(changed,proofs[0],batch)
    assert not check(logs[0],proofs[0][:-1],batch)

def test_conversation_golden_vector():
    from chainguard_gateway.session_grants import recover
    v=json.loads((Path(__file__).resolve().parents[2]/'spec/vectors/conversation-v2.json').read_text())
    assert hash_json(v['scopes'])==v['message']['toolsHash']
    assert digest('ConversationGrant',v['message'],v['domain'])==v['digest']
    assert recover('ConversationGrant',v['message'],v['domain'],v['signature'])==v['message']['requester']


def test_gateway_and_tool_independent_quota_postcheck_and_lost_response(tmp_path):
    gateway=access(tmp_path/'gateway');tool=access(tmp_path/'tool');e=envelope()
    for gate in [gateway,tool]:gate.install(e);bind(gate,e)
    calls=[]
    def dispatch():return tool.execute(request(),key(20),lambda:(calls.append(1) or result()))
    assert gateway.execute(request(),key(20),dispatch)==result()
    assert gateway.status(key(1))['grants'][0]['used']==tool.status(key(1))['grants'][0]['used']==1
    # The tool independently observes revocation after the gateway's initial check.
    tool.policy.generation=2
    with pytest.raises(ToolError,match='POLICY_REVOKED'):gateway.execute(request(),key(21),dispatch)
    assert calls==[1]
    assert gateway.execute(request(),key(21),lambda:pytest.fail('uncertain dispatch'))['status']=='UNKNOWN'


def test_expired_or_exhausted_routes_to_exact_strong_gate_without_renewal(tmp_path,monkeypatch):
    from chainguard_gateway import conversation_gate
    a=access(tmp_path);e=envelope(issuedAt=int(time.time())-20,expiresAt=int(time.time())-1);a.install(e);bind(a,e)
    calls=[]
    class Strong:
        def execute(self,*args,**kwargs):calls.append(args[0]);return dict(status='AWAITING_TOOL_APPROVAL')
    monkeypatch.setattr(conversation_gate,'configured',lambda *args:a)
    monkeypatch.setattr(conversation_gate,'configured_access',lambda *args:Strong())
    result,handled=conversation_gate.gateway(None,[],request(),key(20),USER.address.lower(),lambda *args:pytest.fail('expired LOW dispatch'))
    assert handled and result['status']=='AWAITING_TOOL_APPROVAL' and result['error_code']=='SESSION_EXPIRED' and len(calls)==1
    assert a.status(key(1))['grants'][0]['used']==0


def test_close_keeps_unfinished_LOW_call_visible_until_outcome_is_recorded(tmp_path):
    from chainguard_gateway.conversation_audit import unfinished
    a=access(tmp_path);e=envelope();a.install(e);bind(a,e)
    with a.connect() as db:db.execute('INSERT INTO conversation_calls VALUES (?,?,?,?)',(key(20),hash_json(request()),'STARTED',a.seal(key(20),dict(session_id=key(1),request=request(),params_salt='private'))))
    with a.connect() as db:assert unfinished(a,db,key(1))==[key(20)] and unfinished(a,db,key(9))==[]
    assert a.status(key(1))['pending_calls']==[key(20)]
    a.log(e['message'],key(20),request(),e['scopes'][0],'private',dict(status='UNKNOWN'))
    assert a.status(key(1))['pending_calls']==[] and a.status(key(1))['logs'][0]['outcome']=='UNKNOWN'


def test_publisher_cannot_seal_final_root_before_inflight_LOW_outcome(tmp_path,monkeypatch):
    """Use real signed outbox bytes and SQLite; RPC below is a unit fixture only."""
    from chainguard_gateway import conversation_audit
    a=access(tmp_path);e=envelope();a.install(e);bind(a,e)
    a.execute(request(),key(20),result)
    with a.connect() as db:
        db.execute('INSERT INTO conversation_calls VALUES (?,?,?,?)',(key(21),hash_json(request()),'STARTED',a.seal(key(21),dict(session_id=key(1),request=request(),params_salt='private'))))
        db.execute('INSERT INTO conversation_closed VALUES (?,?)',(key(1),b'unit-close'))

    class RPC:
        def call(self,method,args):
            if method=='eth_getTransactionCount':return '0x0'
            if method in {'eth_getTransactionReceipt','eth_getTransactionByHash'}:return None
            if method=='eth_sendRawTransaction':
                from eth_utils import keccak
                return '0x'+keccak(bytes.fromhex(args[0][2:])).hex()
            pytest.fail('Unexpected RPC: '+method)
    class Contract:
        address='0x'+'24'*20
        def __init__(self,*args):pass
        def call(self,name):assert name=='publisher';return USER.address.lower()
        def data(self,*args):return '0x1234'
    a.policy.config=dict(deployment={'chainId':31337},conversation={'address':Contract.address})
    a.policy.chain=SimpleNamespace(rpc=RPC());a.policy.snapshot=lambda:None
    monkeypatch.setattr(conversation_audit,'Contract',Contract)
    publisher=conversation_audit.Publisher(a,USER.key)
    # Closing stops new calls, but can only checkpoint the completed prefix.
    assert publisher.flush(force=True,session_id=key(1))['status']=='PENDING'
    with a.connect() as db:
        batch=json.loads(db.execute('SELECT data FROM conversation_checkpoints').fetchone()[0])
        assert batch['count']==1 and batch['closed'] is False
        db.execute("UPDATE conversation_checkpoints SET state='ANCHORED'")
    # No new outcomes: timer/manual flush must not turn that prefix into final.
    assert publisher.flush(force=True,session_id=key(1))['status']=='IDLE'
    a.log(e['message'],key(21),request(),e['scopes'][0],'private',dict(status='UNKNOWN'))
    assert publisher.flush(force=True,session_id=key(1))['status']=='PENDING'
    with a.connect() as db:
        last=json.loads(db.execute('SELECT data FROM conversation_checkpoints ORDER BY rowid DESC LIMIT 1').fetchone()[0])
    assert last['count']==2 and last['closed'] is True and last['previous_root']==batch['root']
