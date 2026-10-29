"""Additive conversation routes; existing HIGH approval/execute endpoints stay authoritative."""
from fastapi import Request
from starlette.concurrency import run_in_threadpool
from chainguard_sandbox.protocol import ToolError


def install(app,operations,session,body,asynchronous=None):
    def service():return operations.conversation_service
    def owner(row):return 'requester/OrgA'  # One configured local test requester, never the cookie token.
    def visible(id,row):
        return owner(row) if row['role']=='requester' else None

    @app.get('/ops/v1/conversations')
    def listing(request:Request,summary:bool=False):
        row=session(request)
        return {'conversations':[service().summary(c) if summary else service().detail(c['id'],visible(c['id'],row)) for c in operations.conversations.listing(owner(row),include_hidden=row['role']!='requester')]}

    @app.delete('/ops/v1/conversations/{id}')
    def hide(id:str,request:Request):
        row=session(request,{'requester'},True)
        return operations.store.hide('conversation',id,owner(row))

    @app.post('/ops/v1/conversations',status_code=201)
    async def create(request:Request):
        row=session(request,{'requester'},True)
        value=await body(request,{'session_id','scope'})
        if type(value['scope']) is not dict or 'task_text' in value['scope']:raise ToolError('SCHEMA_INVALID')
        return await run_in_threadpool(service().create,value['session_id'],owner(row),value['scope'])

    @app.post('/ops/v1/tasks/{id}/conversation')
    async def attach(id:str,request:Request):
        row=session(request,{'requester'},True);await body(request,set())
        return await run_in_threadpool(service().attach,id,owner(row))

    @app.get('/ops/v1/conversations/{id}')
    def detail(id:str,request:Request):
        row=session(request)
        return service().detail(id,visible(id,row))

    @app.post('/ops/v1/conversations/{id}/messages',status_code=202)
    async def append(id:str,request:Request):
        row=session(request,{'requester'},True)
        value=await body(request,{'message_id','text','expected_version'})
        return await run_in_threadpool(service().append,id,owner(row),value['message_id'],value['text'],value['expected_version'])

    @app.post('/ops/v1/conversations/{id}/close')
    async def close(id:str,request:Request):
        row=session(request,{'requester'},True);await body(request,set())
        queued=asynchronous(request,row['role'],'close',[id,owner(row)]) if asynchronous else None
        if queued:return queued
        return await run_in_threadpool(service().close,id,owner(row))

    @app.post('/ops/v1/conversations/{id}/grant')
    async def renew(id:str,request:Request):
        row=session(request,{'requester'},True)
        value=await body(request,({'duration_seconds','max_calls'},{'duration_seconds','max_calls','expected_grant_digest'}))
        expected=value.pop('expected_grant_digest',(service().store.get(id,owner(row)).get('low_grant') or {}).get('digest'))
        if expected is not None:
            from .canonical import validate
            validate('Bytes32',expected)
        args=[id,owner(row),value,expected,request.headers.get('idempotency-key')]
        queued=asynchronous(request,row['role'],'renew',args) if asynchronous else None
        if queued:return queued
        return await run_in_threadpool(service().renew,*args)
