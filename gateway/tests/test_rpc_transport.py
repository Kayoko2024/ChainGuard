"""A real loopback RPC server verifies shared transport isolation and fresh reads."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import threading
import pytest
from chainguard_gateway.chain_rpc import RPC
from chainguard_sandbox.protocol import ToolError


@contextmanager
def server(name):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            data=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            result={'jsonrpc':'2.0','id':1}
            if data['method']=='bad':result['error']={'code':-32000,'message':'test rejection'}
            else:result['result']={'endpoint':name,'params':data['params']}
            raw=json.dumps(result).encode();self.send_response(200);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    http=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
    try:yield 'http://127.0.0.1:'+str(http.server_port)
    finally:http.shutdown();http.server_close();thread.join()


def test_many_policy_clients_share_one_transport_without_caching_or_mixing_nodes():
    with server('one') as first,server('two') as second:
        clients=[RPC(first if i%2==0 else second) for i in range(200)]
        assert len({id(c.opener) for c in clients})==1
        def query(i):return clients[i].call('read',[i])
        with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(query,range(200)))
        assert results==[{'endpoint':'one' if i%2==0 else 'two','params':[i]} for i in range(200)]
        assert clients[0].call('read',['fresh'])['params']==['fresh']


def test_shared_transport_has_no_environment_proxy_and_does_not_mask_rpc_failure(monkeypatch):
    from chainguard_gateway.chain_rpc import rpc_transport
    monkeypatch.setenv('HTTP_PROXY','http://127.0.0.1:1');monkeypatch.setenv('HTTPS_PROXY','http://127.0.0.1:1')
    with server('direct') as url:
        client=RPC(url);assert client.call('read',[])['endpoint']=='direct'
        assert all(not getattr(h,'proxies',{}) for h in client.opener.handlers)
        with pytest.raises(ToolError,match='CHAIN_UNAVAILABLE'):client.call('bad',[])
    with pytest.raises(ToolError,match='CHAIN_UNAVAILABLE'):client.call('read',[])
