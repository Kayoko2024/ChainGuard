"""Registration/admission/scope fixtures; not real model or chain evidence."""
import copy
import hashlib
import time
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from chainguard_gateway.canonical import canonical
from chainguard_gateway.custom_tools import prepare,validate_manifest,ToolRegistry,check_grants,function
from chainguard_gateway.phase10_store import OperationsStore
from chainguard_gateway.phase10_service import Operations
from chainguard_gateway.phase10_api import create_operations_app
from chainguard_sandbox.protocol import ToolError
from chainguard_agent.default_proxy import DefaultToolProxy
from chainguard_agent.proxy import ToolExecutionProxy
from chainguard_agent.journal import Journal
from chainguard_agent.model import ToolCall

def sample():
    return dict(name='custom.project_lookup',label='Project lookup',description='Lookup authorized project keys.',
        adapter='dataset.lookup',risk=0,key_field='project_id',output_fields=['project_id','owner'],
        records=[{'project_id':'P1','owner':'PRIVATE_ALICE','secret':'not exported'},{'project_id':'P2','owner':'Bob','secret':'other'}])

@pytest.mark.parametrize('example_id',['contacts','inventory'])
def test_frontend_examples_pass_real_registration_schema_and_resource_grants(tmp_path,example_id):
    import json
    from pathlib import Path
    examples=json.loads((Path(__file__).resolve().parents[2]/'console/src/custom-tool-examples.json').read_text(encoding='utf8'))
    value=next(e['registration'] for e in examples if e['id']==example_id)
    registry=ToolRegistry(OperationsStore(tmp_path));item=registry.create(value);manifest=item['manifest']
    validate_manifest(manifest,value['records']);assert item['state']=='DRAFT'
    assert manifest['risk']==0 and manifest['adapter']=='dataset.lookup'
    keys=[r[value['key_field']] for r in value['records']]
    grant=dict(name=value['name'],revision=manifest['revision'],allowed_keys=keys[:1])
    with pytest.raises(ToolError,match='POLICY_REVOKED'):check_grants([grant],[value['name']],registry.get)
    registry.state(manifest['revision'],'ACTIVE')
    assert check_grants([grant],[value['name']],registry.get)[value['name']]['allowed_keys']==keys[:1]
    with pytest.raises(ToolError,match='UNAUTHORIZED_SCOPE'):check_grants([dict(grant,allowed_keys=['unlisted-record'])],[value['name']],registry.get)
    schema=manifest['output_schema']['properties']['record']['properties']
    if example_id=='inventory':assert schema['quantity']['type']==schema['reorder_level']['type']=='integer'

def test_manifest_commits_data_schema_version_and_no_implicit_mutation():
    value=sample(); manifest=prepare(value,1)
    assert manifest==prepare(value,1) and manifest['revision']!=prepare(value,2)['revision']
    changed=copy.deepcopy(value);changed['records'][0]['owner']='different'
    assert prepare(changed,1)['revision']!=manifest['revision']
    assert function(manifest,['P1'])['function']['name']=='custom_project_lookup'
    validate_manifest(manifest,value['records'])
    with pytest.raises(ToolError): validate_manifest(manifest,changed['records'])
    assert 'secret' not in manifest['output_schema']['properties']['record']['properties']

@pytest.mark.parametrize('change',[
    {'name':'mail.send'},{'name':'custom.x;exec'},{'adapter':'http.request'},{'risk':2},{'risk':False},
    {'records':[]},{'records':[{'project_id':'P1','owner':1},{'project_id':'P2','owner':'s'}]},
    {'records':[{'project_id':'P1','owner':'a'},{'project_id':'P1','owner':'b'}]},
    {'records':[{'project_id':'P1','owner':{'code':'x'}}]}, {'output_fields':['missing']},
    {'records':[{'project_id':'P1','owner':'a'},{'project_id':'P2'}]}, {'output_fields':['project_id','project_id']},
    {'url':'http://example.com'},{'description':''},
])
def test_unsafe_or_malformed_registration_is_rejected(change):
    with pytest.raises(ToolError): prepare(dict(sample(),**change),1)

def test_encrypted_registry_versions_scope_and_no_auto_upgrade(tmp_path):
    store=OperationsStore(tmp_path);registry=ToolRegistry(store)
    one=registry.create(sample());two=registry.create(sample())
    assert one['state']=='DRAFT' and two['manifest']['version']==2
    assert b'PRIVATE_ALICE' not in (tmp_path/'operations.sqlite3').read_bytes()
    m=one['manifest'];g={'name':m['name'],'revision':m['revision'],'allowed_keys':['P1']}
    with pytest.raises(ToolError,match='POLICY_REVOKED'):check_grants([g],[m['name']],registry.get)
    registry.state(m['revision'],'ACTIVE')
    assert check_grants([g],[m['name']],registry.get)[m['name']]['manifest']['version']==1
    for grants,selected in [([dict(g,allowed_keys=['P2','BAD'])],[m['name']]),([], [m['name']]),([g],[]),([g,g],[m['name']])]:
        with pytest.raises(ToolError):check_grants(grants,selected,registry.get)
    registry.state(m['revision'],'DISABLED')
    assert ToolRegistry(OperationsStore(tmp_path)).get(m['revision'])['state']=='DISABLED'

def test_custom_task_persistence_cannot_change_revision_or_keys_under_same_id(tmp_path):
    store=OperationsStore(tmp_path);registry=ToolRegistry(store);item=registry.create(sample());m=item['manifest'];registry.state(m['revision'],'ACTIVE')
    ops=SimpleNamespace(store=store,custom_registry=registry,detail=store.get)
    body=dict(task_text='Lookup P1',allowed_tools=[m['name']],allowed_document_ids=[],read_mailboxes=[],allowed_recipients=[],
        custom_tools=[dict(name=m['name'],revision=m['revision'],allowed_keys=['P1'])])
    id='0x'+'14'*32;Operations.create(ops,id,body)
    assert store.get(id)['custom_tools']==body['custom_tools']
    changed=copy.deepcopy(body);changed['custom_tools'][0]['allowed_keys']=['P2']
    with pytest.raises(ToolError,match='IDEMPOTENCY_CONFLICT'):Operations.create(ops,id,changed)
    registry.state(m['revision'],'DISABLED')
    with pytest.raises(ToolError,match='POLICY_REVOKED'):Operations.create(ops,'0x'+'15'*32,body)

def test_custom_api_role_csrf_revision_and_admission(tmp_path):
    store=OperationsStore(tmp_path);registry=ToolRegistry(store);calls=[]
    class Ops:
        custom_registry=registry;stop=SimpleNamespace(set=lambda:None)
        def __init__(self):self.store=store
        def register_custom(self,value):return Operations.register_custom(self,value)
        def custom_descriptor(self,item):return Operations.custom_descriptor(item)
        def review_custom(self,revision):return registry.get(revision)
        def set_custom_active(self,revision,expected,enabled):
            if revision!=expected:raise ToolError('PARAMS_MISMATCH')
            calls.append((revision,enabled));registry.state(revision,'ACTIVE' if enabled else 'DISABLED');return {}
        def tool_catalog(self):return {'tools':[]}
    ops=Ops();ops.mutex=__import__('threading').RLock()
    origin='http://127.0.0.1:8090';client=TestClient(create_operations_app(ops,{},origin,start_worker=False))
    assert client.get('/ops/v1/custom-tools').status_code==401
    def role(name):
        token,csrf=store.login(name);client.cookies.set('cg_session',token);return {'Origin':origin,'X-CSRF-Token':csrf}
    h=role('requester');created=client.post('/ops/v1/custom-tools',headers=h,json=sample())
    assert created.status_code==201;revision=created.json()['revision']
    url=f'/ops/v1/custom-tools/{revision}/activation'
    assert client.post(url,headers=h,json={'revision':revision,'enabled':True}).status_code==403
    h=role('biz');assert client.post(url,headers=h,json={'revision':revision,'enabled':True}).status_code==403
    h=role('security')
    assert client.post('/ops/v1/custom-tools',headers=h,json=sample()).status_code==403
    assert client.post(url,headers={'Origin':origin},json={'revision':revision,'enabled':True}).status_code==403
    assert client.post(url,headers=h,json={'revision':'0x'+'ff'*32,'enabled':True}).status_code==422
    assert client.post(url,headers=h,json={'revision':revision,'enabled':1}).status_code==422
    assert calls==[]
    assert client.post(url,headers=h,json={'revision':revision,'enabled':True}).status_code==200
    assert client.get(f'/ops/v1/custom-tools/{revision}').json()['state']=='ACTIVE'
    assert len(calls)==1

def test_activation_failures_remain_pending_and_revocation_cannot_be_undone(tmp_path):
    registry=ToolRegistry(OperationsStore(tmp_path));m=registry.create(sample())['manifest']
    class Bridge:
        def install_custom(self,value):raise ToolError('CHAIN_UNAVAILABLE')
        def disable_custom(self,value):return {'revision':m['revision'],'active':False}
    ops=SimpleNamespace(custom_registry=registry,mutex=__import__('threading').RLock(),bridge=Bridge())
    with pytest.raises(ToolError,match='CHAIN_UNAVAILABLE'):Operations.set_custom_active(ops,m['revision'],m['revision'],True)
    assert registry.get(m['revision'])['state']=='ENABLING'
    Operations.set_custom_active(ops,m['revision'],m['revision'],False)
    with pytest.raises(ToolError,match='POLICY_REVOKED'):Operations.set_custom_active(ops,m['revision'],m['revision'],True)

def test_custom_proxy_checks_output_and_retains_untrusted_read(tmp_path):
    m=prepare(sample(),1);requests=[];data={'record':{'project_id':'P1','owner':'PRIVATE_ALICE'}}
    def request(method,path,value,key):
        requests.append((path,value));return dict(tool_name=m['name'],revision=m['revision'],trust='untrusted',data=data,sha256=hashlib.sha256(canonical(data)).hexdigest(),read_execution_id='0x'+'33'*32)
    journal=Journal(tmp_path);proxy=DefaultToolProxy(ToolExecutionProxy(SimpleNamespace(request=request),journal,'run','0x'+'22'*32),[m['name']],custom={m['name']:{'manifest':m,'allowed_keys':['P1']}})
    call=ToolCall('a',m['name'],{'query':'P1'});assert proxy.execute(call)['trust']=='untrusted'
    assert proxy.execute(call)['data']==data and len(requests)==1
    assert requests[0][0]=='/agent/v1/custom-tools/query' and requests[0][1]['revision']==m['revision']
    data['record']['extra']='not in admitted schema'
    assert proxy.execute(ToolCall('b',m['name'],{'query':'P1'}))['status']=='UNKNOWN'
    assert proxy.execute(ToolCall('c',m['name'],{'query':'P1','url':'https://x'}))['status']=='DENIED'

@pytest.mark.parametrize('state,expected',[('valid',200),('revoked',403),('expired',409),('other_agent',403),('inactive',403)])
def test_custom_query_gateway_rechecks_task_role_revocation_and_expiry(state,expected):
    import contextlib
    from chainguard_gateway.phase7_server import gateway_extensions
    from chainguard_gateway.identity import issue_token
    agent='0x'+'42'*20;task='0x'+'41'*32;jwt=b'x'*32;calls=[]
    class Store:
        def private(self,name):return jwt
        @contextlib.contextmanager
        def connect(self):yield None
        def task(self,db,id):return {'revoked':state=='revoked'},{'agent':agent if state!='other_agent' else '0x'+'43'*20,'expires_at':'1' if state=='expired' else str(int(time.time())+60)}
    service=SimpleNamespace(store=Store(),current_actor=lambda subject:dict(address=agent,roles=['AGENT'],active=state!='inactive'),tool_client=SimpleNamespace(request=lambda *a:calls.append(a) or {'read':True}))
    client=TestClient(gateway_extensions(service,dict(authority_fingerprint='fixed',authority_token='fixed',operator_fingerprint='fixed')))
    body=dict(task_id=task,tool_name='custom.project_lookup',revision='0x'+'44'*32,arguments={'query':'P1'})
    h={'Authorization':'Bearer '+issue_token(jwt,'agent',60),'Idempotency-Key':task}
    response=client.post('/agent/v1/custom-tools/query',headers=h,json=body)
    assert response.status_code==expected,response.json()
    assert len(calls)==(1 if state=='valid' else 0)
    assert client.post('/agent/v1/custom-tools/query',json=body).status_code==401

def test_internal_custom_query_requires_both_certificate_and_service_token(monkeypatch):
    from chainguard_gateway import phase7_server as module
    for name in ['ReadBroker','DefaultLibrary','CustomLibrary']:monkeypatch.setattr(module,name,lambda store:None)
    app=module.tool_extensions(None,None,dict(gateway_fingerprint='expected',gateway_token='token'))
    client=TestClient(app)
    assert client.post('/internal/v1/custom-tools/query',json={}).status_code==401
    assert client.post('/internal/v1/custom-tools/query',headers={'Authorization':'Bearer token'},json={}).status_code==401

def test_custom_read_observation_never_overrides_real_high_risk_verifier(monkeypatch):
    from chainguard_gateway import phase10_audit as module
    row=dict(tool='custom.project_lookup',risk=0,state='READ_COMPLETED')
    assert module.verify_live_entry(None,row)['status']=='READ_ONLY_OBSERVATION'
    monkeypatch.setattr(module,'verify_action',lambda *args:{'status':'INVALID'})
    assert module.verify_live_entry(None,dict(row,intent={'params_commit':'untrusted'}))['status']=='INVALID'
