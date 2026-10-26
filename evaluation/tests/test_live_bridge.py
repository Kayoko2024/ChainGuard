import pytest
from evaluation.live_bridge import Session
from chainguard_sandbox.protocol import ToolError


@pytest.mark.parametrize('method,path',[('POST','/v1/actions/reserve'),('POST','/internal/v1/tools/execute'),('POST','/operator/v1/review'),('GET','/v1/actions/unknown')])
def test_agent_bridge_exposes_neither_signing_nor_raw_tool_operations(method,path):
    session=Session.__new__(Session)
    session.actions=[]
    with pytest.raises(ToolError):
        session.request(dict(method=method,path=path,body={},key=None))
