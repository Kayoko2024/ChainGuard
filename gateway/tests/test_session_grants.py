"""Unit fixtures; real four-node acceptance is separate from these deterministic tests."""
import contextlib
import copy
import json
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
import pytest
from eth_account import Account
from chainguard_gateway.session_grants import SessionAccess,ToolPolicy,hash_json,sign,recover
from chainguard_gateway.batch_audit import merkle,check_proof,observations
from chainguard_gateway.phase10_store import OperationsStore
from chainguard_sandbox.protocol import ToolError

class Policy:
    domain=dict(name='ChainGuard ToolAdmissionRegistry',version='1',chainId=20261026,verifyingContract='0x'+'23'*20)
    verify_session=ToolPolicy.verify_session
    risk='LOW';generation=1;online=True
    def snapshot(self):
        if not self.online:raise ToolError('CHAIN_UNAVAILABLE')
        return {}
    def identity(self,*args):return self.snapshot()
    def admission(self,*args):self.snapshot();return dict(risk_level=self.risk,generation=self.generation)
    def role(self,address,role,snapshot):
        if address==BIZ.address.lower() and role=='BUSINESS_APPROVER':return 'A'
        if address==SEC.address.lower() and role=='SECURITY_APPROVER':return 'B'
        raise ToolError('APPROVAL_INVALID')

USER=Account.from_key('0x'+'11'*32);BIZ=Account.from_key('0x'+'12'*32);SEC=Account.from_key('0x'+'13'*32)
AGENT='0x'+'14'*20;TASK='0x'+'15'*32;REV='0x'+'16'*32
def envelope(**kwargs):
    scopes=[dict(name='custom.contacts',revision=REV,allowed_keys=['A','B'],generation=1)]
    message=dict(requester=USER.address.lower(),agent=AGENT,taskId=TASK,toolsHash=hash_json(scopes),nonce=1,issuedAt=int(time.time()),expiresAt=int(time.time())+900,maxCalls=2,**{})
    message.update(kwargs);return dict(message=message,scopes=scopes,signature=sign('SessionGrant',message,Policy.domain,USER.key))
def access(tmp_path):
    store=OperationsStore(tmp_path)
    adapter=SimpleNamespace(connect=store.db,seal=store.seal,unseal=store.open)
    return SessionAccess(adapter,Policy())
def request():return dict(task_id=TASK,agent=AGENT,revision=REV,tool_name='custom.contacts',arguments={'query':'A'})
def key(n):return '0x'+('%064x'%n)
def result():return dict(trust='untrusted',data={'record':{'name':'A'}})

def test_new_strong_approvals_last_24h_without_extending_saved_call(tmp_path,monkeypatch):
    a=access(tmp_path);a.policy.risk='HIGH'
    now=int(time.time());monkeypatch.setattr(time,'time',lambda:now)
    pending=a.execute(request(),key(700),lambda _:pytest.fail('unsigned dispatch'),requester=USER.address.lower())
    original=a.call(key(700))['approval'];assert original['expiresAt']==now+86400
    # Re-entering after 5 minutes preserves the originally signed deadline.
    monkeypatch.setattr(time,'time',lambda:now+301)
    a.execute(request(),key(700),lambda _:pytest.fail('unsigned dispatch'),requester=USER.address.lower())
    assert a.call(key(700))['approval']==original
    for actor in [BIZ,SEC]:a.approve(key(700),sign('ToolUseApproval',original,a.policy.domain,actor.key))
    assert a.complete_approvals(a.call(key(700)))
    monkeypatch.setattr(time,'time',lambda:now+86400)
    with pytest.raises(ToolError,match='APPROVAL_EXPIRED'):a.complete_approvals(a.call(key(700)))

def test_exact_binding_signature_domain_and_nonce_replay(tmp_path):
    a=access(tmp_path);e=envelope();assert a.install(e)['installed'];a.install(e)
    for change in [dict(maxCalls=50),dict(agent='0x'+'99'*20),dict(toolsHash=key(9))]:
        forged=copy.deepcopy(e);forged['message'].update(change)
        with pytest.raises(ToolError):a.install(forged)
    with pytest.raises(ToolError,match='REPLAY_BLOCKED'):a.install(envelope(taskId=key(99)))
    assert recover('SessionGrant',e['message'],Policy.domain,e['signature'])==USER.address.lower()

def test_new_session_golden_vector_matches_python():
    from pathlib import Path
    from chainguard_gateway.session_runtime import message_digest
    v=json.loads((Path(__file__).resolve().parents[2]/'spec/vectors/session-v1.json').read_text())
    assert hash_json(v['scopes'])==v['message']['toolsHash']
    assert message_digest('SessionGrant',v['message'],v['domain'])==v['digest']
    assert recover('SessionGrant',v['message'],v['domain'],v['signature'])==v['message']['requester']

def test_catalog_exposes_reviewer_label_without_changing_adapter_risk(tmp_path):
    from chainguard_gateway.custom_tools import ToolRegistry
    from chainguard_gateway.phase10_service import Operations
    registry=ToolRegistry(OperationsStore(tmp_path))
    item=registry.create(dict(name='custom.risk_label',label='test',description='query',adapter='dataset.lookup',key_field='id',output_fields=['id'],records=[{'id':'A'}]))
    revision=item['manifest']['revision']
    for risk in ['LOW','HIGH']:
        registry.save_admission(revision,dict(risk_level=risk))
        tool=Operations.custom_descriptor(registry.get(revision))
        assert tool['risk']==0 and tool['risk_level']==risk
        assert tool['requires_approval']==(risk=='HIGH')

def test_signed_log_salts_remain_private_and_recompute_result_and_parameters(tmp_path):
    a=access(tmp_path);a.install(envelope());a.execute(request(),key(1),lambda _:result())
    c=a.call(key(1));log=observations(a)[0]['log']
    assert log['params_hash']==hash_json({'salt':c['params_salt'],'arguments':c['request']['arguments']})
    assert log['result_hash']==hash_json({'salt':c['result_salt'],'result':c['audit_result']})
    assert 'params_salt' not in json.dumps(log) and 'result_salt' not in json.dumps(log)

def test_container_autocommit_connection_requires_explicit_commit_and_survives_new_gate(tmp_path):
    store=OperationsStore(tmp_path)
    @contextlib.contextmanager
    def container_connection():
        db=sqlite3.connect(tmp_path/'container.sqlite3',isolation_level=None);db.row_factory=sqlite3.Row
        try:yield db
        finally:db.close()
    adapter=SimpleNamespace(connect=container_connection,seal=store.seal,unseal=store.open)
    a=SessionAccess(adapter,Policy());a.install(envelope(maxCalls=1));a.execute(request(),key(1),lambda _:result())
    b=SessionAccess(adapter,Policy());assert b.envelope(TASK) is not None
    assert b.call(key(1))['state']=='DONE'
    assert b.execute(request(),key(2),lambda _:pytest.fail('quota lost'))['error_code']=='SESSION_EXHAUSTED'

def test_tool_can_demand_approval_after_gateway_session_check_without_becoming_unknown(tmp_path):
    a=access(tmp_path);a.install(envelope())
    result=a.execute(request(),key(1),lambda _:{'status':'AWAITING_TOOL_APPROVAL','error_code':'SESSION_EXPIRED'})
    assert result['status']=='AWAITING_TOOL_APPROVAL' and a.call(key(1))['state']=='AWAITING_TOOL_APPROVAL'

def test_business_api_risk_is_reviewer_only_and_required_on_new_deployment(tmp_path):
    from fastapi.testclient import TestClient
    from chainguard_gateway.phase10_api import create_operations_app
    from chainguard_gateway.custom_tools import ToolRegistry
    s=OperationsStore(tmp_path);registry=ToolRegistry(s);calls=[]
    value=dict(name='custom.api_test',label='test',description='query',adapter='dataset.lookup',key_field='id',output_fields=['id'],records=[{'id':'A'}])
    class Ops:
        config={'tool_sessions':True};store=s;stop=SimpleNamespace(set=lambda:None)
        def register_custom(self,v):
            item=registry.create(v);return {'revision':item['manifest']['revision']}
        def set_custom_active(self,*args):calls.append(args);return {'reviewed':True}
    client=TestClient(create_operations_app(Ops(),{},'http://127.0.0.1:8090',start_worker=False));origin='http://127.0.0.1:8090'
    def headers(role):
        token,csrf=s.login(role);client.cookies.set('cg_session',token);return {'Origin':origin,'X-CSRF-Token':csrf}
    h=headers('requester');r=client.post('/ops/v1/custom-tools',json=value,headers=h);assert r.status_code==201
    assert client.post('/ops/v1/custom-tools',json=dict(value,risk_level='LOW'),headers=h).status_code==422
    rev=r.json()['revision'];url=f'/ops/v1/custom-tools/{rev}/activation'
    assert client.post(url,json=dict(revision=rev,enabled=True,risk_level='LOW'),headers=h).status_code==403
    h=headers('security');assert client.post(url,json=dict(revision=rev,enabled=True),headers=h).json()['error']['code']=='RISK_LABEL_REQUIRED'
    assert client.post(url,json=dict(revision=rev,enabled=True,risk_level='LOW'),headers=h).status_code==200
    assert calls==[(rev,rev,True,'LOW')]

def test_quota_idempotency_persistence_and_concurrent_limit(tmp_path):
    a=access(tmp_path);a.install(envelope());calls=[]
    def run(n):return a.execute(request(),key(n),lambda _:calls.append(n) or result())
    with ThreadPoolExecutor(max_workers=5) as pool:values=list(pool.map(run,range(1,7)))
    assert len(calls)==2 and sum(v.get('status')=='AWAITING_TOOL_APPROVAL' for v in values)==4
    id=key(calls[0]);assert a.execute(request(),id,lambda _:pytest.fail('replayed'))==result()
    b=access(tmp_path);assert b.execute(request(),key(20),lambda _:pytest.fail('quota reset'))['error_code']=='SESSION_EXHAUSTED'
    changed=request();changed['arguments']={'query':'B'}
    with pytest.raises(ToolError,match='IDEMPOTENCY_CONFLICT'):a.execute(changed,id,lambda _:None)

def test_expiry_and_high_risk_fall_back_to_exact_cross_org_approval(tmp_path,monkeypatch):
    a=access(tmp_path);a.install(envelope(expiresAt=int(time.time())+5));monkeypatch.setattr('chainguard_gateway.session_grants.time.time',lambda:9999999999)
    assert a.execute(request(),key(1),lambda _:pytest.fail('expired'))['error_code']=='SESSION_EXPIRED'
    monkeypatch.undo();a.policy.risk='HIGH';pending=a.execute(request(),key(2),lambda _:pytest.fail('HIGH bypass'))
    assert pending['status']=='AWAITING_TOOL_APPROVAL';approval=pending['approval']
    for signer in [BIZ,SEC]:a.approve(key(2),sign('ToolUseApproval',approval,Policy.domain,signer.key))
    got=a.execute(request(),key(2),lambda auth:result(),requester=USER.address.lower());assert got==result()
    assert len(observations(a))==1

def test_tool_independently_rejects_changed_parameters_and_duplicate_org(tmp_path):
    gateway=access(tmp_path/'gateway');tool=access(tmp_path/'tool');gateway.policy.risk=tool.policy.risk='HIGH'
    p=gateway.execute(request(),key(1),lambda _:pytest.fail('no approval'),requester=USER.address.lower())
    for s in [BIZ,SEC]:gateway.approve(key(1),sign('ToolUseApproval',p['approval'],Policy.domain,s.key))
    stored=gateway.call(key(1));auth={k:stored[k] for k in ['approval','signatures','params_salt']}
    changed=request();changed['arguments']={'query':'B'}
    with pytest.raises(ToolError,match='PARAMS_MISMATCH'):tool.execute(changed,key(1),lambda _:pytest.fail('changed'),authorization=auth)
    assert tool.execute(request(),key(2),lambda _:None,requester=USER.address.lower())['status']=='AWAITING_TOOL_APPROVAL'
    # Independent tool receives the two signatures, rather than a trusted gateway allow flag.
    other=access(tmp_path/'tool2');other.policy.risk='HIGH'
    assert other.execute(request(),key(1),lambda _:result(),authorization=auth)==result()

def test_lost_response_chain_outage_revocation_and_scope_never_dispatch_twice(tmp_path):
    a=access(tmp_path);a.install(envelope());calls=[]
    def lost(_):calls.append(1);raise ToolError('EXECUTION_UNKNOWN')
    with pytest.raises(ToolError):a.execute(request(),key(1),lost)
    assert a.execute(request(),key(1),lambda _:pytest.fail('unknown replay'))['status']=='UNKNOWN'
    assert len(calls)==1 and observations(a)[0]['log']['outcome']=='UNKNOWN'
    a.policy.online=False
    with pytest.raises(ToolError,match='CHAIN_UNAVAILABLE'):a.execute(request(),key(2),lost)
    a.policy.online=True;a.policy.generation=2
    with pytest.raises(ToolError,match='UNAUTHORIZED_SCOPE'):a.execute(request(),key(3),lost)

@pytest.mark.parametrize('size',[1,2,3,49,50])
def test_ordered_merkle_proof_every_leaf_and_tampering(size):
    logs=[dict(sequence=i,params_hash=key(i)) for i in range(1,size+1)]
    root,proofs=merkle(logs)
    for log,proof in zip(logs,proofs):
        assert check_proof(log,proof,root)
        assert not check_proof(dict(log,params_hash=key(999)),proof,root)
    if size>1:assert merkle(list(reversed(logs)))[0]!=root
