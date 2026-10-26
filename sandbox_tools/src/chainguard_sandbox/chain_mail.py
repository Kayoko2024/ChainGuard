"""R2 only: independent on-chain checks before an atomic local mailbox delivery."""
import json
import hmac
import os
import time

from Crypto.Cipher import AES
from eth_account import Account

from .protocol import ToolError, request_hash
from .tools import LocalTestTools
from chainguard_gateway.canonical import canonical, validate
from chainguard_gateway.chain_crypto import digest, sign_receipt
from chainguard_gateway.crypto import commit, random_id, label
from chainguard_gateway.policy import evaluate, check_policy_freeze

DDL="""
CREATE TABLE IF NOT EXISTS chain_mail(action_id TEXT PRIMARY KEY,params_commit TEXT NOT NULL,
 intent_digest TEXT NOT NULL,data BLOB NOT NULL);
CREATE TABLE IF NOT EXISTS chain_mail_uses(task_id TEXT NOT NULL,action_id TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS chain_mail_requests(key TEXT PRIMARY KEY,request_mac TEXT NOT NULL,action_id TEXT NOT NULL);
"""


class ChainMailTool:
    def __init__(self,store,chain,authority,signing_key,encryption_key):
        self.store,self.chain,self.authority=store,chain,authority
        self.signing_key,self.encryption_key=signing_key,encryption_key
        self.signer=Account.from_key(signing_key).address.lower()
        self.primitive=LocalTestTools(store)
        with store.connect() as db: db.executescript(DDL)

    def seal(self,action_id,value):
        cipher=AES.new(self.encryption_key,AES.MODE_GCM)
        cipher.update(action_id.encode())
        ciphertext,tag=cipher.encrypt_and_digest(canonical(value))
        return cipher.nonce+tag+ciphertext

    def unseal(self,action_id,value):
        try:
            cipher=AES.new(self.encryption_key,AES.MODE_GCM,nonce=value[:16])
            cipher.update(action_id.encode())
            return json.loads(cipher.decrypt_and_verify(value[32:],value[16:32]))
        except ValueError: raise ToolError('EXECUTION_UNKNOWN') from None

    def status(self,action_id):
        validate('Bytes32',action_id)
        with self.store.connect() as db:
            row=db.execute('SELECT data FROM chain_mail WHERE action_id=?',(action_id,)).fetchone()
        if not row: raise ToolError('NOT_FOUND')
        data=self.unseal(action_id,row[0])
        return validate('ToolStatusResponse',{'action_id':action_id,'checked_at':str(int(time.time())),
            'status':'EXECUTED_OK','receipt':data['receipt'],'tool_signature':data['tool_signature']})

    def execute(self,body,key):
        validate('ExecuteRequest',body)
        validate('Bytes32',key)
        intent,params,salt=body['intent'],body['params'],body['params_salt']
        if intent['risk']!=2 or intent['tool_id']!=label('tool','mail.send'): raise ToolError('POLICY_DENY')
        if commit('params',salt,params)!=intent['params_commit']: raise ToolError('PARAMS_MISMATCH')
        action_id=intent['action_id']
        fingerprint=digest('ActionIntent',intent,self.chain.domain)
        # Same action must never gain a second claim, even with another HTTP idempotency key.
        with self.store.transaction() as db:
            mac=hmac.digest(self.encryption_key,canonical(body),'sha256').hex()
            previous=db.execute('SELECT request_mac FROM chain_mail_requests WHERE key=?',(key,)).fetchone()
            if previous and previous[0]!=mac: raise ToolError('IDEMPOTENCY_CONFLICT')
            old=db.execute('SELECT * FROM chain_mail WHERE action_id=?',(action_id,)).fetchone()
            if old:
                if old['params_commit']!=intent['params_commit'] or old['intent_digest']!=fingerprint: raise ToolError('PARAMS_MISMATCH')
                stored=self.unseal(action_id,old['data'])
                db.execute('INSERT OR IGNORE INTO chain_mail_requests VALUES (?,?,?)',(key,mac,action_id))
                return validate('ToolExecutionResponse',{'action_id':action_id,'state':'EXECUTION_RECORDED',
                    'receipt':stored['receipt'],'tool_signature':stored['tool_signature']})
            # A primitive/other authorization mode already using this actionId cannot be adopted.
            if db.execute('SELECT 1 FROM executions WHERE action_id=?',(action_id,)).fetchone(): raise ToolError('EXECUTION_UNKNOWN')
            check_policy_freeze()
            snapshot=self.chain.reservation(intent,body['reservation_evidence'])
            block=hex(int(snapshot['number']))
            if not self.chain.policy.call('isToolSigner',[intent['tool_id'],self.signer],block): raise ToolError('FORBIDDEN')
            auth=self.authority.request('GET','/internal/v1/authorization/'+action_id)
            grant=auth['grant']
            validate('TaskGrant',grant)
            if (grant['task_id']!=intent['task_id'] or grant['requester']!=intent['requester'] or grant['agent']!=intent['agent'] or
                auth['dispatch_state']!='RESERVED' or not auth.get('dispatch_started') or not auth['charged']): raise ToolError('FORBIDDEN')
            uses=db.execute('SELECT count(*) FROM chain_mail_uses WHERE task_id=?',(grant['task_id'],)).fetchone()[0]
            evaluate(auth['requester'],auth['agent'],dict(grant,revoked=auth['revoked']),'mail.send',params,None,
                     now=int(time.time()),used_actions=uses,epoch=int(intent['policy_epoch']))
            # Last local clock check directly before the atomic claim and side effect.
            if not int(intent['issued_at'])<=int(time.time())<min(int(intent['expires_at']),int(grant['expires_at'])):
                raise ToolError('RESERVATION_EXPIRED')
            started=str(int(time.time()))
            db.execute('INSERT INTO chain_mail_uses VALUES (?,?)',(grant['task_id'],action_id))
            db.execute('INSERT INTO executions VALUES (?,?,?,?,?,?,?,?,?)',(action_id,'chain-gateway','mail.send',
                request_hash(action_id,'chain-gateway','mail.send',params),'CLAIMED',started,None,None,None))
            result=self.primitive._send(db,action_id,params)
            completed=str(int(time.time()))
            result_salt,evidence_salt=random_id(),random_id()
            evidence={'action_id':action_id,'checked_block':snapshot,'started_at':started,
                      'message_ids':result['message_ids'],'mime_sha256':result['mime_sha256']}
            receipt={'schema_version':1,'action_id':action_id,'params_commit':intent['params_commit'],
                'result_commit':commit('result',result_salt,result),'evidence_index_commit':commit('evidence',evidence_salt,evidence),
                'executed_at':completed,'outcome':0}
            signature=sign_receipt(self.signing_key,receipt,self.chain.receipt_domain)
            stored={'receipt':receipt,'tool_signature':signature,'result':result,'result_salt':result_salt,
                    'evidence':evidence,'evidence_salt':evidence_salt}
            encrypted=self.seal(action_id,stored)
            db.execute('INSERT INTO chain_mail VALUES (?,?,?,?)',(action_id,intent['params_commit'],fingerprint,encrypted))
            db.execute('INSERT INTO chain_mail_requests VALUES (?,?,?)',(key,mac,action_id))
            # C result metadata is encrypted; mailbox contains only isolated synthetic test mail.
            db.execute("UPDATE executions SET state='COMPLETED',completed_at=?,result_json=NULL WHERE action_id=?",(completed,action_id))
            db.execute('INSERT INTO events(action_id,state,observed_at) VALUES (?,?,?)',(action_id,'COMPLETED',completed))
        return validate('ToolExecutionResponse',{'action_id':action_id,'state':'EXECUTION_RECORDED','receipt':receipt,'tool_signature':signature})
