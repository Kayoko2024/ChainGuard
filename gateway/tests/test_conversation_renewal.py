"""Renewal unit tests use real signatures/SQLite and fixture RPC policy only."""
import copy
import time
import pytest
from chainguard_agent.model import Turn
from chainguard_gateway import conversation_runtime
from chainguard_gateway.conversation_memory import balanced
from chainguard_gateway.conversation_service import ConversationError
from chainguard_gateway.conversation_grants import NEW_TYPES, digest
from chainguard_gateway.session_grants import sign
from chainguard_sandbox.protocol import ToolError
from test_conversations import setup, key, SCOPE
from test_conversation_grants import access, USER, AGENT


def configured(tmp_path,monkeypatch):
    class Backend:
        mode='unit'
        def next_turn(self,messages,tools):return Turn('已记住前文')
    ops=setup(tmp_path/'ops',Backend)
    gates=[access(tmp_path/'tool'),access(tmp_path/'gateway')]
    ops.config['tool_sessions']={'conversation':True}
    ops.config['signers'].update(requester=USER.address.lower(),agent=AGENT)
    monkeypatch.setattr(conversation_runtime,'policy_for',lambda _:gates[1].policy)
    class Bridge:
        signatures=0;fail_gateway=False
        def call(self,role,value):
            if value['op'].startswith('sign-conversation-'):
                self.signatures+=1
                kind={'sign-conversation-grant':'ConversationGrant','sign-conversation-bind':'ConversationBinding'}[value['op']]
                return dict(message=value['message'],signature=sign(kind,value['message'],gates[0].policy.domain,USER.key))
            if value['op']=='create_task':return dict(task_id=value['key'],requester=USER.address.lower(),agent=AGENT,expires_at=str(int(time.time())+86400))
            pytest.fail('Unexpected bridge op')
        def grant_library(self,*args):pass
        def conversation(self,op,value):
            results=[]
            for i,gate in enumerate(gates):
                if i==1 and self.fail_gateway:raise ToolError('BACKEND_UNAVAILABLE')
                if op=='install':result=gate.install(value)
                elif op=='activate':result=gate.activate(value)
                elif op=='preflight':result=gate.preflight(value['envelope'])
                elif op=='bind':result=gate.bind(value)
                else:pytest.fail('Unexpected conversation op '+op)
                results.append(result)
            if op=='preflight':return dict(results[-1],used=max(r['used'] for r in results),checked_gates=2)
            if op=='activate':return dict(results[-1],checked_gates=2)
            return results[-1]
    ops.bridge=Bridge()
    return ops,gates


def test_old_job_attaches_once_and_continues_in_same_window_without_changing_original(tmp_path):
    class Backend:
        mode='unit'
        def next_turn(self,messages,tools):
            if messages[-1]['content'].startswith('总结'):return Turn('负责人是 Alice')
            assert any(m.get('content')=='负责人是 Alice' for m in messages)
            return Turn('Alice，沿用旧上下文')
    ops=setup(tmp_path,Backend);ops.create(key(7),dict(SCOPE,task_text='总结旧任务'));ops.run_agent(key(7))
    original=copy.deepcopy(ops.store.get(key(7)))
    first=ops.conversation_service.attach(key(7),'owner');second=ops.conversation_service.attach(key(7),'owner')
    assert first['id']==second['id'] and first['runs'][0]['agent_output']=='负责人是 Alice'
    assert ops.store.get(key(7))==original and ops.detail(key(7))['conversation_id']==first['id']
    ops.conversation_service.append(first['id'],'owner',key(8),'刚才是谁',0);ops.tick()
    result=ops.conversation_service.detail(first['id'],'owner')
    assert len(result['runs'])==2 and result['runs'][1]['agent_output']=='Alice，沿用旧上下文'
    assert ops.store.get(key(7))==original


def test_failure_keeps_user_context_without_retrying_or_fabricating_tool_results(tmp_path):
    class Backend:
        mode='unit'
        def next_turn(self,messages,tools):
            if messages[-1]['content'].startswith('故障'):raise ToolError('MODEL_OUTPUT_TRUNCATED')
            assert any(m['role']=='user' and m['content'].startswith('故障') for m in messages)
            assert any(m['role']=='system' and 'MODEL_OUTPUT_TRUNCATED' in m['content'] for m in messages)
            return Turn('记得上一轮失败，不重发')
    ops=setup(tmp_path,Backend)
    ops.conversation_service.append(key(1),'owner',key(2),'故障任务',0);ops.tick()
    assert ops.store.get(key(2))['state']=='MODEL_ERROR'
    ops.conversation_service.append(key(1),'owner',key(3),'继续说明',1);ops.tick()
    assert ops.store.get(key(3))['agent_output']=='记得上一轮失败，不重发'
    assert not any(m['role']=='tool' for m in ops.conversations.get(key(1))['history'])
    assert balanced([dict(role='assistant',content='',tool_calls=[dict(id='unanswered')])])==[]


def test_expired_is_not_enqueued_and_renewal_resends_same_message_once(tmp_path,monkeypatch):
    ops,gates=configured(tmp_path,monkeypatch);sid=key(1);service=ops.conversation_service
    service.append(sid,'owner',key(2),'第一条',0);ops.tick()
    old=ops.conversations.get(sid)['low_grant'];expires=old['message']['expiresAt']
    with monkeypatch.context() as clock:
        clock.setattr(time,'time',lambda:expires+1)
        # A duplicate of an accepted message still returns its original run.
        service.append(sid,'owner',key(2),'第一条',0)
        before=len(ops.store.jobs())
        with pytest.raises(ConversationError,match='AUTH_EXPIRED') as error:service.append(sid,'owner',key(3),'继续',1)
        assert error.value.details['accepted'] is False and len(ops.store.jobs())==before
        result=service.renew(sid,'owner',dict(duration_seconds=86400,max_calls=50),old['digest'],key(90))
        new=result['low_grant'];assert result['authorization']['status']=='ACTIVE'
        assert new['digest']!=old['digest'] and new['message']['sessionId']==sid and new['message']['nonce']!=old['message']['nonce']
        service.append(sid,'owner',key(3),'继续',1)
        service.append(sid,'owner',key(3),'继续',1)
        assert ops.conversations.runs(sid)==[key(2),key(3)]
        assert ops.store.get(key(3))['conversation_grant_digest']==new['digest']
        for gate in gates:
            with gate.connect() as db:
                assert db.execute('SELECT COUNT(*) FROM conversation_grants').fetchone()[0]==2
                assert db.execute('SELECT grant_digest FROM conversation_bindings WHERE task_id=?',(key(2),)).fetchone()[0]==old['digest']


def test_partial_install_restart_and_duplicate_renewal_keep_same_signature(tmp_path,monkeypatch):
    ops,gates=configured(tmp_path,monkeypatch);service=ops.conversation_service;options=dict(duration_seconds=3600,max_calls=2)
    ops.bridge.fail_gateway=True
    with pytest.raises(ToolError,match='BACKEND_UNAVAILABLE'):service.renew(key(1),'owner',options,None,key(90))
    pending=ops.conversations.get(key(1));assert not pending['low_grant'] and pending['pending_renewal']
    envelope=ops.conversations.renewal(pending['pending_renewal'])['envelope']
    ops.bridge.fail_gateway=False
    service.renew(key(1),'owner',options,None,key(90))
    service.renew(key(1),'owner',options,None,key(90))
    assert ops.bridge.signatures==1 and ops.conversations.get(key(1))['low_grant']==envelope
    for gate in gates:
        assert len(gate.status(key(1))['grants'])==1


def test_pending_high_or_unknown_cannot_be_cleared_by_renewal(tmp_path,monkeypatch):
    ops,_=configured(tmp_path,monkeypatch)
    ops.conversations.append(key(1),'owner',key(2),'挂起任务',0)
    for state in ['AWAITING_APPROVAL','AWAITING_TOOL_APPROVAL','UNKNOWN','INTERRUPTED']:
        ops.store.update(key(2),state=state)
        with pytest.raises(ToolError,match='CONVERSATION_BUSY'):ops.conversation_service.renew(key(1),'owner',dict(duration_seconds=3600,max_calls=2))
        result=ops.conversation_service.detail(key(1),'owner')
        assert result['blocking_run']['run_id']==key(2)
    assert ops.bridge.signatures==0


def test_rotation_preserves_quota_and_binding_and_rejects_old_grant_new_calls(tmp_path):
    from test_conversation_grants import envelope,bind,request,result
    gate=access(tmp_path);first=envelope();gate.install(first);bind(gate,first)
    gate.activate(dict(envelope=first,previous_digest=None))
    gate.execute(request(),key(20),result)
    second=envelope(nonce=2);gate.install(second)
    first_digest=digest('ConversationGrant',first['message'],gate.policy.domain)
    gate.activate(dict(envelope=second,previous_digest=first_digest))
    assert gate.execute(request(),key(20),lambda:pytest.fail('duplicate'))==result()
    with pytest.raises(ToolError,match='SESSION_REPLACED'):gate.execute(request(),key(21),lambda:pytest.fail('retired grant'))
    assert gate.status(key(1))['grants'][0]['used']==1
    assert gate.status(key(1))['authorization_epochs'][0]['end_sequence']==1
    log=gate.status(key(1))['logs'][0]
    assert log['schema']==3 and log['grant_digest']==first_digest


def test_http_auth_expired_is_distinct_from_login_and_preserves_message_id(tmp_path,monkeypatch):
    import secrets
    from fastapi.testclient import TestClient
    from chainguard_gateway.phase10_api import create_operations_app,password_hash
    ops,gates=configured(tmp_path,monkeypatch);sid=key(66);owner='requester/OrgA'
    ops.conversation_service.create(sid,owner,SCOPE)
    ops.conversation_service.append(sid,owner,key(67),'最初消息',0);ops.tick()
    old=ops.conversations.get(sid)['low_grant'];expires=old['message']['expiresAt']
    salt=secrets.token_hex(16);credentials={'requester':dict(salt=salt,hash=password_hash('pw',salt),organization='OrgA')}
    app=create_operations_app(ops,credentials,'http://testserver',start_worker=False);client=TestClient(app)
    path='/ops/v1/conversations/'+sid+'/messages';body=dict(message_id=key(68),text='旧窗口继续',expected_version=1)
    assert client.post(path,headers={'Origin':'http://testserver'},json=body).status_code==401
    with monkeypatch.context() as clock:
        clock.setattr(time,'time',lambda:expires+1)
        logged=client.post('/ops/v1/login',headers={'Origin':'http://testserver'},json=dict(role='requester',password='pw'))
        h={'Origin':'http://testserver','X-CSRF-Token':logged.json()['csrf']}
        denied=client.post(path,headers=h,json=body)
        assert denied.status_code==409 and denied.json()['error']==dict(code='AUTH_EXPIRED',accepted=False,session_id=sid,grant_digest=old['digest'])
        assert ops.conversations.runs(sid)==[key(67)]
        renewal=client.post('/ops/v1/conversations/'+sid+'/grant',headers=dict(h,Prefer='respond-async',**{'Idempotency-Key':key(90)}),json=dict(duration_seconds=86400,max_calls=50,expected_grant_digest=old['digest']))
        assert renewal.status_code==202 and renewal.json()['status']=='PENDING'
        assert app.state.control_queue.run_once()
        ready=client.get('/ops/v1/operations/'+renewal.json()['operation_id']).json()
        assert ready['status']=='SUCCEEDED' and ready['result']['authorization']['status']=='ACTIVE'
        assert client.post(path,headers=h,json=body).status_code==202
        assert client.post(path,headers=h,json=body).status_code==202
        assert ops.conversations.runs(sid)==[key(67),key(68)]


def test_new_message_preflight_fails_on_either_gate_or_exhaustion_without_enqueue(tmp_path,monkeypatch):
    ops,gates=configured(tmp_path,monkeypatch);service=ops.conversation_service
    service.append(key(1),'owner',key(2),'第一次',0);ops.tick()
    for gate in gates:
        gate.policy.online=False
        with pytest.raises(ToolError,match='CHAIN_UNAVAILABLE'):service.append(key(1),'owner',key(3),'继续',1)
        gate.policy.online=True
    for gate in gates:
        with gate.connect() as db:db.execute('UPDATE conversation_grants SET used=50')
    with pytest.raises(ConversationError,match='AUTH_EXHAUSTED'):service.append(key(1),'owner',key(3),'继续',1)
    assert ops.conversations.runs(key(1))==[key(2)]


def test_only_fixed_id_renewal_control_resumes_after_process_interruption(tmp_path,monkeypatch):
    from chainguard_gateway.operation_queue import OperationQueue
    ops,_=configured(tmp_path,monkeypatch);queue=OperationQueue(ops)
    renewal=queue.submit('requester','renew',[key(1),'owner',dict(duration_seconds=3600,max_calls=2),None,key(90)],key(91))
    execution=queue.submit('requester','execute',[key(2),'digest'],key(92))
    with ops.store.db() as db:db.execute("UPDATE web_operations SET state='RUNNING'")
    queue=OperationQueue(ops)
    assert queue.get(renewal['operation_id'],'requester')['status']=='PENDING'
    assert queue.get(execution['operation_id'],'requester')['status']=='UNKNOWN'
    queue.run_once()
    assert queue.get(renewal['operation_id'],'requester')['status']=='SUCCEEDED' and ops.bridge.signatures==1


def test_concurrent_renewals_install_only_one_nonce_and_cas_rejects_stale_request(tmp_path,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    ops,gates=configured(tmp_path,monkeypatch);service=ops.conversation_service
    options=dict(duration_seconds=3600,max_calls=2)
    def renew(_):
        try:return service.renew(key(1),'owner',options,None,key(90))['low_grant']['digest']
        except ToolError as error:return error.code
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(renew,range(2)))
    expected=ops.conversations.get(key(1))['low_grant']['digest']
    assert results==[expected,expected]
    for gate in gates:assert len(gate.status(key(1))['grants'])==1
    with pytest.raises(ToolError,match='STATE_CONFLICT'):service.renew(key(1),'owner',options,None,key(91))


def test_hiding_attached_legacy_session_preserves_original_without_list_reappearance(tmp_path):
    ops=setup(tmp_path,None);ops.create(key(7),dict(SCOPE,task_text='旧会话'))
    ops.store.update(key(7),state='NO_ACTION',agent_output='原记录')
    original=copy.deepcopy(ops.store.get(key(7)))
    sid=ops.conversation_service.attach(key(7),'owner')['id']
    ops.store.hide('conversation',sid,'owner')
    assert ops.store.visible_jobs('owner')==[] and ops.store.get(key(7))==original
    assert ops.conversation_service.detail(sid,'owner')['runs'][0]['agent_output']=='原记录'


def test_schema3_proof_commits_grant_digest_and_keeps_schema2_compatibility():
    from chainguard_gateway.batch_audit import merkle
    from chainguard_gateway.conversation_audit import check
    logs=[dict(schema=2,session_id=key(1),sequence=1,risk_level='LOW',tool_name='doc.read'),
          dict(schema=3,session_id=key(1),sequence=2,risk_level='LOW',tool_name='doc.read',grant_digest=key(22))]
    root,proofs=merkle(logs);batch=dict(session_id=key(1),count=2,root=root)
    assert all(check(log,p,batch) for log,p in zip(logs,proofs))
    assert not check(dict(logs[1],grant_digest=key(23)),proofs[1],batch)

