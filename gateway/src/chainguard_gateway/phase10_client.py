"""Local operator stdio adapters. No model-facing signing API; original /v1 unchanged."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import time

from eth_account import Account
from eth_account.messages import encode_typed_data

from .phase6_server import load, client
from .chain_transport import TLSClient, PeerCertificateProtocol
from .chain_crypto import digest, recover_receipt
from .crypto import commit, random_id, typed_intent
from .canonical import canonical, validate
from .chain_store import ChainStore
from .chain_rpc import Chain
from .chain_service import ChainService
from .phase7_server import gateway_extensions, tool_extensions
from chainguard_sandbox.protocol import ToolError
from chainguard_sandbox.storage import Store, require_container
from chainguard_sandbox.chain_mail import ChainMailTool


def connection(root, config, subject=None):
    tokens=json.loads((root/'tokens.json').read_text())
    return TLSClient('https://phase6-gateway:8443',root/'ca.pem',root/'client.pem',root/'client.key',tokens[subject or config['subject']])


def adapter(value):
    root,c=load(); role=c['subject']; op=value['op']
    conn=connection(root,c)
    if op in {'sign-conversation-grant','sign-conversation-bind','sign-conversation-close'}:
        from .conversation_runtime import control
        return control(root,c,op,value)
    if op in {'sign-session','sign-tool-review','sign-tool-use'}:
        from .session_runtime import control
        return control(root,c,op,value)
    if op=='health': return conn.request('GET','/health/ready')
    if role=='requester' and op=='create_task':
        body=value['body']; validate('CreateTaskRequest',body)
        return conn.request('POST','/v1/tasks',body,value['key'])
    if role=='agent' and op=='request':
        method,path=value['method'],value['path']
        if not (method=='POST' and path in {'/v1/agent/actions/propose','/agent/v1/reads','/agent/v1/library','/agent/v1/custom-tools/query'} or method=='GET' and path.startswith('/v1/actions/') and len(path.split('/'))==4):
            raise ToolError('FORBIDDEN')
        return conn.request(method,path,value.get('body'),value.get('key'))
    if role in {'requester','biz','security'} and op=='review':
        validate('Bytes32',value['action_id'])
        result=conn.request('GET','/operator/v1/actions/'+value['action_id']+'/review')
        if commit('params',result['params_salt'],result['params'])!=result['intent']['params_commit']: raise ToolError('PARAMS_MISMATCH')
        return {'intent':result['intent'],'params':result['params'],'intent_digest':digest('ActionIntent',result['intent'],c['domain'])}
    if role in {'requester','biz','security'} and op=='sign':
        reviewed=adapter({'op':'review','action_id':value['action_id']})
        if reviewed['intent_digest']!=value['intent_digest']: raise ToolError('PARAMS_MISMATCH')
        signature='0x'+Account.sign_message(encode_typed_data(full_message=typed_intent(reviewed['intent'],c['domain'])),(root/'signing.key').read_bytes()).signature.hex()
        if role=='requester': return {'signature':signature,'intent_digest':reviewed['intent_digest']}
        record=conn.request('POST','/v1/actions/'+value['action_id']+'/approve',{'signature':signature})
        return {'record':record,'signature':signature,'signer':c['address'],'organization':c['organization'],'intent_digest':reviewed['intent_digest']}
    if role=='requester' and op=='reserve':
        return connection(root,c,'executor').request('POST','/v1/actions/'+value['action_id']+'/reserve',{'requester_signature':value['signature']},value['key'])
    raise ToolError('FORBIDDEN')


def snapshot():
    root,c=load(); store=ChainStore(root); result=[]
    with store.connect() as db:
        for row in db.execute('SELECT * FROM actions ORDER BY rowid'):
            data=store.unseal('action/'+row['action_id'],row['data'])
            result.append({'action_id':row['action_id'],'task_id':row['task_id'],'risk':2,'state':row['state'],
                'chain_state':data.get('chain_state','NONE'),'intent':data['intent'],'receipt':data.get('receipt'),
                'requester_signature':data.get('requester_signature'),'approval_signatures':list(data['approvals'].values()),
                'tool_signature':data.get('tool_signature'),'reservation_evidence':data.get('reservation_evidence'),
                'finalization_evidence':data.get('finalization_evidence'),'error':data.get('error')})
    return result


def web_snapshot(value):
    """One IPC read of durable events and projections; no eth_call or authorization cache."""
    root,c=load();store=ChainStore(root)
    with store.connect() as db:
        events=[dict(sequence=r['sequence'],action_id=r['action_id'],event=r['event'],data=json.loads(r['data'])) for r in db.execute('SELECT * FROM chain_events WHERE sequence>? ORDER BY sequence LIMIT 500',(int(value.get('cursor',0)),))]
        transactions=[dict(action_id=r['action_id'],kind=r['kind'],tx_hash=r['tx_hash'],state=r['state']) for r in db.execute('SELECT action_id,kind,tx_hash,state FROM chain_transactions')]
        timings=[dict(r) for r in db.execute('SELECT * FROM transaction_metrics')] if db.execute("SELECT 1 FROM sqlite_master WHERE name='transaction_metrics'").fetchone() else []
    result=dict(records=snapshot(),events=events,transactions=transactions,performance=timings,sessions={'calls':[],'observations':[]},conversations={})
    if c.get('tool_sessions') or (root/'tool-sessions.json').exists():
        from .session_runtime import control
        result['sessions']=control(root,c,'session-list',{})
        from .conversation_runtime import access_for
        from .conversation_audit import observations
        access=access_for(root,c)
        if access:
            with access.connect() as db:ids=[r[0] for r in db.execute('SELECT DISTINCT session_id FROM conversation_grants')]
            result['conversations']={sid:dict(access.status(sid),observations=observations(access,sid)) for sid in ids}
    return result


def observe(action_id, include_mime=False):
    """Runs against a readonly original tool-volume mount; never executes a tool."""
    validate('Bytes32',action_id); root,c=load()
    from Crypto.Cipher import AES
    from email.parser import BytesParser
    from email import policy
    with sqlite3.connect('file:'+str(root/'state.sqlite3')+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row
        mails=db.execute('SELECT message_id,recipient,mime,mime_sha256 FROM mailbox WHERE action_id=? ORDER BY message_id',(action_id,)).fetchall()
        encrypted=db.execute('SELECT params_commit,data FROM chain_mail WHERE action_id=?',(action_id,)).fetchone()
    result={'action_id':action_id,'checked_at_utc':datetime.now(timezone.utc).isoformat(),'mail_count':len(mails),
        'read_only_mount':True,'sqlite_mode':'ro','status':'ABSENT' if not mails and not encrypted else 'INVALID','messages':[]}
    if not encrypted: return result
    blob=encrypted['data']; cipher=AES.new((root/'data.key').read_bytes(),AES.MODE_GCM,nonce=blob[:16]); cipher.update(action_id.encode())
    stored=json.loads(cipher.decrypt_and_verify(blob[32:],blob[16:32]))
    wire=stored['receipt']
    if wire['action_id']!=action_id or wire['params_commit']!=encrypted['params_commit']: raise ToolError('RECEIPT_INVALID')
    if commit('result',stored['result_salt'],stored['result'])!=wire['result_commit'] or commit('evidence',stored['evidence_salt'],stored['evidence'])!=wire['evidence_index_commit']:
        raise ToolError('RECEIPT_INVALID')
    deployments=[c['deployment'],*c['deployment'].get('legacyDeployments',[])]
    matches=[]
    for deployment in deployments:
        domain={'name':'ChainGuard AuditRegistry','version':'1','chainId':str(deployment['chainId']),
            'verifyingContract':deployment['contracts']['AuditRegistry']['address'].lower()}
        if recover_receipt(wire,domain,stored['tool_signature'])==c['tool_signer']:matches.append(domain)
    if len(matches)!=1: raise ToolError('RECEIPT_INVALID')
    if ([str(m['message_id']) for m in mails]!=stored['result']['message_ids'] or
        [m['recipient'] for m in mails]!=stored['result']['delivered_recipients'] or
        any(m['mime_sha256']!=stored['result']['mime_sha256'] for m in mails)):
        raise ToolError('RECEIPT_INVALID')
    for m in mails:
        raw=m['mime']; sha=hashlib.sha256(raw).hexdigest()
        if sha!=m['mime_sha256']: raise ToolError('RECEIPT_INVALID')
        item={'message_id':m['message_id'],'recipient':m['recipient'],'mime_sha256':sha}
        if include_mime:
            parsed=BytesParser(policy=policy.default).parsebytes(raw)
            item.update(subject=str(parsed['Subject']),body=parsed.get_body(preferencelist=('plain',)).get_content(),mime=raw.decode('utf8'))
        result['messages'].append(item)
    return dict(result,status='VERIFIED',receipt=wire,tool_signature=stored['tool_signature'])


class ReceiptLoss:
    """Explicit local demonstration fault: actual delivery, lost response; no fake receipt."""
    def __init__(self, base, root): self.base,self.root=base,root
    def request(self, method, path, body=None, key=None):
        file=self.root/'receipt-hold.json'
        held=json.loads(file.read_text()) if file.exists() else []
        aid=body['intent']['action_id'] if body and 'intent' in body else path.rsplit('/',1)[-1]
        if method=='GET' and aid in held: raise ToolError('EXECUTION_UNKNOWN')
        result=self.base.request(method,path,body,key)
        if method=='POST' and aid in held: raise ToolError('EXECUTION_UNKNOWN')
        return result


def serve_gateway():
    import ssl
    import uvicorn
    root,c=load(); store=ChainStore(root); chain=Chain(c['deployment'],c['rpc_urls'])
    service=ChainService(store,chain,ReceiptLoss(client(root,c['tool_client']),root),(root/'relay.key').read_bytes(),c['tool_signer'])
    app=gateway_extensions(service,c)
    from .session_runtime import start_batch_worker
    start_batch_worker(root,c,service.stop)
    uvicorn.run(app,host='0.0.0.0',port=8443,http=PeerCertificateProtocol,access_log=False,log_level='warning',
        ssl_keyfile=str(root/'server.key'),ssl_certfile=str(root/'server.pem'),ssl_ca_certs=str(root/'ca.pem'),ssl_cert_reqs=ssl.CERT_REQUIRED)


def main():
    require_container()
    parser=argparse.ArgumentParser(); parser.add_argument('command',choices=['call','snapshot','web-snapshot','observe','gateway','tokens','fault','library-grant','custom-install','custom-disable','custom-grant','session-install','session-list','session-review','session-approve','session-flush','admission-submit','conversation-install','conversation-bind','conversation-close','conversation-status','conversation-flush','conversation-activate','conversation-preflight'])
    args=parser.parse_args()
    try:
        if args.command=='gateway': serve_gateway(); return
        if args.command=='snapshot': result=snapshot()
        else:
            value=json.load(sys.stdin)
            if args.command=='web-snapshot':result=web_snapshot(value)
            elif args.command=='call': result=adapter(value)
            elif args.command.startswith('conversation-'):
                from .conversation_runtime import control
                root,c=load();result=control(root,c,args.command,value)
            elif args.command.startswith('session-') or args.command=='admission-submit':
                from .session_runtime import control
                root,c=load();result=control(root,c,args.command,value)
            elif args.command=='observe': result=observe(value['action_id'],value.get('include_mime',False))
            elif args.command=='library-grant':
                from chainguard_sandbox.default_library import DefaultLibrary
                root,c=load(); store=Store(root)
                result=DefaultLibrary(store).grant(store.private_read('operator.key').decode(),**value)
            elif args.command in {'custom-install','custom-disable','custom-grant'}:
                from chainguard_sandbox.custom_library import CustomLibrary
                root,c=load();store=Store(root);library=CustomLibrary(store)
                operation={'custom-install':library.install,'custom-disable':library.disable,'custom-grant':library.grant}[args.command]
                result=operation(store.private_read('operator.key').decode(),**value)
            elif args.command=='tokens':
                from .identity import issue_token
                root,c=load(); key=ChainStore(root).private('jwt.key')
                result={name:issue_token(key,name,lifetime=900) for name in ['requester','executor','biz','security','agent']}
            else:
                root,c=load(); validate('Bytes32',value['action_id']); path=root/'receipt-hold.json'
                held=set(json.loads(path.read_text()) if path.exists() else [])
                if value['hold']: held.add(value['action_id'])
                else: held.discard(value['action_id'])
                path.write_bytes(canonical(sorted(held))); result={'configured':True}
        print(json.dumps({'ok':True,'result':result}),flush=True)
    except ToolError as error: print(json.dumps({'ok':False,'error':error.code}),flush=True)
    except Exception as error: print(json.dumps({'ok':False,'error':'EXECUTION_UNKNOWN','error_type':type(error).__name__}),flush=True)


if __name__=='__main__': main()
