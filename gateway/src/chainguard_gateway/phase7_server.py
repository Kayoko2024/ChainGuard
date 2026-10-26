"""Stage7 service extensions; original high-risk endpoints/contracts are unchanged."""
import argparse
import secrets
import ssl
import sys

import uvicorn
from fastapi import Request
from starlette.concurrency import run_in_threadpool

from .phase6_server import initialize,load,client
from .chain_rpc import Chain
from .chain_store import ChainStore
from .chain_service import ChainService
from .chain_api import create_chain_app,create_tool_app
from .chain_transport import PeerCertificateProtocol,service_identity
from .canonical import parse_json,validate
from .identity import authenticate
from .policy import require_actor
from chainguard_sandbox.storage import Store,require_container
from chainguard_sandbox.chain_mail import ChainMailTool
from chainguard_sandbox.read_broker import ReadBroker
from chainguard_sandbox.protocol import ToolError,document_id


async def body(request,fields):
    if request.headers.get('content-type','').split(';')[0]!='application/json': raise ToolError('SCHEMA_INVALID')
    parts=[]; size=0
    async for part in request.stream():
        size+=len(part)
        if size>65536: raise ToolError('SCHEMA_INVALID')
        parts.append(part)
    result=parse_json(b''.join(parts))
    if type(result) is not dict or set(result)!=set(fields): raise ToolError('SCHEMA_INVALID')
    return result


def gateway_extensions(service,config):
    app=create_chain_app(service,config['authority_fingerprint'],config['authority_token'])
    def actor(request):
        subject=authenticate(service.store.private('jwt.key'),request.headers.get('authorization'))
        return subject,service.current_actor(subject)
    def reviewer(request):
        if not secrets.compare_digest(request.scope.get('chainguard_peer_fingerprint',''),config['operator_fingerprint']): raise ToolError('FORBIDDEN')
        subject,current=actor(request)
        if not set(current['roles'])&{'REQUESTER','BUSINESS_APPROVER','SECURITY_APPROVER'}: raise ToolError('FORBIDDEN')
        return subject,current

    @app.post('/agent/v1/reads')
    async def read(request:Request):
        subject,current=actor(request); require_actor(current,'AGENT')
        value=await body(request,{'task_id','doc_id'})
        validate('Bytes32',value['task_id']); document_id(value['doc_id'])
        key=validate('Bytes32',request.headers.get('idempotency-key'))
        with service.store.connect() as db:
            task,grant=service.store.task(db,value['task_id'])
            if grant['agent']!=current['address'] or task['revoked']: raise ToolError('FORBIDDEN')
        # A separate explicit R0 read capability is checked by the tool broker.
        return await run_in_threadpool(service.tool_client.request,'POST','/internal/v1/reads',dict(value,agent=current['address']),key)

    @app.get('/operator/v1/pending')
    def pending(request:Request):
        subject,current=reviewer(request)
        found=[]
        with service.store.connect() as db:
            for row in db.execute("SELECT * FROM actions WHERE state='AWAITING_APPROVAL'"):
                try: service._visible(db,subject,row)
                except ToolError: continue
                found.append({'action_id':row['action_id'],'task_id':row['task_id']})
        return {'actions':found}

    @app.get('/operator/v1/actions/{action_id}/review')
    def review(action_id:str,request:Request):
        subject,current=reviewer(request)
        validate('Bytes32',action_id)
        with service.store.connect() as db:
            row,data=service.store.action(db,action_id)
            service._visible(db,subject,row)
        # Original params/salt only traverse the trusted reviewer mTLS channel.
        return {'intent':data['intent'],'params':data['params'],'params_salt':data['salt']}
    return app


def tool_extensions(tool,store,config):
    app=create_tool_app(tool,config['gateway_fingerprint'],config['gateway_token'])
    broker=ReadBroker(store)
    @app.post('/internal/v1/reads')
    async def read(request:Request):
        value=await body(request,{'task_id','agent','doc_id'})
        return await run_in_threadpool(broker.read,value['task_id'],value['agent'],value['doc_id'])
    return app


def serve(kind):
    require_container(); root,config=load()
    chain=Chain(config['deployment'],config['rpc_urls'])
    if kind=='gateway':
        store=ChainStore(root)
        service=ChainService(store,chain,client(root,config['tool_client']),(root/'relay.key').read_bytes(),config['tool_signer'])
        app=gateway_extensions(service,config)
    else:
        store=Store(root)
        tool=ChainMailTool(store,chain,client(root,config['authority_client']),(root/'signing.key').read_bytes(),(root/'data.key').read_bytes())
        app=tool_extensions(tool,store,config)
    uvicorn.run(app,host='0.0.0.0',port=8443,http=PeerCertificateProtocol,access_log=False,log_level='warning',
        ssl_keyfile=str(root/'server.key'),ssl_certfile=str(root/'server.pem'),ssl_ca_certs=str(root/'ca.pem'),ssl_cert_reqs=ssl.CERT_REQUIRED)


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('operation',choices=['init','serve']); parser.add_argument('kind',choices=['gateway','tool','qa'])
    args=parser.parse_args()
    if args.operation=='init':
        initialize(args.kind)
        if args.kind=='tool':
            root,config=load(); store=Store(root)
            ReadBroker(store).provision(store.private_read('operator.key').decode(),config.get('read_documents',[]))
    else: serve(args.kind)
