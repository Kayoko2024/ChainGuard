"""Implemented R2 subset of the frozen HTTP contract; no Agent signing endpoints."""
import copy
import json
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from .canonical import ROOT, ERRORS, validate
from .crypto import random_id
from .identity import authenticate
from .chain_transport import service_identity, request_body
from chainguard_sandbox.protocol import ToolError


def error_response(error,trace=None):
    return JSONResponse(status_code=ERRORS[error.code],content={'error':{'code':error.code,'message':error.code,
        'retryable':error.code=='CHAIN_UNAVAILABLE','trace_id':trace or random_id()}})


def application_base():
    app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None)
    @app.exception_handler(ToolError)
    async def failed(request,error): return error_response(error,getattr(request.state,'trace_id',None))
    return app


def create_chain_app(service,authority_fingerprint,authority_token):
    @asynccontextmanager
    async def lifespan(app):
        thread=threading.Thread(target=service.worker,daemon=True)
        thread.start()
        yield
        service.stop.set()
        thread.join(timeout=10)
    app=application_base()
    app.router.lifespan_context=lifespan

    @app.middleware('http')
    async def identity(request,call_next):
        request.state.trace_id=random_id()
        try:
            if request.url.path.startswith('/internal/'):
                service_identity(request,authority_fingerprint,authority_token)
            elif request.url.path.startswith('/v1/'):
                request.state.subject=authenticate(service.store.private('jwt.key'),request.headers.get('authorization'))
                service.current_actor(request.state.subject)
            response=await call_next(request)
            return error_response(ToolError('NOT_FOUND'),request.state.trace_id) if response.status_code==404 else response
        except ToolError as error: return error_response(error,request.state.trace_id)

    def key(request): return validate('Bytes32',request.headers.get('idempotency-key'))
    @app.get('/health/ready')
    def health(): return {'service':'chainguard-c-gateway','stage':6,'status':'ready'}

    @app.post('/v1/tasks',status_code=201)
    async def create_task(request:Request):
        body=await request_body(request,'CreateTaskRequest')
        return await run_in_threadpool(service.create_task,request.state.subject,body,key(request),request.state.trace_id)

    @app.post('/v1/agent/actions/propose',status_code=202)
    async def propose(request:Request):
        body=await request_body(request,'ProposeRequest')
        return await run_in_threadpool(service.propose,request.state.subject,body,key(request),request.state.trace_id)

    @app.post('/v1/actions/{action_id}/approve')
    async def approve(action_id:str,request:Request):
        validate('Bytes32',action_id)
        body=await request_body(request,'ApproveRequest')
        return await run_in_threadpool(service.approve,request.state.subject,action_id,body,request.state.trace_id)

    @app.post('/v1/actions/{action_id}/reserve',status_code=202)
    async def reserve(action_id:str,request:Request):
        validate('Bytes32',action_id)
        body=await request_body(request,'ReserveRequest')
        return await run_in_threadpool(service.reserve,request.state.subject,action_id,body,key(request),request.state.trace_id)

    @app.get('/v1/actions/{action_id}')
    def get_action(action_id:str,request:Request): return service.get_action(request.state.subject,action_id)

    @app.post('/v1/actions/{action_id}/reconcile',status_code=202)
    async def reconcile(action_id:str,request:Request):
        validate('Bytes32',action_id)
        body=await request_body(request,'ReconcileRequest')
        return await run_in_threadpool(service.reconcile,request.state.subject,action_id,body,key(request),request.state.trace_id)

    @app.get('/internal/v1/authorization/{action_id}')
    def authorization(action_id:str):
        validate('Bytes32',action_id)
        return service.authorization(action_id)

    @app.get('/operations/openapi.json')
    def operations():
        spec=copy.deepcopy(json.loads((ROOT/'spec/openapi.json').read_text()))
        supported={'/v1/tasks','/v1/agent/actions/propose','/v1/actions/{id}/approve','/v1/actions/{id}/reserve','/v1/actions/{id}','/v1/actions/{id}/reconcile'}
        spec['paths']={p:v for p,v in spec['paths'].items() if p in supported}
        spec['info']['title']='ChainGuard C R2 mail.send implemented subset'
        return spec
    return app


def create_tool_app(tool,gateway_fingerprint,token):
    app=application_base()
    @app.middleware('http')
    async def identity(request,call_next):
        try:
            service_identity(request,gateway_fingerprint,token)
            response=await call_next(request)
            return error_response(ToolError('NOT_FOUND')) if response.status_code==404 else response
        except ToolError as error: return error_response(error)

    @app.post('/v1/tools/execute')
    async def execute(request:Request):
        key=validate('Bytes32',request.headers.get('idempotency-key'))
        body=await request_body(request,'ExecuteRequest')
        return await run_in_threadpool(tool.execute,body,key)

    @app.get('/v1/tools/actions/{action_id}')
    def status(action_id:str): return tool.status(action_id)
    return app
