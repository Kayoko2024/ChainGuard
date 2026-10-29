"""Document contract tests. Fake worker fixtures here are not live file/LLM evidence."""
import base64
import hashlib
import secrets
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from chainguard_gateway.document_tools import DocumentLibrary,DocumentProxy,DocumentSandbox,check_scope,functions
from chainguard_gateway.phase10_store import OperationsStore
from chainguard_gateway.phase10_api import create_operations_app
from chainguard_agent.model import ToolCall,ALIASES
from chainguard_sandbox.protocol import ToolError

ID='0x'+'12'*32
TASK='0x'+'34'*32
OTHER='0x'+'56'*32
PDF_ID='0x'+'78'*32
ORIGIN='http://127.0.0.1:8090'

@pytest.fixture
def library(tmp_path):
    calls=[]
    def worker(value):
        calls.append(value)
        if value['op']=='extract':return {'units':[{'locator':'line:1','text':'fixture'}]}
        if value['tool']=='attachment.read':return {'source_id':ID,'units':[{'locator':'line:1','text':'fixture'}]}
        raw=b'generated fixture bytes';return {'content_base64':base64.b64encode(raw).decode(),'sha256':hashlib.sha256(raw).hexdigest(),'note':'unit fixture','replacements':1}
    store=OperationsStore(tmp_path);doc=DocumentLibrary(store,worker);doc.upload(ID,'source.txt',b'private original')
    store.create(TASK,{'task_text':'unit fixture','document_scope':{'attachment_ids':[ID],'allow_create':True},'grant':{'expires_at':str(int(time.time())+60)}})
    store.update(TASK,state='AGENT_RUNNING')
    return doc,calls

def test_encrypted_upload_idempotency_name_limits_and_no_path(library):
    doc,calls=library
    assert doc.upload(ID,'source.txt',b'private original')['id']==ID and len(calls)==1
    assert b'private original' not in (doc.store.root/'operations.sqlite3').read_bytes()
    with pytest.raises(ToolError,match='IDEMPOTENCY_CONFLICT'):doc.upload(ID,'source.txt',b'changed')
    for name,raw,code in [('../secret.txt',b'x','FILENAME'),('C:\\secret.txt',b'x','FILENAME'),('a.exe',b'x','FORMAT'),('a.txt',b'','LIMIT'),('a.txt',b'x'*(5*1024*1024+1),'LIMIT')]:
        with pytest.raises(ToolError,match=code):doc.upload(OTHER,name,raw)
    assert len(calls)==1

def test_bound_scope_copy_only_persistence_and_replay(library):
    doc,calls=library
    call=ToolCall('edit','document.revise',{'source_id':ID,'title':'Revised','format':'docx','find':'a','replace':'b'})
    result=doc.execute(TASK,call);assert result['trust']=='untrusted'
    assert doc.execute(TASK,call)==result and len(calls)==2
    assert doc.get(ID)['sha256']==hashlib.sha256(b'private original').hexdigest()
    assert doc.files_for(doc.store.get(TASK))['artifacts'][0]['id']==result['data']['id']
    restored=DocumentLibrary(OperationsStore(doc.store.root),lambda _:pytest.fail('must not execute'))
    assert restored.execute(TASK,call)==result
    with pytest.raises(ToolError,match='IDEMPOTENCY_CONFLICT'):doc.execute(TASK,ToolCall('edit',call.name,dict(call.arguments,replace='different')))
    with pytest.raises(ToolError,match='UNAUTHORIZED_SCOPE'):doc.execute(TASK,ToolCall('leak','attachment.read',{'source_id':OTHER,'start':0,'limit':1}))
    doc.store.update(TASK,document_scope={'attachment_ids':[ID],'allow_create':False})
    with pytest.raises(ToolError,match='UNAUTHORIZED_SCOPE'):doc.execute(TASK,call)
    doc.store.update(TASK,grant={'expires_at':'1'})
    with pytest.raises(ToolError,match='DOCUMENT_AUTH_EXPIRED'):doc.execute(TASK,ToolCall('read','attachment.read',{'source_id':ID,'start':0,'limit':1}))
    assert len(calls)==2

def test_scope_and_model_aliases_reject_unbounded_or_extra_parameters(library):
    doc,calls=library
    for scope in [{'attachment_ids':[ID,ID],'allow_create':True},{'attachment_ids':['../file'],'allow_create':False},{'attachment_ids':[],'allow_create':'true'}]:
        with pytest.raises(ToolError):check_scope(scope,doc.get)
    for args in [{'source_id':ID,'start':-1,'limit':1},{'source_id':ID,'start':0,'limit':99},{'source_id':ID,'start':0,'limit':1,'path':'/etc'}]:
        with pytest.raises(ToolError,match='SCHEMA_INVALID'):doc.execute(TASK,ToolCall('bad','attachment.read',args))
    assert len(functions({'attachment_ids':[ID],'allow_create':False}))==1
    assert ALIASES['document_create']=='document.create'
    with pytest.raises(ToolError,match='UNAVAILABLE'):DocumentSandbox('mutable:tag')
    original=SimpleNamespace(execute=lambda c:dict(original_mail_gateway=True))
    assert DocumentProxy(original,doc,TASK).execute(ToolCall('mail','mail.send',{}))=={'original_mail_gateway':True}

def test_document_api_auth_csrf_raw_upload_and_task_download_scope(library):
    doc,calls=library;store=doc.store
    ops=SimpleNamespace(store=store,documents=doc,stop=SimpleNamespace(set=lambda:None))
    client=TestClient(create_operations_app(ops,{},ORIGIN,start_worker=False))
    path='/ops/v1/attachments?name=source.txt'
    assert client.post(path,headers={'Origin':ORIGIN},content=b'x').status_code==401
    token,csrf=store.login('biz');client.cookies.set('cg_session',token)
    headers={'Origin':ORIGIN,'X-CSRF-Token':csrf,'Content-Type':'application/octet-stream','Idempotency-Key':OTHER}
    assert client.post(path,headers=headers,content=b'x').status_code==403
    token,csrf=store.login('requester');client.cookies.set('cg_session',token);headers['X-CSRF-Token']=csrf
    assert client.post(path,headers={k:v for k,v in headers.items() if k!='X-CSRF-Token'},content=b'x').status_code==403
    assert client.post(path,headers=headers,content=b'x').status_code==201
    pdf_path='/ops/v1/attachments?name=report.pdf'
    pdf_headers={'Origin':ORIGIN,'X-CSRF-Token':csrf,'Content-Type':'application/pdf','Idempotency-Key':PDF_ID}
    pdf=client.post(pdf_path,headers=pdf_headers,content=b'%PDF-1.7\nfixture')
    assert pdf.status_code==201 and pdf.json()['extension']=='pdf'
    wrong=client.post('/ops/v1/attachments?name=wrong.pdf',headers={**pdf_headers,'Idempotency-Key':'0x'+'9a'*32,'Content-Type':'text/plain'},content=b'%PDF-1.7\nfixture')
    assert wrong.status_code==422 and wrong.json()['error']['code']=='SCHEMA_INVALID'
    download=client.get(f'/ops/v1/tasks/{TASK}/documents/{ID}')
    assert download.status_code==200 and download.content==b'private original'
    assert download.headers['content-disposition'].startswith('attachment;')
    assert client.get(f'/ops/v1/tasks/{TASK}/documents/{OTHER}').status_code==403

def test_document_audit_observation_never_claims_chain_authentication(monkeypatch):
    from chainguard_gateway import phase10_audit as module
    monkeypatch.setattr(module,'verify_action',lambda *a:{'status':'INVALID'})
    row={'tool':'document.create','risk':1,'state':'DOCUMENT_COMPLETED'}
    result=module.verify_live_entry(None,row)
    assert result['status']=='LOCAL_DOCUMENT_OBSERVATION' and result['transactions']==[] and result['current_chain_state'] is None
    assert module.verify_live_entry(None,dict(row,intent={'params_commit':'incomplete high-risk record'}))['status']=='INVALID'

def test_create_freezes_attachment_and_output_permissions_without_send_scope(library):
    from chainguard_gateway.phase10_service import Operations
    doc,calls=library
    ops=SimpleNamespace(store=doc.store,documents=doc,detail=lambda id:doc.store.get(id))
    value={'task_text':'Create a summary','allowed_tools':[],'allowed_document_ids':[],'read_mailboxes':[],'allowed_recipients':[],
        'document_scope':{'attachment_ids':[ID],'allow_create':True}}
    result=Operations.create(ops,OTHER,value)
    assert result['document_scope']==value['document_scope'] and result['allowed_recipients']==[]
    with pytest.raises(ToolError,match='IDEMPOTENCY_CONFLICT'):Operations.create(ops,OTHER,dict(value,document_scope={'attachment_ids':[ID],'allow_create':False}))
    with pytest.raises(ToolError,match='POLICY_DENY'):Operations.create(ops,ID,dict(value,document_scope={'attachment_ids':[],'allow_create':False}))


@pytest.mark.parametrize('scope,expected',[
    (None,4096),
    ({'attachment_ids':[],'allow_create':False},4096),
    ({'attachment_ids':[ID],'allow_create':False},8192),
    ({'attachment_ids':[],'allow_create':True},8192),
])
def test_interactive_document_budget_does_not_change_experiment_or_tool_scope(scope,expected):
    import json
    from pathlib import Path
    from chainguard_gateway.phase10_service import interactive_model_config
    root=Path(__file__).resolve().parents[2]
    job={'document_scope':scope};before=json.dumps(job)
    config=interactive_model_config(root,job)
    assert config['parameters']['max_tokens']==expected
    assert config['parameters']['temperature']==0 and config['parameters']['thinking']=={'type':'disabled'}
    assert config['version']=='chainguard-interactive-3'
    assert json.dumps(job)==before
    assert json.loads((root/'evaluation/live_plan.json').read_text())['parameters']['max_tokens']==512


def test_paused_run_keeps_recorded_model_parameters_while_new_turn_uses_new_budget():
    from pathlib import Path
    from chainguard_gateway.phase10_service import interactive_model_config
    root=Path(__file__).resolve().parents[2]
    old={'version':'chainguard-interactive-2','name':'deepseek-flash','parameters':{'max_tokens':512}}
    job={'model_config':old}
    pinned=interactive_model_config(root,job)
    assert pinned==old
    pinned['parameters']['max_tokens']=1
    assert job['model_config']['parameters']['max_tokens']==512
    assert interactive_model_config(root,{})['parameters']['max_tokens']==4096
