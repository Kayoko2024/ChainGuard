"""Independent localhost audit app: immutable public catalog, no execution routes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .audit_verify import make_chain, verify_action
from .integrity import check_frozen_protocol
from .canonical import ROOT
from chainguard_sandbox.protocol import ToolError


def load_catalog(path):
    path=Path(path)
    raw=path.read_bytes()
    if path.is_symlink() or len(raw)>20_000_000:
        raise ValueError('Unsafe audit catalog')
    if hashlib.sha256(raw).hexdigest()!=path.with_suffix('.sha256').read_text().strip():
        raise ValueError('Audit catalog digest mismatch')
    value=json.loads(raw)
    if value['schema_version']!=1 or not isinstance(value['actions'],list):
        raise ValueError('Unsupported catalog')
    ids=[a['entry_id'] for a in value['actions']]
    if len(ids)!=len(set(ids)) or any(not re.fullmatch('[a-z]+-[0-9]{4}',i) for i in ids):
        raise ValueError('Invalid entry ids')
    return value


def create_audit_app(catalog, chain, static=None):
    app=FastAPI(title='ChainGuard read-only audit',docs_url=None,redoc_url=None,openapi_url='/audit-api/openapi.json')
    app.add_middleware(TrustedHostMiddleware,allowed_hosts=['localhost','127.0.0.1','testserver'])
    actions={a['entry_id']:a for a in catalog['actions']}
    @app.middleware('http')
    async def headers(request,call_next):
        response=await call_next(request)
        response.headers.update({'Cache-Control':'no-store','X-Content-Type-Options':'nosniff',
            'Referrer-Policy':'no-referrer','Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"})
        return response
    @app.get('/health/live')
    def live():
        return dict(status='alive',service='chainguard-audit',read_only=True)
    @app.get('/health/ready')
    def ready():
        check_frozen_protocol(ROOT)
        return dict(status='ready',actions=len(actions),ledger_checked=False)
    @app.get('/audit-api/v1/network')
    def network():
        try:
            return dict(status='ONLINE',chain_id=str(catalog['deployment']['chainId']),snapshot=chain.healthy(),nodes=4)
        except ToolError:
            return JSONResponse(dict(status='UNAVAILABLE',snapshot=None,reason='当前无法核验四节点；历史记录不变'),status_code=503)
    @app.get('/audit-api/v1/actions')
    def listing(group:str|None=None,state:str|None=None):
        selected=[a for a in actions.values() if (not group or a['group']==group) and (not state or a['state']==state)]
        return dict(schema_version=1,generated_at_utc=catalog['generated_at_utc'],trust_note=catalog['trust_note'],
                    actions=selected,total=len(selected),read_only=True)
    def get(entry_id):
        if entry_id not in actions:
            raise HTTPException(404,'Unknown audit entry')
        return actions[entry_id]
    @app.get('/audit-api/v1/actions/{entry_id}')
    def detail(entry_id:str):
        return get(entry_id)
    @app.get('/audit-api/v1/actions/{entry_id}/verify')
    def verify(entry_id:str):
        return verify_action(chain,get(entry_id))
    if static:
        static=Path(static)
        app.mount('/assets',StaticFiles(directory=static/'assets'),name='assets')
        @app.get('/')
        def index():
            return FileResponse(static/'index.html')
    return app


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog',type=Path,default=Path('/audit/catalog.json'))
    parser.add_argument('--static',type=Path,default=Path('/app/dashboard/dist'))
    parser.add_argument('--host',default='127.0.0.1')
    parser.add_argument('--port',type=int,default=8080)
    args=parser.parse_args()
    check_frozen_protocol(ROOT)
    catalog=load_catalog(args.catalog)
    urls=os.environ.get('CHAINGUARD_AUDIT_RPCS','http://node1:8545,http://node2:8545,http://node3:8545,http://node4:8545').split(',')
    chain=make_chain(catalog['deployment'],urls)
    import uvicorn
    uvicorn.run(create_audit_app(catalog,chain,args.static),host=args.host,port=args.port,access_log=False)


if __name__=='__main__':
    main()
