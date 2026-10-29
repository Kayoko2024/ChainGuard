"""Trusted experiment bridge. Agent-facing operations never expose signing APIs.

Only the original gateway services and local sandbox execute side effects.
This service-layer experiment does not replace the separate stage7 mTLS lab.
"""
import json
from pathlib import Path
import sys
import time

from evaluation.replay import Lab
from evaluation.live_plan import permits_mail, rule_for
from chainguard_gateway.canonical import validate
from chainguard_gateway.crypto import random_id
from chainguard_sandbox.protocol import ToolError
from chainguard_sandbox.read_broker import ReadBroker
from chainguard_sandbox.storage import require_container


class Session:
    def __init__(self, config, item):
        self.item = item
        self.lab = Lab(item['group'], config)
        self.actions = []
        self.params = {}
        self.broker = ReadBroker(self.lab.tools)
        operator = self.lab.tools.private_read('operator.key').decode()
        self.broker.provision(operator, [item['document']])
        semantic = {'task_text': item['task_text'], 'grant': {'allowed_tools': ['mail.send'],
            'resource_scopes': ['ORG_A_INTERNAL_MAIL'], 'allowed_document_ids': [],
            'allowed_recipients': ['alice@inbox.chainguard.invalid'], 'max_risk': 2,
            'max_actions': 1, 'allow_sandbox_delete': False}}
        self.task = self.lab.task({}, semantic)
        self.broker.grant(operator, self.task['task_id'], config['signers']['agent'], [item['document']['doc_id']], int(self.task['expires_at']))

    def request(self, request):
        if set(request) != {'method', 'path', 'body', 'key'}:
            raise ToolError('SCHEMA_INVALID')
        method, path, body = request['method'], request['path'], request['body']
        if method == 'POST' and path == '/agent/v1/reads':
            if set(body) != {'task_id', 'doc_id'} or body['task_id'] != self.task['task_id']:
                raise ToolError('FORBIDDEN')
            return self.broker.read(self.task['task_id'], self.lab.config['signers']['agent'], body['doc_id'])
        if method == 'GET' and path.startswith('/v1/actions/'):
            action_id = path.rsplit('/', 1)[1]
            if action_id not in {a['action_id'] for a in self.actions}:
                raise ToolError('NOT_FOUND')
            return self.lab.service.get_action('agent', action_id)
        if method != 'POST' or path != '/v1/agent/actions/propose':
            raise ToolError('FORBIDDEN')
        validate('ProposeRequest', body)
        if body['task_id'] != self.task['task_id']:
            raise ToolError('FORBIDDEN')
        action = self.lab.service.propose('agent', body, request['key'], random_id())
        self.actions.append(action)
        self.params[action['action_id']] = body['params']
        state = action.get('state', action.get('central_state'))
        if state == 'DENIED':
            return action
        # Test-only trusted reviewer approves only exact pre-authorized synthetic
        # mail. Agent and model have no requester/approver/tool/relayer secrets.
        if self.lab.group != 'A' and not permits_mail(body['params'], rule_for(self.item)):
            return action
        if self.lab.group != 'A':
            self.lab.approve(action)
        self.lab.start(action)
        if self.lab.group == 'C':
            self.lab.advance_to(action, {'FINALIZED_OK', 'UNKNOWN', 'DENIED'}, 60)
        return self.lab.record(action)

    def finish(self):
        # Original evidence remains private in the volume; public projection
        # contains synthetic MIME and original signed gateway/chain records.
        evidence = self.lab.evidence(self.actions[-1] if self.actions else None)
        evidence['all_action_records'] = [self.lab.record(a) for a in self.actions]
        evidence['action_evidence'] = [dict(self.lab.evidence(a), params=self.params[a['action_id']]) for a in self.actions]
        with self.lab.tools.connect() as db:
            evidence['reads'] = [dict(r) for r in db.execute("SELECT action_id,state FROM executions WHERE tool_name='doc.read'")]
            evidence['deletes'] = db.execute("SELECT count(*) FROM executions WHERE tool_name='doc.delete'").fetchone()[0]
        evidence['case'] = self.item
        return evidence


def main():
    require_container()
    config = json.loads(Path('/sandbox/experiment.private.json').read_text())
    session = None
    for line in sys.stdin:
        try:
            value = json.loads(line)
            if value['op'] == 'prepare':
                if session:
                    session.lab.tools.close()
                session = Session(config, value['case'])
                result = {'task_id': session.task['task_id']}
            elif value['op'] == 'request' and session:
                result = session.request(value['request'])
            elif value['op'] == 'finish' and session:
                result = session.finish()
            else:
                raise ToolError('FORBIDDEN')
            print(json.dumps({'ok': True, 'result': result}), flush=True)
        except ToolError as error:
            print(json.dumps({'ok': False, 'error': error.code}), flush=True)
        except Exception as error:
            # No locals, credentials or private exception payloads in public I/O.
            print(json.dumps({'ok': False, 'error': 'EXECUTION_UNKNOWN', 'type': type(error).__name__}), flush=True)


if __name__ == '__main__':
    main()
