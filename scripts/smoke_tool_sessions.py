"""Real tools + existing four Besu; model tasks and manual protocol probes are separate."""
import argparse
import copy
import json
from pathlib import Path
import secrets
import sys
import time
import os
import subprocess
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'gateway/src'),str(ROOT/'sandbox_tools/src'),str(ROOT/'agent/src')]
from chainguard_gateway.phase10_store import OperationsStore,PublicStore
from chainguard_gateway.phase10_service import Operations
from chainguard_gateway.phase10_bridge import DockerBridge
from chainguard_gateway.session_grants import hash_json,ToolPolicy
from chainguard_gateway.phase10_audit import verify_live_entry
from chainguard_gateway.audit_verify import make_chain
from chainguard_gateway.crypto import random_id
from chainguard_sandbox.protocol import ToolError

def web_smoke(c,credential_config,private,out):
    audit=dict(port=8093,public_db=str(private/'public.sqlite3'),deployment=c['deployment'],tool_sessions=c['tool_sessions'],static=str(ROOT/'dashboard/dist'))
    audit_file=private/'audit.json';audit_file.write_text(json.dumps(audit))
    runtime=dict(c,port=8092,private_root=str(private/'private'),public_db=str(private/'public.sqlite3'),audit_config=str(audit_file))
    config=private/'runtime.json';config.write_text(json.dumps(runtime))
    env=dict(os.environ,PYTHONPATH=os.pathsep.join(str(ROOT/p) for p in ['gateway/src','sandbox_tools/src','agent/src']),PYTHONUTF8='1')
    processes=[];logs=[]
    try:
        for module,file in [('phase10_api',config),('phase10_audit',audit_file)]:
            log=(private/(module+'.log')).open('wb');logs.append(log)
            processes.append(subprocess.Popen([sys.executable,'-m','chainguard_gateway.'+module,'--config',str(file)],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW))
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for port in [8092,8093]:
            deadline=time.monotonic()+20
            while True:
                try:
                    with opener.open(f'http://127.0.0.1:{port}/health/live',timeout=2) as r:assert json.load(r)['status']=='alive'
                    break
                except Exception:
                    if time.monotonic()>deadline:raise RuntimeError('Temporary web startup failed')
                    time.sleep(.25)
        with (out/'browser.txt').open('wb') as log:
            process=subprocess.Popen(['node','console/tests/tool-sessions-browser.mjs',str(config),str(credential_config.resolve()),str(out/'browser')],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW);processes.append(process)
            process.wait(timeout=240)
        result=json.loads((out/'browser/browser.json').read_text(encoding='utf8'))
        if process.returncode or result['status']!='PASS':raise RuntimeError('Real browser acceptance failed; see retained evidence')
        return result
    finally:
        for process in reversed(processes):
            if process.poll() is None:process.terminate();process.wait(timeout=10)
        for log in logs:log.close()

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--web',action='store_true');p.add_argument('--web-only-source',type=Path);a=p.parse_args()
    out=a.out.resolve()
    if out.exists() or not out.is_relative_to(ROOT/'results/sessions'):raise ValueError('New results/sessions output required')
    out.mkdir(parents=True);c=json.loads(a.config.read_text());private=ROOT/'.local/sessions'/secrets.token_hex(12);store=OperationsStore(private/'private');public=PublicStore(private/'public.sqlite3')
    b=DockerBridge(c);ops=Operations(store,public,b,c);report=dict(status='RUNNING',private_root=str(private),tests={},llm_tasks=[],transactions=[],mail_sent=0)
    def save():(out/'smoke.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    def check(name,condition):
        report['tests'][name]=bool(condition);save()
        if not condition:raise AssertionError(name)
    if a.web_only_source:
        original=json.loads((a.web_only_source/'smoke.json').read_text(encoding='utf8'))
        assert original['status']=='PASS'
        report.update(protocol_source=str(a.web_only_source),policy=c['tool_sessions'],batch_evidence=[]);save()
        try:
            report['web_acceptance']=web_smoke(c,a.config,private,out);report.update(status='PASS',new_business_jobs=1);save()
        except Exception as error:report.update(status='FAIL',error_type=type(error).__name__);save();raise
        finally:
            for item in ops.custom_registry.listing():
                if item['state']=='ACTIVE':
                    try:ops.set_custom_active(item['manifest']['revision'],item['manifest']['revision'],False,(item.get('admission') or {}).get('risk_level') or 'LOW')
                    except Exception:report['cleanup']='PENDING'
            save()
        print(json.dumps(dict(status='PASS',web_tasks=1,protocol_reexecuted=False)));return
    def body(tool,keys,maximum=1):return dict(task_text='Call '+tool['name']+' exactly once with query='+keys[0]+'. Report only the returned record; do not send mail or use another tool.',allowed_tools=[tool['name']],allowed_document_ids=[],read_mailboxes=[],allowed_recipients=[],custom_tools=[dict(name=tool['name'],revision=tool['revision'],allowed_keys=keys)],session_grant=dict(duration_seconds=3600,max_calls=maximum))
    def manual_task(tool,keys,maximum=5,lifetime=900):
        task=b.call('requester',dict(op='create_task',key=random_id(),body=dict(task_text='Synthetic manual session protocol probe',agent=c['signers']['agent'],allowed_tools=['mail.send'],resource_scopes=['ORG_A_INTERNAL_MAIL'],allowed_document_ids=[],allowed_recipients=[],expires_at=str(int(time.time())+900),max_risk=2,max_actions=1,allow_sandbox_delete=False)))
        scope=dict(name=tool['name'],revision=tool['revision'],allowed_keys=keys)
        b.grant_custom(dict(task_id=task['task_id'],agent=task['agent'],tools=[scope],expires_at=int(task['expires_at'])))
        pol=ToolPolicy(c['tool_sessions'],['http://127.0.0.1:8545','http://127.0.0.1:8547']);scope['generation']=pol.admission(tool['revision'])['generation']
        now=int(time.time());m=dict(requester=task['requester'],agent=task['agent'],taskId=task['task_id'],toolsHash=hash_json([scope]),nonce=secrets.randbits(52),issuedAt=now,expiresAt=now+lifetime,maxCalls=maximum)
        e=dict(message=m,scopes=[scope],signature=b.call('requester',dict(op='sign-session',message=m))['signature']);b.session_install(e)
        return task,e
    def query(task,tool,k,key=None):return b.call('agent',dict(op='request',method='POST',path='/agent/v1/custom-tools/query',key=key or random_id(),body=dict(task_id=task['task_id'],tool_name=tool['name'],revision=tool['revision'],arguments={'query':k})))
    tool=None
    save()
    try:
        name='custom.session_'+secrets.token_hex(3)
        registration=dict(name=name,label='Session contacts acceptance',description='Lookup exact authorized synthetic contact ID.',adapter='dataset.lookup',key_field='id',output_fields=['id','name'],records=[dict(id='A',name='Synthetic Alice'),dict(id='B',name='Synthetic Bob')])
        tool=ops.register_custom(registration);check('submitter_omits_risk',tool['risk_level'] is None)
        try:ops.set_custom_active(tool['revision'],tool['revision'],True)
        except ToolError as error:check('missing_review_risk_rejected',error.code=='RISK_LABEL_REQUIRED')
        else:raise AssertionError('risk required')
        tool=ops.set_custom_active(tool['revision'],tool['revision'],True,'LOW');report['transactions'].append(tool['admission']['evidence']);save()
        id=random_id();ops.create(id,body(tool,['A','B']));ops.run_agent(id);ops.sync();job=ops.detail(id)
        report['llm_tasks'].append(dict(id=id,state=job['state'],model_exchanges=sum(e['kind']=='MODEL_EXCHANGE' for e in job['events'])));save()
        check('real_agent_LOW_executes',job['state']=='READ_COMPLETED' and any(e['kind']=='AGENT_ATTEMPT' and e.get('tool_executed') is True for e in job['events']))
        task=job['grant'];call_id=random_id();pending=query(task,tool,'B',call_id);check('quota_exhausted_no_dispatch',pending.get('error_code')=='SESSION_EXHAUSTED')
        ops.sync();review=b.session_review(call_id)
        ops.approve_tool_call(id,call_id,'biz',review['digest']);one=ops.execute_tool_call(id,call_id)
        check('single_organization_still_pending',one['state']=='AWAITING_TOOL_APPROVAL')
        ops.approve_tool_call(id,call_id,'security',review['digest']);completed=ops.execute_tool_call(id,call_id)
        check('two_org_fallback_executes',completed['state']=='READ_COMPLETED')
        before=len([o for o in b.session_snapshot()['observations'] if o['log']['task_id']==task['task_id']]);query(task,tool,'B',call_id)
        after=len([o for o in b.session_snapshot()['observations'] if o['log']['task_id']==task['task_id']]);check('same_call_returns_original_no_extra_log',before==after==2)
        try:query(task,tool,'UNAUTHORIZED')
        except ToolError as error:check('out_of_scope_refused',error.code=='UNAUTHORIZED_SCOPE')
        else:raise AssertionError('scope bypass')
        # New manual task: nonce reuse / altered signature / short session expiry / lost-response boundary.
        probe,e=manual_task(tool,['A','B'],maximum=5)
        tampered=copy.deepcopy(e);tampered['message']['maxCalls']=999
        try:b.session_install(tampered)
        except ToolError as error:check('signature_parameter_tamper_rejected',error.code=='APPROVAL_INVALID')
        else:raise AssertionError('tamper bypass')
        reused=copy.deepcopy(e);reused['message']['taskId']=random_id();reused['signature']=b.call('requester',dict(op='sign-session',message=reused['message']))['signature']
        try:b.session_install(reused)
        except ToolError as error:check('signed_nonce_replay_rejected',error.code=='REPLAY_BLOCKED')
        else:raise AssertionError('nonce bypass')
        expired,_=manual_task(tool,['A'],lifetime=12);time.sleep(13)
        check('expired_session_falls_back',query(expired,tool,'A').get('error_code')=='SESSION_EXPIRED')
        request=dict(task_id=probe['task_id'],agent=probe['agent'],revision=tool['revision'],tool_name=tool['name'],arguments={'query':'A'});unknown_id=random_id()
        code="import sys,json;from chainguard_gateway.phase6_server import load,client;from chainguard_gateway.session_runtime import access_for;from chainguard_sandbox.protocol import ToolError;r,c=load();v=json.load(sys.stdin);a=access_for(r,c)\ndef lost(auth):\n client(r,c['tool_client']).request('POST','/internal/v1/custom-tools/query',dict(v['request'],session_authorization=auth,session_call_id=v['id']),v['id'])\n raise ToolError('EXECUTION_UNKNOWN')\ntry:a.execute(v['request'],v['id'],lost,requester=v['requester'])\nexcept ToolError as e:print(json.dumps(dict(error=e.code,state=a.call(v['id'])['state'])))"
        lost=json.loads(b.docker(['exec','-i',c['containers']['gateway'],'python','-c',code],dict(request=request,id=unknown_id,requester=probe['requester'])))
        check('real_tool_response_lost_UNKNOWN',lost==dict(error='EXECUTION_UNKNOWN',state='STARTED'))
        check('UNKNOWN_never_redispatched',query(probe,tool,'A',unknown_id).get('status')=='UNKNOWN')
        # HIGH label invalidates the previous LOW session without changing any frozen R2 ABI.
        tool=ops.set_custom_active(tool['revision'],tool['revision'],True,'HIGH');report['transactions'].append(tool['admission']['evidence']);save()
        id2=random_id();ops.create(id2,body(tool,['A']));ops.run_agent(id2);ops.sync();high=ops.detail(id2)
        report['llm_tasks'].append(dict(id=id2,state=high['state'],model_exchanges=sum(e['kind']=='MODEL_EXCHANGE' for e in high['events'])));save()
        check('real_agent_HIGH_awaits_approval',high['state']=='AWAITING_TOOL_APPROVAL')
        hcall=next(x for x in high['custom_calls'] if x['state']=='AWAITING_TOOL_APPROVAL')
        for role in ['biz','security']:ops.approve_tool_call(id2,hcall['call_id'],role,hcall['digest'])
        check('HIGH_two_org_tool_verification',ops.execute_tool_call(id2,hcall['call_id'])['state']=='READ_COMPLETED')
        # Force only the batch timer for demo; the same periodic publisher performs the real transaction.
        status=b.session_flush()
        deadline=time.monotonic()+35
        while time.monotonic()<deadline:
            current=b.session_snapshot()
            selected=[o for o in current['observations'] if o['log']['task_id'] in {task['task_id'],probe['task_id'],high['grant']['task_id']}]
            if selected and all(o['status']=='ANCHORED' for o in selected):break
            b.session_flush();time.sleep(.5)
        check('one_batch_covers_multiple_calls',len(selected)>=4 and all(o['status']=='ANCHORED' for o in selected) and len({o['tx_hash'] for o in selected})==1)
        ops.sync();chain=make_chain(c['deployment'],[f'http://127.0.0.1:{p}' for p in range(8545,8549)]);chain.tool_sessions=c['tool_sessions']
        rows=[r for r in public.actions() if r.get('batch_observation') and r['task_id'] in {task['task_id'],probe['task_id'],high['grant']['task_id']}]
        checks=[verify_live_entry(chain,row) for row in rows];check('four_node_merkle_and_receipt_verification',all(v['status']=='BATCH_VERIFIED' and v['evidence']['checked_nodes']==4 for v in checks))
        wrong=copy.deepcopy(rows[0]);wrong['batch_observation']['log']['outcome']='FORGED';check('tampered_log_fails_merkle',verify_live_entry(chain,wrong)['status']=='INVALID')
        report['batch_evidence']=selected;report['independent_verification']=checks;report['policy']=c['tool_sessions'];report['tool_revision']=tool['revision'];report['new_business_jobs']=2
        report['model_attack_success_rate']=None;report['status']='PASS';save()
        if a.web:
            report['status']='RUNNING';save();report['web_acceptance']=web_smoke(c,a.config,private,out);report['new_business_jobs']=3;report['status']='PASS';save()
    except Exception as error:
        report.update(status='FAIL',error_type=type(error).__name__,error_code=error.code if isinstance(error,ToolError) else str(error)[:120]);save();raise
    finally:
        if tool:
            try:
                result=ops.set_custom_active(tool['revision'],tool['revision'],False,tool.get('risk_level') or 'LOW');report['cleanup']='TOOL_DISABLED';report['transactions'].append(result['admission']['evidence'])
            except Exception as error:report['cleanup']='PENDING_'+type(error).__name__
            save()
    print(json.dumps(dict(status=report['status'],tests=len(report['tests']),llm_tasks=len(report['llm_tasks']),mail_sent=0)))

if __name__=='__main__':main()
