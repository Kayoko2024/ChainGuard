"""Business boundary unit tests. Stubs here never count as chain/Agent acceptance."""
import json
import secrets
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from chainguard_gateway.phase10_store import OperationsStore,PublicStore
from chainguard_gateway.phase10_api import create_operations_app,password_hash
from chainguard_gateway.phase10_audit import create_live_audit_app
from chainguard_gateway.phase10_service import AgentTransport
from chainguard_gateway.phase10_client import ReceiptLoss
from chainguard_sandbox.protocol import ToolError

ORIGIN='http://127.0.0.1:8090'


def test_encrypted_persistence_and_conflicting_idempotency(tmp_path):
    store=OperationsStore(tmp_path/'private'); id='0x'+'01'*32
    private={'task_text':'SECRET TASK BODY','allowed_recipients':['alice@inbox.chainguard.invalid']}
    assert store.create(id,private) and not store.create(id,private)
    with pytest.raises(ToolError,match='IDEMPOTENCY_CONFLICT'): store.create(id,dict(private,task_text='changed'))
    store.update(id,state='AWAITING_APPROVAL',grant={'task_id':'original'})
    store.event(id,{'kind':'MODEL_EXCHANGE','sensitive':'SECRET MODEL BODY','elapsed_ms':12.345})
    assert b'SECRET' not in (tmp_path/'private/operations.sqlite3').read_bytes()
    restored=OperationsStore(tmp_path/'private')
    assert restored.get(id)['grant']['task_id']=='original'
    assert restored.events(id)[0]['kind']=='MODEL_EXCHANGE'
    assert restored.events(id)[0]['elapsed_ms']==12.345
    from chainguard_gateway.canonical import canonical
    with pytest.raises(ToolError,match='SCHEMA_INVALID'): canonical({'protocol_value':12.345})


def test_hashed_sessions_expire_and_roles_not_from_request(tmp_path):
    store=OperationsStore(tmp_path); token,csrf=store.login('biz')
    assert store.session(token)['role']=='biz'
    with store.db() as db:
        row=db.execute('SELECT * FROM sessions').fetchone(); assert row['token_hash']!=token
        db.execute('UPDATE sessions SET expires=?',(time.time()-1,))
    with pytest.raises(ToolError,match='AUTH_REQUIRED'): store.session(token)


@pytest.fixture
def web(tmp_path):
    store=OperationsStore(tmp_path/'private'); creds={}
    for role in ['requester','biz','security']:
        salt=secrets.token_hex(16); creds[role]={'salt':salt,'hash':password_hash(role+'-password',salt),'organization':role}
    calls=[]
    class Ops:
        def __init__(self): self.store=store; self.stop=SimpleNamespace(set=lambda:None)
        def detail(self,id): return {'id':id}
        def create(self,id,body): calls.append(('create',body)); return {'id':id}
        def approve(self,id,role,expected): calls.append(('approve',role,expected)); return {'role':role}
        def execute(self,id,expected): calls.append(('execute',expected)); return {'id':id}
        def review(self,id,role): return {'intent_digest':'original','role':role}
    client=TestClient(create_operations_app(Ops(),creds,ORIGIN,start_worker=False))
    return client,calls


def login(client,role):
    response=client.post('/ops/v1/login',headers={'Origin':ORIGIN},json={'role':role,'password':role+'-password'})
    assert response.status_code==200 and 'HttpOnly' in response.headers['set-cookie'] and 'SameSite=strict' in response.headers['set-cookie']
    return {'Origin':ORIGIN,'X-CSRF-Token':response.json()['csrf']}


def test_business_auth_origin_csrf_and_reviewer_cannot_create_or_execute(web):
    client,calls=web
    assert client.get('/ops/v1/tasks').status_code==401
    assert client.post('/ops/v1/login',json={'role':'biz','password':'biz-password'}).status_code==403
    headers=login(client,'biz')
    assert client.post('/ops/v1/tasks',headers=headers,json={}).status_code==403
    assert client.post('/ops/v1/tasks/id/execute',headers=headers,json={'intent_digest':'original'}).status_code==403
    assert client.post('/ops/v1/tasks/id/approve',headers={'Origin':ORIGIN},json={'intent_digest':'original'}).status_code==403
    assert not calls


def test_requester_cannot_approve_and_organization_cannot_be_spoofed(web):
    client,calls=web; headers=login(client,'requester')
    assert client.post('/ops/v1/tasks/id/approve',headers=headers,json={'intent_digest':'original'}).status_code==403
    headers=login(client,'biz')
    assert client.post('/ops/v1/tasks/id/approve',headers=headers,json={'intent_digest':'original','role':'security'}).status_code==422
    response=client.post('/ops/v1/tasks/id/approve',headers=headers,json={'intent_digest':'original'})
    assert response.status_code==200 and calls==[('approve','biz','original')]


def test_malformed_login_role_is_rejected_before_session_creation(web):
    client,calls=web
    for role in [[],{},None,2,True]:
        response=client.post('/ops/v1/login',headers={'Origin':ORIGIN},json={'role':role,'password':'biz-password'})
        assert response.status_code==422 and response.json()['error']['code']=='SCHEMA_INVALID'
    assert client.get('/ops/v1/session').status_code==401 and not calls


def test_malformed_recipient_elements_cannot_create_or_queue_a_task(tmp_path):
    from chainguard_gateway.phase10_service import Operations
    store=OperationsStore(tmp_path/'private')
    operations=SimpleNamespace(store=store)
    for recipients in [[{}],[[]],[None],[True],[2],['alice@inbox.chainguard.invalid',{}]]:
        with pytest.raises(ToolError,match='POLICY_DENY'):
            Operations.create(operations,'0x'+'98'*32,{'task_text':'synthetic','allowed_recipients':recipients})
    assert store.jobs()==[]


def test_agent_transport_cannot_cross_task_scope():
    class Bridge:
        def call(self,*args): raise AssertionError('must reject before bridge')
    transport=AgentTransport(Bridge(),'task-a')
    with pytest.raises(ToolError,match='FORBIDDEN'):
        transport.request('POST','/v1/agent/actions/propose',{'task_id':'task-b'})


def test_real_receipt_loss_adapter_does_not_invent_or_repeat_result(tmp_path):
    aid='0x'+'02'*32; calls=[]
    class Tool:
        def request(self,*args): calls.append(args); return {'original':True}
    wrapper=ReceiptLoss(Tool(),tmp_path); (tmp_path/'receipt-hold.json').write_text(json.dumps([aid]))
    with pytest.raises(ToolError,match='EXECUTION_UNKNOWN'):
        wrapper.request('POST','/v1/tools/execute',{'intent':{'action_id':aid}},'key')
    assert len(calls)==1
    with pytest.raises(ToolError): wrapper.request('GET','/v1/tools/actions/'+aid)
    assert len(calls)==1
    (tmp_path/'receipt-hold.json').write_text('[]')
    assert wrapper.request('GET','/v1/tools/actions/'+aid)=={'original':True}
    assert len(calls)==2 and calls[-1][0]=='GET'


def test_dynamic_audit_readonly_refresh_without_export_or_execution(tmp_path):
    public=PublicStore(tmp_path/'public.sqlite3')
    class Offline:
        def healthy(self): raise ToolError('CHAIN_UNAVAILABLE')
    client=TestClient(create_live_audit_app(public.path,Offline()))
    assert client.get('/audit-api/v1/actions').json()['total']==0
    public.publish({'entry_id':'interactive-new','group':'C','state':'UNKNOWN','action_id':'original'})
    assert client.get('/audit-api/v1/actions').json()['total']==1
    assert client.get('/audit-api/v1/actions/interactive-new').json()['action_id']=='original'
    for path in ['/ops/v1/tasks','/v1/agent/actions/propose','/audit-api/v1/actions','/audit-api/v1/actions/interactive-new/verify']:
        assert client.post(path,json={}).status_code in {404,405}


def test_signed_receipt_without_anchor_cannot_be_reported_finalized(monkeypatch):
    from chainguard_gateway import phase10_audit as module
    row={'receipt':{'action_id':'a','params_commit':'p'},'action_id':'a','intent':{'params_commit':'p','tool_id':'mail'},'tool_signature':'signature','finalization_evidence':None}
    checked=[]
    def reservation(chain,entry):
        checked.append(entry); return {'status':'PENDING_RECEIPT','snapshot':{'number':'5'},'transactions':[{'kind':'reserve'}]}
    monkeypatch.setattr(module,'verify_action',reservation);monkeypatch.setattr(module,'recover_receipt',lambda *a:'tool')
    chain=SimpleNamespace(receipt_domain={},policy=SimpleNamespace(call=lambda *a:True))
    result=module.verify_live_entry(chain,row)
    assert result['status']=='PENDING_ANCHOR' and result['tool_signature_valid']
    assert checked[0]['receipt'] is None and row['receipt']['action_id']=='a'
    row['receipt']['params_commit']='tampered'
    assert module.verify_live_entry(chain,row)['status']=='INVALID'


def test_missing_reservation_gives_correct_next_step_without_faking_execution(monkeypatch):
    from chainguard_gateway import phase10_audit as module
    original={'status':'NO_RESERVATION','current_chain_state':None,'transactions':[]}
    monkeypatch.setattr(module,'verify_action',lambda *args:dict(original))
    row={'intent':{'expires_at':str(int(time.time())+120)},'approval_signatures':['a','b']}
    result=module.verify_live_entry(None,row)
    assert result['next_step']=='REQUESTER_RESERVE' and result['status']=='NO_RESERVATION'
    assert result['current_chain_state'] is None and result['transactions']==[]
    row['approval_signatures']=['a']
    assert module.verify_live_entry(None,row)['next_step']=='COMPLETE_APPROVALS'
    row['intent']['expires_at']='1'
    assert module.verify_live_entry(None,row)['next_step']=='CREATE_NEW_TASK'


def test_missing_history_never_becomes_success_or_permission_to_resend(monkeypatch):
    from chainguard_gateway import phase10_audit as module
    monkeypatch.setattr(module,'verify_action',lambda *args:{'status':'UNAVAILABLE','reason':'CHAIN_UNAVAILABLE'})
    result=module.verify_live_entry(None,{'intent':{'expires_at':'1'},'approval_signatures':['a','b']})
    assert result=={'status':'UNAVAILABLE','reason':'CHAIN_UNAVAILABLE'}


def test_signer_checks_review_commit_and_exact_digest_before_signing(monkeypatch,tmp_path):
    from chainguard_gateway import phase10_client as module
    from chainguard_gateway.crypto import commit
    # Use a frozen valid ActionIntent from the public original protocol evidence.
    path=next((module.Path(__file__).resolve().parents[2]/'results/phase8/complete-experiment-01/protocol').glob('case-*.json'))
    intent=json.loads(path.read_text(encoding='utf8'))['record']['intent']
    params={'to':['alice@inbox.chainguard.invalid'],'subject':'test','body':'synthetic'}; salt='0x'+'12'*32
    intent=dict(intent,params_commit=commit('params',salt,params))
    domain={'name':'ChainGuard ExecutionRegistry','version':'1','chainId':'20261026','verifyingContract':'0x5effbc396c8532801c2a5e7a4d903b7c8702878a'}
    class Connection:
        def request(self,*args): return {'intent':intent,'params':params,'params_salt':salt}
    monkeypatch.setattr(module,'load',lambda:(tmp_path,{'subject':'biz','domain':domain}))
    monkeypatch.setattr(module,'connection',lambda *args:Connection())
    # No signing.key exists. A wrong digest must fail without even opening a key.
    with pytest.raises(ToolError,match='PARAMS_MISMATCH'):
        module.adapter({'op':'sign','action_id':intent['action_id'],'intent_digest':'0x'+'ff'*32})
    intent['params_commit']='0x'+'00'*32
    with pytest.raises(ToolError,match='PARAMS_MISMATCH'):
        module.adapter({'op':'review','action_id':intent['action_id']})


def test_readonly_mime_observer_verifies_original_result_types_and_tampering(monkeypatch,tmp_path):
    import hashlib
    import sqlite3
    from Crypto.Cipher import AES
    from email.message import EmailMessage
    from eth_account import Account
    from chainguard_gateway import phase10_client as module
    from chainguard_gateway.crypto import commit
    from chainguard_gateway.chain_crypto import sign_receipt
    aid='0x'+'34'*32; key=secrets.token_bytes(32); signer=Account.create()
    deployment={'chainId':20261026,'contracts':{'AuditRegistry':{'address':'0x5d505b4ad2c4596b3ba3742ca5b338eb4d05f2ee'}}}
    monkeypatch.setattr(module,'load',lambda:(tmp_path,{'deployment':deployment,'tool_signer':signer.address.lower()}))
    (tmp_path/'data.key').write_bytes(key)
    message=EmailMessage();message['To']='alice@inbox.chainguard.invalid';message['Subject']='Original';message.set_content('Actual synthetic body')
    mime=message.as_bytes();sha=hashlib.sha256(mime).hexdigest()
    result={'message_ids':['1'],'delivered_recipients':['alice@inbox.chainguard.invalid'],'mime_sha256':sha,'transport':'LOCAL_SQLITE_MAILBOX'}
    salt='0x'+'11'*32; evidence={'action_id':aid,'mime_sha256':sha}
    wire={'schema_version':1,'action_id':aid,'params_commit':'0x'+'22'*32,'result_commit':commit('result',salt,result),
        'evidence_index_commit':commit('evidence',salt,evidence),'executed_at':str(int(time.time())),'outcome':0}
    domain={'name':'ChainGuard AuditRegistry','version':'1','chainId':'20261026','verifyingContract':deployment['contracts']['AuditRegistry']['address']}
    stored={'receipt':wire,'tool_signature':sign_receipt(signer.key,wire,domain),'result':result,'result_salt':salt,'evidence':evidence,'evidence_salt':salt}
    cipher=AES.new(key,AES.MODE_GCM);cipher.update(aid.encode());encrypted,tag=cipher.encrypt_and_digest(json.dumps(stored).encode())
    with sqlite3.connect(tmp_path/'state.sqlite3') as db:
        db.executescript('CREATE TABLE mailbox(message_id INTEGER,action_id TEXT,recipient TEXT,mime BLOB,mime_sha256 TEXT); CREATE TABLE chain_mail(action_id TEXT,params_commit TEXT,data BLOB);')
        db.execute('INSERT INTO mailbox VALUES (?,?,?,?,?)',(1,aid,result['delivered_recipients'][0],mime,sha))
        db.execute('INSERT INTO chain_mail VALUES (?,?,?)',(aid,wire['params_commit'],cipher.nonce+tag+encrypted))
    check=module.observe(aid,True); assert check['status']=='VERIFIED' and check['mail_count']==1
    assert check['messages'][0]['body'].strip()=='Actual synthetic body'
    with sqlite3.connect(tmp_path/'state.sqlite3') as db: db.execute('UPDATE mailbox SET mime=?',(b'TAMPERED',))
    with pytest.raises(ToolError,match='RECEIPT_INVALID'): module.observe(aid)
