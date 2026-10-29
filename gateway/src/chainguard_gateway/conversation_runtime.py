"""Trusted signing/install controls; never exposed to the Agent or browser."""
import json
import secrets
import time
from .conversation_grants import ConversationPolicy,ConversationAccess,domain,digest,builtin_revision
from .session_grants import hash_json,sign
from chainguard_sandbox.protocol import ToolError


def access_for(root,c):
    from .session_runtime import access_for as legacy
    old=legacy(root,c)
    return ConversationAccess(old.store,ConversationPolicy(old.policy.config,c['rpc_urls'])) if old and old.policy.config.get('conversation') else None


def control(root,c,op,value):
    if op.startswith('sign-conversation-'):
        if c['subject']!='requester':raise ToolError('FORBIDDEN')
        kind={'sign-conversation-grant':'ConversationGrant','sign-conversation-bind':'ConversationBinding','sign-conversation-close':'ConversationClose'}[op]
        config=json.loads((root/'tool-sessions.json').read_text());m=value['message']
        if kind=='ConversationGrant' and m['requester'].lower()!=c['address'].lower():raise ToolError('FORBIDDEN')
        return dict(message=m,signature=sign(kind,m,domain(config),(root/'signing.key').read_bytes()))
    access=access_for(root,c)
    if not access:raise ToolError('SESSION_NOT_CONFIGURED')
    if op=='conversation-install':return access.install(value)
    if op=='conversation-bind':return access.bind(value)
    if op=='conversation-activate':return access.activate(value)
    if op=='conversation-preflight':return access.preflight(value['envelope'])
    if op=='conversation-close':return access.close(value)
    if op=='conversation-status':
        from .conversation_audit import observations
        return dict(access.status(value['session_id']),observations=observations(access,value['session_id']))
    if op=='conversation-flush':
        from .conversation_audit import Publisher
        return Publisher(access,(root/'conversation-anchor.key').read_bytes()).flush(force=True,session_id=value['session_id'])
    raise ToolError('FORBIDDEN')


def policy_for(ops):
    return ConversationPolicy(ops.config['tool_sessions'],['http://127.0.0.1:8545','http://127.0.0.1:8547'])


def scopes_for(policy,scope):
    from .default_tools import READ_TOOLS
    scopes=[]
    for name in scope['allowed_tools']:
        if name in READ_TOOLS:
            revision=builtin_revision(name);keys=scope['allowed_document_ids'] if name.startswith('doc.') else scope['read_mailboxes']
        elif name.startswith('custom.'):
            item=next(g for g in scope['custom_tools'] if g['name']==name);revision=item['revision'];keys=item['allowed_keys']
        else:continue
        admitted=policy.admission(revision)
        if admitted['risk_level']=='LOW':scopes.append(dict(name=name,revision=revision,allowed_keys=keys,generation=admitted['generation']))
    return scopes


def issue(ops,sid,owner,options,expected=None,request_id=None):
    """Persist signed material, install at BOTH gates, then publish the new grant."""
    c=ops.conversations.get(sid,owner);policy=policy_for(ops)
    scopes=scopes_for(policy,c['scope'])
    if not scopes:return None
    if c.get('low_grant'):
        # A renewal may shorten scope, but cannot silently re-admit changed tools.
        old={s['name']:s for s in c['low_grant']['scopes']}
        if any(s['name'] not in old or s!=old[s['name']] for s in scopes):raise ToolError('POLICY_REVOKED')
    now=int(time.time())
    m=dict(requester=ops.config['signers']['requester'],agent=ops.config['signers']['agent'],sessionId=sid,toolsHash=hash_json(scopes),nonce=secrets.randbits(52),issuedAt=now,expiresAt=now+options['duration_seconds'],maxCalls=options['max_calls'])
    id=digest('ConversationGrant',m,policy.domain)
    request_id=request_id or '0x'+secrets.token_hex(32)
    request_id=ops.conversations.begin_renewal(sid,owner,request_id,expected,options,m,scopes,id)
    renewal=ops.conversations.renewal(request_id)
    if renewal['state']=='ACTIVE':return ops.conversations.get(sid,owner).get('low_grant')
    envelope=renewal.get('envelope')
    if envelope is None:
        signed=ops.bridge.call('requester',dict(op='sign-conversation-grant',message=renewal['message']))
        envelope=dict(message=renewal['message'],scopes=renewal['scopes'],signature=signed['signature'],digest=renewal['digest'])
        ops.conversations.save_renewal(request_id,envelope)
    wire={k:v for k,v in envelope.items() if k!='digest'}
    ops.bridge.conversation('install',wire)
    confirmed=ops.bridge.conversation('activate',dict(envelope=wire,previous_digest=renewal['previous_digest']))
    if confirmed.get('grant_digest')!=envelope['digest'] or not confirmed.get('active') or confirmed.get('checked_gates')!=2:raise ToolError('EXECUTION_UNKNOWN')
    # Expired material can finish crash recovery, but never permits a new call.
    ops.conversations.activate_renewal(sid,request_id)
    return envelope


def prepare(ops,job,task):
    c=ops.conversations.get(job['conversation_id']);envelope=c.get('low_grant')
    if not envelope:
        # Compatibility for tasks accepted before this version. New HTTP messages
        # provision the initial grant before enqueueing instead.
        if job.get('conversation_grant_digest'):raise ToolError('APPROVAL_INVALID')
        envelope=issue(ops,c['id'],c['owner'],c['scope'].get('session_grant',dict(duration_seconds=86400,max_calls=50)))
    if not envelope:return
    if job.get('conversation_grant_digest') and job['conversation_grant_digest']!=envelope['digest']:raise ToolError('STATE_CONFLICT')
    wire={k:v for k,v in envelope.items() if k!='digest'}
    # Install is idempotent, but never implicitly renew expired credentials.
    ops.bridge.conversation('install',wire)
    binding=job.get('conversation_binding')
    if not binding:
        binding=ops.bridge.call('requester',dict(op='sign-conversation-bind',message=dict(sessionId=c['id'],taskId=task['task_id'],grantDigest=envelope['digest'],expiresAt=min(int(task['expires_at']),envelope['message']['expiresAt']))))
        ops.store.update(job['id'],conversation_binding=binding)
    ops.bridge.conversation('bind',binding)
