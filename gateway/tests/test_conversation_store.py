import pytest
from chainguard_gateway.phase10_store import OperationsStore
from chainguard_gateway.conversation_store import Conversations
from chainguard_sandbox.protocol import ToolError

S='0x'+'15'*32;M='0x'+'16'*32
def test_memory_is_owner_bound_durable_and_append_is_idempotent(tmp_path):
    store=OperationsStore(tmp_path);c=Conversations(store);scope=dict(allowed_tools=[],allowed_recipients=[])
    c.create(S,'owner',scope)
    with pytest.raises(ToolError,match='FORBIDDEN'):c.get(S,'another')
    assert c.append(S,'owner',M,'先总结',0)
    assert not c.append(S,'owner',M,'先总结',0)
    with pytest.raises(ToolError,match='IDEMPOTENCY_CONFLICT'):c.append(S,'owner',M,'改参数',0)
    with pytest.raises(ToolError,match='STATE_CONFLICT'):c.append(S,'owner','0x'+'18'*32,'后发邮件',0)
    with pytest.raises(ToolError,match='CONVERSATION_BUSY'):c.append(S,'owner','0x'+'18'*32,'后发邮件',1)
    lease=c.claim(M);assert lease and c.claim(M) is None
    c.checkpoint(M,lease,dict(messages=[{'role':'user','content':'先总结'}]))
    c.release(M,lease)
    assert Conversations(OperationsStore(tmp_path)).get(S,'owner')['version']==1
    assert store.get(M)['runner_snapshot']['messages'][0]['content']=='先总结'
    assert '先总结'.encode() not in (tmp_path/'operations.sqlite3').read_bytes()
    store.update(M,state='READ_COMPLETED');c.close(S,'owner')
    with pytest.raises(ToolError,match='CONVERSATION_CLOSED'):c.append(S,'owner','0x'+'18'*32,'再执行',1)


def test_concurrent_append_and_expired_worker_are_fenced(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    store=OperationsStore(tmp_path);c=Conversations(store);c.create(S,'owner',dict(allowed_tools=[],allowed_recipients=[]))
    def submit(n):
        try:return c.append(S,'owner','0x'+format(n,'064x'),'concurrent message',0)
        except ToolError as e:return e.code
    with ThreadPoolExecutor(max_workers=2) as pool:out=list(pool.map(submit,[7,8]))
    assert out.count(True)==1 and len(c.runs(S))==1
    run=c.runs(S)[0];old=c.claim(run)
    with store.db() as db:db.execute('UPDATE conversation_runs SET lease_until=0 WHERE id=?',(run,))
    new=c.claim(run);assert new and new!=old
    with pytest.raises(ToolError,match='STATE_CONFLICT'):c.checkpoint(run,old,dict(messages=['stale']))
    c.checkpoint(run,new,dict(messages=['new owner']))
    c.release(run,old);assert c.claim(run) is None
    assert store.get(run)['runner_snapshot']['messages']==['new owner']
