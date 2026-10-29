"""Deterministic memory/scheduler tests, not live model or chain evidence."""
import hashlib
import json
import time
from pathlib import Path
from types import SimpleNamespace
import pytest
from chainguard_gateway.phase10_store import OperationsStore,PublicStore
from chainguard_gateway.phase10_service import Operations
from chainguard_gateway.canonical import canonical
from chainguard_agent.model import Turn,ToolCall
from chainguard_sandbox.protocol import ToolError

ROOT=Path(__file__).resolve().parents[2]
def key(n):return '0x'+format(n,'064x')
SCOPE=dict(allowed_tools=['doc.list','mail.send'],allowed_document_ids=['meeting-notes'],read_mailboxes=[],allowed_recipients=['alice@inbox.chainguard.invalid'])

def setup(tmp_path,backend):
    class Bridge:
        count=0
        def call(self,role,value):
            if value['op']=='create_task':return dict(task_id=value['key'],requester='0x'+'11'*20,agent='0x'+'12'*20,expires_at=str(int(time.time())+900))
            self.count+=1;data=dict(documents=[{'doc_id':'meeting-notes','title':'actual synthetic fixture'}])
            return dict(tool_name='doc.list',trust='untrusted',data=data,sha256=hashlib.sha256(canonical(data)).hexdigest(),read_execution_id=key(90))
        def grant_library(self,*args):return {}
    config=dict(deployment=json.loads((ROOT/'results/phase5/besu-run-01/report.json').read_text()),signers={'agent':'0x'+'12'*20},repo=str(ROOT))
    ops=Operations(OperationsStore(tmp_path/'private'),PublicStore(tmp_path/'public.sqlite'),Bridge(),config,backend_factory=lambda _:backend())
    ops.conversation_service.create(key(1),'owner',SCOPE)
    return ops


def test_same_session_remembers_tool_role_and_assistant_reply_after_restart(tmp_path):
    class Backend:
        mode='unit'
        def next_turn(self,messages,tools):
            if messages[-1]['role']=='user' and messages[-1]['content'].startswith('总结'):
                return Turn(calls=(ToolCall('read','doc.list',{}),))
            if messages[-1]['role']=='tool':return Turn('会议摘要：Alice负责核验')
            assert any(m['role']=='assistant' and m.get('content')=='会议摘要：Alice负责核验' for m in messages)
            assert any(m['role']=='tool' for m in messages)
            return Turn('已记住上文，请明确发送授权')
    ops=setup(tmp_path,Backend)
    ops.conversation_service.append(key(1),'owner',key(2),'总结会议',0);ops.tick()
    assert ops.store.get(key(2))['state']=='READ_COMPLETED' and ops.store.get(key(2))['policy_verdict']=='READ_ALLOWED' and ops.bridge.count==1
    ops=Operations(OperationsStore(tmp_path/'private'),ops.public,ops.bridge,ops.config,backend_factory=lambda _:Backend())
    ops.conversation_service.append(key(1),'owner',key(3),'刚才的摘要是什么？',1);ops.tick()
    assert ops.store.get(key(3))['agent_output']=='已记住上文，请明确发送授权' and ops.bridge.count==1
    assert len(ops.conversation_service.detail(key(1),'owner')['runs'])==2
    with pytest.raises(ToolError,match='FORBIDDEN'):ops.conversation_service.detail(key(1),'other')


def test_pending_high_is_checkpointed_and_only_verified_finalization_resumes(tmp_path,monkeypatch):
    from chainguard_gateway import conversation_service
    class Backend:
        mode='unit'
        def next_turn(self,messages,tools):
            if messages[-1]['role']!='tool':return Turn(calls=(ToolCall('send','mail.send',dict(to=['alice@inbox.chainguard.invalid'],subject='s',body='b')),))
            assert json.loads(messages[-1]['content'])['status']=='FINALIZED_OK'
            return Turn('已收到工具核验结果，继续回复')
    ops=setup(tmp_path,Backend);calls=[]
    from chainguard_agent.default_proxy import DefaultToolProxy
    monkeypatch.setattr(DefaultToolProxy,'execute',lambda _,call:(calls.append(call.id) or dict(status='AWAITING_APPROVAL',action_id=key(20))))
    ops.conversation_service.append(key(1),'owner',key(2),'发送',0);ops.tick()
    job=ops.store.get(key(2));assert job['state']=='AWAITING_APPROVAL' and job['runner_snapshot']['cursor']==0 and calls==['send']
    with pytest.raises(ToolError,match='CONVERSATION_BUSY'):ops.conversation_service.append(key(1),'owner',key(3),'插队',1)
    ops.records[key(20)]=dict(state='UNKNOWN');ops.tick();assert calls==['send'] and not ops.store.get(key(2)).get('agent_output')
    ops.records[key(20)]=dict(state='FINALIZED_OK',action_id=key(20))
    monkeypatch.setattr(conversation_service,'verify_action',lambda *args:dict(status='UNAVAILABLE'))
    ops.tick();assert not ops.store.get(key(2)).get('agent_output')
    monkeypatch.setattr(conversation_service,'verify_action',lambda *args:dict(status='VERIFIED'))
    ops.bridge.observe=lambda _:dict(status='VERIFIED')
    ops.tick();ops.tick()
    assert ops.store.get(key(2))['agent_output']=='已收到工具核验结果，继续回复' and calls==['send']


def test_conversation_routes_require_owner_role_csrf_version_and_freeze_scope(tmp_path):
    import secrets
    from fastapi.testclient import TestClient
    from chainguard_gateway.phase10_api import create_operations_app,password_hash
    class Backend:mode='unit'
    ops=setup(tmp_path,Backend);credentials={}
    for role in ['requester','biz','security']:
        salt=secrets.token_hex(16);credentials[role]=dict(salt=salt,hash=password_hash('test-password',salt),organization=role)
    origin='http://127.0.0.1:8090';client=TestClient(create_operations_app(ops,credentials,origin,start_worker=False))
    assert client.get('/ops/v1/conversations').status_code==401
    def login(role):
        response=client.post('/ops/v1/login',headers={'Origin':origin},json=dict(role=role,password='test-password'))
        return {'Origin':origin,'X-CSRF-Token':response.json()['csrf']}
    h=login('security')
    assert client.post('/ops/v1/conversations',headers=h,json=dict(session_id=key(9),scope=SCOPE)).status_code==403
    h=login('requester')
    assert client.post('/ops/v1/conversations',headers={'Origin':origin},json=dict(session_id=key(9),scope=SCOPE)).status_code==403
    assert client.post('/ops/v1/conversations',headers=h,json=dict(session_id=key(9),scope=SCOPE)).status_code==201
    value=dict(message_id=key(10),text='同会话消息',expected_version=0)
    path='/ops/v1/conversations/'+key(9)+'/messages'
    assert client.post(path,headers=h,json=value).status_code==202
    assert client.post(path,headers=h,json=value).status_code==202
    assert len(ops.conversations.runs(key(9)))==1
    assert client.post(path,headers=h,json=dict(value,message_id=key(11),expected_version=1)).status_code==409
    assert client.post(path,headers=h,json=dict(value,allowed_tools=['mail.send'])).status_code==422
    assert client.post('/ops/v1/conversations/'+key(9)+'/grant',headers=h,json=dict(duration_seconds=3600,max_calls=50)).status_code==409
    assert 'runner_snapshot' not in client.get('/ops/v1/tasks/'+key(10)).json()
