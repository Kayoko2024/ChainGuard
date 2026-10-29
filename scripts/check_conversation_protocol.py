"""Real LOW cross-turn quota, two-organization fallback and single session root. No LLM/mail."""
import argparse
import json
from pathlib import Path
import secrets
import sys
import time
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/p) for p in ['gateway/src','sandbox_tools/src','agent/src']]
from chainguard_gateway.phase10_bridge import DockerBridge
from chainguard_gateway.conversation_grants import ConversationPolicy,digest,builtin_revision
from chainguard_gateway.session_grants import hash_json
from chainguard_gateway.crypto import random_id
from chainguard_sandbox.protocol import ToolError


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    if a.out.exists():raise ValueError('New evidence directory required')
    a.out.mkdir(parents=True);c=json.loads(a.config.read_text());b=DockerBridge(c);report=dict(status='RUNNING',llm_calls=0,mail_count=0,checks={},session_id=random_id())
    def save():(a.out/'protocol.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    def check(name,condition):
        report['checks'][name]=bool(condition);save()
        if not condition:raise AssertionError(name)
    def task():return b.call('requester',dict(op='create_task',key=random_id(),body=dict(task_text='Manual synthetic conversation quota verification',agent=c['signers']['agent'],allowed_tools=['mail.send'],resource_scopes=['ORG_A_INTERNAL_MAIL'],allowed_document_ids=[],allowed_recipients=[],expires_at=str(int(time.time())+900),max_risk=2,max_actions=1,allow_sandbox_delete=False)))
    save()
    try:
        policy=ConversationPolicy(c['tool_sessions'],['http://127.0.0.1:8545','http://127.0.0.1:8547']);first=task();second=task();revision=builtin_revision('doc.read');admission=policy.admission(revision)
        scopes=[dict(name='doc.read',revision=revision,allowed_keys=['meeting-notes'],generation=admission['generation'])];now=int(time.time())
        m=dict(requester=first['requester'],agent=first['agent'],sessionId=report['session_id'],toolsHash=hash_json(scopes),nonce=secrets.randbits(52),issuedAt=now,expiresAt=now+600,maxCalls=1)
        signed=b.call('requester',dict(op='sign-conversation-grant',message=m));envelope=dict(message=m,scopes=scopes,signature=signed['signature']);b.conversation('install',envelope)
        for t in [first,second]:
            b.grant_library(dict(task_id=t['task_id'],agent=t['agent'],tools=['doc.read'],documents=['meeting-notes'],mailboxes=[],expires_at=now+600))
            signed=b.call('requester',dict(op='sign-conversation-bind',message=dict(sessionId=m['sessionId'],taskId=t['task_id'],grantDigest=digest('ConversationGrant',m,policy.domain),expiresAt=m['expiresAt'])))
            b.conversation('bind',signed)
        def query(t,id):return b.call('agent',dict(op='request',method='POST',path='/agent/v1/library',body=dict(task_id=t['task_id'],tool_name='doc.read',arguments={'doc_id':'meeting-notes'}),key=id))
        id1=random_id();one=query(first,id1);check('first_LOW_executes',one.get('trust')=='untrusted')
        try:b.call('agent',dict(op='request',method='POST',path='/agent/v1/reads',body=dict(task_id=first['task_id'],doc_id='meeting-notes'),key=random_id()))
        except ToolError as error:check('legacy_endpoint_cannot_bypass_session',error.code=='UNAUTHORIZED_SCOPE')
        else:raise AssertionError('Legacy read bypass')
        id2=random_id();two=query(second,id2);report['quota_response']={k:two.get(k) for k in ['status','error_code','call_id']};save();check('quota_shared_across_task_ids',two.get('status')=='AWAITING_TOOL_APPROVAL' and two.get('error_code')=='SESSION_EXHAUSTED')
        review=b.session_review(id2)
        for role in ['biz','security']:
            signed=b.call(role,dict(op='sign-tool-use',message=review['approval'],digest=review['digest']));b.session_approve(id2,signed['signature'])
            if role=='biz':check('single_org_still_blocked',query(second,id2).get('status')=='AWAITING_TOOL_APPROVAL')
        result=query(second,id2);check('both_orgs_actual_read',result.get('trust')=='untrusted')
        status=b.conversation('status',dict(session_id=m['sessionId']));check('LOW_fallback_in_same_session_audit',len(status['logs'])==2 and status['grants'][0]['used']==1)
        check('duplicate_has_original_execution_id',query(second,id2).get('read_execution_id')==result['read_execution_id'])
        before=len(status['logs']);status=b.conversation('status',dict(session_id=m['sessionId']));check('duplicate_no_extra_log',before==len(status['logs']))
        legacy=b.session_snapshot();check('no_duplicate_global_batch_for_session_LOW',not any(o['log']['call_id'] in {id1,id2} for o in legacy['observations']))
        signed=b.call('requester',dict(op='sign-conversation-close',message=dict(sessionId=m['sessionId'],grantDigest=digest('ConversationGrant',m,policy.domain),closedAt=int(time.time()))));b.conversation('close',signed)
        deadline=time.monotonic()+45
        while time.monotonic()<deadline:
            status=b.conversation('status',dict(session_id=m['sessionId']))
            if all(o['status']=='ANCHORED' for o in status['observations']):break
            b.conversation('flush',dict(session_id=m['sessionId']));time.sleep(1)
        check('two_LOW_records_one_session_transaction',len({o['tx_hash'] for o in status['observations']})==1 and all(o['status']=='ANCHORED' for o in status['observations']))
        from chainguard_gateway.conversation_audit import verify,check as proof
        policy=ConversationPolicy(c['tool_sessions'],[f'http://127.0.0.1:{port}' for port in range(8545,8549)])
        verified=[]
        for o in status['observations']:
            assert proof(o['log'],o['proof'],o['batch']);verified.append(verify(policy,o['batch'],o['tx_hash']))
        report.update(status='PASS',verification=verified,call_ids=[id1,id2]);save()
    except Exception as e:report.update(status='FAIL',error_type=type(e).__name__,failure=str(e));save();raise
    print(json.dumps(dict(status='PASS',checks=len(report['checks']),llm_calls=0,mail_count=0)))

if __name__=='__main__':main()
