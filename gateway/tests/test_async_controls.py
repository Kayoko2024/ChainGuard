"""Queue/concurrency tests with explicit unit stubs, never live-chain evidence."""
from concurrent.futures import ThreadPoolExecutor
import secrets
import threading
import time
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from chainguard_gateway.operation_queue import OperationQueue
from chainguard_gateway.phase10_store import OperationsStore,PublicStore
from chainguard_gateway.phase10_api import create_operations_app,password_hash
from chainguard_gateway.phase10_audit import create_live_audit_app
from chainguard_gateway.verification_jobs import VerificationJobs
from chainguard_sandbox.protocol import ToolError


def test_durable_atomic_control_dedupe_owner_binding_failure_and_interruption(tmp_path):
    calls=[];ops=SimpleNamespace(store=OperationsStore(tmp_path),approve=lambda *a:calls.append(a) or dict(record=None))
    queue=OperationQueue(ops)
    with ThreadPoolExecutor(max_workers=8) as pool:items=list(pool.map(lambda _:queue.submit('biz','approve',['task','biz','digest']),range(8)))
    assert len({v['operation_id'] for v in items})==1 and calls==[]
    id=items[0]['operation_id']
    with pytest.raises(ToolError,match='NOT_FOUND'):queue.get(id,'security')
    assert queue.run_once() and not queue.run_once() and len(calls)==1
    assert queue.get(id,'biz')['status']=='SUCCEEDED'
    assert [s['event'] for s in queue.get(id,'biz')['performance']['samples']]==['REQUEST_ACCEPTED','CONTROL_COMPLETED']
    queued=queue.submit('requester','execute',['other','bad'])
    with ops.store.db() as db:db.execute("UPDATE web_operations SET state='RUNNING' WHERE id=?",(queued['operation_id'],))
    restarted=OperationQueue(ops);assert restarted.get(queued['operation_id'],'requester')['status']=='UNKNOWN'
    assert not restarted.run_once() and len(calls)==1
    bad=restarted.submit('biz','approve',['task','biz','bad'])
    ops.approve=lambda *args:(_ for _ in ()).throw(ToolError('PARAMS_MISMATCH'))
    restarted.run_once();assert restarted.get(bad['operation_id'],'biz')['error']=='PARAMS_MISMATCH'


def test_http_async_submit_returns_while_approval_is_blocked_and_polling_is_local(tmp_path):
    entered=threading.Event();release=threading.Event();calls=[]
    def approve(*args):entered.set();release.wait(5);calls.append(args);return dict(record=None)
    store=OperationsStore(tmp_path);ops=SimpleNamespace(store=store,stop=threading.Event(),approve=approve)
    salt=secrets.token_hex(16);credentials={'biz':dict(salt=salt,hash=password_hash('pw',salt),organization='OrgA')}
    app=create_operations_app(ops,credentials,'http://testserver',start_worker=False);client=TestClient(app)
    login=client.post('/ops/v1/login',headers={'Origin':'http://testserver'},json=dict(role='biz',password='pw'))
    h={'Origin':'http://testserver','X-CSRF-Token':login.json()['csrf'],'Prefer':'respond-async'}
    start=time.perf_counter();accepted=client.post('/ops/v1/tasks/t/approve',headers=h,json=dict(intent_digest='digest'))
    assert accepted.status_code==202 and time.perf_counter()-start<1 and calls==[]
    pending=accepted.json();assert pending['status']=='PENDING' and pending['tx_hash'] is None
    worker=threading.Thread(target=app.state.control_queue.run_once);worker.start();assert entered.wait(2)
    assert client.get('/ops/v1/operations/'+pending['operation_id']).json()['status']=='PENDING'
    assert client.get('/health/live').status_code==200
    release.set();worker.join(5)
    assert client.get('/ops/v1/operations/'+pending['operation_id']).json()['status']=='SUCCEEDED' and len(calls)==1


def test_audit_list_never_uses_chain_and_real_time_verification_runs_asynchronously(tmp_path,monkeypatch):
    public=PublicStore(tmp_path/'public.sqlite');public.publish(dict(entry_id='item',group='C',state='FINALIZED_OK'))
    release=threading.Event();entered=threading.Event();calls=[]
    def verify(*args):entered.set();release.wait(5);calls.append(1);return dict(status='VERIFIED')
    monkeypatch.setattr('chainguard_gateway.phase10_audit.verify_live_entry',verify)
    client=TestClient(create_live_audit_app(public.path,None))
    assert client.get('/audit-api/v1/actions').json()['total']==1 and not calls
    path='/audit-api/v1/actions/item/verify';accepted=client.get(path,headers={'Prefer':'respond-async'})
    assert accepted.status_code==202 and entered.wait(2)
    id=accepted.json()['verification_id']
    assert client.get(path,headers={'Prefer':'respond-async'}).json()['verification_id']==id
    assert client.get('/audit-api/v1/verifications/'+id).json()['status']=='PENDING'
    release.set()
    for _ in range(100):
        value=client.get('/audit-api/v1/verifications/'+id).json()
        if value['status']=='COMPLETED':break
        time.sleep(.01)
    assert value['result']['status']=='VERIFIED' and len(calls)==1
    assert client.post('/audit-api/v1/actions/item/verify').status_code==405


def test_verification_failure_is_never_a_success():
    jobs=VerificationJobs();queued=jobs.submit('key',lambda:(_ for _ in ()).throw(ToolError('CHAIN_UNAVAILABLE')))
    for _ in range(100):
        result=jobs.get(queued['verification_id'])
        if result['status']=='COMPLETED':break
        time.sleep(.01)
    assert result['result']['status']=='UNAVAILABLE';jobs.pool.shutdown()
