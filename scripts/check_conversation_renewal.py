"""Real Edge/DeepSeek renewal, legacy memory, HIGH approval and LOW audit acceptance.

Uses an isolated business database on 8092/8093 and the existing four Besu nodes.
Creates one real sandbox MIME. No external mail, mock model or clock manipulation.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/p) for p in ('gateway/src','sandbox_tools/src','agent/src')]
from chainguard_gateway.phase10_store import OperationsStore,PublicStore
from chainguard_gateway.phase10_service import Operations
from chainguard_gateway.phase10_bridge import DockerBridge
from chainguard_gateway.audit_verify import make_chain
from chainguard_gateway.phase10_audit import verify_live_entry
from chainguard_gateway.crypto import random_id


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--resume-source',type=Path,help='Continue original isolated tasks without re-creating mail')
    args=parser.parse_args();out=args.out.resolve()
    if out.exists() or not out.is_relative_to(ROOT/'results/conversations'):raise ValueError('New conversation result directory required')
    out.mkdir(parents=True)
    source=json.loads((args.resume_source/'check.json').read_text(encoding='utf8')) if args.resume_source else None
    if source:
        runtime=Path(source['private_runtime']);c=json.loads(runtime.read_text(encoding='utf8'));private=runtime.parent
        if not c.get('acceptance_only') or not private.is_relative_to(ROOT/'.local/conversations'):raise ValueError('Isolated acceptance runtime required')
    else:
        c=json.loads(args.config.read_text(encoding='utf8'));private=ROOT/'.local/conversations'/('renewal-'+secrets.token_hex(12));private.mkdir(parents=True)
        c.update(private_root=str(private/'private'),public_db=str(private/'public.sqlite3'),port=8092,acceptance_only=True)
        audit=json.loads(Path(c['audit_config']).read_text(encoding='utf8'))
        audit.update(public_db=c['public_db'],port=8093)
        c['audit_config']=str(private/'audit.json');Path(c['audit_config']).write_text(json.dumps(audit),encoding='utf8')
        runtime=private/'runtime.json';runtime.write_text(json.dumps(c),encoding='utf8')
    report=dict(status='RUNNING',private_runtime=str(runtime),real_llm=False,ASR=None,checks={},mail_count=None)
    processes=[];logs=[]
    def save():(out/'check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    def check(name,value):
        report['checks'][name]=bool(value);save()
        if not value:raise AssertionError(name)
    save()
    try:
        bridge=DockerBridge(c);store=OperationsStore(c['private_root']);public=PublicStore(c['public_db']);ops=Operations(store,public,bridge,c)
        legacy=source['legacy_job_id'] if source else random_id();report['legacy_job_id']=legacy;save()
        if not source:
            scope=dict(allowed_tools=['doc.read','mail.send'],allowed_document_ids=['meeting-notes'],read_mailboxes=[],allowed_recipients=['alice@inbox.chainguard.invalid'],session_grant=dict(duration_seconds=60,max_calls=10))
            ops.create(legacy,dict(scope,task_text='读取 meeting-notes，用一句中文总结负责人和下一步；不发送邮件。'))
            ops.run_agent(legacy);ops.sync()
        original=copy.deepcopy(store.get(legacy))
        check('original_legacy_is_real_completed_read',original['state']=='READ_COMPLETED' and bool(original.get('agent_output')) and not original.get('conversation_id'))
        report['real_llm']=any(e['kind']=='MODEL_EXCHANGE' and e['exchange'].get('http_status')==200 for e in store.events(legacy));save()
        env=dict(os.environ,PYTHONPATH=os.pathsep.join(str(ROOT/p) for p in ('gateway/src','sandbox_tools/src','agent/src')),PYTHONUTF8='1')
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for name,config,port in [('phase10_api',runtime,8092),('phase10_audit',Path(c['audit_config']),8093)]:
            log=(private/(name+'.log')).open('ab');logs.append(log)
            proc=subprocess.Popen([sys.executable,'-m','chainguard_gateway.'+name,'--config',str(config)],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW);processes.append(proc)
            for _ in range(50):
                try:
                    with opener.open(f'http://127.0.0.1:{port}/health/live',timeout=1) as response:json.load(response)
                    break
                except OSError:time.sleep(.3)
            else:raise TimeoutError('Isolated web service did not start')
        with (out/'browser.txt').open('wb') as output:
            command=['node','console/tests/session-renewal-browser.mjs',str(runtime),str(args.config.resolve()),str(out/'browser'),legacy]
            if args.resume_source:command.append(str((args.resume_source/'browser/browser.json').resolve()))
            ran=subprocess.run(command,cwd=ROOT,env=env,stdout=output,stderr=subprocess.STDOUT,timeout=540)
        check('real_browser_full_flow',ran.returncode==0)
        web=json.loads((out/'browser/browser.json').read_text(encoding='utf8'));sid=web['session_id'];report['session_id']=sid
        ops.sync()
        check('original_legacy_row_unchanged',store.get(legacy)==original)
        jobs=[store.get(run['id']) for run in web['runs']];first,new,high=jobs
        report['real_llm']=all(any(e['kind']=='MODEL_EXCHANGE' and e['exchange'].get('http_status')==200 for e in store.events(j['id'])) for j in [original]+jobs)
        check('real_DeepSeek_each_turn',report['real_llm'])
        check('legacy_assistant_in_followup_model_request',any(any(m.get('role')=='assistant' and m.get('content')==original['agent_output'] for m in e['exchange']['request']['messages']) for e in store.events(first['id']) if e['kind']=='MODEL_EXCHANGE'))
        check('one_original_session_for_all_new_turns',all(j['conversation_id']==sid for j in jobs))
        check('grant_changed_without_rebinding_old_task',first['conversation_grant_digest']!=new['conversation_grant_digest'] and new['conversation_grant_digest']==high['conversation_grant_digest'])
        status=bridge.conversation('status',dict(session_id=sid));log=status['logs'];epochs=status['authorization_epochs']
        check('LOW_logs_bind_original_and_renewed_grants',len(log)>=2 and log[0]['grant_digest']==first['conversation_grant_digest'] and log[-1]['grant_digest']==new['conversation_grant_digest'] and all(r['schema']==3 for r in log))
        check('audit_sequence_and_epochs_not_reset',len(epochs)==2 and [r['sequence'] for r in log]==list(range(1,len(log)+1)) and epochs[0]['end_sequence']>=1 and epochs[1]['start_sequence']==epochs[0]['end_sequence']+1)
        # Query independent tool storage without exporting raw params, salts or keys.
        code="import json,sys;from chainguard_gateway.phase6_server import load;from chainguard_gateway.conversation_runtime import access_for;r,c=load();a=access_for(r,c);sid=json.load(sys.stdin);print(json.dumps(a.status(sid)))"
        tool=json.loads(bridge.docker(['exec','-i',c['containers']['tool'],'python','-c',code],sid))
        check('tool_independently_retains_two_grants_and_same_audit_epochs',len(tool['grants'])==2 and tool['authorization_epochs']==epochs and [r['grant_digest'] for r in tool['logs']]==[r['grant_digest'] for r in log])
        chain=make_chain(c['deployment'],[f'http://127.0.0.1:{p}' for p in range(8545,8549)]);chain.tool_sessions=c['tool_sessions']
        rows=[r for r in public.actions() if r.get('session_id')==sid and r.get('conversation_observation') or r.get('action_id')==web['action_id']]
        verified=[{**verify_live_entry(chain,r),'entry_id':r['entry_id']} for r in rows]
        check('four_node_LOW_and_HIGH_independent_verification',{'VERIFIED','BATCH_VERIFIED'}<={v['status'] for v in verified})
        from chainguard_gateway.conversation_audit import verify,check as inclusion
        from chainguard_gateway.conversation_grants import ConversationPolicy
        policy=ConversationPolicy(c['tool_sessions'],[f'http://127.0.0.1:{p}' for p in range(8545,8549)])
        report['checkpoint_verification']=[verify(policy,b,b['evidence']['tx_hash']) for b in web['LOW_checkpoints']]
        check('original_epoch_checkpoint_still_valid',inclusion(log[0],[],web['LOW_checkpoints'][0]) and all(v['checked_nodes']==4 for v in report['checkpoint_verification']))
        mailbox=ops.mailbox(high['id']);report['mail_count']=mailbox['mail_count']
        check('one_actual_signed_sandbox_MIME',mailbox['status']=='VERIFIED' and mailbox['mail_count']==1)
        record=next(r for r in bridge.snapshot() if r['action_id']==web['action_id'])
        probe=ops.manual_probe(high['id'])
        check('unauthorized_recipient_denied_with_no_extra_mail',probe['status']=='DENIED' and probe['mail_before']==probe['mail_after']==1)
        review=ops.review(high['id'],'requester');ops.execute(high['id'],review['intent_digest']);ops.sync()
        repeated=ops.detail(high['id'])['record']
        check('repeat_execute_keeps_original_transactions_and_single_MIME',repeated['reservation_evidence']==record['reservation_evidence'] and repeated['finalization_evidence']==record['finalization_evidence'] and ops.mailbox(high['id'])['mail_count']==1)
        report.update(status='PASS',verification=verified,model_exchanges=sum(sum(e['kind']=='MODEL_EXCHANGE' for e in store.events(j['id'])) for j in [original]+jobs),runs=web['runs'],action_id=web['action_id'],reserve=record['reservation_evidence'],finalize=record['finalization_evidence'],LOW_checkpoints=web['LOW_checkpoints'],mime_sha256=[m['mime_sha256'] for m in mailbox['messages']]);save()
        print(json.dumps(dict(status='PASS',checks=len(report['checks']),real_llm=True,mail_count=1)))
    except Exception as error:
        report.update(status='FAIL',error_type=type(error).__name__,error=str(error));save();raise
    finally:
        for process in processes:
            if process.poll() is None:process.terminate();process.wait(timeout=10)
        for log in logs:log.close()


if __name__=='__main__':main()
