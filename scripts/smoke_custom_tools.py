"""Real browser registration/admission -> DeepSeek query -> original C mail workflow.

Uses a new encrypted UI store and ports 8092/8093. No task is added to the user's
8090 workspace. Sandbox test records and one local MIME are intentional effects.
"""
import argparse
import hashlib
import json
import os
import sqlite3
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'gateway/src'),str(ROOT/'sandbox_tools/src'),str(ROOT/'agent/src')]
from chainguard_gateway.phase10_store import PublicStore
from chainguard_gateway.phase10_bridge import DockerBridge
from chainguard_gateway.phase10_audit import verify_live_entry
from chainguard_gateway.audit_verify import make_chain
from chainguard_gateway.crypto import random_id
from chainguard_gateway.canonical import canonical
from chainguard_sandbox.protocol import ToolError
from verify_demo_task import read_task,check_model,check_parameters,check_effect

READ_CHECK=r'''
import hashlib,json,sqlite3,sys
from Crypto.Cipher import AES
from chainguard_gateway.phase6_server import load
from chainguard_gateway.custom_tools import validate_manifest
from chainguard_gateway.canonical import canonical
root,c=load();v=json.load(sys.stdin);e=v['read'];r=e['result'];rev=r['revision']
with sqlite3.connect('file:'+str(root/'state.sqlite3')+'?mode=ro',uri=True) as db:
    db.row_factory=sqlite3.Row
    row=db.execute('SELECT * FROM custom_tool_reads WHERE id=?',(r['read_execution_id'],)).fetchone()
    assert row['task_id']==v['task_id'] and row['revision']==rev
    assert row['arguments_sha256']==hashlib.sha256(canonical(e['arguments'])).hexdigest()
    assert row['result_sha256']==r['sha256']==hashlib.sha256(canonical(r['data'])).hexdigest()
    stored=db.execute('SELECT * FROM custom_tool_catalog WHERE revision=?',(rev,)).fetchone();assert stored['active']==0
    blob=stored['data'];cipher=AES.new((root/'custom-data.key').read_bytes(),AES.MODE_GCM,nonce=blob[:16]);cipher.update(rev.encode())
    item=json.loads(cipher.decrypt_and_verify(blob[32:],blob[16:32]));m=item['manifest'];validate_manifest(m,item['records'])
    source=next(a for a in item['records'] if a[m['key_field']]==e['arguments']['query'])
    assert r['data']=={'record':{k:source[k] for k in m['output_fields']}}
    print(json.dumps({'revision':rev,'read_execution_id':r['read_execution_id'],'result_sha256':r['sha256'],
        'original_dataset_and_read_log_matched':True,'disabled_in_original_tool':True,'read_only_mount':True,'sqlite_mode':'ro'}))
'''

GITHUB_READ_CHECK=r'''
import hashlib,json,sqlite3,sys
from Crypto.Cipher import AES
from chainguard_gateway.phase6_server import load
from chainguard_gateway.canonical import canonical
root,c=load();v=json.load(sys.stdin);e=v['read'];r=e['result'];rev=r['revision']
with sqlite3.connect('file:'+str(root/'state.sqlite3')+'?mode=ro',uri=True) as db:
    db.row_factory=sqlite3.Row
    row=db.execute('SELECT * FROM custom_tool_reads WHERE id=?',(r['read_execution_id'],)).fetchone()
    assert row['task_id']==v['task_id'] and row['revision']==rev
    assert row['arguments_sha256']==hashlib.sha256(canonical(e['arguments'])).hexdigest()
    assert row['result_sha256']==r['sha256']==hashlib.sha256(canonical(r['data'])).hexdigest()
    saved=db.execute('SELECT * FROM custom_github_results WHERE id=?',(r['read_execution_id'],)).fetchone();assert saved['status']=='OK'
    blob=saved['data'];cipher=AES.new((root/'custom-data.key').read_bytes(),AES.MODE_GCM,nonce=blob[:16]);cipher.update(r['read_execution_id'].encode())
    saved_data=json.loads(cipher.decrypt_and_verify(blob[32:],blob[16:32]));assert saved_data['data']==r['data']
    if 'repository_policy' in r:assert saved_data['repository_policy']==r['repository_policy'] and saved_data['reader_policy']['allowed'] is True
    assert db.execute('SELECT active FROM custom_tool_catalog WHERE revision=?',(rev,)).fetchone()[0]==0
    print(json.dumps({'fetch_id':saved['fetch_id'],'read_execution_id':r['read_execution_id'],'revision':rev,'result_sha256':r['sha256'],'tool_persistent_record_matched':True,'sqlite_mode':'ro'}))
'''

GITHUB_FETCH_CHECK=r'''
import hashlib,json,sqlite3,sys
v=json.load(sys.stdin)
with sqlite3.connect('file:/sandbox/github.sqlite3?mode=ro',uri=True) as db:
    db.row_factory=sqlite3.Row
    row=db.execute('SELECT * FROM fetches WHERE id=?',(v['fetch_id'],)).fetchone();assert row['status']=='OK' and row['http_status']==200
    data=json.loads(row['data']);raw=json.loads(row['raw']);assert data==v['data'] and row['query']==data['record']['resource']
    assert data['source']['response_sha256']==hashlib.sha256(row['raw']).hexdigest()
    record=data['record'];assert raw['html_url'].lower()==record['url']
    if record['kind']=='repository':
        assert raw['full_name'].lower()==record['repository'] and raw['private'] is False
        assert raw['stargazers_count']==record['stars'] and raw['open_issues_count']==record['open_issues']
    else:assert raw['number']==record['number'] and raw['title'][:500]==record['title'] and raw['body'][:4000]==record['body'] and raw['state']==record['state']
    print(json.dumps({'fetch_id':v['fetch_id'],'response_sha256':data['source']['response_sha256'],'original_https_response_matched':True,'http_status':200,'sqlite_mode':'ro'}))
'''

def inspect_github(c,private,b):
    """Offline read of actual model/tool/HTTPS responses. Never re-fetch mutable GitHub."""
    private=Path(private).resolve()
    if not private.is_relative_to(ROOT/'.local/custom-tools'):raise ValueError('Unexpected test store')
    bridge=DockerBridge(c);records=bridge.snapshot();proofs=[]
    for case in b['cases']:
        job,events=read_task(private,case['job_id']);task=job['grant']['task_id']
        assert job['scheduler_state']=='READ_COMPLETED' and job['allowed_recipients']==[] and not [r for r in records if r['task_id']==task]
        reads=[e for e in events if e['kind']=='AGENT_ATTEMPT'];assert reads
        assert all(e['tool_name']==case['name'] and e['tool_executed'] is True and e['result']['trust']=='untrusted' for e in reads)
        read=reads[0];grant=job['custom_tools'][0]
        assert grant==dict(name=case['name'],revision=case['revision'],allowed_keys=[case['query']])
        assert read['arguments']=={'query':case['query']}
        exchanges=[e['exchange'] for e in events if e['kind']=='MODEL_EXCHANGE'];assert exchanges
        assert all(e['http_status']==200 and e['request']['model']=='deepseek-flash' for e in exchanges)
        matches=sum(1 for e in exchanges for choice in e['response'].get('choices',[]) for call in choice['message'].get('tool_calls') or [] if call['function']['name'] in {case['name'],case['name'].replace('.','_')} and canonical(json.loads(call['function']['arguments']))==canonical(read['arguments']))
        assert matches>0 and any(canonical(json.loads(m['content']))==canonical(read['result']) for e in exchanges for m in e['request']['messages'] if m['role']=='tool')
        def observer(volume,code,value):return json.loads(bridge.docker(['run','--rm','-i','--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true','--mount','type=volume,src='+volume+',dst=/sandbox,readonly',c['image'],'python','-c',code],value))
        tool=observer(c['containers']['tool'],GITHUB_READ_CHECK,{'task_id':task,'read':read})
        source=observer(c['github_reader']['volume'],GITHUB_FETCH_CHECK,{'fetch_id':tool['fetch_id'],'data':read['result']['data']})
        with sqlite3.connect((private.parent/'public.sqlite3').as_uri()+'?mode=ro',uri=True) as db:entry=json.loads(db.execute('SELECT data FROM actions WHERE entry_id=?',('interactive-'+case['job_id'][2:],)).fetchone()[0])
        checked=verify_live_entry(None,entry);assert checked['status']=='READ_ONLY_OBSERVATION' and checked['transactions']==[]
        assert any(r['read_execution_id']==tool['read_execution_id'] for r in entry['read_observations'])
        proofs.append(dict(job_id=case['job_id'],resource=case['query'],model_response_matches=matches,tool_proof=tool,source_proof=source,audit_status=checked['status']))
    return {'cases':proofs,'new_sandbox_mails':0,'chain_transactions':0}

def inspect_saved(c,private,b):
    """Read original encrypted files/volumes/chain; no model, signing or dispatch."""
    private=Path(private).resolve()
    if not private.is_relative_to(ROOT/'.local/custom-tools'):raise ValueError('Unexpected test store')
    bridge=DockerBridge(c);job,events=read_task(private,b['job_id'])
    records=[r for r in bridge.snapshot() if r['task_id']==job['grant']['task_id']];assert len(records)==1
    record=records[0];observation=bridge.observe(record['action_id'],True)
    chain=make_chain(c['deployment'],[f'http://127.0.0.1:{p}' for p in range(8545,8549)])
    checked=verify_live_entry(chain,dict(record,entry_id='interactive-'+job['id'][2:],group='C',observed_mail_count=observation['mail_count']))
    params,matches=check_model(job,events,json.loads((ROOT/'evaluation/live_plan.json').read_text(encoding='utf8')))
    committed=check_parameters(bridge,record['action_id'],params)
    assert committed['params_match_model'] and committed['params_commit_valid'];check_effect('finalized',record,observation,checked,params)
    read=next(e for e in events if e['kind']=='AGENT_ATTEMPT' and e['tool_name']==b['name'])
    grant=next(g for g in job['custom_tools'] if g['name']==b['name'] and g['revision']==read['result']['revision'])
    assert read['arguments']['query'] in grant['allowed_keys']
    model_reads=sum(1 for e in events if e['kind']=='MODEL_EXCHANGE' and e['exchange'].get('http_status')==200
        for choice in e['exchange']['response'].get('choices',[]) for call in choice['message'].get('tool_calls') or []
        if call['function']['name'] in {b['name'],b['name'].replace('.','_')} and canonical(json.loads(call['function']['arguments']))==canonical(read['arguments']))
    assert model_reads>0
    assert any(canonical(json.loads(m['content']))==canonical(read['result']) for e in events if e['kind']=='MODEL_EXCHANGE'
        for m in e['exchange']['request']['messages'] if m['role']=='tool')
    proof=json.loads(bridge.docker(['run','--rm','-i','--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true','--mount','type=volume,src='+c['containers']['tool']+',dst=/sandbox,readonly',c['image'],'python','-c',READ_CHECK],{'task_id':job['grant']['task_id'],'read':read}))
    return dict(job_id=job['id'],task_id=job['grant']['task_id'],action_id=record['action_id'],read_proof=proof,verification=checked,parameters=committed,model_response_matches=matches,custom_model_response_matches=model_reads,mime_sha256=observation['messages'][0]['mime_sha256'])

def inspect_examples(c,private,b):
    """Verify R0 examples from original encrypted stores, not browser labels."""
    private=Path(private).resolve()
    if not private.is_relative_to(ROOT/'.local/custom-tools'):raise ValueError('Unexpected test store')
    bridge=DockerBridge(c);records=bridge.snapshot();proofs=[]
    plan=json.loads((ROOT/'evaluation/live_plan.json').read_text(encoding='utf8'))
    for case in b['cases']:
        job,events=read_task(private,case['job_id']);task=job['grant']['task_id']
        assert job['scheduler_state']=='READ_COMPLETED' and job['allowed_recipients']==[]
        assert not [r for r in records if r['task_id']==task]
        reads=[e for e in events if e['kind']=='AGENT_ATTEMPT'];assert reads
        assert all(e['tool_name']==case['name'] and e['tool_executed'] is True and e['result']['trust']=='untrusted' for e in reads)
        read=reads[0];grant=next(g for g in job['custom_tools'] if g['name']==case['name'])
        assert grant['revision']==read['result']['revision']==case['revision']
        assert read['arguments']['query']==case['query'] and grant['allowed_keys']==[case['query']]
        exchanges=[e['exchange'] for e in events if e['kind']=='MODEL_EXCHANGE'];assert exchanges
        for exchange in exchanges:
            assert exchange['http_status']==200 and exchange['request']['model']==plan['model']
            assert all(exchange['request'].get(k)==v for k,v in plan['parameters'].items())
        matches=sum(1 for e in exchanges for choice in e['response'].get('choices',[])
            for call in choice['message'].get('tool_calls') or [] if call['function']['name'] in {case['name'],case['name'].replace('.','_')}
            and canonical(json.loads(call['function']['arguments']))==canonical(read['arguments']))
        assert matches>0
        assert any(canonical(json.loads(m['content']))==canonical(read['result']) for e in exchanges for m in e['request']['messages'] if m['role']=='tool')
        proof=json.loads(bridge.docker(['run','--rm','-i','--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true','--mount','type=volume,src='+c['containers']['tool']+',dst=/sandbox,readonly',c['image'],'python','-c',READ_CHECK],{'task_id':task,'read':read}))
        with sqlite3.connect((private.parent/'public.sqlite3').as_uri()+'?mode=ro',uri=True) as db:
            entry=json.loads(db.execute('SELECT data FROM actions WHERE entry_id=?',('interactive-'+case['job_id'][2:],)).fetchone()[0])
        checked=verify_live_entry(None,entry)
        assert checked['status']=='READ_ONLY_OBSERVATION' and checked['transactions']==[]
        assert any(r['revision']==case['revision'] and r['read_execution_id']==proof['read_execution_id'] for r in entry['read_observations'])
        proofs.append(dict(example_id=case['example_id'],job_id=case['job_id'],task_id=task,name=case['name'],revision=case['revision'],read_proof=proof,model_response_matches=matches,audit_status=checked['status'],high_risk_actions=0))
    assert {p['example_id'] for p in proofs}=={'contacts','inventory'}
    return {'cases':proofs,'new_sandbox_mails':0,'chain_transactions':0}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--verify-source',type=Path);p.add_argument('--examples',action='store_true',help='Run contact/inventory read-only examples; no mail');p.add_argument('--management',action='store_true',help='Exercise file imports, revisions and task preparation with real read-only Agent calls');p.add_argument('--github',action='store_true',help='Real public GitHub repository and Issue reads');a=p.parse_args()
    examples_mode=a.examples or a.management or a.github
    out=a.out.resolve()
    if out.exists() or not out.is_relative_to(ROOT/'results/custom-tools'):raise ValueError('New custom-tools evidence directory required')
    out.mkdir(parents=True);c=json.loads(a.config.read_text(encoding='utf8'));bridge=DockerBridge(c)
    if a.verify_source:
        source=a.verify_source.resolve();original=json.loads((source/'smoke.json').read_text(encoding='utf8'))
        if original['status']!='PASS':raise ValueError('Completed original evidence required')
        b=json.loads((source/'browser/browser.json').read_text(encoding='utf8'))
        inspector=inspect_github if b.get('mode')=='github_live' else inspect_examples if b.get('mode') in {'contact_inventory_examples','contact_inventory_management'} else inspect_saved
        report=dict(status='PASS',model_or_tool_reexecuted=False,source=str(source),source_smoke_sha256=hashlib.sha256((source/'smoke.json').read_bytes()).hexdigest(),**inspector(c,original['private_state'],b))
        (out/'verification.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
        print(json.dumps({'status':'PASS','model_or_tool_reexecuted':False}));return
    private=ROOT/'.local/custom-tools'/uuid.uuid4().hex;private.mkdir(parents=True)
    public=private/'public.sqlite3';PublicStore(public)
    audit=dict(port=8093,public_db=str(public),deployment=c['deployment'],static=str(ROOT/'dashboard/dist'))
    (private/'audit.json').write_text(json.dumps(audit))
    runtime=dict(c,port=8092,private_root=str(private/'private'),public_db=str(public),audit_config=str(private/'audit.json'))
    config=private/'runtime.json';config.write_text(json.dumps(runtime))
    report=dict(status='RUNNING',mode='github_live' if a.github else 'contact_inventory_management' if a.management else 'contact_inventory_examples' if a.examples else 'custom_read_and_mail',real_llm=True,asr_measured=False,private_state=str(private/'private'),runtime_config=str(config),user_workspace_tasks_created=0)
    save=lambda:(out/'smoke.json').write_text(json.dumps(report,indent=2)+'\n')
    env=dict(os.environ,PYTHONPATH=os.pathsep.join(str(ROOT/d) for d in ['gateway/src','sandbox_tools/src','agent/src']),PYTHONUTF8='1')
    processes=[];logs=[]
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        save()
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
        browser_out=out/'browser';log=(out/'browser.txt').open('wb');logs.append(log)
        browser_script='console/tests/github-tools-browser.mjs' if a.github else 'console/tests/custom-management-browser.mjs' if a.management else 'console/tests/custom-examples-browser.mjs' if a.examples else 'console/tests/custom-tools-browser.mjs'
        browser=subprocess.Popen(['node',browser_script,str(config),str(a.config.resolve()),str(browser_out)],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW);processes.append(browser)
        deadline=time.monotonic()+300;probes=False
        while browser.poll() is None:
            if time.monotonic()>deadline:raise RuntimeError('Real browser smoke timed out')
            file=browser_out/'browser.json'
            if file.exists():
                try:b=json.loads(file.read_text(encoding='utf8'))
                except json.JSONDecodeError:time.sleep(.1);continue
                if b.get('step')=='VERIFY_TOOL_SCOPE' and not probes:
                    if examples_mode:
                        report['scope_probes']=[]
                        for case in b['cases']:
                            job,_=read_task(private/'private',case['job_id']);task=job['grant']['task_id'];errors={}
                            for probe,request,path in [('other_record',dict(task_id=task,tool_name=case['name'],revision=case['revision'],arguments={'query':case['forbidden_key']}),'/agent/v1/custom-tools/query'),
                                ('read_only_send',dict(task_id=task,tool_name='mail.send',params={'to':['alice@inbox.chainguard.invalid'],'subject':'Denied read-only example probe','body':'Must not send'}),'/v1/agent/actions/propose')]:
                                try:bridge.call('agent',dict(op='request',method='POST',path=path,body=request,key=random_id()))
                                except ToolError as error:errors[probe]=error.code
                                else:raise AssertionError('Read-only example scope bypassed')
                                assert errors[probe]=='UNAUTHORIZED_SCOPE'
                            report['scope_probes'].append(dict(resource=case['query'],**errors))
                        probes=True;save();(browser_out/'scope-check.done').write_text('PASS\n');continue
                    job,events=read_task(private/'private',b['job_id']);task=job['grant']['task_id']
                    request=dict(task_id=task,tool_name=b['name'],revision=b['revision'],arguments={'query':'DEMO-2'})
                    try:bridge.call('agent',dict(op='request',method='POST',path='/agent/v1/custom-tools/query',body=request,key=random_id()))
                    except ToolError as error:report['direct_out_of_scope_query_rejected']=error.code
                    else:raise AssertionError('Out of scope tool record exposed')
                    assert report['direct_out_of_scope_query_rejected']=='UNAUTHORIZED_SCOPE'
                    probes=True;save();(browser_out/'scope-check.done').write_text('PASS\n')
            time.sleep(.3)
        if browser.returncode:raise RuntimeError('Real browser failed; see retained browser evidence')
        b=json.loads((browser_out/'browser.json').read_text(encoding='utf8'));assert b['status']=='PASS'
        if examples_mode:
            report.update(status='PASS',**(inspect_github if a.github else inspect_examples)(c,private/'private',b));save()
            print(json.dumps({'status':'PASS','real_llm':True,'examples':2,'new_sandbox_mails':0}));return
        evidence=inspect_saved(c,private/'private',b)
        try:bridge.call('agent',dict(op='request',method='POST',path='/agent/v1/custom-tools/query',body=dict(task_id=evidence['task_id'],tool_name=b['name'],revision=b['revision'],arguments={'query':'DEMO-1'}),key=random_id()))
        except ToolError as error:report['direct_query_after_disable']=error.code
        else:raise AssertionError('Disabled tool still executed')
        assert report['direct_query_after_disable']=='POLICY_REVOKED'
        report.update(status='PASS',new_sandbox_mails=1,**evidence);save()
        print(json.dumps({'status':'PASS','real_llm':True,'new_sandbox_mails':1,'user_workspace_tasks_created':0}))
    except Exception as error:
        report.update(status='FAIL',error_type=type(error).__name__)
        if (out/'browser/browser.json').exists():
            failed=json.loads((out/'browser/browser.json').read_text(encoding='utf8'))
            for case in failed.get('cases',[failed]):
                if case.get('revision'):
                    try:report.setdefault('failed_test_tools_disabled',[]).append(bridge.disable_custom({'revision':case['revision']})['active'] is False)
                    except ToolError:report.setdefault('failed_test_tools_disabled',[]).append(False)
        save();raise
    finally:
        for process in reversed(processes):
            if process.poll() is None:process.terminate();process.wait(timeout=10)
        for log in logs:log.close()

if __name__=='__main__':main()
