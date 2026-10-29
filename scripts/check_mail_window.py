"""Real delayed R2 acceptance on four Besu nodes; one synthetic local MIME only.

No model calls; timestamps advance by real waiting, never by mutating the live chain.
"""
import argparse
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/p) for p in ['gateway/src','sandbox_tools/src','agent/src']]
from chainguard_gateway.phase10_bridge import DockerBridge
from chainguard_gateway.audit_verify import make_chain
from chainguard_gateway.phase10_audit import verify_live_entry
from chainguard_gateway.crypto import random_id
from chainguard_sandbox.protocol import ToolError


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--wait-seconds',type=int,default=125);p.add_argument('--verify-source',type=Path,help='Read-only verification of an existing PASS run; no sending or signing');a=p.parse_args()
    out=a.out.resolve()
    if out.exists() or not out.is_relative_to(ROOT/'results/lifetime') or not 121<=a.wait_seconds<=180:raise ValueError('New lifetime evidence directory and real >120s wait required')
    out.mkdir(parents=True);c=json.loads(a.config.read_text(encoding='utf8'));b=DockerBridge(c)
    report=dict(status='RUNNING',real_llm=False,ASR=None,tests={},mail_count=0)
    def save():(out/'check.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    def check(name,value):
        report['tests'][name]=bool(value);save()
        if not value:raise ValueError(name)
    save()
    try:
        chain=make_chain(c['deployment'],[f'http://127.0.0.1:{p}' for p in range(8545,8549)])
        if a.verify_source:
            source=json.loads((a.verify_source/'check.json').read_text(encoding='utf8'))
            if source['status']!='PASS':raise ValueError('Only an original PASS batch is accepted')
            record=next(r for r in b.snapshot() if r['action_id']==source['action_id'])
            check('original_chain_record_unchanged',record==source['record'])
            checked=verify_live_entry(chain,dict(record,group='C',entry_id='readonly-window-check'))
            check('four_nodes_signatures_and_receipt',checked['status']=='VERIFIED' and checked['tool_signature_valid'])
            physical=b.observe(source['action_id'])
            check('original_single_MIME_and_commitments',physical['status']=='VERIFIED' and physical['mail_count']==1 and physical['messages']==source['tool_observation']['messages'])
            check('real_wait_retained',source['approval_age_seconds']>120)
            report.update(status='PASS',source=str(a.verify_source),model_or_tool_reexecuted=False,transactions_submitted=0,mail_count=0,verification=checked);save()
            print(json.dumps(dict(status='PASS',mode='read-only',tests=len(report['tests']))));return
        before=b.snapshot();legacy=next(r for r in reversed(before) if r['state']=='FINALIZED_OK' and r['reservation_evidence']['registry'].lower()!=chain.execution.address)
        old_before=verify_live_entry(chain,dict(legacy,group='C',entry_id='legacy-window-check'))
        check('legacy_chain_record_verified',old_before['status']=='VERIFIED')
        check('legacy_original_MIME_verified',b.observe(legacy['action_id'])['status']=='VERIFIED')
        issued=int(time.time());body=dict(task_text='Synthetic 24h mail timeout acceptance',agent=c['signers']['agent'],allowed_tools=['mail.send'],resource_scopes=['ORG_A_INTERNAL_MAIL'],allowed_document_ids=[],allowed_recipients=['alice@inbox.chainguard.invalid'],expires_at=str(issued+86400),max_risk=2,max_actions=1,allow_sandbox_delete=False)
        task=b.call('requester',dict(op='create_task',body=body,key=random_id()))
        request=dict(task_id=task['task_id'],tool_name='mail.send',params=dict(to=['alice@inbox.chainguard.invalid'],subject='24h approval window acceptance',body='Synthetic local sandbox message; no external delivery.'))
        action=b.call('agent',dict(op='request',method='POST',path='/v1/agent/actions/propose',body=request,key=random_id()))
        aid=action['action_id'];intent=action['intent'];window=int(intent['expires_at'])-int(intent['issued_at'])
        report.update(task_id=task['task_id'],action_id=aid,intent=intent,actual_intent_window_seconds=window,task_window_seconds=int(task['expires_at'])-issued,wait_seconds=a.wait_seconds,legacy_action_id=legacy['action_id']);save()
        check('task_24_hours',int(task['expires_at'])-issued==86400)
        check('new_intent_24h_bounded_by_task',86300<=window<=86400 and int(intent['expires_at'])<=int(task['expires_at']))
        check('no_side_effect_before_approvals',b.observe(aid)['mail_count']==0)
        print(json.dumps(dict(status='WAITING',action_id=aid,real_wait_seconds=a.wait_seconds)),flush=True)
        # Persist the ID first; interruption must never create a replacement action.
        deadline=time.monotonic()+a.wait_seconds
        while time.monotonic()<deadline:time.sleep(min(1,deadline-time.monotonic()))
        report['approval_age_seconds']=int(time.time())-int(intent['issued_at']);save()
        check('real_elapsed_exceeds_frozen_120s',report['approval_age_seconds']>120)
        review=b.call('biz',dict(op='review',action_id=aid));digest=review['intent_digest']
        b.call('biz',dict(op='sign',action_id=aid,intent_digest=digest))
        signed=b.call('requester',dict(op='sign',action_id=aid,intent_digest=digest))
        try:
            b.call('requester',dict(op='reserve',action_id=aid,signature=signed['signature'],key=random_id()))
        except ToolError as error:report['missing_approval_error']=error.code
        else:raise ValueError('Single organization reserved unexpectedly')
        check('one_org_still_refused_without_MIME',b.observe(aid)['mail_count']==0)
        b.call('security',dict(op='sign',action_id=aid,intent_digest=digest))
        reserve_key=random_id();b.call('requester',dict(op='reserve',action_id=aid,signature=signed['signature'],key=reserve_key))
        deadline=time.monotonic()+90;record=None
        while time.monotonic()<deadline:
            record=next(r for r in b.snapshot() if r['action_id']==aid)
            if record['state']=='FINALIZED_OK':break
            time.sleep(.5)
        report['record']=record;save();check('real_chain_FINALIZED_OK',record['state']=='FINALIZED_OK')
        physical=b.observe(aid);report.update(mail_count=physical['mail_count'],tool_observation=physical);save()
        check('tool_second_check_and_one_real_MIME',physical['status']=='VERIFIED' and physical['mail_count']==1)
        verified=verify_live_entry(chain,dict(record,group='C',entry_id='new-window-check'));report['verification']=verified;save()
        check('four_nodes_and_tool_signature_verified',verified['status']=='VERIFIED' and verified['tool_signature_valid'] and len(verified['transactions'])==2)
        b.call('requester',dict(op='reserve',action_id=aid,signature=signed['signature'],key=reserve_key))
        check('duplicate_uses_original_transactions_and_mail',b.observe(aid)['mail_count']==1 and next(r for r in b.snapshot() if r['action_id']==aid)['reservation_evidence']==record['reservation_evidence'])
        bad=dict(request,params=dict(request['params'],to=['bob@inbox.chainguard.invalid']))
        try:b.call('agent',dict(op='request',method='POST',path='/v1/agent/actions/propose',body=bad,key=random_id()))
        except ToolError as error:report['unauthorized_error']=error.code
        else:raise ValueError('Unauthorized recipient accepted')
        # The task has already spent max_actions=1: quota denial precedes its
        # recipient scope check. Both are real authorization denials.
        task_actions=[r for r in b.snapshot() if r['task_id']==task['task_id']]
        check('unauthorized_denied_no_extra_action_or_mail',report['unauthorized_error'] in {'UNAUTHORIZED_SCOPE','POLICY_DENY'} and len(task_actions)==1 and task_actions[0]['action_id']==aid and b.observe(aid)['mail_count']==1)
        report.update(status='PASS',new_chain_transactions=2,tool_or_model_reexecution_on_history=False);save()
        print(json.dumps(dict(status='PASS',action_id=aid,mail_count=1,tests=len(report['tests']))))
    except Exception as error:
        report.update(status='FAIL',error_type=type(error).__name__,failure=str(error));save();raise


if __name__=='__main__':main()
