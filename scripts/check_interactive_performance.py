"""Real HTTP async/soft-hide acceptance: deterministic proposal, real four-node mail.

Uses a new private business database and temporary 8092/8093 servers. One synthetic
local mail; no LLM request, no external mail and no deletion of original evidence.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import threading
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/p) for p in ['gateway/src','sandbox_tools/src','agent/src']]
import httpx
import uvicorn
from chainguard_gateway.crypto import random_id
from chainguard_gateway.phase10_store import OperationsStore,PublicStore
from chainguard_gateway.phase10_service import Operations
from chainguard_gateway.phase10_bridge import DockerBridge
from chainguard_gateway.phase10_api import create_operations_app
from chainguard_gateway.phase10_audit import create_live_audit_app,verify_live_entry
from chainguard_sandbox.protocol import ToolError


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--resume-source',type=Path,help='Reuse original action and receipts; never propose or execute another mail')
    a=p.parse_args()
    out=a.out.resolve()
    if out.exists() or not out.is_relative_to(ROOT/'results/maintenance'):raise ValueError('New maintenance result directory required')
    out.mkdir(parents=True)
    source=json.loads((a.resume_source/'check.json').read_text(encoding='utf8')) if a.resume_source else None
    if source:
        c=json.loads(Path(source['private_runtime']).read_text(encoding='utf8'));private=Path(c['private_root'])
        if not c.get('acceptance_only') or not private.resolve().is_relative_to(ROOT/'.local/maintenance'):raise ValueError('Only isolated acceptance data may be resumed')
    else:
        c=json.loads(a.config.read_text(encoding='utf8'));private=ROOT/'.local/maintenance'/('interactive-'+uuid.uuid4().hex);private.mkdir(parents=True)
        c.update(private_root=str(private),public_db=str(private/'public.sqlite'),port=8092,acceptance_only=True)
        (private/'runtime.json').write_text(json.dumps(c),encoding='utf8')
    store=OperationsStore(private);public=PublicStore(c['public_db']);bridge=DockerBridge(c);ops=Operations(store,public,bridge,c)
    ops.chain.tool_sessions=c.get('tool_sessions')
    report=dict(status='RUNNING',mode='deterministic_protocol_with_real_chain_and_tool',real_llm=False,ASR=None,checks={},http_timings=[],private_runtime=str(private/'runtime.json'))
    servers=[];threads=[];clients=[]
    def save():(out/'check.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf8')
    def check(name,value):
        report['checks'][name]=bool(value);save()
        if not value:raise AssertionError(name)
    def wait(fn,predicate,seconds=90):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            value=fn()
            if predicate(value):return value
            time.sleep(.3)
        raise TimeoutError('Acceptance wait exceeded; original IDs retained, do not recreate automatically')
    save()
    try:
        if source:
            sid=report['session_id']=source['session_id'];jid=report['job_id']=source['job_id'];aid=report['action_id']=source['action_id']
            report.update(task_id=source['task_id'],source=str(a.resume_source),new_local_mails=0,new_business_transactions=0)
            ops.sync()
        else:
            scope=dict(allowed_tools=['mail.send'],allowed_document_ids=[],read_mailboxes=[],allowed_recipients=['alice@inbox.chainguard.invalid'])
            sid=report['session_id']=random_id();jid=report['job_id']=random_id()
            ops.conversations.create(sid,'requester/OrgA',scope);ops.conversations.append(sid,'requester/OrgA',jid,'Synthetic HTTP async and visibility acceptance',0)
            now=int(time.time());task=bridge.call('requester',dict(op='create_task',key=random_id(),body=dict(task_text='Synthetic HTTP async acceptance',agent=c['signers']['agent'],allowed_tools=['mail.send'],resource_scopes=['ORG_A_INTERNAL_MAIL'],allowed_document_ids=[],allowed_recipients=scope['allowed_recipients'],expires_at=str(now+86400),max_risk=2,max_actions=1,allow_sandbox_delete=False)))
            request=dict(task_id=task['task_id'],tool_name='mail.send',params=dict(to=scope['allowed_recipients'],subject='Async and soft-hide acceptance',body='Synthetic local sandbox message. Original receipts and audit evidence are retained.'))
            action=bridge.call('agent',dict(op='request',method='POST',path='/v1/agent/actions/propose',body=request,key=random_id()))
            aid=report['action_id']=action['action_id'];report['task_id']=task['task_id'];save()
            store.update(jid,state='AWAITING_APPROVAL',grant=task,action_id=aid,source_track='deterministic_protocol',attempt=dict(tool='mail.send'))
            ops.sync();check('before_approval_no_mail',bridge.observe(aid)['mail_count']==0)
        app=create_operations_app(ops,c['credentials'],'http://127.0.0.1:8092',ROOT/'console/dist',audit_url='http://127.0.0.1:8093')
        audit=create_live_audit_app(public.path,ops.chain,ROOT/'dashboard/dist')
        for port,application in [(8092,app),(8093,audit)]:
            server=uvicorn.Server(uvicorn.Config(application,host='127.0.0.1',port=port,log_level='warning',access_log=False));thread=threading.Thread(target=server.run,daemon=True);thread.start();servers.append(server);threads.append(thread)
        wait(lambda:all(s.started for s in servers),bool,15)
        passwords=dict(line.split(' : ',1) for line in (a.config.parent/'access.local.txt').read_text(encoding='utf8').splitlines() if ' : ' in line)
        for role in ['requester','biz','security']:
            client=httpx.Client(base_url='http://127.0.0.1:8092',trust_env=False,timeout=30)
            r=client.post('/ops/v1/login',headers={'Origin':'http://127.0.0.1:8092'},json=dict(role=role,password=passwords[role]));r.raise_for_status()
            client.headers.update({'Origin':'http://127.0.0.1:8092','X-CSRF-Token':r.json()['csrf']});clients.append(client)
        requester,biz,security=clients
        if not source:
            digest=biz.get('/ops/v1/tasks/'+jid+'/review').json()['intent_digest']
            def command(client,path,body,key=None):
                started=time.perf_counter();r=client.post(path,headers={'Prefer':'respond-async','Idempotency-Key':key or random_id()},json=body);elapsed=(time.perf_counter()-started)*1000
                report['http_timings'].append(dict(path=path.rsplit('/',1)[-1],response_ms=elapsed,http_status=r.status_code));save()
                check('async_'+str(len(report['http_timings']))+'_202',r.status_code==202)
                value=r.json();check('async_'+str(len(report['http_timings']))+'_real_hash_or_null',value['tx_hash'] is None or value['tx_hash'].startswith('0x'))
                result=wait(lambda:client.get('/ops/v1/operations/'+value['operation_id']).json(),lambda v:v['status']!='PENDING')
                return result
            approved=command(biz,'/ops/v1/tasks/'+jid+'/approve',dict(intent_digest=digest));check('OrgA_signature_processed',approved['status']=='SUCCEEDED')
            missing=command(requester,'/ops/v1/tasks/'+jid+'/execute',dict(intent_digest=digest));check('missing_OrgB_rejected',missing['status']=='FAILED')
            check('missing_OrgB_no_mail',bridge.observe(aid)['mail_count']==0)
            approved_b=command(security,'/ops/v1/tasks/'+jid+'/approve',dict(intent_digest=digest));check('OrgB_signature_processed',approved_b['status']=='SUCCEEDED')
            execute_key=random_id();accepted=command(requester,'/ops/v1/tasks/'+jid+'/execute',dict(intent_digest=digest),execute_key);check('execute_accepted',accepted['status']=='SUCCEEDED')
            final=wait(lambda:requester.get('/ops/v1/tasks/'+jid).json(),lambda v:v['display_state']=='FINALIZED_OK')
            report['record']=final['record'];report['tool_observation']=bridge.observe(aid);save()
            check('one_real_sandbox_MIME',report['tool_observation']['status']=='VERIFIED' and report['tool_observation']['mail_count']==1)
            entry='interactive-'+jid[2:];row=next(r for r in public.actions() if r['entry_id']==entry)
            report['verification']=verify_live_entry(ops.chain,row);check('four_node_transactions_tool_signature_verified',report['verification']['status']=='VERIFIED' and report['verification']['tool_signature_valid'])
            duplicate=command(requester,'/ops/v1/tasks/'+jid+'/execute',dict(intent_digest=digest),execute_key)
            check('same_operation_deduplicated',duplicate['operation_id']==accepted['operation_id'])
            check('duplicate_no_second_mail',bridge.observe(aid)['mail_count']==1)
            try:bridge.call('agent',dict(op='request',method='POST',path='/v1/agent/actions/propose',body=dict(request,params=dict(request['params'],to=['bob@inbox.chainguard.invalid'])),key=random_id()))
            except ToolError as error:report['unauthorized_error']=error.code
            else:raise AssertionError('Unauthorized action accepted')
            check('unauthorized_call_rejected',report['unauthorized_error'] in {'UNAUTHORIZED_SCOPE','POLICY_DENY'})
            check('unauthorized_no_extra_action',len([r for r in bridge.snapshot() if r['task_id']==task['task_id']])==1)
        else:
            final=requester.get('/ops/v1/tasks/'+jid).json()
            check('original_action_is_finalized',final['display_state']=='FINALIZED_OK')
            report['record']=final['record'];report['tool_observation']=bridge.observe(aid)
            check('original_single_sandbox_MIME',report['tool_observation']['status']=='VERIFIED' and report['tool_observation']['mail_count']==1)
            report['approval_performance']=source['approval_performance'];report['execution_performance']=source['execution_performance']
        entry='interactive-'+jid[2:]
        wait(lambda:ops.store.cached('transaction_performance',[]),lambda rows:len([r for r in rows if r['action_id']==aid and r['confirmed_at_ms']])==2)
        report['transaction_performance']=[r for r in ops.store.cached('transaction_performance',[]) if r['action_id']==aid]
        if not source:report['approval_performance']=approved['performance'];report['execution_performance']=accepted['performance']
        target_height=int(final['record']['finalization_evidence']['block_number'])
        wait(lambda:store.cached('chain_event_cursor',{}),lambda v:v.get('height',0)>=target_height,120)
        with store.db() as db:report['indexed_events']=[dict(r) for r in db.execute('SELECT tx_hash,block_number,block_hash FROM indexed_chain_events WHERE tx_hash IN (?,?)',(final['record']['reservation_evidence']['tx_hash'],final['record']['finalization_evidence']['tx_hash']))]
        check('real_events_indexed_from_four_nodes',len(report['indexed_events'])>=2)
        timings=[]
        for _ in range(5):
            started=time.perf_counter();requester.get('/ops/v1/tasks').raise_for_status();requester.get('/ops/v1/conversations').raise_for_status();timings.append((time.perf_counter()-started)*1000)
        report['local_list_pair_ms']=timings;save()
        with (out/'browser.txt').open('wb') as log:
            r=subprocess.run(['node','console/tests/soft-delete-browser.mjs',str(private/'runtime.json'),str(a.config.resolve()),str(out/'browser'),jid],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,timeout=90)
        check('real_browser_delete_and_audit_async_verification',r.returncode==0)
        check('requester_lists_hidden',requester.get('/ops/v1/tasks').json()['tasks']==[] and requester.get('/ops/v1/conversations').json()['conversations']==[])
        check('reviewers_still_see_pending_and_history',len(security.get('/ops/v1/tasks').json()['tasks'])==1)
        check('original_private_message_preserved',store.get(jid)['task_text']=='Synthetic HTTP async and visibility acceptance' and len(ops.conversations.runs(sid))==1)
        row=next(r for r in public.actions() if r['entry_id']==entry)
        check('hidden_record_four_node_verification_still_valid',verify_live_entry(ops.chain,row)['status']=='VERIFIED')
        check('hidden_original_MIME_still_valid',bridge.observe(aid)['mail_count']==1)
        report.update(status='PASS',new_local_mails=0 if source else 1,new_business_transactions=0 if source else 2,no_LLM_calls=True);save()
        print(json.dumps(dict(status=report['status'],checks=len(report['checks']),http_response_ms=[round(t['response_ms'],2) for t in report['http_timings']],confirmation_observed_ms=[t['confirmation_observed_ms'] for t in report['transaction_performance']])))
    except Exception as error:report.update(status='FAIL',error_type=type(error).__name__,error=str(error));save();raise
    finally:
        for server in servers:server.should_exit=True
        for thread in threads:thread.join(8)
        for client in clients:client.close()


if __name__=='__main__':main()
