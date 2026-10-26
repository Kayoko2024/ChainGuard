"""TEST ONLY: real TLS fault proxy and R2 acceptance client. No production hooks."""
import argparse
import base64
from functools import lru_cache
import hashlib
import http.client
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
import ssl
import threading
import time
import urllib.request

from eth_account import Account
from eth_account.messages import encode_typed_data
from eth_utils import keccak
import rlp

from chainguard_gateway.canonical import canonical,parse_json,validate
from chainguard_gateway.crypto import random_id,typed_intent
from chainguard_gateway.chain_transport import TLSClient
from chainguard_gateway.phase6_server import load,client
from chainguard_sandbox.protocol import ToolError

ROOT,CONFIG=load()
STATE=ROOT/'control.json'
LOCK=threading.RLock()


def read_state():
    with LOCK:
        return json.loads(STATE.read_text()) if STATE.exists() else {}


def update(**changes):
    with LOCK:
        value=read_state()
        value.update(changes)
        STATE.write_bytes(canonical(value))
        return value


def event(name,**fields):
    with LOCK:
        with (ROOT/'fault-events.jsonl').open('ab') as stream:
            stream.write(canonical({'event':name,'at':str(int(time.time())),**fields})+b'\n')


def rpc_forward(index,data):
    # All targets are fixed internal HTTP Besu endpoints. A fresh urllib opener
    # builds an unused TLS trust store on every call; cyclic collection can lag
    # behind this high-frequency proxy and exhaust its cgroup memory.
    connection=http.client.HTTPConnection('node'+str(index+1),8545,timeout=6)
    try:
        connection.request('POST','/',data,{'Content-Type':'application/json','Host':'localhost'})
        response=connection.getresponse()
        if response.status!=200: raise OSError('Besu RPC transport unavailable')
        return response.read(65536)
    finally:
        connection.close()


def rpc_handler(index):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def do_POST(self):
            body=self.rfile.read(min(int(self.headers.get('content-length','0')),65536))
            mode=read_state()
            if mode.get('gateway_rpc_down') and index in (0,2) or mode.get('tool_rpc_down') and index in (1,3):
                self.send_error(503)
                return
            try:
                request=parse_json(body)
                if mode.get('audit_reject_once') and request.get('method')=='eth_sendRawTransaction':
                    raw=bytes.fromhex(request['params'][0][2:])
                    tx=rlp.decode(raw)
                    if tx[3].hex()==CONFIG['deployment']['contracts']['AuditRegistry']['address'][2:].lower():
                        update(audit_reject_once=False,gateway_rpc_down=True)
                        event('audit_not_delivered_to_node',tx_hash='0x'+keccak(raw).hex())
                        self.send_error(503)
                        return
                response=rpc_forward(index,body)
                if mode.get('audit_drop_once') and request.get('method')=='eth_sendRawTransaction':
                    raw=bytes.fromhex(request['params'][0][2:])
                    tx=rlp.decode(raw)
                    if tx[3].hex()==CONFIG['deployment']['contracts']['AuditRegistry']['address'][2:].lower():
                        accepted=json.loads(response).get('result')
                        if accepted:
                            update(audit_drop_once=False,gateway_rpc_down=True)
                            event('audit_broadcast_response_lost',tx_hash=accepted)
                            self.send_error(503)
                            return
                self.send_response(200)
                self.send_header('Content-Type','application/json')
                self.end_headers()
                self.wfile.write(response)
            except Exception:
                self.send_error(502)
    return Handler


class ToolProxy(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def do_GET(self): self.forward()
    def do_POST(self): self.forward()
    def forward(self):
        peer=self.connection.getpeercert(binary_form=True)
        if hashlib.sha256(peer).hexdigest()!=CONFIG['gateway_fingerprint']:
            self.send_error(403)
            return
        if self.headers.get('authorization')!='Bearer '+CONFIG['tool_client']['token']:
            self.send_error(401)
            return
        if self.command=='GET' and read_state().get('hold_status'):
            self.send_response(503)
            self.send_header('Content-Type','application/json')
            self.end_headers()
            self.wfile.write(canonical({'error':{'code':'CHAIN_UNAVAILABLE'}}))
            return
        body=None
        if self.command=='POST':
            body=parse_json(self.rfile.read(min(int(self.headers.get('content-length','0')),65536)))
            with LOCK:
                path=ROOT/'requests.json'
                saved=json.loads(path.read_text()) if path.exists() else {}
                saved[body['intent']['action_id']]=body
                path.write_bytes(canonical(saved))
            event('tool_execute_http',action_id=body['intent']['action_id'])
        try:
            response=tool().request(self.command,self.path,body,self.headers.get('idempotency-key'))
            if body and read_state().get('corrupt_once'):
                response['receipt']['result_commit']=random_id()
                update(corrupt_once=False,hold_status=True)
                event('tool_receipt_corrupted',action_id=body['intent']['action_id'])
            payload=canonical(response)
            self.send_response(200)
        except ToolError as error:
            from chainguard_gateway.canonical import ERRORS
            payload=canonical({'error':{'code':error.code}})
            self.send_response(ERRORS[error.code])
        self.send_header('Content-Type','application/json')
        self.end_headers()
        try: self.wfile.write(payload)
        except OSError: pass


def proxy():
    for index in range(4):
        server=ThreadingHTTPServer(('0.0.0.0',18545+index),rpc_handler(index))
        threading.Thread(target=server.serve_forever,daemon=True).start()
    server=ThreadingHTTPServer(('0.0.0.0',8443),ToolProxy)
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(ROOT/'proxy.pem',ROOT/'proxy.key')
    context.load_verify_locations(ROOT/'ca.pem')
    context.verify_mode=ssl.CERT_REQUIRED
    server.socket=context.wrap_socket(server.socket,server_side=True)
    server.serve_forever()


@lru_cache(maxsize=8)
def gateway(subject):
    return TLSClient('https://phase6-gateway:8443',ROOT/'ca.pem',ROOT/'operator.pem',ROOT/'operator.key',CONFIG['tokens'][subject])


@lru_cache(maxsize=1)
def tool(): return client(ROOT,CONFIG['tool_client'])


def call(subject,path,body=None,key=None):
    return gateway(subject).request('GET' if body is None else 'POST',path,body,key)


def expect_error(code,work):
    try: work()
    except ToolError as error:
        assert error.code==code,(error.code,code)
    else: raise AssertionError('Unauthorized operation succeeded')


def wait_action(action_id,states,timeout=65):
    deadline=time.monotonic()+timeout
    last=None
    while time.monotonic()<deadline:
        last=call('requester','/v1/actions/'+action_id)
        validate('ActionRecord',last)
        if last['state'] in states: return last
        time.sleep(0.3)
    raise AssertionError('Action did not reach '+str(states)+': '+str(last))


def propose():
    addresses=CONFIG['signers']
    grant=call('requester','/v1/tasks',{'task_text':'Deliver one locally isolated ChainGuard R2 test message',
        'agent':addresses['agent'],'allowed_tools':['mail.send'],'resource_scopes':['ORG_A_INTERNAL_MAIL'],
        'allowed_document_ids':[],'allowed_recipients':['alice@inbox.chainguard.invalid'],'expires_at':str(int(time.time())+600),
        'max_risk':2,'allow_sandbox_delete':False,'max_actions':1},random_id())
    validate('TaskGrant',grant)
    params={'to':['alice@inbox.chainguard.invalid'],'subject':'ChainGuard phase 6 local delivery','body':'Synthetic local test message. No external mailbox.'}
    expect_error('UNAUTHORIZED_SCOPE',lambda:call('agent','/v1/agent/actions/propose',
        {'task_id':grant['task_id'],'tool_name':'mail.send','params':dict(params,to=['bob@inbox.chainguard.invalid'])},random_id()))
    expect_error('SCHEMA_INVALID',lambda:call('agent','/v1/agent/actions/propose',
        {'task_id':grant['task_id'],'tool_name':'mail.send','params':dict(params,to=['outside@example.com'])},random_id()))
    before=call('agent','/v1/agent/actions/propose',{'task_id':grant['task_id'],'tool_name':'mail.send','params':params},random_id())
    action_id=before['action_id']
    domain={'name':'ChainGuard ExecutionRegistry','version':'1','chainId':str(CONFIG['deployment']['chainId']),
            'verifyingContract':CONFIG['deployment']['contracts']['ExecutionRegistry']['address'].lower()}
    signatures={}
    for subject in ('biz','security','requester'):
        signatures[subject]='0x'+Account.sign_message(encode_typed_data(full_message=typed_intent(before['intent'],domain)),CONFIG['signing_keys'][subject]).signature.hex()
    for subject in ('biz','security'):
        approved=call(subject,'/v1/actions/'+action_id+'/approve',{'signature':signatures[subject]})
        assert approved['state']=='AWAITING_APPROVAL'
    request={'requester_signature':signatures['requester']}
    expect_error('FORBIDDEN',lambda:call('agent','/v1/actions/'+action_id+'/reserve',request,random_id()))
    reserved=call('executor','/v1/actions/'+action_id+'/reserve',request,random_id())
    assert reserved['state']=='RESERVING'
    return action_id,grant,params,request


def save_case(name,value):
    path=ROOT/'cases.json'
    saved=json.loads(path.read_text()) if path.exists() else {}
    saved[name]=value
    path.write_bytes(canonical(saved))


def suite_normal():
    deadline=time.monotonic()+40
    while True:
        try:
            gateway('requester').request('GET','/health/ready')
            break
        except ToolError:
            if time.monotonic()>deadline: raise
            time.sleep(0.5)
    action_id,grant,params,request=propose()
    final=wait_action(action_id,{'FINALIZED_OK'})
    assert final['receipt']['outcome']==0 and final['anchor_status']=='CONFIRMED'
    repeat=call('executor','/v1/actions/'+action_id+'/reserve',request,random_id())
    assert repeat==final
    approval=json.loads((ROOT/'requests.json').read_text())[action_id]['intent']
    sig='0x'+Account.sign_message(encode_typed_data(full_message=typed_intent(approval,{
        'name':'ChainGuard ExecutionRegistry','version':'1','chainId':str(CONFIG['deployment']['chainId']),
        'verifyingContract':CONFIG['deployment']['contracts']['ExecutionRegistry']['address'].lower()})),CONFIG['signing_keys']['biz']).signature.hex()
    assert call('biz','/v1/actions/'+action_id+'/approve',{'signature':sig})==final
    original=json.loads((ROOT/'requests.json').read_text())[action_id]
    repeat=tool().request('POST','/v1/tools/execute',original,random_id())
    assert repeat['receipt']==final['receipt']
    altered={**original,'params':dict(params,body='tampered message')}
    expect_error('PARAMS_MISMATCH',lambda:tool().request('POST','/v1/tools/execute',altered,random_id()))
    fake=json.loads(json.dumps(original))
    fake['intent']['action_id']=random_id()
    expect_error('RESERVATION_UNCONFIRMED',lambda:tool().request('POST','/v1/tools/execute',fake,random_id()))
    wrong=TLSClient('https://phase6-tool:8443',ROOT/'ca.pem',ROOT/'operator.pem',ROOT/'operator.key',CONFIG['tool_client']['token'])
    expect_error('FORBIDDEN',lambda:wrong.request('GET','/v1/tools/actions/'+action_id))
    missing=TLSClient('https://phase6-tool:8443',ROOT/'ca.pem',ROOT/'gateway-client.pem',ROOT/'gateway-client.key','invalid-token')
    expect_error('AUTH_REQUIRED',lambda:missing.request('GET','/v1/tools/actions/'+action_id))
    save_case('normal',{'action_id':action_id,'record':final,'checks':['real_mail','task_scope_denied','external_domain_denied','reserve_idempotent','approval_idempotent_after_final','tool_idempotent','params_mismatch','no_reservation','wrong_mtls_peer','wrong_bearer','agent_cannot_reserve']})
    print(json.dumps({'status':'PASS','case':'normal','action_id':action_id}))


def suite_unknown():
    update(corrupt_once=True)
    action_id,_,_,_=propose()
    unknown=wait_action(action_id,{'UNKNOWN'})
    assert unknown['error']['code']=='RECEIPT_INVALID'
    save_case('unknown',{'action_id':action_id,'unknown_record':unknown})
    print(json.dumps({'status':'PASS','case':'unknown-observed','action_id':action_id}))


def suite_recover_unknown():
    case=json.loads((ROOT/'cases.json').read_text())['unknown']
    action_id=case['action_id']
    original=tool().request('GET','/v1/tools/actions/'+action_id)
    damaged=json.loads(json.dumps(original['receipt']))
    damaged['result_commit']=random_id()
    expect_error('RECEIPT_INVALID',lambda:call('reconciler','/v1/actions/'+action_id+'/reconcile',
        {'receipt':damaged,'tool_signature':original['tool_signature']},random_id()))
    call('reconciler','/v1/actions/'+action_id+'/reconcile',
        {'receipt':original['receipt'],'tool_signature':original['tool_signature']},random_id())
    update(hold_status=False)
    final=wait_action(action_id,{'FINALIZED_OK'})
    assert final['receipt']==original['receipt']
    save_case('unknown',dict(case,recovered_record=final,checks=['corrupt_receipt_rejected','unknown_durable_restart','chain_unknown_reconcile','original_receipt_only','no_second_dispatch']))
    print(json.dumps({'status':'PASS','case':'unknown-recovered','action_id':action_id}))


def suite_pending():
    update(audit_drop_once=True)
    action_id,_,_,_=propose()
    deadline=time.monotonic()+65
    while not read_state().get('gateway_rpc_down'):
        if time.monotonic()>deadline: raise AssertionError('No real audit broadcast intercepted')
        time.sleep(0.2)
    pending=wait_action(action_id,{'EXECUTION_RECORDED'})
    save_case('pending',{'action_id':action_id,'pending_record':pending})
    print(json.dumps({'status':'PASS','case':'pending-observed','action_id':action_id}))


def suite_recover_pending():
    case=json.loads((ROOT/'cases.json').read_text())['pending']
    update(gateway_rpc_down=False)
    final=wait_action(case['action_id'],{'FINALIZED_OK'})
    assert final['receipt']==case['pending_record']['receipt']
    save_case('pending',dict(case,recovered_record=final,checks=['audit_send_response_lost','chain_outage_pending','restart_preserves_receipt','same_tx_hash_recovered','no_second_dispatch']))
    print(json.dumps({'status':'PASS','case':'pending-recovered','action_id':case['action_id']}))


def suite_prebroadcast():
    update(audit_reject_once=True)
    action_id,_,_,_=propose()
    deadline=time.monotonic()+65
    while not read_state().get('gateway_rpc_down'):
        if time.monotonic()>deadline: raise AssertionError('No pre-broadcast outage intercepted')
        time.sleep(0.2)
    pending=wait_action(action_id,{'EXECUTION_RECORDED'})
    rejected=[json.loads(line) for line in (ROOT/'fault-events.jsonl').read_text().splitlines() if 'audit_not_delivered_to_node' in line][-1]
    result=json.loads(rpc_forward(0,canonical({'jsonrpc':'2.0','id':1,'method':'eth_getTransactionByHash','params':[rejected['tx_hash']]})))
    assert result['result'] is None
    save_case('prebroadcast',{'action_id':action_id,'pending_record':pending,'original_tx_hash':rejected['tx_hash'],'absent_on_node_before_recovery':True})
    print(json.dumps({'status':'PASS','case':'prebroadcast-pending','action_id':action_id}))


def suite_recover_prebroadcast():
    case=json.loads((ROOT/'cases.json').read_text())['prebroadcast']
    update(gateway_rpc_down=False)
    final=wait_action(case['action_id'],{'FINALIZED_OK'})
    assert final['receipt']==case['pending_record']['receipt']
    assert final['finalization_evidence']['tx_hash']==case['original_tx_hash']
    save_case('prebroadcast',dict(case,recovered_record=final,checks=['tx_absent_on_real_node','durable_signed_outbox_restart','identical_tx_resubmitted','original_receipt_only','no_second_dispatch']))
    print(json.dumps({'status':'PASS','case':'prebroadcast-recovered','action_id':case['action_id']}))


def suite_tool_outage():
    update(tool_rpc_down=True)
    action_id,_,_,_=propose()
    unknown=wait_action(action_id,{'UNKNOWN'})
    assert unknown['error']['code']=='CHAIN_UNAVAILABLE'
    update(tool_rpc_down=False)
    time.sleep(1)
    assert call('requester','/v1/actions/'+action_id)['state']=='UNKNOWN'
    expect_error('NOT_FOUND',lambda:tool().request('GET','/v1/tools/actions/'+action_id))
    original=json.loads((ROOT/'requests.json').read_text())[action_id]
    deadline=time.monotonic()+25
    while True:
        try: tool().request('POST','/v1/tools/execute',original,random_id())
        except ToolError as error:
            if error.code=='FORBIDDEN': break
            if error.code=='CHAIN_UNAVAILABLE' and time.monotonic()<deadline:
                event('tool_chain_recovery_wait',action_id=action_id)
                time.sleep(0.5)
                continue
            raise
        else: raise AssertionError('Uncertain dispatch was executed again')
    save_case('tool-outage',{'action_id':action_id,'record':unknown,'checks':['independent_tool_chain_unavailable_denied','no_mail','no_blind_redispatch']})
    print(json.dumps({'status':'PASS','case':'tool-chain-outage','action_id':action_id}))


def suite_post_restart():
    case=json.loads((ROOT/'cases.json').read_text())['normal']
    request=json.loads((ROOT/'requests.json').read_text())[case['action_id']]
    response=tool().request('POST','/v1/tools/execute',request,random_id())
    assert response['receipt']==case['record']['receipt']
    original=tool().request('GET','/v1/tools/actions/'+case['action_id'])
    assert original['receipt']==response['receipt'] and original['tool_signature']==response['tool_signature']
    print(json.dumps({'status':'PASS','case':'persistent-tool-idempotency'}))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('command',choices=['proxy','normal','unknown','recover-unknown','pending','recover-pending','prebroadcast','recover-prebroadcast','tool-outage','post-restart','export'])
    command=parser.parse_args().command
    if command=='proxy': proxy()
    elif command=='export':
        cases=json.loads((ROOT/'cases.json').read_text())
        events=[json.loads(line) for line in (ROOT/'fault-events.jsonl').read_text().splitlines()]
        print(json.dumps({'cases':cases,'events':events}))
    else:
        globals()['suite_'+command.replace('-','_')]()
