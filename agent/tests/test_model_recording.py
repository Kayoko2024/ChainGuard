"""Local HTTP protocol fixtures, not real LLM experiment samples."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import pytest
from chainguard_agent.model import HTTPModelBackend, LLMConfig
from chainguard_agent.runner import AgentRunner
from chainguard_sandbox.protocol import ToolError


@pytest.mark.parametrize('status',[200,401])
def test_model_parameters_and_recorded_http_failures_are_redacted(status):
    received=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def do_POST(self):
            received.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
            self.send_response(status); self.end_headers()
            value=({'choices':[{'message':{'role':'assistant','content':'unit-model-key'}}]} if status==200 else {'error':'unit-model-key'})
            self.wfile.write(json.dumps(value).encode())
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
    events=[]
    try:
        backend=HTTPModelBackend(LLMConfig('fixture',f'http://127.0.0.1:{server.server_port}','unit-model-key'),
            parameters={'top_p':1,'thinking':{'type':'disabled'},'max_tokens':512},recorder=events.append)
        if status==200: backend.next_turn([],[])
        else:
            with pytest.raises(ToolError,match='EXECUTION_UNKNOWN'): backend.next_turn([],[])
        assert received[0]['thinking']=={'type':'disabled'} and received[0]['max_tokens']==512
        assert len(events)==1 and events[0]['http_status']==status
        assert 'unit-model-key' not in json.dumps(events)
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=2)


@pytest.mark.parametrize('message',[
    {'role':'assistant','content':None,'tool_calls':[
        {'id':'partial','type':'function','function':{'name':'document_create','arguments':'{"title":"cut off'}}]},
    # Even syntactically complete JSON must not escape a length-limited turn.
    {'role':'assistant','content':None,'tool_calls':[
        {'id':'first','type':'function','function':{'name':'mail_send','arguments':'{}'}},
        {'id':'partial','type':'function','function':{'name':'document_create','arguments':'{"content":"'}}]},
    {'role':'assistant','content':'An incomplete answer'},
])
def test_truncated_turn_preserves_response_never_dispatches_or_retries(message):
    received=[];events=[];dispatched=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            received.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
            self.send_response(200);self.end_headers()
            self.wfile.write(json.dumps({'choices':[{'finish_reason':'length','message':message}]}).encode())
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        from types import SimpleNamespace
        backend=HTTPModelBackend(LLMConfig('fixture',f'http://127.0.0.1:{server.server_port}','unit-model-key'),recorder=events.append)
        with pytest.raises(ToolError,match='MODEL_OUTPUT_TRUNCATED'):
            AgentRunner(backend,SimpleNamespace(execute=lambda call:dispatched.append(call))).run('fixture task')
        assert len(received)==1 and not dispatched
        assert len(events)==1 and events[0]['response']['choices'][0]['finish_reason']=='length'
        assert events[0]['response']['choices'][0]['message']==message
        assert 'unit-model-key' not in json.dumps(events)
    finally:
        server.shutdown();server.server_close();thread.join(timeout=2)


@pytest.mark.parametrize('document,expected',[(False,4096),(True,8192)])
def test_interactive_profile_reaches_http_request_and_accepts_complete_long_reply(document,expected):
    from pathlib import Path
    from chainguard_gateway.phase10_service import interactive_model_config
    profile=interactive_model_config(Path(__file__).resolve().parents[2],{'document_scope':{'attachment_ids':[],'allow_create':document}})
    received=[];events=[]
    reply='A complete long reply. '*200
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            received.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
            self.send_response(200);self.end_headers()
            self.wfile.write(json.dumps({'choices':[{'finish_reason':'stop','message':{'role':'assistant','content':reply}}]}).encode())
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        backend=HTTPModelBackend(LLMConfig('fixture',f'http://127.0.0.1:{server.server_port}','unit-model-key'),parameters=profile['parameters'],recorder=events.append)
        result=backend.next_turn([],[])
        assert received[0]['max_tokens']==expected
        assert len(received)==1 and result.content==reply and not result.calls
        assert events[0]['request']['max_tokens']==expected
        assert 'unit-model-key' not in json.dumps(events)
    finally:
        server.shutdown();server.server_close();thread.join(timeout=2)
