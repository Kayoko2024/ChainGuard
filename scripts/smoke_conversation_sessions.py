"""Fresh real DeepSeek conversation -> original HIGH approvals -> four Besu/MIME -> resume.

Uses an isolated encrypted operations DB and the existing sandbox services. No external mail.
"""
import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/p) for p in ['gateway/src','sandbox_tools/src','agent/src']]
from chainguard_gateway.phase10_store import OperationsStore,PublicStore
from chainguard_gateway.phase10_service import Operations
from chainguard_gateway.phase10_bridge import DockerBridge
from chainguard_gateway.crypto import random_id
from chainguard_gateway.phase10_audit import verify_live_entry
from chainguard_gateway.audit_verify import make_chain


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--web',action='store_true');a=p.parse_args()
    out=a.out.resolve()
    if out.exists() or not out.is_relative_to(ROOT/'results/conversations'):raise ValueError('New conversation evidence directory required')
    out.mkdir(parents=True);c=json.loads(a.config.read_text());private=ROOT/'.local/conversations'/secrets.token_hex(12)
    c=dict(c,private_root=str(private/'private'),public_db=str(private/'public.sqlite3'),port=8092)
    private.mkdir(parents=True);runtime=private/'runtime.json';runtime.write_text(json.dumps(c),encoding='utf8')
    report=dict(status='RUNNING',private_runtime=str(runtime),tests={},real_llm=None,ASR=None,mail_count=0)
    def save():(out/'smoke.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    def check(name,condition):
        report['tests'][name]=bool(condition);save()
        if not condition:raise AssertionError(name)
    b=DockerBridge(c);ops=Operations(OperationsStore(c['private_root']),PublicStore(c['public_db']),b,c)
    sid=random_id();owner='requester/OrgA';report['session_id']=sid
    scope=dict(allowed_tools=['doc.read','mail.send'],allowed_document_ids=['meeting-notes'],read_mailboxes=[],allowed_recipients=['alice@inbox.chainguard.invalid'],session_grant=dict(duration_seconds=3600,max_calls=10))
    save()
    try:
        ops.conversation_service.create(sid,owner,scope)
        first=random_id();ops.conversation_service.append(sid,owner,first,'读取 meeting-notes，用一句中文总结会议结论、负责人和下一步。此轮不发送邮件。',0)
        ops.run_agent(first);ops.sync();one=ops.store.get(first)
        check('real_read_and_summary',one['state']=='READ_COMPLETED' and bool(one.get('agent_output')))
        report['real_llm']=any(e['kind']=='MODEL_EXCHANGE' and e['exchange'].get('http_status')==200 for e in ops.store.events(first));save()
        status=b.conversation('status',{'session_id':sid});check('LOW_one_grant_one_call',len(status['grants'])==1 and status['grants'][0]['used']==1)
        second=random_id();ops.conversation_service.append(sid,owner,second,'请把你上一条给我的完整摘要作为正文，发送到 alice@inbox.chainguard.invalid，主题“会话摘要验收”。请实际调用 mail_send，不要重新读取文档。',1)
        # Reconstruct the service to prove memory is durable rather than Python-local.
        ops=Operations(OperationsStore(c['private_root']),ops.public,b,c);ops.run_agent(second);ops.sync();job=ops.detail(second)
        check('HIGH_suspended_exact_snapshot',job['state']=='AWAITING_APPROVAL' and ops.store.get(second)['runner_snapshot']['phase']=='TOOL_PENDING')
        review=ops.review(second,'requester');check('summary_carried_into_mail',one['agent_output'] in review['params']['body'])
        check('no_mail_before_approvals',ops.mailbox(second)['mail_count']==0)
        ops.approve(second,'biz',review['intent_digest']);check('one_org_no_side_effect',ops.mailbox(second)['mail_count']==0)
        ops.approve(second,'security',review['intent_digest']);ops.execute(second,review['intent_digest'])
        deadline=time.monotonic()+90
        while time.monotonic()<deadline:
            ops.sync();job=ops.detail(second)
            if job['record']['state']=='FINALIZED_OK':break
            time.sleep(1)
        check('HIGH_real_finalized',job['record']['state']=='FINALIZED_OK')
        mailbox=ops.mailbox(second);check('exactly_one_verified_MIME',mailbox['status']=='VERIFIED' and mailbox['mail_count']==1)
        report['mail_count']=1;save()
        # New process-equivalent service, then resume from the saved pending cursor.
        ops=Operations(OperationsStore(c['private_root']),ops.public,b,c);ops.sync();ops.tick();job=ops.detail(second)
        check('automatic_resume_after_verified_finalize',bool(job.get('agent_output')) and ops.store.get(second)['runner_snapshot']['phase']=='COMPLETED')
        before=len(ops.store.events(second));ops.tick();check('no_second_continuation_or_mail',len(ops.store.events(second))==before and ops.mailbox(second)['mail_count']==1)
        negative=ops.manual_probe(second);check('scope_denial_no_effect',negative['status']=='DENIED' and negative['mail_after']==negative['mail_before']==1)
        original=job['record'];ops.execute(second,review['intent_digest']);ops.sync();check('duplicate_execute_original_tx_and_one_mail',ops.detail(second)['record']['reservation_evidence']==original['reservation_evidence'] and ops.mailbox(second)['mail_count']==1)
        ops.conversation_service.close(sid,owner)
        deadline=time.monotonic()+45
        while time.monotonic()<deadline:
            status=b.conversation('status',{'session_id':sid})
            if status['observations'] and all(o['status']=='ANCHORED' and o['batch']['closed'] for o in status['observations']):break
            b.conversation('flush',{'session_id':sid});time.sleep(1)
        ops.sync();check('LOW_session_final_root_real_chain',len(status['observations'])==1 and status['observations'][0]['status']=='ANCHORED' and status['observations'][0]['batch']['closed'])
        chain=make_chain(c['deployment'],[f'http://127.0.0.1:{port}' for port in range(8545,8549)]);chain.tool_sessions=c['tool_sessions']
        rows=ops.public.actions();verified=[]
        for row in rows:
            if row.get('conversation_observation') or row.get('action_id')==original['action_id']:
                v=verify_live_entry(chain,row);verified.append(dict(entry_id=row['entry_id'],status=v['status'],evidence=v.get('evidence'),transactions=v.get('transactions')))
        check('independent_four_node_LOW_and_HIGH_verify',{v['status'] for v in verified}=={'VERIFIED','BATCH_VERIFIED'})
        report.update(session_id=sid,runs=[first,second],action_id=original['action_id'],mail_count=1,transactions=dict(reserve=original['reservation_evidence'],finalize=original['finalization_evidence'],low=status['observations'][0]['batch']['evidence']),verification=verified,model_exchanges=sum(sum(e['kind']=='MODEL_EXCHANGE' for e in ops.store.events(run)) for run in [first,second]));save()
        # New independent HIGH run: actually drop the tool response, retain MIME,
        # then recover by querying its original signed receipt rather than sending again.
        unknown_session=random_id();unknown_run=random_id()
        ops.conversation_service.create(unknown_session,owner,dict(scope,allowed_tools=['mail.send'],allowed_document_ids=[]))
        ops.conversation_service.append(unknown_session,owner,unknown_run,'调用 mail_send 给 alice@inbox.chainguard.invalid 发送主题“UNKNOWN会话验收”、正文“本地合成回执恢复测试”的邮件。',0)
        ops.run_agent(unknown_run);ops.sync();check('UNKNOWN_case_pauses_before_execution',ops.detail(unknown_run)['state']=='AWAITING_APPROVAL')
        unknown_review=ops.review(unknown_run,'requester');ops.fault(unknown_run,True)
        ops.approve(unknown_run,'biz',unknown_review['intent_digest']);ops.approve(unknown_run,'security',unknown_review['intent_digest']);ops.execute(unknown_run,unknown_review['intent_digest'])
        deadline=time.monotonic()+60
        while time.monotonic()<deadline:
            ops.sync()
            if ops.detail(unknown_run)['record']['state']=='UNKNOWN':break
            time.sleep(1)
        uncertain=ops.detail(unknown_run);physical=ops.mailbox(unknown_run)
        check('real_UNKNOWN_with_one_physical_mail',uncertain['record']['state']=='UNKNOWN' and physical['mail_count']==1)
        report['mail_count']=2;report['unknown_run']=unknown_run;report['unknown_session']=unknown_session;save()
        count=len(ops.store.events(unknown_run));ops.tick();ops.tick()
        check('UNKNOWN_does_not_resume_or_redispatch',len(ops.store.events(unknown_run))==count and ops.mailbox(unknown_run)['mail_count']==1 and not ops.store.get(unknown_run).get('agent_output'))
        ops.fault(unknown_run,False)
        deadline=time.monotonic()+90
        while time.monotonic()<deadline:
            ops.sync()
            if ops.detail(unknown_run)['record']['state']=='FINALIZED_OK':break
            time.sleep(1)
        ops.tick();recovered=ops.detail(unknown_run)
        check('UNKNOWN_original_receipt_recovers_and_resumes_once',recovered['record']['state']=='FINALIZED_OK' and bool(recovered.get('agent_output')) and ops.mailbox(unknown_run)['mail_count']==1)
        report['unknown_transactions']=dict(reserve=recovered['record']['reservation_evidence'],finalize=recovered['record']['finalization_evidence']);save()
        if a.web:
            env=dict(os.environ,PYTHONPATH=os.pathsep.join(str(ROOT/q) for q in ['gateway/src','sandbox_tools/src','agent/src']),PYTHONUTF8='1')
            log=(private/'web.log').open('wb');process=subprocess.Popen([sys.executable,'-m','chainguard_gateway.phase10_api','--config',str(runtime)],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
                for _ in range(60):
                    try:opener.open('http://127.0.0.1:8092/health/live',timeout=1);break
                    except Exception:time.sleep(.3)
                with (out/'browser.txt').open('wb') as web_log:
                    r=subprocess.run(['node','console/tests/session-memory-browser.mjs',str(runtime),str(a.config.resolve()),str(out/'browser'),sid],cwd=ROOT,env=env,stdout=web_log,stderr=subprocess.STDOUT,timeout=240)
                check('real_browser_memory_refresh_and_new_turn',r.returncode==0)
            finally:process.terminate();process.wait(timeout=10);log.close()
        report['status']='PASS';save()
    except Exception as error:report.update(status='FAIL',error_type=type(error).__name__,failure=str(error));save();raise
    print(json.dumps(dict(status=report['status'],session_id=sid,mail_count=report['mail_count'],tests=len(report['tests']))))

if __name__=='__main__':main()
