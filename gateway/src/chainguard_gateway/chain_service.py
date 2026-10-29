"""R2 orchestration: durable reservation, single dispatch and receipt-only recovery."""
import hashlib
import threading
import time

from eth_account import Account
from eth_abi import decode

from .canonical import canonical, validate
from .central_service import CentralService
from .chain_crypto import digest, recover_receipt
from .crypto import random_id, label, commit, recover_intent, PROTOCOL
from .policy import evaluate, require_actor, check_policy_freeze
from .mail_window import action_expiry
from chainguard_sandbox.protocol import ToolError

FINAL={0:'FINALIZED_OK',1:'FINALIZED_ERROR',2:'FINALIZED_REJECTED'}


class ChainService(CentralService):
    def __init__(self,store,chain,tool_client,relay_key,tool_signer,*,executor_subject='executor'):
        self.store,self.chain,self.tool_client=store,chain,tool_client
        self.relayer=Account.from_key(relay_key)
        self.tool_signer=tool_signer.lower()
        self.executor_subject=executor_subject
        self.stop=threading.Event()
        from .transaction_metrics import TransactionMetrics
        self.performance=TransactionMetrics(store)
        # Dispatch is distinct from confirmed tool execution. Never redispatch after restart.
        with store.transaction() as db:
            for row in db.execute("SELECT * FROM actions WHERE state IN ('RESERVED','EXECUTING')").fetchall():
                data=store.unseal('action/'+row['action_id'],row['data'])
                if row['state']=='EXECUTING' or data.get('dispatch_started'):
                    store.save(db,row['action_id'],'UNKNOWN',data)

    def trace(self,db,subject,event,trace_id,**values):
        self.store.event(db,values.get('action_id'),event,{'trace_id':trace_id,'subject_hash':hashlib.sha256((subject or '').encode()).hexdigest(),
            'error_code':values.get('code'),'observed_at':str(int(time.time()))})

    def _visible(self,db,subject,row):
        actor=self.store.actor(db,subject=subject)
        if not actor or not actor['active']: raise ToolError('FORBIDDEN')
        _,grant=self.store.task(db,row['task_id'])
        owns=actor['address'] in (grant['requester'],grant['agent'])
        review=bool(set(actor['roles']) & {'BUSINESS_APPROVER','SECURITY_APPROVER','AUDITOR','RECONCILER'})
        if not owns and subject!=self.executor_subject and not (review and 'ORG_A_INTERNAL_MAIL' in actor['resource_scopes']):
            raise ToolError('NOT_FOUND')
        return actor,owns

    def _view(self,db,subject,row,data):
        self._visible(db,subject,row)
        value={'action_id':row['action_id'],'task_id':row['task_id'],'risk':2,'state':row['state'],
            'chain_state':data.get('chain_state','NONE'),'anchor_status':'CONFIRMED' if row['state'] in FINAL.values() else
                ('PENDING' if row['state'] not in {'AWAITING_APPROVAL','DENIED'} else 'NOT_APPLICABLE'),
            'intent':data['intent'],'receipt':data.get('receipt'),'reservation_evidence':data.get('reservation_evidence'),
            'finalization_evidence':data.get('finalization_evidence'),'error':data.get('error')}
        return validate('ActionRecord',value)

    def create_task(self,subject,body,key,trace_id):
        validate('CreateTaskRequest',body)
        if body['allowed_tools']!=['mail.send'] or body['resource_scopes']!=['ORG_A_INTERNAL_MAIL'] or body['max_risk']!=2 or body['allow_sandbox_delete'] or body['allowed_document_ids']:
            raise ToolError('POLICY_DENY')
        return super().create_task(subject,body,key,trace_id)

    def propose(self,subject,body,key,trace_id):
        validate('ProposeRequest',body)
        if body['tool_name']!='mail.send': raise ToolError('POLICY_DENY')
        snapshot=self.chain.healthy()
        rule=self.chain.policy.call('getEffectiveRule',[label('policy','POLICY_R2_MAIL')],hex(int(snapshot['number'])))
        if not rule['enabled'] or self.chain.policy.call('paused',block=hex(int(snapshot['number']))): raise ToolError('POLICY_REVOKED')
        with self.store.transaction() as db:
            agent=self.store.actor(db,subject=subject)
            require_actor(agent,'AGENT')
            task_row,grant=self.store.task(db,body['task_id'])
            if grant['agent']!=agent['address']: raise ToolError('NOT_FOUND')
            old,mac=self._idempotency(db,subject,'propose',key,body)
            if old:
                row,data=self.store.action(db,old)
                return self._view(db,subject,row,data)
            requester=self.store.actor(db,address=grant['requester'])
            evaluate(requester,agent,dict(grant,revoked=bool(task_row['revoked'])),'mail.send',body['params'],None,
                     now=int(time.time()),used_actions=task_row['used_actions'],epoch=rule['policyEpoch'])
            issued=int(time.time())
            action_id,salt=random_id(),random_id()
            nonce_row=db.execute('SELECT next_nonce FROM nonces WHERE requester=?',(grant['requester'],)).fetchone()
            nonce=int(nonce_row[0]) if nonce_row else int(random_id()[2:18],16)
            if nonce >= (1<<64)-1: raise ToolError('NONCE_REUSED')
            db.execute('INSERT INTO nonces VALUES (?,?) ON CONFLICT(requester) DO UPDATE SET next_nonce=excluded.next_nonce',(grant['requester'],str(nonce+1)))
            intent={'schema_version':1,'action_id':action_id,'task_id':grant['task_id'],'requester':grant['requester'],'agent':grant['agent'],
                'tool_id':label('tool','mail.send'),'resource_scope':label('scope','ORG_A_INTERNAL_MAIL'),'params_commit':commit('params',salt,body['params']),
                'policy_id':label('policy','POLICY_R2_MAIL'),'policy_epoch':str(rule['policyEpoch']),'nonce':str(nonce),
                'issued_at':str(issued),'expires_at':str(action_expiry(issued,grant['expires_at'],rule['maxLifetime'],self.chain.config)),'risk':2}
            validate('ActionIntent',intent)
            data={'intent':intent,'params':body['params'],'salt':salt,'scope':'ORG_A_INTERNAL_MAIL','approvals':{},'requester_signature':None,'charged':False}
            db.execute('INSERT INTO actions(action_id,task_id,tool_name,state,data) VALUES (?,?,?,?,?)',
                (action_id,grant['task_id'],'mail.send','AWAITING_APPROVAL',self.store.seal('action/'+action_id,data)))
            self._save_idempotency(db,subject,'propose',key,mac,action_id)
            self.store.event(db,action_id,'PROPOSED',{'params_commit':intent['params_commit']})
            row,data=self.store.action(db,action_id)
            return self._view(db,subject,row,data)

    def _grant_check(self,db,row,data,*,accounted=False):
        task_row,grant=self.store.task(db,row['task_id'])
        evaluate(self.store.actor(db,address=grant['requester']),self.store.actor(db,address=grant['agent']),
            dict(grant,revoked=bool(task_row['revoked'])),'mail.send',data['params'],None,now=int(time.time()),
            used_actions=max(0,task_row['used_actions']-(1 if accounted else 0)),epoch=int(data['intent']['policy_epoch']))
        return task_row,grant

    def approve(self,subject,action_id,body,trace_id):
        validate('ApproveRequest',body)
        with self.store.transaction() as db:
            row,data=self.store.action(db,action_id)
            actor,_=self._visible(db,subject,row)
            signer=recover_intent(data['intent'],self.chain.domain,body['signature'])
            if signer!=actor['address']: raise ToolError('APPROVAL_INVALID')
            previous=data['approvals'].get(signer)
            if previous and previous!=body['signature']: raise ToolError('IDEMPOTENCY_CONFLICT')
            if previous: return self._view(db,subject,row,data)
            if row['state']!='AWAITING_APPROVAL': raise ToolError('STATE_CONFLICT')
            self._grant_check(db,row,data)
            snapshot=self.chain.healthy()
            data['approvals'][signer]=body['signature']
            self.chain.validate_authorization(data['intent'],None,list(data['approvals'].values()),snapshot,complete=False)
            self.store.save(db,action_id,row['state'],data)
            return self._view(db,subject,row,data)

    def reserve(self,subject,action_id,body,key,trace_id):
        validate('ReserveRequest',body)
        if subject!=self.executor_subject: raise ToolError('FORBIDDEN')
        with self.store.transaction() as db:
            row,data=self.store.action(db,action_id)
            self._visible(db,subject,row)
            _,mac=self._idempotency(db,subject,'reserve',key,{'action_id':action_id,**body})
            if data['requester_signature'] and data['requester_signature']!=body['requester_signature']: raise ToolError('IDEMPOTENCY_CONFLICT')
            if row['state']=='AWAITING_APPROVAL':
                self._grant_check(db,row,data)
                snapshot=self.chain.healthy()
                self.chain.validate_authorization(data['intent'],body['requester_signature'],list(data['approvals'].values()),snapshot)
                if self.chain.execution.call('usedNonce',[data['intent']['requester'],data['intent']['nonce']]): raise ToolError('NONCE_REUSED')
                data['requester_signature']=body['requester_signature']
                data['charged']=True
                db.execute('UPDATE tasks SET used_actions=used_actions+1 WHERE task_id=?',(row['task_id'],))
                self.store.save(db,action_id,'RESERVING',data)
            self._save_idempotency(db,subject,'reserve',key,mac,action_id)
            row,data=self.store.action(db,action_id)
            return self._view(db,subject,row,data)

    def authorization(self,action_id):
        with self.store.connect() as db:
            row,data=self.store.action(db,action_id)
            task_row,grant=self.store.task(db,row['task_id'])
            return {'grant':grant,'revoked':bool(task_row['revoked']),'charged':data['charged'],'dispatch_state':row['state'],
                    'dispatch_started':bool(data.get('dispatch_started')),
                    'requester':self.store.actor(db,address=grant['requester']),'agent':self.store.actor(db,address=grant['agent'])}

    def _transaction(self,action_id,kind,contract,method,args):
        # Nonce allocation and signed bytes are persisted before any broadcast.
        with self.store.transaction() as db:
            row=db.execute('SELECT * FROM chain_transactions WHERE action_id=? AND kind=?',(action_id,kind)).fetchone()
            if row is None:
                nonce=int(self.chain.rpc.call('eth_getTransactionCount',[self.relayer.address.lower(),'pending']),16)
                previous=db.execute('SELECT max(nonce) FROM chain_transactions').fetchone()[0]
                nonce=max(nonce,previous+1 if previous is not None else 0)
                signed=self.relayer.sign_transaction({'chainId':self.chain.config['chainId'],'nonce':nonce,'gasPrice':0,'gas':8000000,
                    'to':bytes.fromhex(contract.address[2:]),'data':contract.data(method,args),'value':0})
                tx_hash='0x'+signed.hash.hex().removeprefix('0x')
                raw='0x'+signed.raw_transaction.hex().removeprefix('0x')
                db.execute('INSERT INTO chain_transactions VALUES (?,?,?,?,?,?)',(action_id,kind,nonce,tx_hash,self.store.seal('tx/'+tx_hash,raw),'PREPARED'))
                row=db.execute('SELECT * FROM chain_transactions WHERE action_id=? AND kind=?',(action_id,kind)).fetchone()
        receipt=self.chain.rpc.call('eth_getTransactionReceipt',[row['tx_hash']])
        if receipt: return row['tx_hash'],receipt
        pending=self.chain.rpc.call('eth_getTransactionByHash',[row['tx_hash']])
        if pending is None:
            # A pre-broadcast outage must not strand the outbox. Only identical signed
            # bytes may be resubmitted; this cannot create another nonce/action/receipt.
            self.chain.healthy()
            consumed=int(self.chain.rpc.call('eth_getTransactionCount',[self.relayer.address.lower(),'latest']),16)
            if consumed>row['nonce']: raise ToolError('STATE_CONFLICT')
            with self.store.transaction() as db:
                db.execute("UPDATE chain_transactions SET state='SENDING' WHERE tx_hash=?",(row['tx_hash'],))
            self.performance.submitted(row['tx_hash'],action_id,kind)
            returned=self.chain.rpc.call('eth_sendRawTransaction',[self.store.unseal('tx/'+row['tx_hash'],row['raw'])])
            if returned!=row['tx_hash']: raise ToolError('CHAIN_UNAVAILABLE')
            receipt=self.chain.rpc.call('eth_getTransactionReceipt',[row['tx_hash']])
        return row['tx_hash'],receipt

    def _receipt(self,action_id,response):
        validate('ToolExecutionResponse',response)
        with self.store.transaction() as db:
            row,data=self.store.action(db,action_id)
            receipt=response['receipt']
            if response['state']!='EXECUTION_RECORDED' or response['action_id']!=action_id or not receipt: raise ToolError('RECEIPT_INVALID')
            if (receipt['action_id']!=action_id or receipt['params_commit']!=data['intent']['params_commit'] or receipt['outcome'] not in FINAL or
                not int(data['intent']['issued_at'])<=int(receipt['executed_at'])<=int(time.time()) or
                recover_receipt(receipt,self.chain.receipt_domain,response['tool_signature'])!=self.tool_signer):
                raise ToolError('RECEIPT_INVALID')
            if data.get('receipt') and (data['receipt']!=receipt or data['tool_signature']!=response['tool_signature']): raise ToolError('RECEIPT_INVALID')
            if row['state'] in FINAL.values(): return
            if row['state']=='RESERVED':
                if not data.get('dispatch_started'): raise ToolError('STATE_CONFLICT')
                # The signed original result now proves that the tool passed its
                # own guards. Record the intermediate edge within this transaction.
                self.store.save(db,action_id,'EXECUTING',data)
                self.store.event(db,action_id,'EXECUTING_CONFIRMED',{'receipt_digest':digest('ExecutionReceipt',receipt,self.chain.receipt_domain)})
            data['receipt'],data['tool_signature']=receipt,response['tool_signature']
            data.pop('error',None)
            self.store.save(db,action_id,'EXECUTION_RECORDED',data)

    def reconcile(self,subject,action_id,body,key,trace_id):
        validate('ReconcileRequest',body)
        actor=self.current_actor(subject)
        require_actor(actor,'RECONCILER')
        snapshot=self.chain.healthy()
        if not self.chain.policy.call('hasRole',[label('role','RECONCILER'),actor['address']],hex(int(snapshot['number']))): raise ToolError('FORBIDDEN')
        with self.store.transaction() as db:
            row,data=self.store.action(db,action_id)
            self._visible(db,subject,row)
            _,mac=self._idempotency(db,subject,'reconcile',key,{'action_id':action_id,**body})
            if row['state'] not in {'UNKNOWN','EXECUTION_RECORDED',*FINAL.values()}: raise ToolError('STATE_CONFLICT')
            self._save_idempotency(db,subject,'reconcile',key,mac,action_id)
        self._receipt(action_id,dict(body,action_id=action_id,state='EXECUTION_RECORDED'))
        return self.get_action(subject,action_id)

    def advance(self,action_id):
        with self.store.connect() as db: row,data=self.store.action(db,action_id)
        state=row['state']
        if state=='RESERVING':
            value={target:data['intent'][source] for source,target in PROTOCOL['json_to_typed']['ActionIntent'].items()}
            tx_hash,receipt=self._transaction(action_id,'reserve',self.chain.execution,'reserve',
                [value,data['requester_signature'],[{'signature':s} for s in data['approvals'].values()]])
            if not receipt: return
            snapshot=self.chain.healthy()
            reservation=self.chain.execution.call('getReservation',[action_id],hex(int(snapshot['number'])))
            if receipt['status']!='0x1':
                if reservation['status']==0:
                    with self.store.transaction() as db: self.store.save(db,action_id,'DENIED',data)
                raise ToolError('RESERVATION_UNCONFIRMED')
            evidence,_,_=self.chain.transaction_evidence(tx_hash,self.chain.execution.address,snapshot,
                'ActionReserved(bytes32,bytes32,bytes32,bytes32,uint64)',action_id)
            if reservation['intentHash']!=digest('ActionIntent',data['intent'],self.chain.domain) or reservation['status']!=1:
                raise ToolError('RESERVATION_UNCONFIRMED')
            data['reservation_evidence'],data['chain_state']=evidence,'RESERVED'
            with self.store.transaction() as db:
                self.store.save(db,action_id,'RESERVED',data)
                db.execute("UPDATE chain_transactions SET state='CONFIRMED' WHERE tx_hash=?",(tx_hash,))
                self.performance.confirmed(db,tx_hash)
            return
        if state=='RESERVED':
            # A gateway-side chain outage leaves an undispatched reservation waiting.
            snapshot=self.chain.healthy()
            with self.store.transaction() as db:
                row,data=self.store.action(db,action_id)
                if row['state']!='RESERVED': return
                if data.get('dispatch_started'):
                    self.store.save(db,action_id,'UNKNOWN',data)
                    return
                self._grant_check(db,row,data,accounted=True)
                self.chain.validate_authorization(data['intent'],data['requester_signature'],list(data['approvals'].values()),snapshot)
                data['dispatch_started']=True
                self.store.save(db,action_id,'RESERVED',data)
                self.store.event(db,action_id,'DISPATCH_STARTED',{'observed_at':str(int(time.time()))})
            response=None
            try:
                response=self.tool_client.request('POST','/v1/tools/execute',{'intent':data['intent'],'params_salt':data['salt'],
                    'params':data['params'],'reservation_evidence':data['reservation_evidence']},random_id())
                self._receipt(action_id,response)
            except ToolError as error:
                with self.store.transaction() as db:
                    row,latest=self.store.action(db,action_id)
                    latest['error']={'code':error.code,'message':error.code,'retryable':False,'trace_id':random_id()}
                    if response: latest['anomalous_receipt']=response
                    self.store.save(db,action_id,'UNKNOWN',latest)
            return
        if state=='UNKNOWN':
            original=self.tool_client.request('GET','/v1/tools/actions/'+action_id)
            validate('ToolStatusResponse',original)
            if original['action_id']!=action_id or original['status'] not in {'EXECUTED_OK','EXECUTED_ERROR','REJECTED'}: return
            self._receipt(action_id,{k:original[k] for k in ('action_id','receipt','tool_signature')}|{'state':'EXECUTION_RECORDED'})
            return
        if state=='EXECUTION_RECORDED':
            snapshot=self.chain.healthy()
            block=hex(int(snapshot['number']))
            signer=recover_receipt(data['receipt'],self.chain.receipt_domain,data['tool_signature'])
            if signer!=self.tool_signer or not self.chain.policy.call('isToolSigner',[data['intent']['tool_id'],signer],block): raise ToolError('RECEIPT_INVALID')
            if int(data['receipt']['executed_at'])>int(snapshot['timestamp']): return
            reservation=self.chain.execution.call('getReservation',[action_id],block)
            method='reconcile' if reservation['status']==2 else 'finalize'
            value={target:data['receipt'][source] for source,target in PROTOCOL['json_to_typed']['ExecutionReceipt'].items()}
            tx_hash,receipt=self._transaction(action_id,'audit',self.chain.audit,method,[value,data['tool_signature']])
            if not receipt: return
            if receipt['status']!='0x1': raise ToolError('RECEIPT_INVALID')
            snapshot=self.chain.healthy()
            evidence,_,event=self.chain.transaction_evidence(tx_hash,self.chain.audit.address,snapshot,
                'ActionFinalized(bytes32,bytes32,address,uint8)',action_id)
            block=hex(int(snapshot['number']))
            current=self.chain.execution.call('getReservation',[action_id],block)
            if (current['status']!=data['receipt']['outcome']+3 or self.chain.audit.call('receiptHash',[action_id],block)!=digest('ExecutionReceipt',data['receipt'],self.chain.receipt_domain) or
                self.chain.audit.call('receiptSigner',[action_id],block)!=signer or event['topics'][2][-40:]!=signer[2:] or
                decode(['bytes32','uint8'],bytes.fromhex(event['data'][2:]))!=(bytes.fromhex(data['receipt']['result_commit'][2:]),data['receipt']['outcome'])):
                raise ToolError('RECEIPT_INVALID')
            data['finalization_evidence'],data['chain_state']=evidence,FINAL[data['receipt']['outcome']]
            data.pop('error',None)
            with self.store.transaction() as db:
                self.store.save(db,action_id,data['chain_state'],data)
                db.execute("UPDATE chain_transactions SET state='CONFIRMED' WHERE tx_hash=?",(tx_hash,))
                self.performance.confirmed(db,tx_hash)

    def worker(self):
        while not self.stop.wait(0.3):
            with self.store.connect() as db:
                actions=[r[0] for r in db.execute("SELECT action_id FROM actions WHERE state IN ('RESERVING','RESERVED','UNKNOWN','EXECUTION_RECORDED')")]
            for action_id in actions:
                try: self.advance(action_id)
                except ToolError as error:
                    with self.store.transaction() as db:
                        self.store.event(db,action_id,'WAIT',{'code':error.code,'observed_at':str(int(time.time()))})
                except Exception:
                    # No retry of tool dispatch; unexpected failures remain observable and closed.
                    with self.store.transaction() as db:
                        current,data=self.store.action(db,action_id)
                        if current['state']=='EXECUTING' or current['state']=='RESERVED' and data.get('dispatch_started'):
                            self.store.save(db,action_id,'UNKNOWN',data)
                        self.store.event(db,action_id,'INTERNAL_WAIT',{'code':'EXECUTION_UNKNOWN'})
