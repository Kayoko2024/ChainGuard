"""Trusted localhost control-plane bridge, fixed commands only. Never passed to model."""
import json
import subprocess
import threading
import time
from .canonical import canonical
from chainguard_sandbox.protocol import ToolError


class DockerBridge:
    def __init__(self,config):
        self.config=config; self.prefix=['wsl.exe','-d','Ubuntu','-u','root','--','docker']
        self.last_refresh=0; self.lock=threading.RLock()
    def docker(self,args,value=None,timeout=45):
        try:p=subprocess.run(self.prefix+args,input=canonical(value) if value is not None else None,capture_output=True,timeout=timeout)
        except (OSError,subprocess.TimeoutExpired):raise ToolError('BACKEND_UNAVAILABLE') from None
        if p.returncode: raise ToolError('BACKEND_UNAVAILABLE')
        return p.stdout
    def cli(self,kind,command,value=None):
        raw=self.docker(['exec','-i',self.config['containers'][kind],'python','-m','chainguard_gateway.phase10_client',command],value or {})
        result=json.loads(raw)
        if not result['ok']: raise ToolError(result['error'])
        return result['result']
    def refresh(self):
        with self.lock:
            if time.monotonic()-self.last_refresh<300: return
            tokens=self.cli('gateway','tokens')
            # Each volume gets only its own subject. JWT lifetime stays <=900s.
            for kind in ['requester','biz','security','agent']:
                subset={kind:tokens[kind]}
                if kind=='requester': subset['executor']=tokens['executor']
                self.docker(['exec','-i',self.config['containers'][kind],'python','-c',
                    "import sys,json; from chainguard_gateway.phase6_server import load; r,c=load(); p=r/'tokens.new'; p.write_text(json.dumps(json.load(sys.stdin))); p.replace(r/'tokens.json')"],subset)
            self.last_refresh=time.monotonic()
    def call(self,kind,value):
        if kind not in {'requester','biz','security','agent'}: raise ToolError('FORBIDDEN')
        self.refresh(); return self.cli(kind,'call',value)
    def snapshot(self): return self.cli('gateway','snapshot')
    def web_snapshot(self,cursor=0):return self.cli('gateway','web-snapshot',{'cursor':cursor})
    def grant_library(self,value): return self.cli('tool','library-grant',value)
    def install_custom(self,value): return self.cli('tool','custom-install',value)
    def disable_custom(self,value): return self.cli('tool','custom-disable',value)
    def grant_custom(self,value): return self.cli('tool','custom-grant',value)
    def session_install(self,value):
        self.cli('tool','session-install',value)
        return self.cli('gateway','session-install',value)
    def session_snapshot(self):return self.cli('gateway','session-list')
    def session_review(self,id):return self.cli('gateway','session-review',{'call_id':id})
    def session_approve(self,id,signature):return self.cli('gateway','session-approve',{'call_id':id,'signature':signature})
    def session_flush(self):return self.cli('gateway','session-flush',{'force':True})
    def admission_submit(self,value):return self.cli('gateway','admission-submit',value)
    def conversation(self,op,value):
        if op in {'install','bind','close','activate','preflight'}:
            tool=self.cli('tool','conversation-'+op,value)
        else:tool=None
        if op=='preflight':
            gateway=self.cli('gateway','conversation-'+op,value)
            if tool['grant_digest']!=gateway['grant_digest']:raise ToolError('APPROVAL_INVALID')
            return dict(gateway,used=max(tool['used'],gateway['used']),checked_gates=2)
        if op=='activate':
            gateway=self.cli('gateway','conversation-'+op,value)
            if not tool.get('active') or not gateway.get('active') or tool['grant_digest']!=gateway['grant_digest']:raise ToolError('APPROVAL_INVALID')
            return dict(gateway,checked_gates=2)
        return self.cli('gateway','conversation-'+op,value)
    def github_fetch_stats(self):
        reader=self.config.get('github_reader')
        if not reader:raise ToolError('STATE_CONFLICT')
        code="import sqlite3,json; d=sqlite3.connect('file:/sandbox/github.sqlite3?mode=ro',uri=True); print(json.dumps(dict(total=d.execute('SELECT COUNT(*) FROM fetches').fetchone()[0],ok=d.execute(\"SELECT COUNT(*) FROM fetches WHERE status='OK'\").fetchone()[0])))"
        return json.loads(self.docker(['run','--rm','--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true','--mount','type=volume,src='+reader['volume']+',dst=/sandbox,readonly',self.config['image'],'python','-c',code]))
    def fault(self,action_id,hold): return self.cli('gateway','fault',{'action_id':action_id,'hold':hold})
    def observe(self,action_id,include_mime=False):
        args=['run','--rm','-i','--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true',
            '--mount','type=volume,src='+self.config['containers']['tool']+',dst=/sandbox,readonly',self.config['image'],
            'python','-m','chainguard_gateway.phase10_client','observe']
        result=json.loads(self.docker(args,{'action_id':action_id,'include_mime':include_mime}))
        if not result['ok']: raise ToolError(result['error'])
        return result['result']
