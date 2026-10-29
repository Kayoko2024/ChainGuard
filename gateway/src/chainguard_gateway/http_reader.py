"""Isolated HTTP query service. Pins public DNS addresses and never follows redirects."""
import argparse
from datetime import datetime,timezone
import hashlib
import http.client
import ipaddress
import json
from pathlib import Path
import secrets
import socket
import sqlite3
import ssl
import threading
import time
from urllib.parse import urlencode
from Crypto.Cipher import AES
from fastapi import FastAPI,Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from .canonical import canonical,parse_json,validate
from .custom_tools import validate_manifest
from .http_tools import endpoint,HTTPFailure
from chainguard_sandbox.protocol import ToolError


def public_addresses(host):
    try:
        addresses=list(dict.fromkeys(r[4][0] for r in socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)))
        if not addresses:raise HTTPFailure('HTTP_TARGET_DENIED')
        for address in addresses:
            ip=ipaddress.ip_address(address)
            if not ip.is_global or isinstance(ip,ipaddress.IPv6Address) and (ip.ipv4_mapped is not None or ip.sixtofour is not None or ip.teredo is not None or ip in ipaddress.ip_network('64:ff9b::/96') or ip in ipaddress.ip_network('64:ff9b:1::/48')):
                raise HTTPFailure('HTTP_TARGET_DENIED')
        return addresses
    except OSError:raise HTTPFailure('HTTP_UNAVAILABLE') from None


class PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self,host,address):
        super().__init__(host,timeout=6,context=ssl.create_default_context());self.address=address
    def connect(self):
        sock=socket.create_connection((self.address,443),timeout=self.timeout)
        try:self.sock=self._context.wrap_socket(sock,server_hostname=self.host)
        except BaseException:sock.close();raise


def fetch(manifest,record):
    config=manifest['http'];p=endpoint(config['url']);addresses=public_addresses(p.hostname)
    conn=PinnedHTTPS(p.hostname,addresses[0])
    target=(p.path or '/')+('?' + urlencode(record['query']) if record['query'] else '')
    body=canonical(record['body']) if config['method']=='POST' else None
    request_sha=hashlib.sha256(canonical({'http':config,'record':record})).hexdigest()
    try:
        conn.request(config['method'],target,body=body,headers={'Accept':'application/json','Accept-Encoding':'identity','Content-Type':'application/json','User-Agent':'ChainGuard-reviewed-http/0.10'})
        response=conn.getresponse()
        if 300<=response.status<400:raise HTTPFailure('HTTP_REDIRECT_REJECTED')
        if not 200<=response.status<300:raise HTTPFailure('HTTP_REMOTE_ERROR')
        if response.getheader('Content-Encoding','identity').lower() not in {'','identity'}:raise HTTPFailure('HTTP_RESPONSE_INVALID')
        if response.getheader('Content-Type','').split(';')[0].lower() not in {'application/json'}:raise HTTPFailure('HTTP_RESPONSE_INVALID')
        chunks=[];size=0;deadline=time.monotonic()+8
        while True:
            if time.monotonic()>deadline:raise HTTPFailure('HTTP_UNAVAILABLE')
            chunk=response.read1(min(8192,131073-size))
            if not chunk:break
            chunks.append(chunk);size+=len(chunk)
            if size>131072:raise HTTPFailure('HTTP_RESPONSE_TOO_LARGE')
        raw=b''.join(chunks)
        if len(raw)>131072:raise HTTPFailure('HTTP_RESPONSE_TOO_LARGE')
        value=json.loads(raw)
        text=json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(',',':'))
        if len(text)>16000:raise HTTPFailure('HTTP_RESPONSE_TOO_LARGE')
        return {'record':{'profile':record['profile'],'response':text},'source':{'url':config['url'],'method':config['method'],
            'http_status':response.status,'fetched_at_utc':datetime.now(timezone.utc).isoformat(),
            'response_sha256':hashlib.sha256(raw).hexdigest(),'request_sha256':request_sha}},raw
    except (OSError,TimeoutError,http.client.HTTPException):raise HTTPFailure('HTTP_UNAVAILABLE') from None
    except (ValueError,UnicodeError,RecursionError):raise HTTPFailure('HTTP_RESPONSE_INVALID') from None
    finally:conn.close()


def create_app(root,token,*,fetcher=fetch):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    keyfile=root/'http-data.key'
    try:
        with keyfile.open('xb') as f:f.write(secrets.token_bytes(32))
        keyfile.chmod(0o600)
    except FileExistsError:pass
    key=keyfile.read_bytes()
    def seal(id,value):
        cipher=AES.new(key,AES.MODE_GCM);cipher.update(id.encode());data,tag=cipher.encrypt_and_digest(canonical(value));return cipher.nonce+tag+data
    def unseal(id,blob):
        cipher=AES.new(key,AES.MODE_GCM,nonce=blob[:16]);cipher.update(id.encode());return json.loads(cipher.decrypt_and_verify(blob[32:],blob[16:32]))
    def db():
        c=sqlite3.connect(root/'http.sqlite3',timeout=10);c.row_factory=sqlite3.Row;return c
    with db() as c:
        c.executescript('''CREATE TABLE IF NOT EXISTS manifests(revision TEXT PRIMARY KEY,active INTEGER,data BLOB);
            CREATE TABLE IF NOT EXISTS fetches(id TEXT PRIMARY KEY,request_sha256 TEXT,status TEXT,data BLOB,observed_at INTEGER);''')
    app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None)
    lock=threading.Lock();calls=[]

    @app.post('/{operation}')
    async def handle(operation:str,request:Request):
        if not secrets.compare_digest(request.headers.get('authorization',''),'Bearer '+token):return JSONResponse({'error':{'code':'AUTH_REQUIRED'}},401)
        try:
            if request.headers.get('content-type','').split(';')[0]!='application/json':raise ToolError('SCHEMA_INVALID')
            chunks=[];size=0
            async for chunk in request.stream():
                size+=len(chunk)
                if size>65536:raise ToolError('SCHEMA_INVALID')
                chunks.append(chunk)
            value=parse_json(b''.join(chunks))
            return await run_in_threadpool(run,operation,value)
        except (ToolError,HTTPFailure) as error:
            return JSONResponse({'error':{'code':error.code}},403 if error.code in {'HTTP_TARGET_DENIED','POLICY_REVOKED','UNAUTHORIZED_SCOPE'} else 503 if isinstance(error,HTTPFailure) else 422)

    def run(operation,value):
        if type(value) is not dict:raise ToolError('SCHEMA_INVALID')
        if operation=='install':
            if set(value)!={'manifest','records'}:raise ToolError('SCHEMA_INVALID')
            m=value['manifest'];validate_manifest(m,value['records'])
            if m['adapter']!='http.request':raise ToolError('POLICY_DENY')
            rev=m['revision']
            with db() as c:
                old=c.execute('SELECT * FROM manifests WHERE revision=?',(rev,)).fetchone()
                if old and unseal(rev,old['data'])!=value:raise ToolError('PARAMS_MISMATCH')
                c.execute('INSERT OR IGNORE INTO manifests VALUES (?,?,?)',(rev,1,seal(rev,value)))
                active=c.execute('SELECT active FROM manifests WHERE revision=?',(rev,)).fetchone()[0]
            return {'revision':rev,'active':bool(active)}
        if operation=='disable':
            if set(value)!={'revision'}:raise ToolError('SCHEMA_INVALID')
            validate('Bytes32',value['revision'])
            with db() as c:c.execute('UPDATE manifests SET active=0 WHERE revision=?',(value['revision'],))
            return {'revision':value['revision'],'active':False}
        if operation!='fetch' or set(value)!={'revision','profile','execution_id'}:raise ToolError('SCHEMA_INVALID')
        validate('Bytes32',value['revision']);validate('Bytes32',value['execution_id'])
        if type(value['profile']) is not str:raise ToolError('SCHEMA_INVALID')
        rev=value['revision'];id=value['execution_id'];sha=hashlib.sha256(canonical(value)).hexdigest()
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            m=c.execute('SELECT * FROM manifests WHERE revision=?',(rev,)).fetchone()
            if not m or not m['active']:raise ToolError('POLICY_REVOKED')
            installed=unseal(rev,m['data']);manifest=installed['manifest']
            record=next((r for r in installed['records'] if r['profile']==value['profile']),None)
            if record is None:raise ToolError('UNAUTHORIZED_SCOPE')
            old=c.execute('SELECT * FROM fetches WHERE id=?',(id,)).fetchone()
            if old:
                if old['request_sha256']!=sha:raise ToolError('IDEMPOTENCY_CONFLICT')
                if old['status']=='OK':return unseal(id,old['data'])['result']
                raise HTTPFailure('HTTP_EXECUTION_UNKNOWN')
            with lock:
                calls[:]=[t for t in calls if t>time.monotonic()-60]
                if len(calls)>=20:raise HTTPFailure('HTTP_LOCAL_RATE_LIMIT')
                calls.append(time.monotonic())
            c.execute('INSERT INTO fetches VALUES (?,?,?,?,?)',(id,sha,'STARTED',None,int(time.time())))
        try:
            data,raw=fetcher(manifest,record)
            result={'data':data,'fetch_id':id}
            with db() as c:
                active=c.execute('SELECT active FROM manifests WHERE revision=?',(rev,)).fetchone()[0]
                c.execute('UPDATE fetches SET status=?,data=? WHERE id=?',('OK' if active else 'WITHHELD_POLICY',seal(id,{'result':result,'raw_hex':raw.hex()}),id))
            if not active:raise ToolError('POLICY_REVOKED')
            return result
        except HTTPFailure as error:
            with db() as c:c.execute('UPDATE fetches SET status=? WHERE id=?',(error.code,id))
            raise
    return app


def main():
    from chainguard_sandbox.storage import require_container
    require_container();p=argparse.ArgumentParser();p.add_argument('operation',choices=['init','serve']);a=p.parse_args();root=Path('/sandbox')
    if a.operation=='init':
        import sys
        config=json.load(sys.stdin)
        if set(config)!={'token'} or type(config['token']) is not str or len(config['token'])!=64:raise ValueError('Expected internal token')
        file=root/'http-reader.json'
        with file.open('x') as f:json.dump(config,f)
        file.chmod(0o600)
    else:
        import uvicorn
        uvicorn.run(create_app(root,json.loads((root/'http-reader.json').read_text())['token']),host='0.0.0.0',port=8080,access_log=False,log_level='warning')

if __name__=='__main__':main()
