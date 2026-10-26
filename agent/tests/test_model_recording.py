"""Local HTTP protocol fixtures, not real LLM experiment samples."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import pytest
from chainguard_agent.model import HTTPModelBackend, LLMConfig
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
