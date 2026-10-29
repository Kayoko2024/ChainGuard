"""Transport failure is not a ledger verdict; maintenance cannot bypass in-flight guards."""
import importlib.util
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from chainguard_gateway.phase10_bridge import DockerBridge
from chainguard_gateway.phase10_api import create_operations_app
from chainguard_gateway.phase10_store import OperationsStore
from chainguard_sandbox.protocol import ToolError


@pytest.mark.parametrize('failure',['exit','timeout','missing'])
def test_docker_failure_reports_backend_without_claiming_chain_is_down(monkeypatch,failure):
    def run(*args,**kwargs):
        if failure=='timeout':raise subprocess.TimeoutExpired('docker',1)
        if failure=='missing':raise FileNotFoundError()
        return SimpleNamespace(returncode=1,stderr=b'diagnostic must not become public',stdout=b'')
    monkeypatch.setattr(subprocess,'run',run)
    with pytest.raises(ToolError,match='BACKEND_UNAVAILABLE'):DockerBridge({}).docker(['exec','gateway','python'])


@pytest.mark.parametrize('code',['BACKEND_UNAVAILABLE','CHAIN_UNAVAILABLE'])
def test_business_transient_failure_is_503_and_preserves_error_type(tmp_path,code):
    store=OperationsStore(tmp_path)
    def review(*_):raise ToolError(code)
    ops=SimpleNamespace(store=store,stop=SimpleNamespace(set=lambda:None),review=review)
    app=create_operations_app(ops,{},'http://127.0.0.1:8090',start_worker=False)
    client=TestClient(app);token,_=store.login('requester');client.cookies.set('cg_session',token)
    response=client.get('/ops/v1/tasks/id/review')
    assert response.status_code==503 and response.json()=={'error':{'code':code}}


def test_initial_and_upgrade_resource_limits_are_bounded_and_restartable():
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
    try:
        from phase10_resources import service_limits,MIB
        from update_default_tools import require_idle
        for kind,expected in [('gateway',1024),('tool',512),('agent',512)]:
            args=service_limits(kind);assert int(args[args.index('--memory')+1])==expected*MIB
            assert args[args.index('--restart')+1]=='unless-stopped'
        assert str(2048*MIB) in service_limits('gateway',2048*MIB)
        require_idle([{'state':'AWAITING_APPROVAL'}],[{'state':'AWAITING_APPROVAL','intent':{'expires_at':'200'}}],now=100,allow_waiting=True)
        for state in ['RESERVING','RESERVED','EXECUTING','UNKNOWN','EXECUTION_RECORDED']:
            with pytest.raises(ValueError):require_idle([], [{'state':state}],allow_waiting=True)
    finally:sys.path.pop(0)
