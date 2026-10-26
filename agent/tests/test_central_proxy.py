import pytest
from chainguard_agent.central_proxy import CentralExecutionProxy
from chainguard_agent.journal import Journal
from chainguard_agent.model import ToolCall
from chainguard_sandbox.protocol import ToolError

TASK='0x'+'11'*32
ACTION='0x'+'22'*32


def record(state):
    return dict(record_type='CentralActionRecord',group='B',action_id=ACTION,task_id=TASK,tool_name='mail.send',risk=2,
        central_state=state,policy_verdict='REQUIRE_APPROVAL',policy_error_code=None,policy_enforced=True,intent=None,
        typed_data=None,approval_count=2,result=None,chain_state='NONE',chain_evidence=None,execution_receipt=None)


def test_central_unknown_queries_original_action_after_restart(tmp_path):
    requests=[]
    class Gateway:
        def request(self,method,path,body=None,key=None):
            requests.append(method)
            if len(requests)>1: raise ToolError('FORBIDDEN')
            return record('UNKNOWN')
    call=ToolCall('c','mail.send',{'to':['alice@inbox.chainguard.invalid'],'subject':'s','body':'b'})
    for _ in range(2):
        journal=Journal(tmp_path)
        result=CentralExecutionProxy(Gateway(),journal,'run',TASK).execute(call)
        assert result['status']=='UNKNOWN'
    assert requests==['POST','GET'] and journal.events()[-1]['tool_executed'] is None


def test_central_proxy_completed_calls_are_persistently_idempotent(tmp_path):
    requests=[]
    class Gateway:
        def request(self,*args):
            requests.append(args)
            return record('CENTRAL_OK')
    call=ToolCall('c','mail.send',{'to':['alice@inbox.chainguard.invalid'],'subject':'s','body':'b'})
    for _ in range(2):
        assert CentralExecutionProxy(Gateway(),Journal(tmp_path),'run',TASK).execute(call)['status']=='CENTRAL_OK'
    assert len(requests)==1


@pytest.mark.parametrize('name,params',[('doc.delete',{'doc_id':'report'}),('shell.exec',{})])
def test_central_proxy_denial_never_invokes_a_local_tool(tmp_path,name,params):
    class Gateway:
        def request(self,*args): raise ToolError('POLICY_DENY')
    journal=Journal(tmp_path)
    result=CentralExecutionProxy(Gateway(),journal,'run',TASK).execute(ToolCall('c',name,params))
    assert result['status']=='DENIED' and journal.events()[-1]['tool_executed'] is False
