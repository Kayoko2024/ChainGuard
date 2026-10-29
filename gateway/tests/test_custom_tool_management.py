"""Import previews and immutable revision management; fixtures are not LLM evidence."""
import copy
import json
from types import SimpleNamespace
import threading
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient
from chainguard_gateway.custom_tool_import import preview
from chainguard_gateway.custom_tools import ToolRegistry,check_grants
from chainguard_gateway.phase10_store import OperationsStore
from chainguard_gateway.phase10_api import create_operations_app
from chainguard_gateway.phase10_service import Operations
from chainguard_sandbox.protocol import ToolError

def registration():
    return dict(name='custom.inventory_lookup',label='Inventory',description='Exact authorized stock query',adapter='dataset.lookup',risk=0,key_field='sku',output_fields=['sku','quantity'],records=[{'sku':'001','quantity':2},{'sku':'002','quantity':12}])

def test_csv_preserves_identifiers_quoted_content_and_explicit_integer_boolean_types():
    result=preview(dict(format='csv',content='\ufeffsku,name,quantity,enabled\r\n001,"Keyboard, test",2,true\r\n002,"Line one\nline two",12,false\r\n',column_types={'quantity':'integer','enabled':'boolean'}))
    assert result['persisted'] is False and result['row_count']==2
    assert result['records']==[dict(sku='001',name='Keyboard, test',quantity=2,enabled=True),dict(sku='002',name='Line one\nline two',quantity=12,enabled=False)]
    assert preview(dict(format='csv',content='sku,quantity\n001,2',column_types={}))['records'][0]['quantity']=='2'

def test_json_preserves_numeric_types_and_rejects_duplicate_keys():
    data=registration()['records'];assert preview(dict(format='json',content=json.dumps(data),column_types={}))['records']==data
    with pytest.raises(ToolError):preview(dict(format='json',content='[{"sku":"001","sku":"002"}]',column_types={}))

@pytest.mark.parametrize('value',[
    dict(format=[],content='x',column_types={}),dict(format='csv',content='x\n1',column_types={'x':[]}),
    dict(format='csv',content='x,x\n1,2',column_types={}),dict(format='csv',content='x,y\n1',column_types={}),
    dict(format='csv',content='sku,q\n001,02',column_types={'q':'integer'}),
    dict(format='csv',content='x\nYES',column_types={'x':'boolean'}),
    dict(format='csv',content='x\n"unterminated',column_types={}),
    dict(format='csv',content='x\n1',column_types={'missing':'string'}),
    dict(format='json',content='[{"x":1},{"x":"1"}]',column_types={}),
    dict(format='json',content='[{"x":1.5}]',column_types={}),
    dict(format='json',content='[{"x":null}]',column_types={}),
    dict(format='json',content='[]',column_types={}),
    dict(format='json',content='[{"x":"x"}]',column_types={'x':'string'}),
    dict(format='json',content=json.dumps([{'x':'v'}]*201),column_types={}),
    dict(format='csv',content='x\n'+'x'*501,column_types={}),
    dict(format='csv',content='x\n'+'a'*65536,column_types={}),
])
def test_import_rejects_ambiguous_malformed_nested_or_oversized_data(value):
    with pytest.raises(ToolError,match='SCHEMA_INVALID'):preview(value)

def test_versions_are_immutable_idempotent_linked_and_require_new_admission(tmp_path):
    store=OperationsStore(tmp_path);registry=ToolRegistry(store);one=registry.create(registration())
    old=copy.deepcopy(one['manifest']);registry.state(old['revision'],'ACTIVE')
    changed=registration();changed['records'][0]['quantity']=7;changed['records'].pop();changed['records'].append({'sku':'003','quantity':3})
    two=registry.create(changed,old['revision'],'0x'+'a1'*32);new=two['manifest']
    assert new['version']==2 and new['revision']!=old['revision'] and two['state']=='DRAFT'
    assert registry.get(old['revision'])['manifest']==old and registry.get(old['revision'])['records'][0]['quantity']==2
    assert registry.create(changed,old['revision'],'0x'+'a1'*32)['manifest']==new and len(registry.listing())==2
    with pytest.raises(ToolError,match='IDEMPOTENCY_CONFLICT'):registry.create(registration(),old['revision'],'0x'+'a1'*32)
    with pytest.raises(ToolError,match='STATE_CONFLICT'):registry.create(changed,old['revision'])
    with pytest.raises(ToolError,match='PARAMS_MISMATCH'):registry.create(dict(changed,name='custom.renamed_tool'),new['revision'])
    reviewed=registry.review(new['revision'])
    assert reviewed['parent_revision']==old['revision']
    assert reviewed['changes']['changed_keys']==['001'] and reviewed['changes']['removed_keys']==['002'] and reviewed['changes']['added_keys']==['003']
    assert reviewed['history'][0]['kind']=='REGISTERED' and reviewed['history'][0]['recorded_at_utc']
    for rev,allowed in [(old['revision'],True),(new['revision'],False)]:
        g=dict(name=old['name'],revision=rev,allowed_keys=['001'])
        if allowed:assert check_grants([g],[old['name']],registry.get)
        else:
            with pytest.raises(ToolError,match='POLICY_REVOKED'):check_grants([g],[old['name']],registry.get)
    assert len(ToolRegistry(OperationsStore(tmp_path)).review(new['revision'])['history'])==1

def test_concurrent_updates_reject_stale_parent_and_keep_private_rows_encrypted(tmp_path):
    store=OperationsStore(tmp_path);registry=ToolRegistry(store)
    one=registry.create(registration())['manifest']['revision']
    def submit(quantity):
        changed=registration();changed['records'][0]['quantity']=quantity
        try:return ToolRegistry(store).create(changed,one)['manifest']['version']
        except ToolError as error:return error.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(submit,[21,22]),key=str)==[2,'STATE_CONFLICT']
    with store.db() as db:
        rows=db.execute('SELECT data FROM custom_tools').fetchall()
        assert len(rows)==2 and all(b'"quantity"' not in row[0] for row in rows)

def test_import_formula_like_text_is_kept_as_data_and_invalid_json_is_rejected():
    result=preview(dict(format='csv',content='id,note\n001,=SOME_FUNCTION(1)',column_types={}))
    assert result['records'][0]=={'id':'001','note':'=SOME_FUNCTION(1)'}
    for content in ['{"id":"001"}','[{"id":"001"', '[{"id":"001","nested":{"x":1}}]']:
        with pytest.raises(ToolError,match='SCHEMA_INVALID'):
            preview(dict(format='json',content=content,column_types={}))

def test_import_and_version_apis_enforce_role_csrf_and_do_not_register_preview(tmp_path):
    store=OperationsStore(tmp_path);registry=ToolRegistry(store)
    ops=SimpleNamespace(store=store,custom_registry=registry,mutex=threading.RLock(),stop=SimpleNamespace(set=lambda:None),custom_descriptor=Operations.custom_descriptor)
    ops.register_custom=lambda value,key=None:Operations.register_custom(ops,value,key)
    ops.version_custom=lambda rev,value,key=None:Operations.version_custom(ops,rev,value,key)
    ops.review_custom=registry.review
    origin='http://127.0.0.1:8090';client=TestClient(create_operations_app(ops,{},origin,start_worker=False))
    def role(name):
        token,csrf=store.login(name);client.cookies.set('cg_session',token);return {'Origin':origin,'X-CSRF-Token':csrf}
    value=dict(format='csv',content='sku,quantity\n001,2',column_types={'quantity':'integer'})
    assert client.post('/ops/v1/custom-tools/import-preview',headers={'Origin':origin},json=value).status_code==401
    h=role('security');assert client.post('/ops/v1/custom-tools/import-preview',headers=h,json=value).status_code==403
    h=role('requester');assert client.post('/ops/v1/custom-tools/import-preview',headers={'Origin':origin},json=value).status_code==403
    response=client.post('/ops/v1/custom-tools/import-preview',headers=h,json=value)
    assert response.status_code==200 and response.json()['persisted'] is False and registry.listing()==[]
    h['Idempotency-Key']='0x'+'a2'*32
    one=client.post('/ops/v1/custom-tools',headers=h,json=registration()).json();revision=one['revision']
    assert client.post('/ops/v1/custom-tools',headers=h,json=registration()).json()['revision']==revision and len(registry.listing())==1
    headers={**h,'Idempotency-Key':'0x'+'a3'*32};changed=registration();changed['records'][0]['quantity']=7
    two=client.post(f'/ops/v1/custom-tools/{revision}/versions',headers=headers,json=changed)
    assert two.status_code==201 and two.json()['version']==2
    assert client.get('/ops/v1/custom-tools/'+two.json()['revision']).json()['changes']['changed_keys']==['001']
    h=role('biz');assert client.post(f'/ops/v1/custom-tools/{revision}/versions',headers=h,json=changed).status_code==403
