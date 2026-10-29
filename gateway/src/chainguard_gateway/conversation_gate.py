"""Shared routing only; gateway and tool each own a separate signed quota database."""
from .conversation_grants import configured,builtin_revision
from .session_grants import configured_access,SessionAccess
from chainguard_sandbox.protocol import ToolError


class ConversationStrongAccess(SessionAccess):
    def log(self,id,request,value,outcome,result):
        # Exact strong approvals retain their private journal. LOW inclusion is
        # recorded by the conversation gate, with no duplicate V1 global batch.
        value.update(audit_track='CONVERSATION_LOW',audit_result=result,audit_outcome=outcome)
        with self.connect() as db:db.execute('UPDATE session_calls SET data=? WHERE id=?',(self.seal(id,value),id))


def strong_access(store,urls,low):
    old=configured_access(store,urls)
    return ConversationStrongAccess(old.store,old.policy) if low and isinstance(old,SessionAccess) else old


def gateway(store,urls,request,key,requester,dispatch):
    access=configured(store,urls)
    if not access or not access.bound(request['task_id']):return None,False
    request=dict(request)
    if 'revision' not in request:request['revision']=builtin_revision(request['tool_name'])
    risk=access.policy.admission(request['revision'])['risk_level']
    reason='HIGH_RISK' if risk=='HIGH' else None
    if risk=='LOW':
        try:return access.execute(request,key,lambda:dispatch(request,None),requester=requester),True
        except ToolError as error:
            if error.code not in {'SESSION_EXPIRED','SESSION_EXHAUSTED'}:raise
            reason=error.code
    old=strong_access(store,urls,risk=='LOW')
    def approved(auth):
        if risk=='LOW':
            if auth is None:raise ToolError('APPROVAL_INVALID')
            return access.execute(request,key,lambda:dispatch(request,auth),requester=requester,strong=True)
        return dispatch(request,auth)
    result=old.execute(request,key,approved,requester=requester)
    if result.get('status')=='AWAITING_TOOL_APPROVAL' and reason:result=dict(result,error_code=reason)
    return result,True


def tool(store,urls,request,key,authorization,dispatch):
    access=configured(store,urls)
    if not access or not access.bound(request['task_id']):raise ToolError('APPROVAL_INVALID')
    if authorization is not None:
        low=access.policy.admission(request['revision'])['risk_level']=='LOW'
        def approved(_):
            if low:return access.execute(request,key,dispatch,strong=True)
            return dispatch()
        return strong_access(store,urls,low).execute(request,key,approved,authorization=authorization)
    return access.execute(request,key,dispatch)
