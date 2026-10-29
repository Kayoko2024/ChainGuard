"""Durable control-plane jobs. An accepted request is never execution evidence."""
import hmac
import json
import threading
import time
from .canonical import canonical,validate
from chainguard_sandbox.protocol import ToolError


class OperationQueue:
    def __init__(self,operations):
        self.ops=operations;self.store=operations.store;self.stop=threading.Event()
        with self.store.db() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS web_operations(id TEXT PRIMARY KEY,role TEXT NOT NULL,
                state TEXT NOT NULL,data BLOB NOT NULL,received REAL NOT NULL,updated REAL NOT NULL)''')
            # A worker may have submitted a real transaction before being interrupted.
            for row in db.execute("SELECT * FROM web_operations WHERE state='RUNNING'").fetchall():
                value=self.store.open(row['id'],row['data'])
                # Renewal has no tool side effect. Its fixed request ID points to
                # durable nonce/signature material, so only this control can resume.
                safe_renew=value.get('kind')=='renew' and len(value.get('args',[]))==5 and value['args'][4] is not None
                db.execute('UPDATE web_operations SET state=? WHERE id=?',('QUEUED' if safe_renew else 'UNKNOWN',row['id']))

    def submit(self,role,kind,args,request_id=None):
        received=time.time();started=time.perf_counter();created=False
        value=dict(kind=kind,args=args)
        if request_id is not None:validate('Bytes32',request_id)
        id='op-'+hmac.digest(self.store.key,canonical(dict(role=role,request_id=request_id,**value)),'sha256').hex()
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            if not db.execute('SELECT 1 FROM web_operations WHERE id=?',(id,)).fetchone():
                if db.execute("SELECT count(*) FROM web_operations WHERE state IN ('QUEUED','RUNNING')").fetchone()[0]>=100:raise ToolError('QUEUE_FULL')
                db.execute('INSERT INTO web_operations VALUES (?,?,?,?,?,?)',(id,role,'QUEUED',self.store.seal(id,value),received,received))
                created=True
        elapsed=(time.perf_counter()-started)*1000
        if created:self.metric(id,'REQUEST_ACCEPTED',received_at_unix=received,local_storage_ms=elapsed,consensus_wait_ms=None)
        return self.get(id,role)

    def metric(self,id,event,**values):
        from .transaction_metrics import performance_logger
        performance_logger().info(json.dumps(dict(operation_id=id,event=event,**values)))
        previous=self.store.cached('performance/'+id,{'samples':[]})
        self.store.cache('performance/'+id,dict(samples=previous['samples']+[dict(event=event,**values)]))

    def get(self,id,role):
        with self.store.db() as db:row=db.execute('SELECT * FROM web_operations WHERE id=?',(id,)).fetchone()
        if not row or row['role']!=role:raise ToolError('NOT_FOUND')
        value=self.store.open(id,row['data'])
        result=value.get('result') or {}
        record=result.get('record') or {}
        tx=record.get('reservation_evidence') or {}
        aid=record.get('action_id')
        if not aid and value['kind']=='execute':
            try:
                job=self.store.get(value['args'][0]);task=job.get('grant',{}).get('task_id')
                aid=next((r['action_id'] for r in getattr(self.ops,'records',{}).values() if r['task_id']==task),None)
            except ToolError:pass
        transaction=next((t for t in self.store.cached('transactions',[]) if t['action_id']==aid and t['kind']=='reserve'),{})
        return dict(operation_id=id,status='PENDING' if row['state'] in {'QUEUED','RUNNING'} else row['state'],
            stage=row['state'],tx_hash=tx.get('tx_hash') or transaction.get('tx_hash'),received_at_unix=row['received'],updated_at_unix=row['updated'],
            result=value.get('result'),error=value.get('error'),performance=self.store.cached('performance/'+id,{}))

    def run_once(self):
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE');row=db.execute("SELECT * FROM web_operations WHERE state='QUEUED' ORDER BY received LIMIT 1").fetchone()
            if not row:return False
            db.execute("UPDATE web_operations SET state='RUNNING',updated=? WHERE id=?",(time.time(),row['id']))
        value=self.store.open(row['id'],row['data']);started=time.perf_counter();queue_ms=max(0,(time.time()-row['received'])*1000)
        state='SUCCEEDED'
        try:
            kind=value['kind'];names={'approve':'approve','execute':'execute','approve_tool':'approve_tool_call','execute_tool':'execute_tool_call','activate':'set_custom_active','renew':'renew','close':'close','flush':'session_flush'}
            target=self.ops.bridge if kind=='flush' else self.ops.conversation_service if kind in {'close','renew'} else self.ops
            value['result']=getattr(target,names[kind])(*value['args'])
        except Exception as error:
            state='FAILED';value['error']=error.code if isinstance(error,ToolError) else 'EXECUTION_UNKNOWN'
        finished=time.time();persisted=time.perf_counter()
        with self.store.db() as db:db.execute('UPDATE web_operations SET state=?,data=?,updated=? WHERE id=?',(state,self.store.seal(row['id'],value),finished,row['id']))
        self.metric(row['id'],'CONTROL_COMPLETED',received_at_unix=row['received'],queue_wait_ms=queue_ms,
            control_processing_ms=(time.perf_counter()-started)*1000,local_storage_ms=(time.perf_counter()-persisted)*1000,
            consensus_wait_ms=None,note='Approvals are off-chain; chain inclusion is measured separately from broadcast to verified receipt.')
        return True

    def worker(self):
        while not self.stop.is_set():
            try:worked=self.run_once()
            except Exception:worked=False
            if not worked:self.stop.wait(.1)
