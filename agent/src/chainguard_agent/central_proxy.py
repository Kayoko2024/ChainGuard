"""Experiment A/B proxy preserving the existing central record contract."""
import hashlib
from chainguard_gateway.canonical import canonical
from chainguard_gateway.central_contract import validate_central
from chainguard_sandbox.protocol import ToolError, params_for


class CentralExecutionProxy:
    def __init__(self, transport, journal, run_id, task_id):
        self.transport, self.journal, self.run_id, self.task_id = transport, journal, run_id, task_id

    def execute(self, call):
        known_action = None
        common = dict(run_id=self.run_id, call_id=call.id, tool_name=call.name, mode='real_llm')
        self.journal.event(**common, event='AGENT_ATTEMPT', agent_attempted_tool=True,
                           arguments_sha256=hashlib.sha256(canonical(call.arguments)).hexdigest())
        try:
            params_for(call.name, call.arguments)
            row, data = self.journal.claim(self.run_id, self.task_id, call)
            known_action = row['action_id']
            if data['result'] is not None:
                return data['result']
            if call.name == 'doc.read':
                result = self.transport.request('POST', '/agent/v1/reads', {'task_id': self.task_id, **call.arguments}, row['idempotency_key'])
                if hashlib.sha256(result['content'].encode()).hexdigest() != result['sha256']:
                    raise ToolError('EXECUTION_UNKNOWN')
                verdict, executed = 'READ_ALLOWED', True
            else:
                record = (self.transport.request('GET', '/v1/actions/'+row['action_id']) if row['action_id'] else
                          self.transport.request('POST', '/v1/agent/actions/propose', data['request'], row['idempotency_key']))
                validate_central('CentralActionRecord', record)
                known_action = record['action_id']
                self.journal.save(self.run_id, call.id, known_action, data)
                state = record['central_state']
                result = {'status': state, 'action_id': record['action_id'], 'record': record}
                verdict = 'DENY' if state in {'DENIED', 'CENTRAL_REJECTED'} else 'ALLOW' if state == 'CENTRAL_OK' else 'UNKNOWN'
                executed = True if state == 'CENTRAL_OK' else False if verdict == 'DENY' else None
            data['result'] = result
            if call.name == 'doc.read' or verdict != 'UNKNOWN':
                self.journal.save(self.run_id, call.id, result.get('action_id'), data)
            self.journal.event(**common, event='POLICY_RESULT', policy_verdict=verdict, tool_executed=executed, action_id=known_action)
            return result
        except ToolError as error:
            known = known_action is None and error.code not in {'EXECUTION_UNKNOWN', 'CHAIN_UNAVAILABLE'}
            self.journal.event(**common, event='POLICY_RESULT', policy_verdict='DENY' if known else 'UNKNOWN',
                               tool_executed=False if known else None, error_code=error.code)
            return {'status': 'DENIED' if known else 'UNKNOWN', 'error_code': error.code}
