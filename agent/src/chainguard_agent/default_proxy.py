"""Optional default-library reads around the original high-risk execution proxy."""
import hashlib
from chainguard_gateway.canonical import canonical
from chainguard_gateway.default_tools import READ_TOOLS, validate_arguments
from chainguard_sandbox.protocol import ToolError
from jsonschema import Draft202012Validator


class DefaultToolProxy:
    def __init__(self,base,allowed,*,custom=None):
        self.base,self.allowed=base,set(allowed)
        self.custom=custom or {}

    def execute(self,call):
        base=self.base
        if call.name not in self.allowed:
            result={'status':'DENIED','error_code':'UNAUTHORIZED_SCOPE'}
            base.journal.event(run_id=base.run_id,call_id=call.id,tool_name=call.name,mode=base.mode,
                event='POLICY_RESULT',agent_attempted_tool=True,policy_verdict='DENY',tool_executed=False)
            return result
        custom=self.custom.get(call.name)
        if not custom and (call.name=='doc.read' and not getattr(base.transport,'conversation',False) or call.name not in READ_TOOLS): return base.execute(call)
        base.journal.event(run_id=base.run_id,call_id=call.id,tool_name=call.name,mode=base.mode,
            event='AGENT_ATTEMPT',agent_attempted_tool=True,arguments_sha256=hashlib.sha256(canonical(call.arguments)).hexdigest())
        try:
            if custom:
                if not Draft202012Validator(custom['manifest']['input_schema']).is_valid(call.arguments): raise ToolError('SCHEMA_INVALID')
            else: validate_arguments(call.name,call.arguments)
            row,data=base.journal.claim(base.run_id,base.task_id,call)
            if data['result'] is not None: return data['result']
            request={'task_id':base.task_id,'tool_name':call.name,'arguments':call.arguments}
            if custom: request['revision']=custom['manifest']['revision']
            value=base.transport.request('POST','/agent/v1/custom-tools/query' if custom else '/agent/v1/library',request,row['idempotency_key'])
            if isinstance(value,dict) and value.get('status') in {'AWAITING_TOOL_APPROVAL','UNKNOWN'}:
                # A pending approval is a checkpoint, never a completed observation.
                data['pending']=value;base.journal.save(base.run_id,call.id,None,data)
                base.journal.event(run_id=base.run_id,call_id=call.id,tool_name=call.name,mode=base.mode,event='POLICY_RESULT',policy_verdict='REQUIRE_APPROVAL' if value['status']=='AWAITING_TOOL_APPROVAL' else 'UNKNOWN',tool_executed=False if value['status']=='AWAITING_TOOL_APPROVAL' else None)
                return value
            if custom and custom['manifest']['adapter'] in {'github.read','http.request'} and isinstance(value,dict) and value.get('status')=='READ_FAILED':
                error=value.get('error_code','GITHUB_UNAVAILABLE')
                denied=error in {'GITHUB_REPOSITORY_DENIED','HTTP_TARGET_DENIED','POLICY_REVOKED','UNAUTHORIZED_SCOPE'}
                result={'status':'DENIED' if denied else 'UNKNOWN','error_code':error,'read_execution_id':value.get('read_execution_id'),'repository_policy':value.get('repository_policy')}
                data['result']=result; base.journal.save(base.run_id,call.id,None,data)
                base.journal.event(run_id=base.run_id,call_id=call.id,tool_name=call.name,mode=base.mode,event='POLICY_RESULT',policy_verdict='DENY' if denied else 'UNKNOWN',tool_executed=False if denied else None,error_code=error)
                return result
            if (not isinstance(value,dict) or not isinstance(value.get('data'),dict) or value.get('trust')!='untrusted' or value.get('tool_name')!=call.name or
                not isinstance(value.get('read_execution_id'),str) or
                hashlib.sha256(canonical(value['data'])).hexdigest()!=value.get('sha256')):
                raise ToolError('EXECUTION_UNKNOWN')
            if custom and (value.get('revision')!=custom['manifest']['revision'] or not Draft202012Validator(custom['manifest']['output_schema']).is_valid(value['data'])):
                raise ToolError('EXECUTION_UNKNOWN')
            data['result']=value; base.journal.save(base.run_id,call.id,None,data)
            base.journal.event(run_id=base.run_id,call_id=call.id,tool_name=call.name,mode=base.mode,
                event='POLICY_RESULT',policy_verdict='READ_ALLOWED',tool_executed=True,observation_sha256=value['sha256'])
            return value
        except ToolError as error:
            denied=error.code not in {'CHAIN_UNAVAILABLE','EXECUTION_UNKNOWN'}
            base.journal.event(run_id=base.run_id,call_id=call.id,tool_name=call.name,mode=base.mode,
                event='POLICY_RESULT',policy_verdict='DENY' if denied else 'UNKNOWN',tool_executed=False if denied else None,error_code=error.code)
            return {'status':'DENIED' if denied else 'UNKNOWN','error_code':error.code}
