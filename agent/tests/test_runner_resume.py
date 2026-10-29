import json
import pytest
from chainguard_agent.model import Turn,ToolCall
from chainguard_agent.runner import AgentRunner


def test_resume_retains_completed_reads_pending_batch_and_budget():
    snapshots=[];calls=[]
    class Pause(Exception):pass
    class Backend:
        mode='unit'
        def next_turn(self,messages,tools):
            if not any(m['role']=='tool' for m in messages):return Turn(calls=(ToolCall('read','doc.read',{'doc_id':'meeting-notes'}),ToolCall('mail','mail.send',{'to':['alice@inbox.chainguard.invalid'],'subject':'s','body':'b'})))
            assert [m['tool_call_id'] for m in messages if m['role']=='tool']==['read','mail']
            assert json.loads(messages[-1]['content'])['status']=='FINALIZED_OK'
            return Turn('继续：已核验发送')
    class Proxy:
        def execute(self,call):
            calls.append(call.id)
            if call.id=='mail':raise Pause()
            return {'trust':'untrusted','content':'实际会议总结'}
    with pytest.raises(Pause):AgentRunner(Backend(),Proxy(),max_calls=2).run('总结再发送',checkpoint=snapshots.append)
    frozen=snapshots[-1]
    assert frozen['cursor']==1 and frozen['count']==2
    out=AgentRunner(Backend(),Proxy(),max_calls=2).run('ignored',snapshot=frozen,checkpoint=snapshots.append,resume_results={'mail':{'status':'FINALIZED_OK'}})
    assert calls==['read','mail'] and out['output']=='继续：已核验发送'
    history=snapshots[-1]['messages']
    class Follow:
        mode='unit'
        def next_turn(self,messages,tools):
            assert messages[-2]['content']=='继续：已核验发送' and messages[-1]['content']=='刚才总结是什么'
            return Turn('同一个上下文')
    AgentRunner(Follow(),Proxy()).run('刚才总结是什么',history=history)


def test_resume_does_not_reset_model_turn_budget():
    class Backend:
        mode='unit'
        def next_turn(self,*args):raise AssertionError('Must not reset budget')
    snap=dict(version=1,messages=[],outputs=[],count=0,turns=1,pending=[],cursor=0)
    with pytest.raises(Exception,match='POLICY_DENY'):AgentRunner(Backend(),None,max_turns=1).run('',snapshot=snap)


def test_completed_checkpoint_never_requests_another_model_turn():
    class Backend:
        mode='unit'
        def next_turn(self,*args):raise AssertionError('Completed run must not call model again')
    snapshot=dict(version=1,messages=[dict(role='assistant',content='原回复')],outputs=[],count=0,turns=1,pending=[],cursor=0,phase='COMPLETED')
    assert AgentRunner(Backend(),None,max_turns=1).run('',snapshot=snapshot)['output']=='原回复'
