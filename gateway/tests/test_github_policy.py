"""Isolated admission unit tests; fixtures are never counted as live chain evidence."""
import json
import sqlite3
from fastapi.testclient import TestClient
import pytest
from chainguard_gateway.github_policy import repository_hash, configured_check
from chainguard_gateway.github_read import GitHubFailure
from chainguard_gateway.github_reader import create_app

TOKEN='a'*64
HEADERS={'Authorization':'Bearer '+TOKEN}

def test_repository_hash_separates_repositories_and_includes_issue_parent():
    assert repository_hash('microsoft/vscode#1')==repository_hash('microsoft/vscode')
    assert repository_hash('facebook/react#1')!=repository_hash('microsoft/vscode#1')

def test_missing_policy_fails_closed_before_external_request(tmp_path):
    calls=[]
    client=TestClient(create_app(tmp_path,TOKEN,fetcher=lambda query:calls.append(query)))
    result=client.post('/fetch',headers=HEADERS,json={'query':'microsoft/vscode#1'})
    assert result.status_code==503 and result.json()['error']['code']=='GITHUB_POLICY_UNAVAILABLE' and calls==[]
    with sqlite3.connect(tmp_path/'github.sqlite3') as db:assert db.execute('SELECT COUNT(*) FROM fetches').fetchone()[0]==0

def test_local_reader_token_cannot_bypass_chain_deny_and_log_is_persistent(tmp_path):
    calls=[];proof={'allowed':False,'repository':'facebook/react','block_number':'12'}
    client=TestClient(create_app(tmp_path,TOKEN,policy_checker=lambda query:proof,fetcher=lambda query:calls.append(query)))
    response=client.post('/fetch',headers=HEADERS,json={'query':'facebook/react#1'})
    assert response.status_code==403 and response.json()['repository_policy']==proof and calls==[]
    with sqlite3.connect(tmp_path/'github.sqlite3') as db:
        assert db.execute('SELECT COUNT(*) FROM fetches').fetchone()[0]==0
        assert db.execute('SELECT verdict FROM repository_policy_checks').fetchone()[0]=='GITHUB_REPOSITORY_DENIED'

def test_revoke_during_https_retains_original_but_never_releases_it(tmp_path):
    proof={'allowed':True}
    def fetch(query):proof['allowed']=False;return {'fixture':'unreleased'},b'original fixture bytes'
    client=TestClient(create_app(tmp_path,TOKEN,policy_checker=lambda query:dict(proof),fetcher=fetch))
    response=client.post('/fetch',headers=HEADERS,json={'query':'microsoft/vscode#1'})
    assert response.status_code==403 and 'data' not in response.json()
    with sqlite3.connect(tmp_path/'github.sqlite3') as db:
        row=db.execute('SELECT status,raw FROM fetches').fetchone();assert row==('WITHHELD_POLICY',b'original fixture bytes')

def test_tool_without_policy_configuration_fails_closed():
    class Store:
        def private_read(self,name):raise FileNotFoundError(name)
    with pytest.raises(GitHubFailure,match='GITHUB_POLICY_UNAVAILABLE'):configured_check(Store(),'microsoft/vscode#1')

def test_proxy_distinguishes_chain_deny_from_unavailable_and_does_not_retry(tmp_path):
    from chainguard_agent.default_proxy import DefaultToolProxy
    from chainguard_agent.proxy import ToolExecutionProxy
    from chainguard_agent.journal import Journal
    from chainguard_agent.model import ToolCall
    from chainguard_gateway.custom_tools import prepare
    from chainguard_gateway.github_read import FIELDS
    m=prepare(dict(name='custom.github_vscode',label='GitHub',description='Read',adapter='github.read',risk=0,key_field='resource',output_fields=FIELDS,records=[{'resource':'facebook/react#1'}]),1)
    calls=[]
    class Transport:
        def request(self,*args):
            calls.append(args)
            return dict(status='READ_FAILED',error_code='GITHUB_REPOSITORY_DENIED',repository_policy={'allowed':False},read_execution_id='id')
    base=ToolExecutionProxy(Transport(),Journal(tmp_path),'run','0x'+'45'*32,mode='fixed_trace',wait_seconds=0)
    proxy=DefaultToolProxy(base,[m['name']],custom={m['name']:{'manifest':m,'allowed_keys':['facebook/react#1']}})
    call=ToolCall('denied',m['name'],{'query':'facebook/react#1'})
    first=proxy.execute(call);assert first['status']=='DENIED' and first['repository_policy']['allowed'] is False
    assert proxy.execute(call)==first and len(calls)==1

def test_manual_probe_chain_result_does_not_fabricate_local_or_chain_enforcement(tmp_path):
    from types import SimpleNamespace
    import threading
    from chainguard_gateway.phase10_service import Operations
    from chainguard_gateway.phase10_store import OperationsStore
    from chainguard_gateway.crypto import random_id
    store=OperationsStore(tmp_path);id=random_id()
    store.create(id,{'allowed_tools':['custom.github_vscode'],'custom_tools':[dict(name='custom.github_vscode',revision='revision',allowed_keys=['facebook/react#1'])]})
    store.update(id,grant={'task_id':'task'})
    proof={'allowed':False,'enforcement':'ON_CHAIN_REPOSITORY_POLICY'}
    class Bridge:
        def github_fetch_stats(self):return {'total':2,'ok':2}
        def call(self,*args):return {'status':'READ_FAILED','error_code':'GITHUB_REPOSITORY_DENIED','repository_policy':proof}
    ops=SimpleNamespace(store=store,mutex=threading.RLock(),custom_registry=SimpleNamespace(get=lambda rev:{'manifest':{'adapter':'github.read'}}),bridge=Bridge(),github_policy=lambda query:proof)
    result=Operations.github_probe(ops,id,'custom.github_vscode','facebook/react#1')
    assert result['chain_enforced'] and result['no_new_github_fetch'] and result['tool_executed'] is False
    assert store.events(id)[0]['agent_attempted_tool'] is False

@pytest.mark.parametrize('fault',['rpc','code','disagreement'])
def test_independent_node_failure_code_drift_and_state_disagreement_fail_closed(monkeypatch,fault):
    from types import SimpleNamespace
    from chainguard_gateway import github_policy as module
    from chainguard_sandbox.protocol import ToolError
    from eth_utils import keccak
    class Node:
        def __init__(self,index):self.index=index
        def call(self,*args):
            if fault=='rpc' and self.index==1:raise ToolError('CHAIN_UNAVAILABLE')
            return '0x02' if fault=='code' and self.index==1 else '0x01'
    class FakeContract:
        def __init__(self,name,address,node,abi=None):self.node=node
        def call(self,name,args=(),block=None):
            return {'policyRegistry':'policy','epoch':2,'paused':False,'requireRepository':2,'repositoryAllowed':not (fault=='disagreement' and self.node.index==1)}[name]
    monkeypatch.setattr(module,'Contract',FakeContract)
    instance=object.__new__(module.RepositoryPolicy)
    instance.config={'deployment':{'chainId':20261026},'contract':{'address':'registry','codeHash':'0x'+keccak(b'\x01').hex()}}
    instance.chain=SimpleNamespace(healthy=lambda:{'number':'12','hash':'hash'},nodes=[Node(0),Node(1)],policy=SimpleNamespace(address='policy'))
    with pytest.raises(GitHubFailure,match='GITHUB_POLICY_UNAVAILABLE'):instance.check('microsoft/vscode#1')

def test_http_policy_read_and_negative_probe_enforce_session_role_and_csrf(tmp_path):
    from types import SimpleNamespace
    import secrets
    from chainguard_gateway.phase10_api import create_operations_app,password_hash
    from chainguard_gateway.phase10_store import OperationsStore
    store=OperationsStore(tmp_path);calls=[];credentials={}
    for role in ['requester','security']:
        salt=secrets.token_hex(16);credentials[role]=dict(salt=salt,hash=password_hash(role,salt),organization=role)
    ops=SimpleNamespace(store=store,stop=SimpleNamespace(set=lambda:None),github_policy=lambda query:{'allowed':False},github_probe=lambda *args:calls.append(args) or {'status':'DENIED'})
    client=TestClient(create_operations_app(ops,credentials,'http://testserver',start_worker=False))
    assert client.get('/ops/v1/github-policy').status_code==401
    h={'Origin':'http://testserver'}
    s=client.post('/ops/v1/login',headers=h,json={'role':'requester','password':'requester'}).json()
    assert client.get('/ops/v1/github-policy').json()=={'allowed':False}
    path='/ops/v1/tasks/test/github-negative-control';body={'tool_name':'custom.github_vscode','query':'facebook/react#1'}
    assert client.post(path,headers=h,json=body).status_code==403
    h['X-CSRF-Token']=s['csrf'];assert client.post(path,headers=h,json=body).status_code==200 and len(calls)==1
    s=client.post('/ops/v1/login',headers={'Origin':'http://testserver'},json={'role':'security','password':'security'}).json()
    h['X-CSRF-Token']=s['csrf'];assert client.post(path,headers=h,json=body).status_code==403 and len(calls)==1
