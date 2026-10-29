"""GET-only live observer. Public DB only; no execution bridge, keys or private volumes."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import sqlite3
import time
from fastapi import FastAPI,HTTPException,Request
from fastapi.responses import JSONResponse,FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from .audit_verify import make_chain,verify_action
from .chain_crypto import recover_receipt
from chainguard_sandbox.protocol import ToolError
from .default_tools import READ_TOOLS
from .custom_tools import is_custom


def verify_live_entry(chain,row):
    from .mail_window import chain_for_action
    try:chain=chain_for_action(chain,row)
    except (ValueError,KeyError,TypeError):return dict(status='INVALID',reason='UNTRUSTED_RESERVATION_REGISTRY',transactions=[],current_chain_state=None)
    if row.get('conversation_observation'):
        from .conversation_audit import check,verify
        from .conversation_grants import ConversationPolicy
        o=row['conversation_observation'];result=dict(status='PENDING_BATCH',checked_at_utc=datetime.now(timezone.utc).isoformat(),current_chain_state=None,transactions=[],reason='LOW会话日志已持久化，等待真实根交易确认')
        if any(row.get(k) for k in ['action_id','intent','receipt','tool_signature','reservation_evidence','finalization_evidence','requester_signature','approval_signatures']):return dict(result,status='INVALID',reason='HIGH_IS_NOT_LOW')
        if o['status']!='ANCHORED':return result
        try:
            trusted=getattr(chain,'tool_sessions',None)
            if not trusted or row['tool_policy']!=trusted:return dict(result,status='INVALID',reason='UNTRUSTED_BATCH_DEPLOYMENT')
            if o['leaf_index']!=o['log']['sequence']-1 or not check(o['log'],o['proof'],o['batch']):return dict(result,status='INVALID',reason='MERKLE_PROOF_INVALID')
            evidence=verify(ConversationPolicy(trusted,[n.url for n in chain.nodes]),o['batch'],o['tx_hash'])
            return dict(result,status='BATCH_VERIFIED',evidence=evidence,merkle_root=o['batch']['root'],grant_digest=o['log'].get('grant_digest'),sequence=o['log']['sequence'],reason=f"LOW会话记录包含于区块 {evidence['block_number']}，交易 {o['tx_hash']}，验证通过；HIGH仍独立预约和确认")
        except (ToolError,KeyError,ValueError,TypeError) as e:return dict(result,status='UNAVAILABLE' if isinstance(e,ToolError) and e.code=='CHAIN_UNAVAILABLE' else 'INVALID',reason=e.code if isinstance(e,ToolError) else 'MERKLE_PROOF_INVALID')
    if row.get('batch_observation') and not any(row.get(k) for k in ['action_id','intent','receipt','tool_signature','reservation_evidence','finalization_evidence','requester_signature','approval_signatures']):
        from .batch_audit import check_proof,verify_batch
        from .session_grants import ToolPolicy
        observation=row['batch_observation']
        result=dict(status='PENDING_BATCH',checked_at_utc=datetime.now(timezone.utc).isoformat(),reason='本地日志已持久化，等待批量根上链；尚无不可篡改的链上包含性证明。',current_chain_state=None,transactions=[])
        if observation['status']!='ANCHORED':return result
        try:
            if not check_proof(observation['log'],observation['proof'],observation['batch']['root']):return dict(result,status='INVALID',reason='MERKLE_PROOF_INVALID')
            config=row['tool_policy']
            # Trusted observer deployment pins additive registry addresses/code hashes, not the public DB.
            trusted=getattr(chain,'tool_sessions',None)
            if trusted is None or config!=trusted:return dict(result,status='INVALID',reason='UNTRUSTED_BATCH_DEPLOYMENT')
            policy=ToolPolicy(trusted,[n.url for n in chain.nodes]);evidence=verify_batch(policy,observation['batch'],observation['tx_hash'])
            return dict(result,status='BATCH_VERIFIED',evidence=evidence,merkle_root=observation['batch']['root'],reason=f"该记录已包含在区块 {evidence['block_number']} 的交易 {evidence['tx_hash']} 中，Merkle 包含性验证通过；不证明外部工具诚实或替代R2回执。")
        except (ToolError,KeyError,TypeError,ValueError) as error:return dict(result,status='UNAVAILABLE' if isinstance(error,ToolError) and error.code=='CHAIN_UNAVAILABLE' else 'INVALID',reason=error.code if isinstance(error,ToolError) else 'BATCH_INVALID')
    if (row.get('risk')==1 and is_custom(row.get('tool')) and row.get('adapter')=='http.request' and
        not any(row.get(k) for k in ['action_id','intent','receipt','tool_signature','reservation_evidence','finalization_evidence','requester_signature','approval_signatures'])):
        return {'status':'EXTERNAL_TOOL_OBSERVATION','checked_at_utc':datetime.now(timezone.utc).isoformat(),
            'current_chain_state':None,'transactions':[],
            'reason':'R1 外部 API 查询／推理记录。请求与响应摘要来自隔离工具的持久记录，不是链上预约、签名回执或独立来源认证。'}
    if (row.get('tool') in {'attachment.read','document.create','document.revise'} and row.get('risk') in {0,1} and
        not any(row.get(k) for k in ['action_id','intent','receipt','tool_signature','reservation_evidence','finalization_evidence','requester_signature','approval_signatures'])):
        return {'status':'LOCAL_DOCUMENT_OBSERVATION','checked_at_utc':datetime.now(timezone.utc).isoformat(),
            'current_chain_state':None,'transactions':[],
            'reason':'本地附件读取或新副本生成记录，摘要来自私有服务的公开投影。请在业务台下载文件核对摘要；不是链上执行认证。'}
    if (row.get('risk')==0 and (row.get('tool') in READ_TOOLS or is_custom(row.get('tool'))) and
        not any(row.get(k) for k in ['action_id','intent','receipt','tool_signature','reservation_evidence','finalization_evidence','requester_signature','approval_signatures'])):
        return {'status':'READ_ONLY_OBSERVATION','checked_at_utc':datetime.now(timezone.utc).isoformat(),
            'current_chain_state':None,'transactions':[],
            'reason':'R0 只读任务不需要链上预约。这里展示服务端读取日志摘要，不是链上认证或独立来源证明。'}
    if row.get('receipt') and not row.get('finalization_evidence'):
        # Verify the reservation through the unchanged verifier, while making
        # explicit that a locally signed result has not yet been anchored.
        result=verify_action(chain,dict(row,receipt=None,tool_signature=None))
        if result['status']!='PENDING_RECEIPT': return result
        receipt=row['receipt']
        if receipt['action_id']!=row['action_id'] or receipt['params_commit']!=row['intent']['params_commit']:
            return dict(result,status='INVALID',reason='RECEIPT_INVALID')
        try:
            signer=recover_receipt(receipt,chain.receipt_domain,row['tool_signature'])
            valid=chain.policy.call('isToolSigner',[row['intent']['tool_id'],signer],hex(int(result['snapshot']['number'])))
            if not valid:return dict(result,status='INVALID',reason='RECEIPT_INVALID')
            return dict(result,status='PENDING_ANCHOR',tool_signature_valid=True,tool_signer=signer,
                reason='预约及工具签名已核对，回执尚未链上确认；不声明FINALIZED')
        except ToolError as error:return dict(result,status='UNAVAILABLE' if error.code=='CHAIN_UNAVAILABLE' else 'INVALID',reason=error.code)
    result=verify_action(chain,row)
    if result['status']=='NO_RESERVATION' and row.get('intent'):
        expired=int(row['intent']['expires_at'])<=time.time()
        approvals=len(row.get('approval_signatures',[]))
        if expired:
            result.update(next_step='CREATE_NEW_TASK',reason='未观察到预约交易，且原动作的签名期限已过。请在业务台新建任务、重新审批，再由请求者发起链上预约；旧动作不会补发。')
        elif approvals>=2:
            result.update(next_step='REQUESTER_RESERVE',reason='两份组织审批已记录，但尚未形成预约交易。请切回业务台的请求者身份，审阅同一意图后点击“发起链上预约并执行”；审批不会自动发邮件。')
        else:
            result.update(next_step='COMPLETE_APPROVALS',reason=f'未观察到预约交易，当前记录有{approvals}/2份组织审批。请先完成双组织审批，再由请求者在业务台发起链上预约。')
    return result


def create_live_audit_app(database,chain,static=None):
    from .verification_jobs import VerificationJobs
    jobs=VerificationJobs()
    app=FastAPI(docs_url=None,redoc_url=None,openapi_url='/audit-api/openapi.json')
    app.add_middleware(TrustedHostMiddleware,allowed_hosts=['127.0.0.1','localhost','testserver'])
    def actions():
        # Database and parent are provisioned by the trusted publisher; open readonly on each GET.
        with sqlite3.connect('file:'+Path(database).as_posix()+'?mode=ro',uri=True) as db:
            return [json.loads(r[0]) for r in db.execute('SELECT data FROM actions ORDER BY rowid DESC')]
    @app.middleware('http')
    async def headers(request,call_next):
        response=await call_next(request)
        response.headers.update({'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer',
            'Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"})
        return response
    @app.get('/health/live')
    def live(): return {'status':'alive','read_only':True,'source':'live-public-database'}
    @app.get('/health/ready')
    def ready(): return {'status':'ready','actions':len(actions()),'ledger_checked':False}
    @app.get('/audit-api/v1/actions')
    def listing(group:str|None=None,state:str|None=None):
        rows=[a for a in actions() if (not group or a['group']==group) and (not state or a['state']==state)]
        return {'schema_version':1,'actions':rows,'total':len(rows),'read_only':True,'generated_at_utc':datetime.now(timezone.utc).isoformat(),
            'trust_note':'动态只读投影。点击实时核验独立查四节点与原签名；副作用验证时间单列。不授予执行权。'}
    @app.get('/audit-api/v1/actions/{entry_id}')
    def detail(entry_id:str):
        row=next((a for a in actions() if a['entry_id']==entry_id),None)
        if row is None: raise HTTPException(404)
        return row
    @app.get('/audit-api/v1/actions/{entry_id}/verify')
    def verify(entry_id:str,request:Request):
        row=detail(entry_id)
        def check():
            result=verify_live_entry(chain,row);result['tool_observation']=row.get('tool_observation');return result
        if request.headers.get('prefer')=='respond-async':
            try:return JSONResponse(jobs.submit(json.dumps(row,sort_keys=True),check),status_code=202)
            except ToolError:return JSONResponse({'error':{'code':'QUEUE_FULL'}},status_code=429)
        return check()
    @app.get('/audit-api/v1/verifications/{id}')
    def verification(id:str):
        try:return jobs.get(id)
        except ToolError:raise HTTPException(404) from None
    @app.get('/audit-api/v1/network')
    def network():
        try: return {'status':'ONLINE','chain_id':'20261026','nodes':4,'snapshot':chain.healthy()}
        except ToolError: return JSONResponse({'status':'UNAVAILABLE','snapshot':None},status_code=503)
    if static:
        app.mount('/assets',StaticFiles(directory=Path(static)/'assets'),name='assets')
        @app.get('/')
        def index(): return FileResponse(Path(static)/'index.html')
    return app


def main():
    p=argparse.ArgumentParser(); p.add_argument('--config',type=Path,required=True); a=p.parse_args()
    c=json.loads(a.config.read_text(encoding='utf8'))
    chain=make_chain(c['deployment'],[f'http://127.0.0.1:{port}' for port in range(8545,8549)])
    chain.tool_sessions=c.get('tool_sessions')
    app=create_live_audit_app(c['public_db'],chain,c['static'])
    import uvicorn
    uvicorn.run(app,host='127.0.0.1',port=c['port'],access_log=False)


if __name__=='__main__': main()
