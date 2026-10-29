"""Independent localhost business UI/API. Browser sessions never contain service credentials."""
import argparse
from contextlib import asynccontextmanager
import hashlib
import json
from pathlib import Path
import secrets
import threading
import time

from fastapi import FastAPI,Request,HTTPException
from fastapi.responses import FileResponse,JSONResponse,Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.concurrency import run_in_threadpool

from .phase10_store import OperationsStore,PublicStore
from .phase10_service import Operations
from .phase10_bridge import DockerBridge
from .canonical import parse_json,validate
from chainguard_sandbox.protocol import ToolError
from .default_tools import catalog


def password_hash(password,salt):
    return hashlib.scrypt(password.encode(),salt=bytes.fromhex(salt),n=16384,r=8,p=1).hex()


# Raw uploads may carry either the generic type used by the original client or
# the browser's honest MIME type. The document worker still checks magic bytes
# and all content limits after this transport-level check.
UPLOAD_MIME_TYPES={
    'pdf':{'application/pdf'},
    'doc':{'application/msword'},
    'docx':{'application/vnd.openxmlformats-officedocument.wordprocessingml.document'},
    'txt':{'text/plain'},
    'md':{'text/markdown','text/plain'},
}


def create_operations_app(operations,credentials,origin,static=None,*,start_worker=True,audit_url='http://127.0.0.1:8091'):
    store=operations.store; failures=[]
    from .operation_queue import OperationQueue
    queue=OperationQueue(operations)
    @asynccontextmanager
    async def lifespan(app):
        thread=None;control=None;events=None
        if start_worker:
            thread=threading.Thread(target=operations.worker,daemon=True); thread.start()
            control=threading.Thread(target=queue.worker,daemon=True);control.start()
            if hasattr(operations,'event_worker'):
                events=threading.Thread(target=operations.event_worker,daemon=True);events.start()
        yield
        operations.stop.set()
        queue.stop.set()
        if thread: thread.join(timeout=5)
        if control:control.join(timeout=5)
        if events:events.join(timeout=5)
    app=FastAPI(docs_url=None,redoc_url=None,openapi_url='/ops/openapi.json',lifespan=lifespan)
    app.add_middleware(TrustedHostMiddleware,allowed_hosts=['localhost','127.0.0.1','testserver'])
    @app.exception_handler(ToolError)
    async def failure(request,error):
        code=503 if error.code in {'BACKEND_UNAVAILABLE','CHAIN_UNAVAILABLE'} else 401 if error.code=='AUTH_REQUIRED' else 403 if error.code=='FORBIDDEN' else 404 if error.code=='NOT_FOUND' else 409 if error.code in {'STATE_CONFLICT','IDEMPOTENCY_CONFLICT','CONVERSATION_BUSY','CONVERSATION_CLOSED','AUTH_EXPIRED','AUTH_EXHAUSTED','AUTH_RENEWAL_PENDING'} else 422
        return JSONResponse({'error':{'code':error.code,**getattr(error,'details',{})}},status_code=code)
    @app.middleware('http')
    async def guard(request,call_next):
        if request.method not in {'GET','HEAD'} and request.headers.get('origin')!=origin:
            return JSONResponse({'error':{'code':'ORIGIN_REJECTED'}},status_code=403)
        response=await call_next(request)
        response.headers.update({'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer',
            'Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"})
        return response
    def session(request,allowed=None,write=False):
        row=store.session(request.cookies.get('cg_session'))
        if allowed and row['role'] not in allowed: raise ToolError('FORBIDDEN')
        if write and not secrets.compare_digest(request.headers.get('x-csrf-token',''),row['csrf']): raise ToolError('FORBIDDEN')
        return row
    def asynchronous(request,role,kind,args):
        if request.headers.get('prefer')=='respond-async':
            return JSONResponse(queue.submit(role,kind,args,request.headers.get('idempotency-key')),status_code=202,headers={'Preference-Applied':'respond-async'})
    @app.get('/ops/v1/operations/{id}')
    def operation(id:str,request:Request):
        return queue.get(id,session(request)['role'])
    async def body(request,fields):
        if request.headers.get('content-type','').split(';')[0]!='application/json': raise ToolError('SCHEMA_INVALID')
        chunks=[]; n=0
        async for chunk in request.stream():
            n+=len(chunk)
            if n>65536: raise ToolError('SCHEMA_INVALID')
            chunks.append(chunk)
        value=parse_json(b''.join(chunks))
        choices=fields if isinstance(fields,tuple) else (fields,)
        if type(value) is not dict or not any(set(value)==set(f) for f in choices): raise ToolError('SCHEMA_INVALID')
        return value
    @app.get('/health/live')
    def live(): return {'service':'chainguard-operations','status':'alive','scope':'DEFAULT_SANDBOX_TOOLS_R2_MAIL'}
    @app.post('/ops/v1/login')
    async def login(request:Request):
        value=await body(request,{'role','password'})
        failures[:]=[t for t in failures if t>time.time()-60]
        if len(failures)>=12: raise HTTPException(429,'Too many attempts')
        role,password=value['role'],value['password']
        if not isinstance(role,str): raise ToolError('SCHEMA_INVALID')
        config=credentials.get(role)
        if not config or not isinstance(password,str) or len(password)>256 or not secrets.compare_digest(password_hash(password,config['salt']),config['hash']):
            failures.append(time.time()); raise ToolError('AUTH_REQUIRED')
        token,csrf=store.login(role)
        response=JSONResponse({'role':role,'csrf':csrf,'organization':config['organization'],'audit_url':audit_url})
        response.set_cookie('cg_session',token,httponly=True,samesite='strict',max_age=3600,path='/')
        return response
    @app.get('/ops/v1/session')
    def current(request:Request):
        row=session(request); return {'role':row['role'],'csrf':row['csrf'],'organization':credentials[row['role']]['organization'],'audit_url':audit_url}
    @app.post('/ops/v1/logout')
    def logout(request:Request):
        row=session(request,write=True)
        with store.db() as db: db.execute('DELETE FROM sessions WHERE token_hash=?',(row['token_hash'],))
        response=JSONResponse({'logged_out':True}); response.delete_cookie('cg_session'); return response
    @app.post('/ops/v1/tasks',status_code=202)
    async def create(request:Request):
        session(request,{'requester'},True)
        old={'task_text','allowed_recipients'}; new=old|{'allowed_tools','allowed_document_ids','read_mailboxes'}
        variants=(old,new,new|{'custom_tools'})
        variants=variants+tuple(v|{'document_scope'} for v in variants)
        value=await body(request,variants+tuple(v|{'session_grant'} for v in variants))
        return await run_in_threadpool(operations.create,request.headers.get('idempotency-key'),value)
    @app.post('/ops/v1/attachments',status_code=201)
    async def upload(request:Request,name:str):
        session(request,{'requester'},True)
        if not operations.documents:raise ToolError('DOCUMENT_SANDBOX_UNAVAILABLE')
        content_type=request.headers.get('content-type','').split(';')[0].lower()
        extension=name.rsplit('.',1)[-1].lower() if isinstance(name,str) and '.' in name else ''
        if content_type not in {'application/octet-stream'}|UPLOAD_MIME_TYPES.get(extension,set()):raise ToolError('SCHEMA_INVALID')
        from .document_tools import MAX_FILE
        raw=bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw)>MAX_FILE:raise ToolError('DOCUMENT_LIMIT')
        return await run_in_threadpool(operations.documents.upload,request.headers.get('idempotency-key'),name,bytes(raw))
    @app.get('/ops/v1/tasks/{id}/documents/{file_id}')
    def download(id:str,file_id:str,request:Request):
        session(request)
        if not operations.documents:raise ToolError('DOCUMENT_SANDBOX_UNAVAILABLE')
        files=operations.documents.files_for(store.get(id))
        if file_id not in [f['id'] for f in files['attachments']+files['artifacts']]:raise ToolError('FORBIDDEN')
        value=operations.documents.get(file_id)
        import base64
        from urllib.parse import quote
        return Response(base64.b64decode(value['content_base64']),media_type='application/octet-stream',headers={
            'Content-Disposition':"attachment; filename*=UTF-8''"+quote(value['name'],safe=''), 'X-Document-SHA256':value['sha256']})
    @app.get('/ops/v1/tools')
    def tools(request:Request):
        session(request); return operations.tool_catalog()
    @app.get('/ops/v1/custom-tools')
    def custom_tools(request:Request):
        session(request)
        return {'tools':[operations.custom_descriptor(i) for i in operations.custom_registry.listing()]}
    @app.post('/ops/v1/custom-tools',status_code=201)
    async def register_tool(request:Request):
        session(request,{'requester'},True)
        fields={'name','label','description','adapter','risk','key_field','output_fields','records'}
        value=await body(request,(fields,fields|{'http'},fields-{'risk'},(fields-{'risk'})|{'http'}))
        key=request.headers.get('idempotency-key')
        if key is not None:validate('Bytes32',key)
        return await run_in_threadpool(operations.register_custom,value,key) if key else await run_in_threadpool(operations.register_custom,value)
    @app.post('/ops/v1/custom-tools/import-preview')
    async def import_tool(request:Request):
        session(request,{'requester'},True)
        value=await body(request,{'format','content','column_types'})
        from .custom_tool_import import preview
        return await run_in_threadpool(preview,value)
    @app.post('/ops/v1/custom-tools/{revision}/versions',status_code=201)
    async def version_tool(revision:str,request:Request):
        session(request,{'requester'},True);validate('Bytes32',revision)
        fields={'name','label','description','adapter','risk','key_field','output_fields','records'}
        value=await body(request,(fields,fields|{'http'},fields-{'risk'},(fields-{'risk'})|{'http'}))
        key=request.headers.get('idempotency-key')
        if key is not None:validate('Bytes32',key)
        return await run_in_threadpool(operations.version_custom,revision,value,key)
    @app.get('/ops/v1/custom-tools/{revision}')
    def review_tool(revision:str,request:Request):
        session(request)
        return operations.review_custom(revision)
    @app.post('/ops/v1/custom-tools/{revision}/activation')
    async def activate_tool(revision:str,request:Request):
        session(request,{'security'},True)
        value=await body(request,({'revision','enabled'},{'revision','enabled','risk_level'}))
        if type(value['enabled']) is not bool: raise ToolError('SCHEMA_INVALID')
        if getattr(operations,'config',{}).get('tool_sessions') or 'risk_level' in value:
            if value.get('risk_level') not in {'LOW','HIGH'}:raise ToolError('RISK_LABEL_REQUIRED')
            queued=asynchronous(request,'security','activate',[revision,value['revision'],value['enabled'],value['risk_level']])
            if queued:return queued
            return await run_in_threadpool(operations.set_custom_active,revision,value['revision'],value['enabled'],value['risk_level'])
        return await run_in_threadpool(operations.set_custom_active,revision,value['revision'],value['enabled'])
    @app.post('/ops/v1/tasks/{id}/tool-calls/{call_id}/approve')
    async def approve_call(id:str,call_id:str,request:Request):
        row=session(request,{'biz','security'},True);value=await body(request,{'digest'})
        queued=asynchronous(request,row['role'],'approve_tool',[id,call_id,row['role'],value['digest']])
        if queued:return queued
        return await run_in_threadpool(operations.approve_tool_call,id,call_id,row['role'],value['digest'])
    @app.post('/ops/v1/tasks/{id}/tool-calls/{call_id}/execute')
    async def execute_call(id:str,call_id:str,request:Request):
        session(request,{'requester'},True);await body(request,set())
        queued=asynchronous(request,'requester','execute_tool',[id,call_id])
        if queued:return queued
        return await run_in_threadpool(operations.execute_tool_call,id,call_id)
    @app.post('/ops/v1/audit-batches/flush')
    async def flush_batch(request:Request):
        row=session(request,{'requester','security'},True);await body(request,set())
        queued=asynchronous(request,row['role'],'flush',[])
        if queued:return queued
        return await run_in_threadpool(operations.bridge.session_flush)
    @app.get('/ops/v1/tasks')
    def tasks(request:Request):
        row=session(request)
        jobs=store.visible_jobs('requester/OrgA') if row['role']=='requester' else store.jobs()
        return {'tasks':[operations.detail(j['id']) for j in jobs]}
    @app.delete('/ops/v1/tasks/{id}')
    def hide_task(id:str,request:Request):
        session(request,{'requester'},True)
        job=operations.detail(id)
        return store.hide('conversation',job['conversation_id'],'requester/OrgA') if job.get('conversation_id') else store.hide('task',id,'requester/OrgA')
    @app.get('/ops/v1/tasks/{id}')
    def detail(id:str,request:Request): session(request); return operations.detail(id)
    @app.get('/ops/v1/github-policy')
    def github_policy(request:Request,resource:str='microsoft/vscode'):
        session(request);return operations.github_policy(resource)
    @app.post('/ops/v1/tasks/{id}/github-negative-control')
    async def github_probe(id:str,request:Request):
        session(request,{'requester'},True)
        value=await body(request,{'tool_name','query'})
        if type(value['tool_name']) is not str:raise ToolError('SCHEMA_INVALID')
        return await run_in_threadpool(operations.github_probe,id,value['tool_name'],value['query'])
    @app.get('/ops/v1/tasks/{id}/review')
    def review(id:str,request:Request):
        row=session(request); return operations.review(id,row['role'])
    @app.post('/ops/v1/tasks/{id}/approve')
    async def approve(id:str,request:Request):
        row=session(request,{'biz','security'},True); value=await body(request,{'intent_digest'})
        queued=asynchronous(request,row['role'],'approve',[id,row['role'],value['intent_digest']])
        if queued:return queued
        return await run_in_threadpool(operations.approve,id,row['role'],value['intent_digest'])
    @app.post('/ops/v1/tasks/{id}/execute')
    async def execute(id:str,request:Request):
        session(request,{'requester'},True); value=await body(request,{'intent_digest'})
        queued=asynchronous(request,'requester','execute',[id,value['intent_digest']])
        if queued:return queued
        return await run_in_threadpool(operations.execute,id,value['intent_digest'])
    @app.get('/ops/v1/tasks/{id}/mailbox')
    def mailbox(id:str,request:Request): session(request); return operations.mailbox(id)
    @app.post('/ops/v1/tasks/{id}/negative-control')
    async def negative(id:str,request:Request):
        session(request,{'requester'},True); await body(request,set())
        return await run_in_threadpool(operations.manual_probe,id)
    @app.post('/ops/v1/tasks/{id}/receipt-loss')
    async def fault(id:str,request:Request):
        session(request,{'requester'},True); value=await body(request,{'hold'})
        if type(value['hold']) is not bool: raise ToolError('SCHEMA_INVALID')
        return await run_in_threadpool(operations.fault,id,value['hold'])
    from .conversation_api import install
    install(app,operations,session,body,asynchronous)
    app.state.control_queue=queue
    if static:
        app.mount('/assets',StaticFiles(directory=Path(static)/'assets'),name='assets')
        @app.get('/')
        def index(): return FileResponse(Path(static)/'index.html')
    return app


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--config',type=Path,required=True); args=parser.parse_args()
    c=json.loads(args.config.read_text(encoding='utf8')); store=OperationsStore(c['private_root']); public=PublicStore(c['public_db'])
    operations=Operations(store,public,DockerBridge(c),c)
    audit=json.loads(Path(c['audit_config']).read_text(encoding='utf8'))
    app=create_operations_app(operations,c['credentials'],f"http://127.0.0.1:{c['port']}",Path(c['repo'])/'console/dist',audit_url=f"http://127.0.0.1:{audit['port']}")
    import uvicorn
    uvicorn.run(app,host='127.0.0.1',port=c['port'],access_log=False)


if __name__=='__main__': main()
