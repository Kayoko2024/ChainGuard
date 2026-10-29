"""Real browser -> DeepSeek -> 24h tool capability -> same-session followup.

Creates an isolated business database and LOW audit anchor on the existing Besu
network. Reads only synthetic documents, sends no mail, never retries old jobs.
"""
import argparse
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
from chainguard_gateway.phase10_bridge import DockerBridge
from chainguard_gateway.audit_verify import make_chain
from chainguard_gateway.phase10_audit import verify_live_entry


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();out=a.out.resolve()
    if out.exists() or not out.is_relative_to(ROOT/'results/maintenance'):raise ValueError('New maintenance result directory required')
    out.mkdir(parents=True)
    c=json.loads(a.config.read_text(encoding='utf8'))
    private=ROOT/'.local/maintenance'/('read-capability-'+secrets.token_hex(12));private.mkdir(parents=True)
    c.update(private_root=str(private/'private'),public_db=str(private/'public.sqlite'),port=8092,acceptance_only=True)
    runtime=private/'runtime.json';runtime.write_text(json.dumps(c),encoding='utf8')
    report=dict(status='RUNNING',real_llm=False,ASR=None,mail_count=0,private_runtime=str(runtime),checks={})
    process=None;log=None
    def save():(out/'check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    def check(name,value):
        report['checks'][name]=bool(value);save()
        if not value:raise AssertionError(name)
    save()
    try:
        env=dict(os.environ,PYTHONPATH=os.pathsep.join(str(ROOT/q) for q in ('gateway/src','sandbox_tools/src','agent/src')),PYTHONUTF8='1')
        log=(private/'web.log').open('wb')
        process=subprocess.Popen([sys.executable,'-m','chainguard_gateway.phase10_api','--config',str(runtime)],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for _ in range(60):
            try:
                with opener.open('http://127.0.0.1:8092/health/live',timeout=1) as response:healthy=json.load(response)
                if healthy.get('status')=='alive':break
            except OSError:pass
            if process.poll() is not None:raise RuntimeError('Isolated acceptance server exited')
            time.sleep(.3)
        else:raise TimeoutError('Isolated server unavailable')
        with (out/'browser.txt').open('wb') as output:
            ran=subprocess.run(['node','console/tests/session-memory-browser.mjs',str(runtime),str(a.config.resolve()),str(out/'browser')],cwd=ROOT,env=env,stdout=output,stderr=subprocess.STDOUT,timeout=300)
        check('real_browser_read_followup_refresh_and_LOW_anchor',ran.returncode==0)
        browser=json.loads((out/'browser/browser.json').read_text(encoding='utf8'));report['session_id']=browser['session_id']
        store=OperationsStore(c['private_root']);jobs=[store.get(r['id']) for r in browser['runs']]
        check('both_new_turns_use_same_session',len(jobs)==2 and all(j['conversation_id']==browser['session_id'] for j in jobs))
        check('24h_task_grants_installed_on_tool',all(j.get('library_installed') and int(j['grant']['expires_at'])-int(j['created'])>=86300 for j in jobs))
        first_events=store.events(jobs[0]['id']);second_events=store.events(jobs[1]['id'])
        check('actual_document_read_via_gateway',any(e['kind']=='AGENT_ATTEMPT' and e['tool_name']=='doc.read' and e.get('policy_verdict')=='READ_ALLOWED' and e.get('tool_executed') is True for e in first_events))
        responses=[e for e in first_events+second_events if e['kind']=='MODEL_EXCHANGE' and e['exchange'].get('http_status')==200]
        report['real_llm']=bool(responses);report['model_exchanges']=len(responses)
        check('real_model_used_in_both_turns',all(any(e['kind']=='MODEL_EXCHANGE' and e['exchange'].get('http_status')==200 for e in store.events(j['id'])) for j in jobs))
        check('second_request_contains_original_assistant_summary',any(any(m.get('role')=='assistant' and m.get('content')==jobs[0]['agent_output'] for m in e['exchange']['request']['messages']) for e in second_events if e['kind']=='MODEL_EXCHANGE'))
        bridge=DockerBridge(c);task_ids=[j['grant']['task_id'] for j in jobs]
        code="import sqlite3,json,sys;from chainguard_gateway.phase6_server import load;r,c=load();d=sqlite3.connect('file:'+str(r/'state.sqlite3')+'?mode=ro',uri=True);tasks=json.load(sys.stdin);print(json.dumps({t:json.loads(d.execute('SELECT data FROM library_capabilities WHERE task_id=?',(t,)).fetchone()[0])['expires_at'] for t in tasks}))"
        expiries=json.loads(bridge.docker(['exec','-i',c['containers']['tool'],'python','-c',code],task_ids))
        report['tool_capability_expiries']=expiries
        check('persisted_tool_expiries_equal_original_task_expiries',all(expiries[j['grant']['task_id']]==int(j['grant']['expires_at']) for j in jobs))
        check('no_HIGH_action_or_mail_for_these_tasks',not any(r['task_id'] in task_ids for r in bridge.snapshot()) and not any(j.get('action_id') for j in jobs))
        chain=make_chain(c['deployment'],['http://127.0.0.1:'+str(p) for p in range(8545,8549)]);chain.tool_sessions=c['tool_sessions']
        rows=[r for r in PublicStore(c['public_db']).actions() if r.get('conversation_observation')]
        report['verifications']=[dict(entry_id=r['entry_id'],**verify_live_entry(chain,r)) for r in rows]
        check('LOW_inclusion_independently_verified_on_four_nodes',bool(rows) and all(v['status']=='BATCH_VERIFIED' for v in report['verifications']))
        paths=('sandbox_tools/src/chainguard_sandbox/default_library.py',)
        code="import hashlib,json;from pathlib import Path;print(json.dumps({p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in "+repr(paths)+"}))"
        report['deployed_sources']=json.loads(bridge.docker(['exec',c['containers']['tool'],'python','-c',code]))
        check('deployed_tool_matches_fixed_source',all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==v for p,v in report['deployed_sources'].items()))
        report.update(status='PASS',new_HIGH_transactions=0,LOW_anchor=browser['anchor'],runs=[dict(id=j['id'],state=j['state'],task_id=j['grant']['task_id']) for j in jobs]);save()
        print(json.dumps(dict(status='PASS',checks=len(report['checks']),real_llm=report['real_llm'],model_exchanges=report['model_exchanges'],mail_count=0)))
    except Exception as e:
        report.update(status='FAIL',error_type=type(e).__name__,error=str(e));save();raise
    finally:
        if process is not None and process.poll() is None:process.terminate();process.wait(timeout=10)
        if log is not None:log.close()


if __name__=='__main__':main()
