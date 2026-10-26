"""Closed tool boundary: all high-risk calls propose to the real stage6 gateway."""
from chainguard_gateway.canonical import canonical,validate
from chainguard_sandbox.protocol import ToolError,params_for
import hashlib
import time

FINAL={'FINALIZED_OK','FINALIZED_ERROR','FINALIZED_REJECTED'}


class ToolExecutionProxy:
    def __init__(self,transport,journal,run_id,task_id,mode='fixed_trace',wait_seconds=0):
        validate('Bytes32',task_id)
        self.transport,self.journal,self.run_id,self.task_id,self.mode=transport,journal,run_id,task_id,mode
        if not 0<=wait_seconds<=90: raise ValueError('Invalid confirmation wait')
        self.wait_seconds=wait_seconds

    def execute(self,call):
        self.journal.event(run_id=self.run_id,task_id=self.task_id,call_id=call.id,tool_name=call.name,
            mode=self.mode,event='AGENT_ATTEMPT',agent_attempted_tool=True,
            arguments_sha256=hashlib.sha256(canonical(call.arguments)).hexdigest())
        known_action=None
        try:
            params_for(call.name,call.arguments)
            row,data=self.journal.claim(self.run_id,self.task_id,call)
            known_action=row['action_id']
            if data['result'] is not None: return data['result']
            if call.name=='doc.read':
                result=self.transport.request('POST','/agent/v1/reads',{'task_id':self.task_id,**call.arguments},row['idempotency_key'])
                if (result.get('trust')!='untrusted' or result.get('doc_id')!=call.arguments['doc_id'] or
                    hashlib.sha256(result['content'].encode()).hexdigest()!=result.get('sha256')): raise ToolError('EXECUTION_UNKNOWN')
                data['result']=result
                self.journal.save(self.run_id,call.id,None,data)
                self.journal.event(run_id=self.run_id,call_id=call.id,mode=self.mode,event='POLICY_RESULT',tool_name=call.name,
                    policy_verdict='READ_ALLOWED',tool_executed=True,observation_sha256=result['sha256'])
                return result
            # The Agent cannot approve/reserve or reach a tool executor. Even an
            # unsupported R3 deletion goes through the gateway and is denied there.
            if row['action_id']:
                record=self.transport.request('GET','/v1/actions/'+row['action_id'])
            else:
                record=self.transport.request('POST','/v1/agent/actions/propose',data['request'],row['idempotency_key'])
            validate('ActionRecord',record)
            known_action=record['action_id']
            self.journal.save(self.run_id,call.id,record['action_id'],dict(data,action_record=record))
            if record['state']=='AWAITING_APPROVAL':
                self.journal.event(run_id=self.run_id,call_id=call.id,mode=self.mode,event='POLICY_RESULT',tool_name=call.name,
                    action_id=record['action_id'],policy_verdict='REQUIRE_APPROVAL',tool_executed=False,gateway_state=record['state'])
            deadline=time.monotonic()+self.wait_seconds
            while record['state'] not in FINAL|{'DENIED','EXPIRED','UNKNOWN'} and time.monotonic()<deadline:
                time.sleep(0.25)
                record=self.transport.request('GET','/v1/actions/'+record['action_id'])
                validate('ActionRecord',record)
            data['action_record']=record
            if record['state'] in FINAL or record['state'] in {'DENIED','EXPIRED'}:
                data['result']={'status':record['state'],'action_id':record['action_id'],'record':record}
            self.journal.save(self.run_id,call.id,record['action_id'],data)
            self.journal.event(run_id=self.run_id,call_id=call.id,mode=self.mode,event='POLICY_RESULT',tool_name=call.name,
                action_id=record['action_id'],policy_verdict='REQUIRE_APPROVAL' if record['state']=='AWAITING_APPROVAL' else
                    'DENY' if record['state'] in {'DENIED','EXPIRED','FINALIZED_REJECTED'} else
                    'ALLOW' if record['state'] in {'RESERVING','RESERVED','EXECUTING','EXECUTION_RECORDED','FINALIZED_OK','FINALIZED_ERROR'} else 'UNKNOWN',
                tool_executed=True if record['state']=='FINALIZED_OK' else False if record['state'] in {'FINALIZED_REJECTED','AWAITING_APPROVAL','DENIED','EXPIRED'} else None,
                gateway_state=record['state'])
            return data['result'] or {'status':record['state'],'action_id':record['action_id'],'record':record}
        except ToolError as error:
            # Losing visibility of a submitted action is not proof that the
            # tool never executed. Preserve its ID and query only on recovery.
            denied=known_action is None and error.code not in {'CHAIN_UNAVAILABLE','EXECUTION_UNKNOWN'}
            result={'status':'DENIED' if denied else 'UNKNOWN','error_code':error.code}
            if 'data' in locals() and denied:
                data['result']=result
                self.journal.save(self.run_id,call.id,row['action_id'],data)
            self.journal.event(run_id=self.run_id,call_id=call.id,mode=self.mode,event='POLICY_RESULT',tool_name=call.name,
                policy_verdict='DENY' if denied else 'UNKNOWN',tool_executed=False if denied else None,error_code=error.code)
            return result
