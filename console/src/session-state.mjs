export const activeSessionKey='chainguard.activeConversation.v1';
export function conversationBusy(conversation){
 if(conversation?.blocking_run)return true;
 if(conversation?.legacy_job_id)return Boolean(conversation.runs?.some(r=>r.id!==conversation.legacy_job_id&&['QUEUED','AGENT_RUNNING','AWAITING_APPROVAL','AWAITING_TOOL_APPROVAL','RESUMING','UNKNOWN','INTERRUPTED'].includes(r.scheduler_state)));
 return Boolean(conversation?.runs?.some(r=>['QUEUED','AGENT_RUNNING','AWAITING_APPROVAL','AWAITING_TOOL_APPROVAL','RESUMING','UNKNOWN','INTERRUPTED'].includes(r.scheduler_state)));
}
export function messageRequest(text,version,messageId){return {message_id:messageId,text,expected_version:version};}
export function renewableError(error){return error?.details?.accepted===false&&['AUTH_EXPIRED','AUTH_EXHAUSTED','AUTH_RENEWAL_PENDING'].includes(error.code);}
export function canRetryMessage(pending,conversation,activeId){return Boolean(pending&&conversation?.id===activeId&&pending.sessionId===activeId&&conversation.version===pending.request.expected_version&&conversation.authorization?.status==='ACTIVE'&&!conversationBusy(conversation));}
