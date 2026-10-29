"""Owner-bound memory and verified continuation around the original HIGH protocol."""
import time
from .canonical import validate
from .crypto import random_id
from .audit_verify import verify_action
from chainguard_sandbox.protocol import ToolError

CURRENT_GRANT = object()
class ConversationError(ToolError):
    def __init__(self,code,sid,**details):
        super().__init__(code)
        self.details=dict(session_id=sid,accepted=False,**details)


class ConversationService:
    def __init__(self,operations):
        self.ops=operations;self.store=operations.conversations

    def create(self,id,owner,scope):
        # Reuse exactly the task validator without leaving a throwaway job behind.
        self.ops.create(random_id(),dict(scope,task_text='scope validation'),validate_only=True)
        self.store.create(id,owner,scope)
        return self.detail(id,owner)

    def summary(self,value):
        ids=self.store.runs(value['id'])
        first=value.get('legacy_job_id') or (ids[0] if ids else None)
        return dict(id=value['id'],state=value['state'],version=value['version'],created=value['created'],
                    title=self.ops.store.get(first)['task_text'] if first else '',latest_run_id=ids[-1] if ids else first)

    def detail(self,id,owner=None):
        value=self.store.get(id,owner)
        value.pop('history',None)  # Messages are rendered from ordered run projections.
        ids=([value['legacy_job_id']] if value.get('legacy_job_id') else [])+self.store.runs(id)
        value['runs']=[self.ops.detail(run) for run in ids]
        for run in value['runs']:
            run.pop('runner_snapshot',None);run.pop('continuation_results',None)
        if self.ops.config.get('tool_sessions',{}).get('conversation'):
            value['low_status']=self.ops.store.cached('conversation/'+id,{})
        value['authorization']=self.authorization(value)
        value['blocking_run']=self.blocking(value)
        value['messages']=[]
        for run in value['runs']:
            value['messages'].append(dict(role='user',content=run['task_text'],run_id=run['id']))
            for event in run.get('events',[]):
                if event.get('kind')=='AGENT_ATTEMPT':
                    value['messages'].append(dict(role='tool',tool_name=event['tool_name'],result=event['result'],run_id=run['id']))
            if run.get('agent_output'):value['messages'].append(dict(role='assistant',content=run['agent_output'],run_id=run['id']))
            if run.get('error'):value['messages'].append(dict(role='status',error_code=run['error'],state=run['scheduler_state'],run_id=run['id']))
        return value

    def authorization(self,value):
        envelope=value.get('low_grant')
        if value.get('pending_renewal'):return dict(status='RENEWING',grant_digest=(envelope or {}).get('digest'))
        if not envelope:return dict(status='MISSING' if self.ops.config.get('tool_sessions',{}).get('conversation') else 'NOT_APPLICABLE',grant_digest=None)
        m=envelope['message'];used=next((g['used'] for g in value.get('low_status',{}).get('grants',[]) if g['digest']==envelope['digest']),0)
        return dict(status='EXPIRED' if m['expiresAt']<=time.time() else 'EXHAUSTED' if used>=m['maxCalls'] else 'ACTIVE',grant_digest=envelope['digest'],expires_at=m['expiresAt'],used=used,max_calls=m['maxCalls'])

    def blocking(self,value):
        from .conversation_store import ACTIVE
        for run in value['runs']:
            if run['id']==value.get('legacy_job_id'):
                if value.get('legacy_resolved'):continue
                if run.get('record',{} ) and run['record']['state'].startswith('FINALIZED_'):continue
            if run['scheduler_state'] in ACTIVE:
                reason='WAITING_APPROVAL' if run['scheduler_state'] in {'AWAITING_APPROVAL','AWAITING_TOOL_APPROVAL'} else 'RESULT_UNKNOWN' if run['scheduler_state']=='UNKNOWN' else 'RUN_INTERRUPTED' if run['scheduler_state']=='INTERRUPTED' else 'RUNNING'
                return dict(run_id=run['id'],state=run['display_state'],reason=reason)
        return None

    def attach(self,job_id,owner):
        job=self.ops.store.get(job_id)
        if job.get('conversation_id'):return self.detail(job['conversation_id'],owner)
        sid=self.store.legacy_session(job_id)
        if sid:return self.detail(sid,owner)
        from .default_tools import selection
        from .conversation_memory import from_job
        tools,documents,mailboxes=selection(job)
        scope=dict(allowed_tools=tools,allowed_document_ids=documents,read_mailboxes=mailboxes,allowed_recipients=job['allowed_recipients'])
        for field in ['custom_tools','document_scope','session_grant']:
            if field in job:scope[field]=job[field]
        self.ops.create(random_id(),dict(scope,task_text='legacy scope validation'),validate_only=True)
        sid=self.store.attach_legacy(job_id,owner,scope,from_job(job,self.ops.store.events(job_id)))
        return self.detail(sid,owner)

    def resolve_legacy(self,value):
        legacy=value.get('legacy_job_id')
        if not legacy or value.get('legacy_resolved'):return
        job=self.ops.detail(legacy)
        from .conversation_store import ACTIVE
        if job['scheduler_state'] not in ACTIVE:return
        record=job.get('record')
        if not record or not record['state'].startswith('FINALIZED_'):raise ConversationError('CONVERSATION_BUSY',value['id'],blocking_run=dict(run_id=legacy,state=job['display_state']))
        checked=verify_action(self.ops.chain,dict(record,entry_id='legacy-'+legacy,group='C'))
        if checked['status']!='VERIFIED' or self.ops.bridge.observe(record['action_id']).get('status')!='VERIFIED':raise ToolError('CHAIN_UNAVAILABLE')
        from .conversation_memory import from_job
        self.store.update(value['id'],legacy_resolved=True,history=from_job(dict(job,state=record['state']),self.ops.store.events(legacy)))

    def append(self,id,owner,message_id,text,version):
        if type(text) is not str or not 1<=len(text.strip())<=8000 or type(version) is not int:raise ToolError('SCHEMA_INVALID')
        if self.store.accepted(id,owner,message_id,text):return self.detail(id,owner)
        value=self.store.get(id,owner)
        self.resolve_legacy(value)
        value=self.detail(id,owner)
        if value['state']!='OPEN':raise ConversationError('CONVERSATION_CLOSED',id)
        if value['version']!=version:raise ConversationError('STATE_CONFLICT',id)
        if value['blocking_run']:raise ConversationError('CONVERSATION_BUSY',id,blocking_run=value['blocking_run'])
        grant_digest=None
        if self.ops.config.get('tool_sessions',{}).get('conversation'):
            if value.get('pending_renewal') and value.get('low_grant'):raise ConversationError('AUTH_RENEWAL_PENDING',id)
            envelope=value.get('low_grant')
            if not envelope:
                from .conversation_runtime import issue
                envelope=issue(self.ops,id,owner,value['scope'].get('session_grant',dict(duration_seconds=86400,max_calls=50)))
            if envelope:
                wire={k:v for k,v in envelope.items() if k!='digest'}
                try:
                    checked=self.ops.bridge.conversation('preflight',dict(envelope=wire))
                    if checked.get('grant_digest')!=envelope['digest'] or checked.get('checked_gates')!=2:raise ToolError('APPROVAL_INVALID')
                except ToolError as error:
                    mapped={'SESSION_EXPIRED':'AUTH_EXPIRED','SESSION_EXHAUSTED':'AUTH_EXHAUSTED','SESSION_NOT_INSTALLED':'AUTH_RENEWAL_PENDING'}
                    if error.code in mapped:raise ConversationError(mapped[error.code],id,grant_digest=envelope['digest']) from None
                    raise
                grant_digest=envelope['digest']
        self.store.append(id,owner,message_id,text,version,grant_digest=grant_digest)
        return self.detail(id,owner)

    def close(self,id,owner):
        self.store.get(id,owner)
        grant=self.store.get(id,owner).get('low_grant')
        if grant:
            value=self.ops.bridge.call('requester',dict(op='sign-conversation-close',message=dict(sessionId=id,grantDigest=grant['digest'],closedAt=int(time.time()))))
            self.ops.bridge.conversation('close',value)
        self.store.close(id,owner)
        return self.detail(id,owner)

    def renew(self,id,owner,options,expected=CURRENT_GRANT,request_id=None):
        value=self.store.get(id,owner)
        if value['state']!='OPEN':raise ToolError('CONVERSATION_CLOSED')
        active={'QUEUED','AGENT_RUNNING','AWAITING_APPROVAL','AWAITING_TOOL_APPROVAL','RESUMING','UNKNOWN','INTERRUPTED'}
        if any(self.ops.store.get(r)['state'] in active for r in self.store.runs(id)):raise ToolError('CONVERSATION_BUSY')
        scope=dict(value['scope'],session_grant=options)
        self.ops.create(random_id(),dict(scope,task_text='explicit renewal validation'),validate_only=True)
        if not self.ops.config.get('tool_sessions',{}).get('conversation'):raise ToolError('SESSION_NOT_CONFIGURED')
        from .conversation_runtime import issue
        # API callers provide the expected digest; compatibility callers snapshot it.
        if expected is CURRENT_GRANT:expected=(value.get('low_grant') or {}).get('digest')
        issue(self.ops,id,owner,options,expected,request_id)
        return self.detail(id,owner)

    def ready(self,job):
        """Never inject a UI completion claim or redispatch an uncertain HIGH action."""
        snapshot=job.get('runner_snapshot')
        if not snapshot:return None
        if snapshot['cursor']>=len(snapshot['pending']):return None
        pending=snapshot['pending'][snapshot['cursor']]
        if job.get('action_id'):
            record=self.ops.records.get(job['action_id'])
            if record and record['state']=='AWAITING_APPROVAL' and not record.get('reservation_evidence') and int(record['intent']['expires_at'])<=time.time():
                snapshot=self.ops.chain.healthy();block=hex(int(snapshot['number']))
                from .chain_rpc import Contract
                reservations=[Contract('ExecutionRegistry',self.ops.chain.execution.address,node).call('getReservation',[record['action_id']],block) for node in self.ops.chain.nodes]
                if all(reservation['status']==0 for reservation in reservations):
                    return {pending['id']:dict(status='EXPIRED',action_id=record['action_id'],tool_executed=False,reason='原意图签名期限已过且当前链无预约。需要用户新一轮明确请求和全新双审批；本轮不得重发。')}
            if not record or record['state'] not in {'FINALIZED_OK','FINALIZED_ERROR','FINALIZED_REJECTED'}:return None
            checked=verify_action(self.ops.chain,dict(record,entry_id='resume-'+job['id'],group='C'))
            if checked['status']!='VERIFIED':return None
            observation=self.ops.bridge.observe(record['action_id'])
            if observation.get('status')!='VERIFIED':return None
            return {pending['id']:dict(status=record['state'],action_id=record['action_id'],verification=checked,tool_executed=record['state']=='FINALIZED_OK')}
        if job.get('resume_result'):
            return {pending['id']:job['resume_result']}
        return None
