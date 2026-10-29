"""Dedicated egress process: public GitHub GET only; no Agent/mail/chain credentials."""
import argparse
import hashlib
import json
from pathlib import Path
import secrets
import sqlite3
import time
import threading
import uvicorn
from fastapi import FastAPI,Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from .canonical import canonical,parse_json
from .github_read import fetch,resource,GitHubFailure
from .github_policy import RepositoryPolicy
from chainguard_sandbox.protocol import ToolError
from chainguard_sandbox.storage import require_container

def create_app(root,token,*,fetcher=fetch,policy_checker=None):
    app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None)
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    def db():return sqlite3.connect(root/'github.sqlite3',timeout=10)
    with db() as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS fetches(id TEXT PRIMARY KEY,query TEXT,status TEXT,http_status INTEGER,data BLOB,raw BLOB,recorded_at INTEGER)')
        conn.execute('CREATE TABLE IF NOT EXISTS repository_policy_checks(id TEXT PRIMARY KEY,query TEXT,phase TEXT,verdict TEXT,evidence BLOB,recorded_at INTEGER)')
    if policy_checker is None:
        # Absent/broken configuration must never fall back to ungoverned HTTPS.
        def policy_checker(query):
            try:
                config=json.loads((root/'github-policy.json').read_text())
                return RepositoryPolicy(config,['http://node1:8545','http://node3:8545']).check(query)
            except (OSError,ValueError,KeyError,ToolError):raise GitHubFailure('GITHUB_POLICY_UNAVAILABLE') from None
    def check(query,phase):
        evidence=None
        try:
            evidence=policy_checker(query)
            if evidence['allowed'] is not True:raise GitHubFailure('GITHUB_REPOSITORY_DENIED',repository_policy=evidence)
        except GitHubFailure as error:
            with db() as conn:conn.execute('INSERT INTO repository_policy_checks VALUES (?,?,?,?,?,?)',('0x'+secrets.token_hex(32),query,phase,error.code,canonical(evidence) if evidence else None,int(time.time())))
            raise
        with db() as conn:conn.execute('INSERT INTO repository_policy_checks VALUES (?,?,?,?,?,?)',('0x'+secrets.token_hex(32),query,phase,'ALLOW',canonical(evidence),int(time.time())))
        return evidence
    lock=threading.Lock();calls=[]
    @app.post('/fetch')
    async def read(request:Request):
        if not secrets.compare_digest(request.headers.get('authorization',''),'Bearer '+token):return JSONResponse({'error':{'code':'AUTH_REQUIRED'}},401)
        try:
            if request.headers.get('content-type','').split(';')[0]!='application/json':raise ToolError('SCHEMA_INVALID')
            chunks=[];length=0
            async for chunk in request.stream():
                length+=len(chunk)
                if length>1024:raise ToolError('SCHEMA_INVALID')
                chunks.append(chunk)
            value=parse_json(b''.join(chunks))
            if type(value) is not dict or set(value)!={'query'}:raise ToolError('SCHEMA_INVALID')
            resource(value['query'])
        except ToolError:return JSONResponse({'error':{'code':'SCHEMA_INVALID'}},422)
        with lock:
            calls[:]=[t for t in calls if t>time.monotonic()-60]
            if len(calls)>=20:return JSONResponse({'error':{'code':'GITHUB_LOCAL_RATE_LIMIT'}},429)
            calls.append(time.monotonic())
        id='0x'+secrets.token_hex(32)
        try:
            await run_in_threadpool(check,value['query'],'BEFORE_FETCH')
            data,raw=await run_in_threadpool(fetcher,value['query'])
            try:proof=await run_in_threadpool(check,value['query'],'BEFORE_RELEASE')
            except GitHubFailure:
                with db() as conn:conn.execute('INSERT INTO fetches VALUES (?,?,?,?,?,?,?)',(id,value['query'],'WITHHELD_POLICY',200,canonical(data),raw,int(time.time())))
                raise
            with db() as conn:conn.execute('INSERT INTO fetches VALUES (?,?,?,?,?,?,?)',(id,value['query'],'OK',200,canonical(data),raw,int(time.time())))
            return dict(data=data,fetch_id=id,repository_policy=proof)
        except GitHubFailure as error:
            # Denied/unavailable admission creates no fetch row and performs no HTTPS.
            if not error.code.startswith('GITHUB_POLICY_') and error.code!='GITHUB_REPOSITORY_DENIED':
                with db() as conn:conn.execute('INSERT INTO fetches VALUES (?,?,?,?,?,?,?)',(id,value['query'],error.code,error.status,None,None,int(time.time())))
            return JSONResponse({'error':{'code':error.code},'fetch_id':id,'repository_policy':error.repository_policy},403 if error.code=='GITHUB_REPOSITORY_DENIED' else 503)
    return app

def main():
    require_container();parser=argparse.ArgumentParser();parser.add_argument('operation',choices=['init','serve']);a=parser.parse_args();root=Path('/sandbox')
    if a.operation=='init':
        import sys
        value=json.load(sys.stdin)
        if set(value)!={'token'} or type(value['token']) is not str or len(value['token'])!=64:raise ValueError('Expected internal service token')
        file=root/'github-reader.json'
        with file.open('x') as f:json.dump(value,f)
        file.chmod(0o600)
    else:
        config=json.loads((root/'github-reader.json').read_text())
        uvicorn.run(create_app(root,config['token']),host='0.0.0.0',port=8080,access_log=False,log_level='warning')
if __name__=='__main__':main()
