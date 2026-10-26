from types import SimpleNamespace
import pytest

from evaluation.workspace_adapter import WorkspaceMapper,IncompatibleSample
from chainguard_agent.journal import Journal
from chainguard_agent.proxy import ToolExecutionProxy
from chainguard_sandbox.protocol import ToolError


def mapper():
    return WorkspaceMapper({'benchmark@example.org':'alice@inbox.chainguard.invalid'},{'13':'ad-file-13'})


def call(name,args): return SimpleNamespace(id='official-call',function=name,args=args)


def test_workspace_mail_file_and_delete_mapping_preserves_arguments():
    m=mapper()
    assert m.map(call('send_email',{'recipients':['benchmark@example.org'],'subject':'subject','body':'unaltered'})).arguments=={
        'to':['alice@inbox.chainguard.invalid'],'subject':'subject','body':'unaltered'}
    assert m.map(call('get_file_by_id',{'file_id':'13'})).name=='doc.read'
    assert m.map(call('delete_file',{'file_id':'13'})).arguments=={'doc_id':'ad-file-13'}


@pytest.mark.parametrize('extra',[{'cc':['someone@example.org']},{'bcc':['someone@example.org']},{'attachments':[{'type':'file','file_id':'13'}]}])
def test_mapper_rejects_semantic_loss_instead_of_dropping_fields(extra):
    with pytest.raises(IncompatibleSample,match='ATTACHMENTS_CC_BCC_UNSUPPORTED'):
        mapper().map(call('send_email',dict(recipients=['benchmark@example.org'],subject='s',body='b',**extra)))


def test_unmapped_identities_and_tools_cannot_gain_capabilities():
    for name,args in [('send_email',{'recipients':['attacker@example.org'],'subject':'s','body':'b'}),
        ('delete_file',{'file_id':'../../real'}),('create_calendar_event',{})]:
        with pytest.raises(IncompatibleSample): mapper().map(call(name,args))
    with pytest.raises(ValueError): WorkspaceMapper({'x':'real@example.org'},{})
    with pytest.raises(ValueError): WorkspaceMapper({'x':'alice@inbox.chainguard.invalid','y':'alice@inbox.chainguard.invalid'},{})


def test_mapped_high_risk_call_reaches_same_security_proxy(tmp_path):
    class DenyTransport:
        def __init__(self): self.seen=[]
        def request(self,method,path,body=None,key=None):
            self.seen.append((method,path,body))
            raise ToolError('POLICY_DENY')
    transport=DenyTransport()
    proxy=ToolExecutionProxy(transport,Journal(tmp_path),'benchmark','0x'+'11'*32)
    result=mapper().execute(call('delete_file',{'file_id':'13'}),proxy)
    assert result=={'status':'DENIED','error_code':'POLICY_DENY'}
    assert transport.seen[0][1]=='/v1/agent/actions/propose'
    assert transport.seen[0][2]['tool_name']=='doc.delete'
