"""New browser task -> real DeepSeek -> reviewed HTTP request; verify original encrypted evidence."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
import urllib.request
import uuid
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'gateway/src'),str(ROOT/'sandbox_tools/src'),str(ROOT/'agent/src')]
from chainguard_gateway.phase10_store import PublicStore
from chainguard_gateway.phase10_bridge import DockerBridge
from chainguard_gateway.canonical import canonical
from chainguard_gateway.crypto import random_id
from chainguard_sandbox.protocol import ToolError
from verify_demo_task import read_task

TOOL_CHECK=r'''
import json,sqlite3,hashlib,sys
from Crypto.Cipher import AES
from chainguard_gateway.phase6_server import load
from chainguard_gateway.canonical import canonical
root,c=load();v=json.load(sys.stdin);r=v['result'];rev=r['revision'];id=r['http_execution_id']
def decrypt(context,raw):
 cipher=AES.new((root/'custom-data.key').read_bytes(),AES.MODE_GCM,nonce=raw[:16]);cipher.update(context.encode());return json.loads(cipher.decrypt_and_verify(raw[32:],raw[16:32]))
with sqlite3.connect('file:'+str(root/'state.sqlite3')+'?mode=ro',uri=True) as db:
 db.row_factory=sqlite3.Row
 original=db.execute('SELECT * FROM custom_http_results WHERE id=?',(id,)).fetchone();assert original['status']=='OK' and decrypt(id,original['data'])==r
 row=db.execute('SELECT * FROM custom_tool_reads WHERE id=?',(r['read_execution_id'],)).fetchone()
 assert row['task_id']==v['task_id'] and row['revision']==rev and row['result_sha256']==r['sha256']==hashlib.sha256(canonical(r['data'])).hexdigest()
 assert row['arguments_sha256']==hashlib.sha256(canonical({'query':'demo'})).hexdigest()
 catalog=db.execute('SELECT * FROM custom_tool_catalog WHERE revision=?',(rev,)).fetchone();assert catalog['active']==0
 manifest=decrypt(rev,catalog['data'])['manifest'];assert manifest['http']['method']=='POST' and manifest['http']['url']=='https://httpbin.org/anything'
 print(json.dumps(dict(tool_record_verified=True,result_sha256=r['sha256'],revision=rev,http_execution_id=id)))
'''
READER_CHECK=r'''
import json,sqlite3,hashlib,sys
from Crypto.Cipher import AES
from chainguard_gateway.canonical import canonical
v=json.load(sys.stdin);r=v['result'];id=r['http_execution_id']
with sqlite3.connect('file:/sandbox/http.sqlite3?mode=ro',uri=True) as db:
 db.row_factory=sqlite3.Row;row=db.execute('SELECT * FROM fetches WHERE id=?',(id,)).fetchone();assert row['status']=='OK'
 blob=row['data'];cipher=AES.new(open('/sandbox/http-data.key','rb').read(),AES.MODE_GCM,nonce=blob[:16]);cipher.update(id.encode());saved=json.loads(cipher.decrypt_and_verify(blob[32:],blob[16:32]))
 assert saved['result']['data']==r['data'];raw=bytes.fromhex(saved['raw_hex']);assert hashlib.sha256(raw).hexdigest()==r['data']['source']['response_sha256']
 response=json.loads(raw);assert response['json']['message']==v['marker'] and response['args']['lang']=='zh' and response['method']=='POST'
 assert db.execute('SELECT active FROM manifests WHERE revision=?',(r['revision'],)).fetchone()[0]==0
 print(json.dumps(dict(original_https_bytes_verified=True,response_sha256=hashlib.sha256(raw).hexdigest(),http_status=200)))
'''


def verify(c,private,b,*,probe_revocation=False):
    bridge=DockerBridge(c);case=b['cases'][0];job,events=read_task(private,case['job_id'])
    assert job['scheduler_state']=='READ_COMPLETED' and not job['allowed_recipients']
    reads=[e for e in events if e['kind']=='AGENT_ATTEMPT'];exchanges=[e for e in events if e['kind']=='MODEL_EXCHANGE']
    assert exchanges and reads and all(e['tool_executed'] is True and e['tool_name']==case['name'] for e in reads)
    plan=json.loads((ROOT/'evaluation/live_plan.json').read_text())
    for event in exchanges:
        exchange=event['exchange'];request=exchange['request']
        assert request['model']==plan['model'] and request.get('parallel_tool_calls') is False
        assert all(request.get(k)==v for k,v in plan['parameters'].items()) and exchange['http_status']==200
    functions=[call['function'] for e in exchanges for choice in e['exchange']['response'].get('choices',[]) for call in choice['message'].get('tool_calls') or []]
    assert any(fn['name']==case['name'].replace('.','_') and json.loads(fn['arguments'])=={'query':'demo'} for fn in functions)
    assert any(message.get('role')=='tool' and message.get('content') and case['marker'] in message['content'] for e in exchanges for message in e['exchange']['request']['messages'])
    result=reads[0]['result'];task=job['grant']['task_id']
    assert not any(r['task_id']==task for r in bridge.snapshot())
    def observer(volume,code):return json.loads(bridge.docker(['run','--rm','-i','--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true','--mount','type=volume,src='+volume+',dst=/sandbox,readonly',c['image'],'python','-c',code],{'result':result,'task_id':task,'marker':case['marker']}))
    tool=observer(c['containers']['tool'],TOOL_CHECK);reader=observer(c['http_reader']['volume'],READER_CHECK)
    with sqlite3.connect((private.parent/'public.sqlite3').as_uri()+'?mode=ro',uri=True) as db:
        entry=json.loads(db.execute('SELECT data FROM actions WHERE entry_id=?',('interactive-'+case['job_id'][2:],)).fetchone()[0])
    assert entry['risk']==1 and entry['adapter']=='http.request' and not entry['intent'] and not entry['receipt']
    assert reads[0]['result']['sha256'] in [r['sha256'] for r in entry['read_observations']]
    if probe_revocation:
        args=dict(task_id=task,tool_name=case['name'],revision=case['revision'],arguments={'query':'demo'})
        try:bridge.call('agent',dict(op='request',method='POST',path='/agent/v1/custom-tools/query',body=args,key=random_id()))
        except ToolError as e:assert e.code=='POLICY_REVOKED'
        else:raise AssertionError('Disabled HTTP tool executed')
    return {'model_exchange_count':len(exchanges),'tool_calls':len(reads),'tool':tool,'reader':reader,'public_projection_verified':True,'tool_and_reader_revoked':True,'direct_revocation_probe':probe_revocation}


def probe(c,private,b):
    bridge=DockerBridge(c);case=b['cases'][0];job,events=read_task(private,case['job_id']);task=job['grant']['task_id']
    expected=next(e['result'] for e in events if e['kind']=='AGENT_ATTEMPT')
    def count():return int(bridge.docker(['exec',c['http_reader']['container'],'python','-c',"import sqlite3;print(sqlite3.connect('file:/sandbox/http.sqlite3?mode=ro',uri=True).execute('SELECT COUNT(*) FROM fetches').fetchone()[0])"]))
    before=count();value=dict(task_id=task,tool_name=case['name'],revision=case['revision'],arguments={'query':'demo'})
    actual=bridge.call('agent',dict(op='request',method='POST',path='/agent/v1/custom-tools/query',body=value,key=random_id()))
    assert actual==expected
    errors={}
    for name,args in [('change_url',{'query':'demo','url':'https://other.example.com'}),('change_params',{'query':'demo','body':{'message':'tampered'}}),('other_profile',{'query':'not-authorized'})]:
        try:bridge.call('agent',dict(op='request',method='POST',path='/agent/v1/custom-tools/query',body=dict(value,arguments=args),key=random_id()))
        except ToolError as error:errors[name]=error.code;assert error.code in {'SCHEMA_INVALID','UNAUTHORIZED_SCOPE'}
        else:raise AssertionError('HTTP scope bypass')
    after=count();assert after==before
    return {'duplicate_returned_original':True,'rejected_calls':errors,'fetches_before':before,'fetches_after':after,'no_new_https':True}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--verify-source',type=Path);a=p.parse_args()
    out=a.out.resolve()
    if out.exists() or not out.is_relative_to(ROOT/'results/http-tools'):raise ValueError('Use new results/http-tools directory')
    out.mkdir(parents=True);c=json.loads(a.config.read_text());bridge=DockerBridge(c);report={'status':'RUNNING','real_llm':None,'asr_measured':False,'user_workspace_tasks_created':0}
    def save():(out/'smoke.json').write_text(json.dumps(report,indent=2)+'\n')
    if a.verify_source:
        source=a.verify_source.resolve();original=json.loads((source/'smoke.json').read_text());b=json.loads((source/'browser/browser.json').read_text())
        report.update(status='PASS',source=str(source),model_or_tool_reexecuted=False,**verify(c,Path(original['private_state']),b));save();print('PASS: original HTTP/model/tool evidence verified');return
    private=ROOT/'.local/http-tools'/uuid.uuid4().hex;private.mkdir(parents=True);public=private/'public.sqlite3';PublicStore(public)
    audit=dict(port=8093,public_db=str(public),deployment=c['deployment'],static=str(ROOT/'dashboard/dist'));(private/'audit.json').write_text(json.dumps(audit))
    runtime=dict(c,port=8092,private_root=str(private/'private'),public_db=str(public),audit_config=str(private/'audit.json'));config=private/'runtime.json';config.write_text(json.dumps(runtime))
    report.update(private_state=str(private/'private'),runtime_config=str(config));save()
    env=dict(os.environ,PYTHONPATH=os.pathsep.join(str(ROOT/d) for d in ['gateway/src','sandbox_tools/src','agent/src']),PYTHONUTF8='1');processes=[];logs=[]
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        for module,file in [('phase10_api',config),('phase10_audit',private/'audit.json')]:
            log=(private/(module+'.log')).open('wb');logs.append(log)
            processes.append(subprocess.Popen([sys.executable,'-m','chainguard_gateway.'+module,'--config',str(file)],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW))
        for port in [8092,8093]:
            deadline=time.monotonic()+20
            while True:
                try:
                    with opener.open(f'http://127.0.0.1:{port}/health/live',timeout=2) as r:assert json.load(r)['status']=='alive'
                    break
                except Exception:
                    if time.monotonic()>deadline:raise RuntimeError('Test Web startup failed')
                    time.sleep(.25)
        log=(out/'browser.txt').open('wb');logs.append(log)
        browser=subprocess.Popen(['node','console/tests/http-tools-browser.mjs',str(config),str(a.config.resolve()),str(out/'browser')],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW);processes.append(browser)
        deadline=time.monotonic()+240;probed=False
        while browser.poll() is None:
            if time.monotonic()>deadline:raise RuntimeError('Browser timeout')
            file=out/'browser/browser.json'
            if file.exists():
                try:current=json.loads(file.read_text())
                except json.JSONDecodeError:time.sleep(.1);continue
                if current.get('step')=='VERIFY_SCOPE' and not probed:
                    report['scope_probes']=probe(c,private/'private',current);save();probed=True;(out/'browser/scope-check.done').write_text('PASS\n')
            time.sleep(.25)
        b=json.loads((out/'browser/browser.json').read_text());report['real_llm']=b['real_llm']
        if browser.returncode or b['status']!='PASS':raise RuntimeError('Browser failed; retained original evidence')
        report.update(status='PASS',new_sandbox_mails=0,read_transactions=0,chain_transactions=None if c.get('tool_sessions') else 0,**verify(c,private/'private',b,probe_revocation=True));save();print('PASS: new browser/DeepSeek/real HTTPS flow and original encrypted evidence')
    except Exception as error:
        report.update(status='FAIL',error_type=type(error).__name__);save()
        browser=out/'browser/browser.json'
        if browser.exists():
            for case in json.loads(browser.read_text()).get('cases',[]):
                if case.get('revision'):
                    try:bridge.disable_custom({'revision':case['revision']})
                    except ToolError:pass
        raise
    finally:
        for process in reversed(processes):
            if process.poll() is None:process.terminate();process.wait(timeout=10)
        for log in logs:log.close()

if __name__=='__main__':main()
