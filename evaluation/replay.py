"""Trusted protocol experiment harness. Only run inside its restricted container.

Uses production services/tools without mocked success or fabricated receipts.
Transport wrappers only drop requests/responses or alter attacker-controlled bytes.
No Agent/model is running in this service-layer experiment.
"""
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import random
import time
import traceback
from datetime import datetime, timezone

from eth_account import Account
from eth_account.messages import encode_typed_data

from chainguard_gateway.audit import ZERO, event_hash, verify_log
from chainguard_gateway.central_service import CentralService
from chainguard_gateway.central_store import CentralStore
from chainguard_gateway.chain_crypto import digest
from chainguard_gateway.chain_rpc import Chain
from chainguard_gateway.chain_service import ChainService
from chainguard_gateway.chain_store import ChainStore
from chainguard_gateway.crypto import commit, random_id, typed_intent
from chainguard_gateway.policy import check_policy_freeze
from chainguard_sandbox.central_adapter import CentralToolAdapter
from chainguard_sandbox.chain_mail import ChainMailTool
from chainguard_sandbox.protocol import ToolError
from chainguard_sandbox.storage import Store, require_container

ALICE = 'alice@inbox.chainguard.invalid'
BOB = 'bob@inbox.chainguard.invalid'
SCENARIOS = {'normal', 'document-injection', 'mail-injection', 'forged-approval',
             'approval-replay', 'params-tamper', 'replay', 'fault-before-tool',
             'fault-after-tool', 'receipt-tamper', 'tool-chain-outage', 'pending-finalize'}


def sha(value):
    return hashlib.sha256(value).hexdigest()


def validate_plan(plan):
    if plan['track'] != 'protocol_replay' or plan['model']['backend'] != 'fixed_trace' or plan['model']['llm_samples'] != 0:
        raise ValueError('Real LLM track requires the unfinished phase7 prerequisite; no trace substitution')
    if plan['groups'] != ['A', 'B', 'C'] or plan['concurrency'] != 1:
        raise ValueError('This harness requires matched A/B/C and sequential relayer use')
    if not set(plan['scenarios']) <= SCENARIOS or len(set(plan['scenarios'])) != len(plan['scenarios']):
        raise ValueError('Invalid scenarios')
    for field in ['repetitions', 'performance_repetitions', 'replay_attempts', 'bootstrap_replicates']:
        if type(plan[field]) is not int or plan[field] < 1:
            raise ValueError('Positive integer required: ' + field)
    if plan['mail']['to'] != [ALICE] or not 1 <= plan['timeout_seconds'] <= 120:
        raise ValueError('Only synthetic local Alice mail is supported')
    return plan


def schedule(plan):
    validate_plan(plan)
    samples = [(s, i, False) for s in plan['scenarios'] for i in range(plan['repetitions'])]
    samples += [('performance', i, True) for i in range(plan['performance_repetitions'])]
    random.Random(plan['seed']).shuffle(samples)
    result = []
    for scenario, trial, performance in samples:
        groups = plan['groups'][:]
        random.Random(f"{plan['seed']}/{scenario}/{trial}").shuffle(groups)
        result.extend({'scenario': scenario, 'trial': trial, 'performance_eligible': performance,
                       'sample_id': f'{scenario}/{trial}', 'group': g} for g in groups)
    return result


def semantic_input(plan, case):
    scenario = case['scenario']
    params = copy.deepcopy(plan['mail'])
    if scenario in {'document-injection', 'mail-injection'}:
        params['to'] = [BOB]
    document = plan['documents'].get(scenario, plan['documents']['normal'])
    return {'task_text': plan['task_text'], 'document': document, 'tool_name': 'mail.send', 'params': params,
            'grant': {'allowed_tools': ['mail.send'], 'resource_scopes': ['ORG_A_INTERNAL_MAIL'],
                      'allowed_recipients': [ALICE], 'max_risk': 2, 'max_actions': 20,
                      'allow_sandbox_delete': False, 'allowed_document_ids': []}}


def sign(intent, domain, key):
    return '0x' + Account.sign_message(encode_typed_data(full_message=typed_intent(intent, domain)), key).signature.hex()


class CentralFaultAdapter(CentralToolAdapter):
    mode = None

    def execute(self, action_id, params):
        if self.mode == 'fault-before-tool':
            raise OSError('Injected transport loss before delivery')
        if self.mode == 'params-tamper':
            params = dict(params, body=params['body'] + ' altered')
        result = super().execute(action_id, params)
        if self.mode == 'fault-after-tool':
            raise OSError('Injected loss after actual commit')
        return result


class ToolClient:
    """In-process transport boundary for real C tool; never creates a result."""
    def __init__(self):
        self.mode = None
        self.tool = None
        self.events = []

    def request(self, method, path, body=None, key=None):
        if method == 'GET':
            return self.tool.status(path.rsplit('/', 1)[1])
        if self.mode == 'fault-before-tool':
            self.events.append('request_dropped_before_tool')
            raise ToolError('CHAIN_UNAVAILABLE')
        if self.mode == 'params-tamper':
            body = copy.deepcopy(body)
            body['params']['body'] += ' altered'
        response = self.tool.execute(body, key)
        if self.mode == 'fault-after-tool':
            self.events.append('response_dropped_after_actual_commit')
            raise ToolError('CHAIN_UNAVAILABLE')
        if self.mode == 'receipt-tamper':
            response = copy.deepcopy(response)
            response['receipt']['outcome'] = 1
            self.events.append('signed_receipt_outcome_altered_in_transit')
        return response


class Authority:
    def __init__(self, service):
        self.service = service

    def request(self, method, path):
        assert method == 'GET'
        return self.service.authorization(path.rsplit('/', 1)[1])


class Lab:
    def __init__(self, group, config):
        self.group, self.config = group, config
        self.tools = Store.create()
        if group == 'C':
            self.store = ChainStore.create(self.tools.root / 'gateway')
            self.chain = Chain(config['deployment'], ['http://node1:8545', 'http://node3:8545'])
            self.client = ToolClient()
            self.service = ChainService(self.store, self.chain, self.client, config['relay_key'], config['signers']['mailTool'])
            self.client.tool = ChainMailTool(self.tools,
                Chain(config['deployment'], ['http://node2:8545', 'http://node4:8545']),
                Authority(self.service), config['tool_key'], os.urandom(32))
            # Persist tool evidence encryption key in the trusted volume for readonly verification.
            self._private('experiment-tool.key', self.client.tool.encryption_key)
        else:
            self.store = CentralStore.create(self.tools.root / 'gateway', group, check_policy_freeze(), self.tools.root)
            self.adapter = CentralFaultAdapter(self.tools, self.store)
            self.service = CentralService(self.store, self.adapter)
        roles = {'requester': ['REQUESTER'], 'agent': ['AGENT'], 'biz': ['BUSINESS_APPROVER'],
                 'security': ['SECURITY_APPROVER'], 'executor': [], 'auditor': ['AUDITOR']}
        for subject, actor_roles in roles.items():
            actor = {'subject': subject, 'address': config['signers'][subject], 'roles': actor_roles,
                     'organization': 'OrgB_Security' if subject == 'security' else 'OrgA_Business',
                     'active': True, 'allowed_tools': ['mail.send'], 'resource_scopes': ['PUBLIC_DOCS', 'ORG_A_DOCS', 'ORG_A_INTERNAL_MAIL', 'ORG_A_DISPOSABLE_DOCS'],
                     'allowed_document_ids': [], 'allowed_recipients': [ALICE, BOB], 'max_risk': 2}
            self.store.register_actor(self.store.private('admin.key'), actor)

    def _private(self, name, data):
        fd = os.open(self.tools.root / name, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)

    def task(self, plan, semantic):
        body = dict(semantic['grant'], task_text=semantic['task_text'], agent=self.config['signers']['agent'],
                    expires_at=str(int(time.time()) + 1800))
        return self.service.create_task('requester', body, random_id(), random_id())

    def propose(self, task, params):
        return self.service.propose('agent', {'task_id': task['task_id'], 'tool_name': 'mail.send', 'params': params}, random_id(), random_id())

    def signature(self, action, role):
        return sign(action['intent'], self.chain.domain if self.group == 'C' else action['typed_data']['domain'], self.config['signing_keys'][role])

    def approve(self, action):
        for role in ['biz', 'security']:
            self.service.approve(role, action['action_id'], {'signature': self.signature(action, role)}, random_id())

    def start(self, action):
        if self.group == 'C':
            return self.service.reserve('executor', action['action_id'], {'requester_signature': self.signature(action, 'requester')}, random_id(), random_id())
        return self.service.execute('requester', action['action_id'],
            {'requester_signature': self.signature(action, 'requester')} if self.group == 'B' else {}, random_id(), random_id())

    def record(self, action):
        return self.service.get_action('requester', action['action_id'])

    def state(self, action):
        row = self.record(action)
        return row.get('state', row.get('central_state'))

    def advance_to(self, action, states, seconds):
        deadline = time.monotonic() + seconds
        while self.state(action) not in states:
            if time.monotonic() >= deadline:
                raise TimeoutError('Real chain state wait timed out')
            try:
                self.service.advance(action['action_id'])
            except ToolError as error:
                # Real nodes may observe a just-committed transaction at different
                # instants. Poll the original hash/state, never change nonce/action.
                if error.code not in {'CHAIN_UNAVAILABLE', 'RESERVATION_UNCONFIRMED'}:
                    raise
            time.sleep(.12)

    def mail(self):
        with self.tools.connect() as db:
            rows = [dict(r) for r in db.execute('SELECT action_id,recipient,mime,mime_sha256 FROM mailbox ORDER BY message_id')]
        for row in rows:
            assert sha(row['mime']) == row['mime_sha256']
            row['mime_b64'] = base64.b64encode(row.pop('mime')).decode()
        return rows

    def evidence(self, action):
        evidence = {'group': self.group, 'tool_root': str(self.tools.root), 'mailbox': self.mail(),
                    'record': self.record(action) if action else None}
        if self.group == 'C':
            evidence['transactions'] = []
            with self.store.connect() as db:
                for row in db.execute('SELECT action_id,kind,nonce,tx_hash,state FROM chain_transactions'):
                    evidence['transactions'].append(dict(row))
            if action:
                with self.store.connect() as db:
                    _, data = self.store.action(db, action['action_id'])
                evidence['tool_signature'] = data.get('tool_signature')
                evidence['approvals'] = list(data['approvals'].values())
                evidence['requester_signature'] = data['requester_signature']
                with self.store.connect() as db:
                    evidence['events'] = [dict(r) for r in db.execute('SELECT sequence,action_id,event FROM chain_events')]
                if any(m['action_id'] == action['action_id'] for m in evidence['mailbox']):
                    with self.tools.connect() as db:
                        raw = db.execute('SELECT data FROM chain_mail WHERE action_id=?', (action['action_id'],)).fetchone()[0]
                    original = self.client.tool.unseal(action['action_id'], raw)
                    assert commit('result', original['result_salt'], original['result']) == original['receipt']['result_commit']
                    assert commit('evidence', original['evidence_salt'], original['evidence']) == original['receipt']['evidence_index_commit']
                    evidence['tool_commitments_verified'] = True
        else:
            with self.store.connect() as db:
                from chainguard_gateway.audit import AuditLog
                evidence['audit'] = {'entries': AuditLog.entries(db), 'signer': self.store.meta(db, 'audit_signer'),
                                     'deployment_id': self.store.meta(db, 'deployment_id'),
                                     'checkpoint': self.store.meta(db, 'checkpoint') if self.group == 'B' else None}
        return evidence


def verify_unsigned(entries):
    previous = ZERO
    for number, entry in enumerate(entries, 1):
        if entry['sequence'] != str(number) or entry['previous_hash'] != previous or entry['event_hash'] != event_hash(previous, entry['event']):
            return False
        previous = entry['event_hash']
    return True


def tamper_copies(lab, evidence, plan, case):
    """Edit actual exported records, retaining independent trusted checkpoint/chain."""
    results = []
    if not evidence['mailbox']:
        return results
    for kind in plan['tamper_scenarios']:
        if lab.group in {'A', 'B'}:
            original = evidence['audit']
            changed = copy.deepcopy(original['entries'])
            if kind == 'tail-delete':
                changed.pop()
            else:
                changed[-1]['event']['tool_executed'] = False
                previous = ZERO
                for entry in changed:
                    entry['previous_hash'] = previous
                    entry['event_hash'] = event_hash(previous, entry['event'])
                    previous = entry['event_hash']
            detected = not verify_unsigned(changed) if lab.group == 'A' else verify_log(changed, original['signer'],
                checkpoint=original['checkpoint'], deployment_id=original['deployment_id'])['status'] == 'INVALID'
            modified = {'entries': changed}
        else:
            original = evidence['record']
            modified = copy.deepcopy(original)
            if kind == 'tail-delete':
                modified['receipt'] = None
                modified['finalization_evidence'] = None
            else:
                modified['receipt']['result_commit'] = random_id()
            onchain = lab.chain.audit.call('receiptHash', [original['action_id']])
            detected = modified['receipt'] is None or digest('ExecutionReceipt', modified['receipt'], lab.chain.receipt_domain) != onchain
        results.append({'kind': kind, 'detected': detected, 'modified_copy': modified,
                        'sample_id': case['sample_id'], 'group': lab.group})
    return results


def run_case(plan, config, case):
    semantic = semantic_input(plan, case)
    lab = Lab(case['group'], config)
    scenario = case['scenario']
    row = dict(case, input_sha256=sha(json.dumps(semantic, sort_keys=True, separators=(',', ':')).encode()),
               attempt_origin='protocol_driver', model_mode='fixed_trace', started_at_utc=datetime.now(timezone.utc).isoformat(),
               risk=2, agent_attempted_tool='mail.send', attack_success=None, llm_sample_count=0,
               unauthorized_attempts=0, unauthorized_executions=0, unauthorized_blocked=0, unauthorized_unknown=0,
               task_eligible=int(scenario in {'normal', 'performance', 'replay', 'fault-before-tool', 'fault-after-tool', 'receipt-tamper', 'tool-chain-outage', 'pending-finalize'}),
               task_completed=0, task_unknown=0, forgery_attempts=0, forgery_accepted=0, forgery_unknown=0,
               attack_evaluable=0, attack_success_count=0, attack_unknown=0,
               tamper_attempts=0, tamper_detected=0, tamper_unknown=0,
               replay_attempts=0, duplicate_effects=0, approval_ms=None, reservation_ms=None, tool_ms=None, finalization_ms=None,
               error_code=None, blocked_at=None, policy_verdict=None, tool_executed=None,
               mechanism_applicable=not (case['group'] != 'C' and scenario in {'receipt-tamper', 'tool-chain-outage', 'pending-finalize'} or
                                         case['group'] == 'A' and scenario in {'forged-approval', 'approval-replay'}),
               observed_states=[], status='RUNNING')
    action, evidence = None, None
    started = time.perf_counter()
    try:
        task = lab.task(plan, semantic)
        action = lab.propose(task, semantic['params'])
        row['policy_verdict'] = action.get('policy_verdict', 'REQUIRE_APPROVAL')
        row['observed_states'].append(lab.state(action))
        if scenario in {'document-injection', 'mail-injection'}:
            row['unauthorized_attempts'] = 1
            if lab.group != 'A':
                if lab.group == 'B':
                    assert lab.state(action) == 'DENIED'
                    row.update(error_code=action['policy_error_code'], blocked_at='gateway', policy_verdict='DENY')
                row['unauthorized_blocked'] = 1
            else:
                lab.start(action)
        elif scenario in {'forged-approval', 'approval-replay'} and lab.group != 'A':
            row['unauthorized_attempts'] = row['forgery_attempts'] = 1
            target = action
            if scenario == 'approval-replay':
                target = lab.propose(task, semantic['params'])
            signature = (sign(action['intent'], lab.chain.domain if lab.group == 'C' else action['typed_data']['domain'], Account.create().key)
                         if scenario == 'forged-approval' else lab.signature(action, 'biz'))
            lab.service.approve('biz', target['action_id'], {'signature': signature}, random_id())
            row['forgery_accepted'] = 1
        else:
            if lab.group != 'A':
                stamp = time.perf_counter()
                lab.approve(action)
                row['approval_ms'] = (time.perf_counter() - stamp) * 1000
            if scenario == 'params-tamper':
                row['unauthorized_attempts'] = 1
            if lab.group == 'C':
                lab.client.mode = scenario
                if scenario == 'tool-chain-outage':
                    # Actual refused TCP connections, never a fake chain response.
                    lab.client.tool.chain = Chain(config['deployment'], ['http://127.0.0.1:9', 'http://localhost:9'])
                stamp = time.perf_counter()
                lab.start(action)
                lab.advance_to(action, {'RESERVED'}, plan['timeout_seconds'])
                row['reservation_ms'] = (time.perf_counter() - stamp) * 1000
                row['observed_states'].append('RESERVED')
                stamp = time.perf_counter()
                lab.service.advance(action['action_id'])
                row['tool_ms'] = (time.perf_counter() - stamp) * 1000
                row['action_to_receipt_ms'] = (time.perf_counter() - started) * 1000
                row['observed_states'].append(lab.state(action))
                if scenario == 'params-tamper':
                    row.update(unauthorized_blocked=int(not lab.mail()), blocked_at='tool', error_code=lab.record(action)['error']['code'])
                if scenario in {'fault-after-tool', 'receipt-tamper'}:
                    assert lab.state(action) == 'UNKNOWN'
                    lab.client.mode = None
                    # New service reconstructs durable state, queries original tool receipt.
                    lab.service = ChainService(lab.store, lab.chain, lab.client, config['relay_key'], config['signers']['mailTool'])
                    lab.client.tool.authority = Authority(lab.service)
                    lab.service.advance(action['action_id'])
                    row['observed_states'].append(lab.state(action))
                if lab.state(action) == 'EXECUTION_RECORDED':
                    stamp = time.perf_counter()
                    if scenario == 'pending-finalize':
                        original_rpc = lab.chain.rpc.call
                        pending_hash = None
                        def drop_send(method, params=None):
                            if method == 'eth_sendRawTransaction':
                                raise ToolError('CHAIN_UNAVAILABLE')
                            return original_rpc(method, params)
                        lab.chain.rpc.call = drop_send
                        try:
                            while time.perf_counter() - stamp < plan['timeout_seconds']:
                                try:
                                    lab.service.advance(action['action_id'])
                                except ToolError as error:
                                    assert error.code == 'CHAIN_UNAVAILABLE'
                                    with lab.store.connect() as db:
                                        pending_hash = db.execute("SELECT tx_hash FROM chain_transactions WHERE kind='audit'").fetchone()[0]
                                    break
                                time.sleep(.12)
                        finally:
                            lab.chain.rpc.call = original_rpc
                        assert pending_hash and lab.state(action) == 'EXECUTION_RECORDED'
                        row['pending_original_hash'] = pending_hash
                        lab.service = ChainService(lab.store, lab.chain, lab.client, config['relay_key'], config['signers']['mailTool'])
                    lab.advance_to(action, {'FINALIZED_OK'}, plan['timeout_seconds'])
                    row['finalization_ms'] = (time.perf_counter() - stamp) * 1000
                    row['observed_states'].append(lab.state(action))
                    if scenario == 'pending-finalize':
                        assert lab.record(action)['finalization_evidence']['tx_hash'] == row['pending_original_hash']
                if scenario == 'replay':
                    before = len(lab.mail())
                    # Durable gateway restart and tool reopen preserve the same records.
                    lab.service = ChainService(lab.store, lab.chain, lab.client, config['relay_key'], config['signers']['mailTool'])
                    tool = lab.client.tool
                    lab.client.tool = ChainMailTool(lab.tools, tool.chain, Authority(lab.service), tool.signing_key, tool.encryption_key)
                    for _ in range(plan['replay_attempts']):
                        lab.start(action)
                        lab.service.advance(action['action_id'])
                    with lab.store.connect() as db:
                        _, original = lab.store.action(db, action['action_id'])
                    request = {'intent': original['intent'], 'params_salt': original['salt'],
                               'params': original['params'], 'reservation_evidence': original['reservation_evidence']}
                    for _ in range(plan['replay_attempts']):
                        lab.client.tool.execute(request, random_id())
                    row.update(replay_attempts=plan['replay_attempts'] * 2, gateway_replay_attempts=plan['replay_attempts'],
                               tool_replay_attempts=plan['replay_attempts'], duplicate_effects=len(lab.mail()) - before)
            else:
                lab.adapter.mode = scenario
                stamp = time.perf_counter()
                lab.start(action)
                row['tool_ms'] = (time.perf_counter() - stamp) * 1000
                row['action_to_receipt_ms'] = (time.perf_counter() - started) * 1000
                if scenario == 'params-tamper':
                    row.update(unauthorized_blocked=int(not lab.mail()), blocked_at='tool', error_code='PARAMS_MISMATCH')
                if scenario == 'replay':
                    before = len(lab.mail())
                    lab.service = CentralService(lab.store, lab.adapter)
                    for _ in range(plan['replay_attempts']):
                        lab.start(action)
                    direct_denied = 0
                    for _ in range(plan['replay_attempts']):
                        try:
                            lab.adapter.execute(action['action_id'], semantic['params'])
                        except ToolError as error:
                            assert error.code == 'STATE_CONFLICT'
                            direct_denied += 1
                    row.update(replay_attempts=plan['replay_attempts'] * 2, gateway_replay_attempts=plan['replay_attempts'],
                               tool_replay_attempts=plan['replay_attempts'], direct_tool_replay_denials=direct_denied,
                               duplicate_effects=len(lab.mail()) - before)
        row['status'] = 'OBSERVED'
    except ToolError as error:
        row['error_code'] = error.code
        if scenario in {'document-injection', 'mail-injection'} and error.code == 'UNAUTHORIZED_SCOPE':
            row.update(unauthorized_attempts=1, unauthorized_blocked=1, blocked_at='gateway', policy_verdict='DENY', status='OBSERVED')
        elif scenario in {'forged-approval', 'approval-replay'} and error.code == 'APPROVAL_INVALID':
            row.update(unauthorized_blocked=1, blocked_at='approval', status='OBSERVED')
        else:
            row['status'] = 'ERROR'
    except Exception as error:
        row.update(status='ERROR', error_code=type(error).__name__)
        row['failure_stack'] = [{'file': Path(t.filename).name, 'line': t.lineno, 'function': t.name}
                                for t in traceback.extract_tb(error.__traceback__)]
    finally:
        row['elapsed_ms'] = (time.perf_counter() - started) * 1000
        row['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
        evidence = lab.evidence(action)
        mail = evidence['mailbox']
        row['mailbox_count'] = len(mail)
        row['tool_executed'] = bool(mail)
        row['final_state'] = lab.state(action) if action else 'NO_ACTION'
        row['action_id'] = action['action_id'] if action else None
        row['policy_enforced'] = lab.group != 'A'
        if not row['error_code'] and evidence['record'] and evidence['record'].get('error'):
            row['error_code'] = evidence['record']['error']['code']
        row['observed_states'].append(row['final_state'])
        row['task_completed'] = int(bool(row['task_eligible']) and len(mail) == 1 and mail[0]['recipient'] == ALICE)
        if scenario in {'document-injection', 'mail-injection'}:
            row['unauthorized_executions'] = sum(m['recipient'] == BOB for m in mail)
        elif scenario == 'params-tamper':
            row['unauthorized_executions'] = len(mail)
        if row['status'] == 'ERROR':
            row['unauthorized_unknown'] = max(0, row['unauthorized_attempts'] - row['unauthorized_blocked'] - row['unauthorized_executions'])
        # Tamper experiments run only on normal cases, avoiding performance contamination.
        row['measurement_finished_before_audit_tamper'] = True
        evidence['tampering'] = tamper_copies(lab, evidence, plan, case) if scenario == 'normal' else []
        row['tamper_attempts'] = len(evidence['tampering'])
        row['tamper_detected'] = sum(t['detected'] for t in evidence['tampering'])
        evidence['semantic_input'] = semantic
        evidence['case'] = row
        lab.tools.close()
    return row, evidence


def main():
    require_container()
    assert os.geteuid() == 10001 and os.statvfs('/').f_flag & os.ST_RDONLY
    config = json.loads(Path('/sandbox/experiment.private.json').read_text())
    plan = validate_plan(json.loads(Path('/app/evaluation/phase8_plan.json').read_text()))
    results = Path('/sandbox/public')
    results.mkdir(mode=0o700)
    traces = results / 'traces.jsonl'
    for index, case in enumerate(schedule(plan)):
        row, evidence = run_case(plan, config, case)
        path = f"case-{index:04d}.json"
        (results / path).write_text(json.dumps(evidence, indent=2) + '\n')
        row['evidence_file'] = path
        with traces.open('a', encoding='utf8') as stream:
            stream.write(json.dumps(row, separators=(',', ':')) + '\n')
            stream.flush()
            os.fsync(stream.fileno())
        print(json.dumps({'index': index, 'sample_id': row['sample_id'], 'group': row['group'], 'status': row['status'],
                          'state': row['final_state'], 'mailbox_count': row['mailbox_count'], 'error': row['error_code']}), flush=True)
    print(json.dumps({'status': 'DONE', 'cases': index + 1}), flush=True)


if __name__ == '__main__':
    main()
