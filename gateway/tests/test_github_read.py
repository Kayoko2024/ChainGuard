"""Adapter security/transport unit fixtures, separate from real GitHub acceptance."""
import copy
import hashlib
import io
import json
from email.message import Message
from urllib.error import HTTPError,URLError
import pytest
from fastapi.testclient import TestClient
from chainguard_gateway.github_read import resource,fetch,FIELDS,GitHubFailure
from chainguard_gateway.github_reader import create_app
from chainguard_gateway.custom_tools import prepare,validate_manifest,ToolRegistry,check_grants
from chainguard_gateway.phase10_store import OperationsStore
from chainguard_sandbox.protocol import ToolError

def registration():
    return dict(name='custom.github_lookup',label='GitHub read',description='Read authorized public GitHub repositories or issues.',adapter='github.read',risk=0,key_field='resource',output_fields=FIELDS,records=[{'resource':'psf/requests'},{'resource':'psf/requests#1'}])

@pytest.mark.parametrize('key',['https://github.com/a/b','a/b/../../x','a/b?x=1','a/b%2fissues','a/b#0','a/b#01','a/b#1?x','a/b#1\n','a/b@evil','A/b','127.0.0.1/x','a/b#1000000000','a/b\\x','a/b#1/'])
def test_resources_reject_urls_paths_ambiguous_scopes_and_hosts(key):
    with pytest.raises(ToolError,match='SCHEMA_INVALID'):resource(key)

def test_manifest_scope_and_original_snapshot_manifest_validation(tmp_path):
    v=registration();m=prepare(v,1);validate_manifest(m,v['records'])
    assert m['output_schema']['properties']['source']['required']
    for change in [{'risk':2},{'key_field':'repo'},{'output_fields':['resource']},{'records':[{'resource':'a/b','body':'ignored'}]},{'adapter':[]}]:
        with pytest.raises(ToolError):prepare(dict(v,**change),1)
    registry=ToolRegistry(OperationsStore(tmp_path));item=registry.create(v);rev=item['manifest']['revision'];registry.state(rev,'ACTIVE')
    g=dict(name=v['name'],revision=rev,allowed_keys=['psf/requests#1'])
    assert check_grants([g],[v['name']],registry.get)
    with pytest.raises(ToolError,match='UNAUTHORIZED_SCOPE'):check_grants([dict(g,allowed_keys=['other/repo'])],[v['name']],registry.get)

def repo():return dict(full_name='psf/requests',private=False,html_url='https://github.com/psf/requests',description='fixture only',updated_at='2026-10-28T01:00:00Z',stargazers_count=1,open_issues_count=2)
class Response(io.BytesIO):
    status=200
    def __init__(self,value):
        super().__init__(json.dumps(value).encode());self.headers=Message();self.headers['Content-Type']='application/json';self.headers['X-GitHub-Request-Id']='unit-fixture'
class Opener:
    def __init__(self,value):self.value=value;self.requests=[]
    def open(self,request,timeout):
        self.requests.append(request)
        if isinstance(self.value,Exception):raise self.value
        return Response(self.value)
def test_only_fixed_https_get_and_bounded_projection_with_raw_digest():
    opener=Opener(repo());data,raw=fetch('psf/requests',opener=opener)
    request=opener.requests[0];assert request.method=='GET' and request.full_url=='https://api.github.com/repos/psf/requests'
    assert not request.has_header('Authorization') and data['source']['response_sha256']==hashlib.sha256(raw).hexdigest()
    assert data['record']['stars']==1 and data['record']['repository']=='psf/requests'
    issue=dict(html_url='https://github.com/psf/requests/issues/1',number=1,title='fixture',state='closed',body='x'*5000)
    data,_=fetch('psf/requests#1',opener=Opener(issue));assert len(data['record']['body'])==4000
@pytest.mark.parametrize('change',[{'private':True},{'html_url':'https://evil.test/a'},{'full_name':'different/repo'},{'stargazers_count':True}])
def test_wrong_or_private_repository_is_never_returned(change):
    with pytest.raises(GitHubFailure):fetch('psf/requests',opener=Opener(dict(repo(),**change)))
def test_pr_not_accepted_as_issue_and_redirects_rate_limits_network_errors_explicit():
    with pytest.raises(GitHubFailure,match='GITHUB_RESOURCE_MISMATCH'):fetch('psf/requests#1',opener=Opener(dict(repo(),pull_request={})))
    h=Message();h['X-RateLimit-Remaining']='0'
    for error,code in [(HTTPError('url',403,'limited',h,None),'GITHUB_RATE_LIMITED'),(HTTPError('url',301,'redirect',Message(),None),'GITHUB_REDIRECT_REJECTED'),(HTTPError('url',404,'missing',Message(),None),'GITHUB_NOT_FOUND'),(URLError('offline'),'GITHUB_UNAVAILABLE')]:
        with pytest.raises(GitHubFailure,match=code):fetch('psf/requests',opener=Opener(error))
def test_reader_auth_schema_and_durable_real_transport_record_boundary(tmp_path):
    calls=[]
    def fixture(query):calls.append(query);return fetch(query,opener=Opener(repo()))
    client=TestClient(create_app(tmp_path,'a'*64,fetcher=fixture,policy_checker=lambda query:{'allowed':True}));h={'Authorization':'Bearer '+'a'*64}
    assert client.post('/fetch',json={'query':'psf/requests'}).status_code==401
    assert client.post('/fetch',headers=h,json={'query':'https://evil.test'}).status_code==422
    assert client.post('/fetch',headers=h,json={'query':'psf/requests','method':'POST'}).status_code==422
    assert client.get('/fetch',headers=h).status_code==405
    response=client.post('/fetch',headers=h,json={'query':'psf/requests'});assert response.status_code==200 and calls==['psf/requests']
    import sqlite3
    with sqlite3.connect(tmp_path/'github.sqlite3') as db:
        row=db.execute('SELECT status,data,raw FROM fetches').fetchone();assert row[0]=='OK';assert json.loads(row[1])['source']['response_sha256']==hashlib.sha256(row[2]).hexdigest()

def test_agent_proxy_preserves_real_reader_failure_as_unknown(tmp_path):
    from chainguard_agent.default_proxy import DefaultToolProxy
    from chainguard_agent.proxy import ToolExecutionProxy
    from chainguard_agent.journal import Journal
    from chainguard_agent.model import ToolCall
    class Transport:
        def request(self,*args):return {'status':'READ_FAILED','error_code':'GITHUB_RATE_LIMITED','read_execution_id':'0x'+'12'*32}
    m=prepare(registration(),1);base=ToolExecutionProxy(Transport(),Journal(tmp_path),'run','0x'+'45'*32,mode='fixed_trace',wait_seconds=0)
    result=DefaultToolProxy(base,[m['name']],custom={m['name']:{'manifest':m,'allowed_keys':['psf/requests']}}).execute(ToolCall('read_one',m['name'],{'query':'psf/requests'}))
    assert result['status']=='UNKNOWN' and result['error_code']=='GITHUB_RATE_LIMITED'
