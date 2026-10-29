"""Real paired mechanism experiments. Sensitive operations require the sandbox.

No security implementation is replaced. Faults target storage topology, transport
availability or the explicitly controlled administrative trust root.
"""
import base64
import copy
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import sqlite3
import time

from eth_account import Account
from eth_account.messages import encode_typed_data
from eth_abi import encode
from eth_utils import keccak
import rlp

from chainguard_gateway.audit import verify_log
from chainguard_gateway.chain_crypto import digest, recover_receipt
from chainguard_gateway.chain_rpc import Chain, Contract, RPC, abi_type, pack
from chainguard_gateway.chain_service import ChainService
from chainguard_gateway.chain_store import ChainStore
from chainguard_gateway.central_service import CentralService
from chainguard_gateway.central_store import CentralStore
from chainguard_gateway.crypto import label, random_id, PROTOCOL
from chainguard_sandbox.central_adapter import CentralToolAdapter
from chainguard_sandbox.chain_mail import ChainMailTool
from chainguard_sandbox.protocol import ToolError
from chainguard_sandbox.storage import Store, require_container

from .metrics import quantile, wilson, write_csv
from .replay import Lab, Authority, ToolClient, sign

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = ['normal', 'directory-takeover', 'shared-state-race', 'split-state-race',
             'split-tool-delivery', 'history-withheld', 'dependency-outage', 'one-rpc-outage']


def dump(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf8')


def validate_plan(plan):
    if (plan['track'] != 'mechanism_intervention' or plan['llm_samples'] != 0
            or plan['groups'] != ['B', 'C'] or plan['scenarios'] != SCENARIOS
            or plan['mail']['to'] != ['alice@inbox.chainguard.invalid']):
        raise ValueError('Only the fixed local paired mechanism plan is supported')
    for k in ['repetitions', 'performance_repetitions', 'bootstrap_replicates']:
        if type(plan[k]) is not int or plan[k] < 1:
            raise ValueError('Positive repetitions required')
    if not 1 <= plan['timeout_seconds'] <= 120:
        raise ValueError('Frozen intent deadline may not be extended')
    return plan


def schedule(plan):
    validate_plan(plan)
    cases = [(s, t) for s in plan['scenarios'] for t in range(plan['repetitions'])]
    cases += [('performance', t) for t in range(plan['performance_repetitions'])]
    random.Random(plan['seed']).shuffle(cases)
    result = []
    for scenario, trial in cases:
        groups = plan['groups'][:] if scenario != 'one-rpc-outage' else ['C']
        random.Random(f"{plan['seed']}/{scenario}/{trial}").shuffle(groups)
        result += [dict(scenario=scenario, trial=trial, group=g, sample_id=f'{scenario}/{trial}') for g in groups]
    return result


def semantic(plan, case):
    return dict(task_text=plan['task_text'], params=plan['mail'], intervention=case['scenario'],
                grant=dict(allowed_tools=['mail.send'], resource_scopes=['ORG_A_INTERNAL_MAIL'],
                           allowed_recipients=plan['mail']['to'], max_risk=2, max_actions=1,
                           allow_sandbox_delete=False, allowed_document_ids=[]))


def metrics(rows, plan):
    expected = {(c['group'], c['sample_id']) for c in schedule(plan)}
    if len(rows) != len(expected) or {(r['group'], r['sample_id']) for r in rows} != expected:
        raise ValueError('Missing or duplicate planned observation')
    pairs = {}
    for r in rows:
        pairs.setdefault(r['sample_id'], []).append(r)
    for pair in pairs.values():
        if len({r['input_sha256'] for r in pair}) != 1:
            raise ValueError('Mismatched paired inputs')
    output = []
    for scenario in SCENARIOS + ['performance']:
        for group in ['B', 'C']:
            selected = [r for r in rows if r['group'] == group and r['scenario'] == scenario]
            if not selected:
                continue
            for field in ['unauthorized_expansion', 'duplicate_effect', 'history_detected',
                          'metadata_recovered', 'recovered_after_outage', 'acknowledged', 'error']:
                valid = [r for r in selected if r.get(field) is not None]
                k, n = sum(bool(r[field]) for r in valid), len(valid)
                value, lo, hi = wilson(k, n)
                output.append(dict(scenario=scenario, group=group, metric=field, k=k, n=n,
                    estimate=value, ci95_low=lo, ci95_high=hi, method='Wilson95 descriptive; repeated single workload',
                    status='MEASURED_SMALL_SAMPLE' if n else 'NOT_APPLICABLE'))
            if scenario == 'history-withheld' and group == 'B':
                k = sum(bool(r.get('full_replica_recovered')) for r in selected)
                value, lo, hi = wilson(k, len(selected))
                output.append(dict(scenario=scenario, group='B+log', metric='metadata_recovered', k=k, n=len(selected),
                    estimate=value, ci95_low=lo, ci95_high=hi, method='Same B observations, extra independently held full signed log; not extra trials',
                    status='MEASURED_SMALL_SAMPLE'))
            if scenario == 'performance':
                values = [r['elapsed_ms'] for r in selected if not r['error'] and r['acknowledged']]
                for name, p in [('P50', .5), ('P95', .95), ('P99', .99)]:
                    rng = random.Random(plan['seed'])
                    boots = [quantile(rng.choices(values, k=len(values)), p) for _ in range(plan['bootstrap_replicates'])] if values else []
                    output.append(dict(scenario=scenario, group=group, metric='elapsed_ms_' + name,
                        n=len(values), estimate=quantile(values, p), ci95_low=quantile(boots, .025), ci95_high=quantile(boots, .975),
                        method='Trial bootstrap95, conditional on one workload; excludes setup/export/LLM/HTTP/humans', status='MEASURED_SMALL_SAMPLE'))
                for field in ['gas_used', 'state_bytes']:
                    values = [r[field] for r in selected if not r['error']]
                    output.append(dict(scenario=scenario, group=group, metric=field + '_P50', n=len(values),
                                       estimate=quantile(values, .5), status='MEASURED_SMALL_SAMPLE'))
    return output


def export(out, rows, plan):
    write_csv(out / 'cases.csv', rows)
    result = metrics(rows, plan)
    write_csv(out / 'aggregated_metrics.csv', result)
    return result


def verify_observation(row, observation):
    # Older writer shares the row reference with its evidence object and adds
    # evidence_file before serializing; that index is not an execution field.
    if ({k: v for k, v in row.items() if k != 'evidence_file'} !=
            {k: v for k, v in observation.items() if k != 'evidence_file'}):
        raise ValueError('Trace and original observation differ')


class Transactions:
    """Persist public hash before broadcast, verify all four real receipts."""
    def __init__(self, urls, key, out):
        self.nodes, self.key, self.out = [RPC(u) for u in urls], key, out
        self.items = []

    def save(self):
        dump(self.out / 'setup-transactions.json', self.items)

    def send(self, kind, data, to=None, expected=1):
        node, sender = self.nodes[0], Account.from_key(self.key)
        nonce = int(node.call('eth_getTransactionCount', [sender.address.lower(), 'pending']), 16)
        value = dict(chainId=20261026, nonce=nonce, gasPrice=0, gas=10000000, value=0, data=data)
        if to:
            value['to'] = bytes.fromhex(to[2:])
        signed = sender.sign_transaction(value)
        tx_hash = '0x' + signed.hash.hex().removeprefix('0x')
        self.items.append(dict(kind=kind, tx_hash=tx_hash, expected_status=expected))
        self.save()
        assert node.call('eth_sendRawTransaction', ['0x' + signed.raw_transaction.hex().removeprefix('0x')]) == tx_hash
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            receipts = [n.call('eth_getTransactionReceipt', [tx_hash]) for n in self.nodes]
            if all(receipts):
                assert all(r == receipts[0] for r in receipts)
                for n, r in zip(self.nodes, receipts):
                    b = n.call('eth_getBlockByNumber', [r['blockNumber'], False])
                    assert b['hash'] == r['blockHash'] and tx_hash in b['transactions']
                self.items[-1]['node_receipts'] = receipts
                self.save()
                assert int(receipts[0]['status'], 16) == expected
                return receipts[0]
            time.sleep(.12)
        raise TimeoutError('Unconfirmed original transaction; no replacement broadcast')


def isolated_deployment(source, contracts):
    """Fresh original registries inherit chain identity, never live deployment privileges.

    The live mail-window profile and legacy signing domains refer to other
    addresses. Copying them onto freshly deployed original bytecode is invalid;
    the experiment intentionally retains the original 120-second policy.
    """
    return {**{name: copy.deepcopy(source[name]) for name in ['chainId', 'genesisHash', 'validators']},
            'contracts': copy.deepcopy(contracts)}


def fresh_deployment(config, tx):
    """Deploy original bytecode to new addresses; never govern the live registry."""
    s = config['signers']
    def deploy(name, args):
        a = json.loads((ROOT / f'artifacts/contracts/{name}.sol/{name}.json').read_text())
        constructor = next(e for e in a['abi'] if e['type'] == 'constructor')['inputs']
        data = a['bytecode'] + encode([abi_type(p) for p in constructor], [pack(p, v) for p, v in zip(constructor, args)]).hex()
        receipt = tx.send('deploy-' + name, data)
        address = receipt['contractAddress']
        code = tx.nodes[0].call('eth_getCode', [address, 'latest'])
        assert code != '0x' and all(n.call('eth_getCode', [address, 'latest']) == code for n in tx.nodes)
        return dict(address=address, codeHash='0x' + keccak(bytes.fromhex(code[2:])).hex())
    contracts = {'PolicyRegistry': deploy('PolicyRegistry', [s['govA'], label('org', 'OrgA_Business'), s['govB'], label('org', 'OrgB_Security')])}
    sender = Account.from_key(tx.key).address.lower()
    nonce = int(tx.nodes[0].call('eth_getTransactionCount', [sender, 'pending']), 16)
    predicted = '0x' + keccak(rlp.encode([bytes.fromhex(sender[2:]), nonce + 1]))[-20:].hex()
    contracts['ExecutionRegistry'] = deploy('ExecutionRegistry', [contracts['PolicyRegistry']['address'], predicted])
    contracts['AuditRegistry'] = deploy('AuditRegistry', [contracts['PolicyRegistry']['address'], contracts['ExecutionRegistry']['address'], 0])
    assert contracts['AuditRegistry']['address'].lower() == predicted
    config['deployment'] = isolated_deployment(config['deployment'], contracts)
    chain = Chain(config['deployment'], [n.url for n in tx.nodes])
    chain.healthy()
    changes = []
    spec = json.loads((ROOT / 'spec/phase5/governance.json').read_text())
    def change(kind, args):
        changes.append(dict(kind=kind, data='0x' + encode(spec['payloads'][str(kind)]['abi'],
            [bytes.fromhex(v[2:]) if t.startswith('bytes') else v for t, v in zip(spec['payloads'][str(kind)]['abi'], args)]).hex()))
    for name, role in [('requester', 'REQUESTER'), ('agent', 'AGENT'), ('biz', 'BUSINESS_APPROVER'),
                       ('security', 'SECURITY_APPROVER'), ('mailTool', 'TOOL_SIGNER')]:
        change(0, [s[name], label('org', 'OrgB_Security' if name == 'security' else 'OrgA_Business'), True])
        change(1, [s[name], label('role', role), True])
        change(2, [s[name], label('scope', 'ORG_A_INTERNAL_MAIL'), True])
    change(3, [s['requester'], s['agent'], True])
    change(4, [label('tool', 'mail.send'), s['mailTool'], True])
    change(5, [label('policy', 'POLICY_R2_MAIL'), label('tool', 'mail.send'), label('scope', 'ORG_A_INTERNAL_MAIL'), 120, 2, True])
    governance(chain, config, tx, changes, ['govA', 'govB'], 'bootstrap')
    chain.healthy()
    return chain


def governance(chain, config, tx, changes, signers, name, expected=1):
    epoch = chain.policy.call('governanceEpoch')
    now = int(tx.nodes[0].call('eth_getBlockByNumber', ['latest', False])['timestamp'], 16)
    packed = [(c['kind'], bytes.fromhex(c['data'][2:])) for c in changes]
    message = dict(changesHash='0x' + keccak(encode(['(uint8,bytes)[]'], [packed])).hex(), nonce=epoch,
                   governanceEpoch=epoch, issuedAt=now, expiresAt=now + 120)
    spec = json.loads((ROOT / 'spec/phase5/governance.json').read_text())
    typed = dict(types=spec['types'], primaryType='GovernanceChange', domain=dict(name='ChainGuard PolicyRegistry',
                 version='1', chainId=20261026, verifyingContract=chain.policy.address), message=message)
    sigs = ['0x' + Account.sign_message(encode_typed_data(full_message=typed), config['signing_keys'][n]).signature.hex() for n in signers]
    tx.send(name, chain.policy.data('executeGovernance', [changes, epoch, epoch, now, now + 120, sigs]), chain.policy.address, expected)
    return dict(message=message, signatures=sigs, changes=changes, epoch_after=chain.policy.call('governanceEpoch'))


def clone_lab(lab, config):
    """A real quiescent snapshot, separate SQLite/keys and tool root; no fake state."""
    clone = object.__new__(Lab)
    clone.group, clone.config, clone.tools = lab.group, config, Store.create()
    # Gateway is copied before any dispatch/transaction; both copies retain exact intent and signatures.
    shutil.copytree(lab.store.root, clone.tools.root / 'gateway')
    if lab.group == 'B':
        clone.store = CentralStore(clone.tools.root / 'gateway')
        clone.adapter = CentralToolAdapter(clone.tools, clone.store)
        clone.service = CentralService(clone.store, clone.adapter)
    else:
        clone.store = ChainStore(clone.tools.root / 'gateway')
        clone.chain = Chain(config['deployment'], ['http://node3:8545', 'http://node1:8545'])
        clone.client = ToolClient()
        clone.service = ChainService(clone.store, clone.chain, clone.client, config['relay2_key'], config['signers']['mailTool'])
        clone.client.tool = ChainMailTool(clone.tools, Chain(config['deployment'], ['http://node4:8545', 'http://node2:8545']),
                                         Authority(clone.service), config['tool_key'], os.urandom(32))
        clone._private('experiment-tool.key', clone.client.tool.encryption_key)
    return clone


def finish(lab, action, seconds):
    if lab.group == 'C':
        lab.advance_to(action, {'FINALIZED_OK'}, seconds)
    return lab.state(action)


def recover_chain_metadata(chain, action_id):
    """No gateway/tool database or exported success labels are consulted."""
    reservation = chain.execution.call('getReservation', [action_id])
    stored_hash = chain.audit.call('receiptHash', [action_id])
    assert reservation['status'] == 3 and stored_hash != '0x' + '00' * 32
    intent = {source: str(reservation['intent'][target]) if target not in {'schemaVersion', 'risk'} and isinstance(reservation['intent'][target], int)
              else reservation['intent'][target] for source, target in PROTOCOL['json_to_typed']['ActionIntent'].items()}
    assert reservation['intentHash'] == digest('ActionIntent', intent, chain.domain)
    assert chain.execution.call('usedNonce', [intent['requester'], intent['nonce']])
    return dict(action_id=action_id, task_id=intent['task_id'], params_commit=intent['params_commit'],
                final_outcome='OK', approvers=reservation['approvers'], receipt_hash=stored_hash,
                receipt_signer=chain.audit.call('receiptSigner', [action_id]), mime_recovered=False)


def case_run(plan, config, case, tx, public):
    lab, others = Lab(case['group'], config), []
    sem = semantic(plan, case)
    row = dict(case, input_sha256=hashlib.sha256(json.dumps(sem, sort_keys=True).encode()).hexdigest(),
        track=plan['track'], llm_samples=0, attack_success=None, error=False, error_code=None,
        unauthorized_expansion=None, duplicate_effect=None, history_detected=None, metadata_recovered=None,
        recovered_after_outage=None, acknowledged=False, started_at_utc=datetime.now(timezone.utc).isoformat())
    action, extra, start = None, {}, time.perf_counter()
    try:
        task = lab.task(plan, sem)
        action = lab.propose(task, sem['params'])
        if case['scenario'] == 'directory-takeover':
            if lab.group == 'B':
                # Attacker controls the original central directory admin, not honest approver keys.
                for role in ['biz', 'security']:
                    with lab.store.connect() as db:
                        actor = lab.store.actor(db, subject=role)
                    actor['address'] = config['signers']['rogue_' + role]
                    lab.store.register_actor(lab.store.private('admin.key'), actor)
                    signature = sign(action['intent'], action['typed_data']['domain'], config['signing_keys']['rogue_' + role])
                    lab.service.approve(role, action['action_id'], {'signature': signature}, random_id())
                extra['directory_substitution'] = dict(honest_approval_keys_used=False, admin_api='CentralStore.register_actor',
                    claimed_orgs=['OrgA_Business', 'OrgB_Security'], replacements=[config['signers']['rogue_' + r] for r in ['biz', 'security']])
                lab.start(action)
            else:
                changes = []
                for role, onchain_role, org in [('biz', 'BUSINESS_APPROVER', 'OrgA_Business'), ('security', 'SECURITY_APPROVER', 'OrgB_Security')]:
                    addr = config['signers']['rogue_' + role]
                    for kind, types, values in [(0, ['address', 'bytes32', 'bool'], [addr, bytes.fromhex(label('org', org)[2:]), True]),
                        (1, ['address', 'bytes32', 'bool'], [addr, bytes.fromhex(label('role', onchain_role)[2:]), True]),
                        (2, ['address', 'bytes32', 'bool'], [addr, bytes.fromhex(label('scope', 'ORG_A_INTERNAL_MAIL')[2:]), True])]:
                        changes.append(dict(kind=kind, data='0x' + encode(types, values).hex()))
                extra['single_org_governance'] = governance(lab.chain, config, tx, changes, ['govA'], 'single-org-' + case['sample_id'], 0)
                extra['duplicate_org_governance'] = governance(lab.chain, config, tx, changes, ['govA', 'govA'], 'duplicate-org-' + case['sample_id'], 0)
                extra['approval_rejections'] = []
                for role in ['biz', 'security']:
                    signature = sign(action['intent'], lab.chain.domain, config['signing_keys']['rogue_' + role])
                    try:
                        lab.service.approve(role, action['action_id'], {'signature': signature}, random_id())
                    except ToolError as e:
                        extra['approval_rejections'].append(e.code)
                    else:
                        raise AssertionError('Unregistered replacement accepted')
                try:
                    lab.start(action)
                except ToolError as e:
                    row['error_code'] = e.code
                else:
                    raise AssertionError('Missing honest approvals accepted')
            row['unauthorized_expansion'] = bool(lab.mail())
        else:
            lab.approve(action)
            scenario = case['scenario']
            if scenario == 'split-state-race':
                clone = clone_lab(lab, config)
                others.append(clone)
                with ThreadPoolExecutor(2) as pool:
                    calls = [pool.submit(l.start, action) for l in [lab, clone]]
                    for f in calls:
                        f.result()
                if lab.group == 'C':
                    # Broadcast both prepared reservations before dispatching either tool.
                    deadline = time.monotonic() + plan['timeout_seconds']
                    while time.monotonic() < deadline:
                        for l in [lab, clone]:
                            try:
                                l.service.advance(action['action_id']) if l.state(action) == 'RESERVING' else None
                            except ToolError as e:
                                if e.code != 'RESERVATION_UNCONFIRMED':
                                    raise
                        receipts = []
                        for l in [lab, clone]:
                            with l.store.connect() as db:
                                item = db.execute("SELECT tx_hash FROM chain_transactions WHERE kind='reserve'").fetchone()
                            receipts.append(l.chain.rpc.call('eth_getTransactionReceipt', [item[0]]) if item else None)
                        if all(receipts):
                            assert sorted(int(r['status'], 16) for r in receipts) == [0, 1]
                            extra['race_receipts'] = receipts
                            winner = [lab, clone][[r['status'] for r in receipts].index('0x1')]
                            finish(winner, action, plan['timeout_seconds'])
                            break
                        time.sleep(.12)
                    else:
                        raise TimeoutError('Concurrent reservations unconfirmed')
                row['duplicate_effect'] = len(lab.mail()) + len(clone.mail()) > 1
            elif scenario == 'split-tool-delivery':
                separate = Store.create()
                extra['split_tool_root'] = str(separate.root)
                if lab.group == 'B':
                    first, second = lab.adapter, CentralToolAdapter(separate, lab.store)
                    class Fanout:
                        def attributes(self, *a):
                            return first.attributes(*a)
                        def execute(self, *a):
                            with ThreadPoolExecutor(2) as pool:
                                results = list(pool.map(lambda tool: tool.execute(*a), [first, second]))
                            return results[0]
                    lab.service = CentralService(lab.store, Fanout())
                else:
                    first = lab.client.tool
                    second = ChainMailTool(separate, first.chain, first.authority, config['tool_key'], os.urandom(32))
                    fd = os.open(separate.root / 'experiment-tool.key', os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                    with os.fdopen(fd, 'wb') as f:
                        f.write(second.encryption_key)
                    original = lab.client.request
                    def fanout(method, path, body=None, key=None):
                        if method == 'GET':
                            return original(method, path, body, key)
                        with ThreadPoolExecutor(2) as pool:
                            results = list(pool.map(lambda tool: tool.execute(body, key), [first, second]))
                        return results[0]
                    lab.client.request = fanout
                lab.start(action)
                finish(lab, action, plan['timeout_seconds'])
                with separate.connect() as db:
                    extra['split_tool_mailbox'] = [dict(r) for r in db.execute('SELECT action_id,recipient,mime_sha256 FROM mailbox')]
                row['duplicate_effect'] = len(lab.mail()) + len(extra['split_tool_mailbox']) > 1
                separate.close()
            elif scenario in {'dependency-outage', 'one-rpc-outage'}:
                before_height = int(tx.nodes[0].call('eth_blockNumber'), 16)
                if lab.group == 'B':
                    db_path = lab.store.root / 'state.sqlite3'
                    saved = lab.store.root / 'unavailable-state.sqlite3'
                    db_path.rename(saved)
                    db_path.mkdir()  # Actual sqlite open failure, inside disposable volume only.
                    try:
                        lab.start(action)
                    except sqlite3.OperationalError:
                        row['error_code'] = 'SQLITE_UNAVAILABLE'
                    else:
                        raise AssertionError('Unavailable state unexpectedly executed')
                    finally:
                        db_path.rmdir()
                        saved.rename(db_path)
                else:
                    original = lab.service.chain
                    urls = ['http://node1:8545', 'http://127.0.0.1:9'] if scenario == 'one-rpc-outage' else ['http://127.0.0.1:9', 'http://localhost:9']
                    lab.service.chain = Chain(config['deployment'], urls)
                    try:
                        lab.start(action)
                    except ToolError as e:
                        assert e.code == 'CHAIN_UNAVAILABLE'
                        row['error_code'] = e.code
                    else:
                        raise AssertionError('Unavailable dependency unexpectedly accepted')
                    finally:
                        lab.service.chain = original
                extra['mail_before_recovery'] = len(lab.mail())
                assert not lab.mail()
                time.sleep(2.2)
                extra['healthy_ledger_height_delta'] = int(tx.nodes[0].call('eth_blockNumber'), 16) - before_height
                lab.start(action)
                finish(lab, action, plan['timeout_seconds'])
                row['recovered_after_outage'] = len(lab.mail()) == 1
            elif scenario == 'shared-state-race':
                # Independent service objects share the original transactional state and tool DB.
                service = lab.service
                second = (CentralService(lab.store, lab.adapter) if lab.group == 'B' else
                          ChainService(lab.store, lab.chain, lab.client, config['relay_key'], config['signers']['mailTool']))
                def start_one(s):
                    if lab.group == 'B':
                        return s.execute('requester', action['action_id'], {'requester_signature': lab.signature(action, 'requester')}, random_id(), random_id())
                    return s.reserve('executor', action['action_id'], {'requester_signature': lab.signature(action, 'requester')}, random_id(), random_id())
                with ThreadPoolExecutor(2) as pool:
                    for f in [pool.submit(start_one, s) for s in [service, second]]:
                        f.result()
                finish(lab, action, plan['timeout_seconds'])
                row['duplicate_effect'] = len(lab.mail()) > 1
            else:
                lab.start(action)
                finish(lab, action, plan['timeout_seconds'])
        row['elapsed_ms'] = (time.perf_counter() - start) * 1000
        row['acknowledged'] = any(l.state(action) in {'CENTRAL_OK', 'FINALIZED_OK'} for l in [lab] + others)
        # History intervention happens after latency measurement, against an actual log copy.
        if case['scenario'] == 'history-withheld':
            recovery_start = time.perf_counter()
            if lab.group == 'B':
                audit = lab.evidence(action)['audit']
                # Independent checkpoint was saved before withholding the service's exported entries.
                withheld = audit['entries'][:-1]
                extra['independent_checkpoint'] = audit['checkpoint']
                extra['withheld_log'] = withheld
                check = verify_log(withheld, audit['signer'], checkpoint=audit['checkpoint'], deployment_id=audit['deployment_id'])
                row['history_detected'] = check['status'] == 'INVALID'
                row['metadata_recovered'] = any(e['event']['event'] == 'TOOL_RESULT' for e in withheld)
                full = verify_log(audit['entries'], audit['signer'], checkpoint=audit['checkpoint'], deployment_id=audit['deployment_id'])
                row['full_replica_recovered'] = full['status'] == 'VALID' and any(e['event'].get('event') == 'TOOL_RESULT' for e in audit['entries'])
                extra['full_replica_verification'] = full
            else:
                changed = copy.deepcopy(lab.record(action))
                changed['receipt'] = changed['finalization_evidence'] = None
                extra['withheld_record'] = changed
                extra['recovered_public_metadata'] = recover_chain_metadata(lab.chain, action['action_id'])
                row['history_detected'] = changed['receipt'] is None and extra['recovered_public_metadata']['final_outcome'] == 'OK'
                row['metadata_recovered'] = extra['recovered_public_metadata']['action_id'] == action['action_id']
                # Chain only recovers public authorization/result metadata, never MIME plaintext.
            row['recovery_ms'] = (time.perf_counter() - recovery_start) * 1000
    except Exception as e:
        import traceback
        row.update(error=True, error_code=type(e).__name__, failure_stack=[dict(file=Path(t.filename).name, line=t.lineno, function=t.name) for t in traceback.extract_tb(e.__traceback__)])
    row.setdefault('elapsed_ms', (time.perf_counter() - start) * 1000)
    evidence = dict(primary=lab.evidence(action), replicas=[l.evidence(action) for l in others], intervention=extra, semantic_input=sem)
    row['mailbox_count'] = len(lab.mail()) + sum(len(l.mail()) for l in others) + len(extra.get('split_tool_mailbox', []))
    row['action_id'] = action['action_id'] if action else None
    row['final_states'] = [l.state(action) for l in [lab] + others] if action else []
    row['gas_used'] = 0
    for part in [evidence['primary']] + evidence['replicas']:
        for item in part.get('transactions', []):
            receipt = tx.nodes[0].call('eth_getTransactionReceipt', [item['tx_hash']])
            if receipt:
                row['gas_used'] += int(receipt['gasUsed'], 16)
    row['state_bytes'] = sum(p.stat().st_size for l in [lab] + others for p in [l.store.root / 'state.sqlite3', l.tools.root / 'state.sqlite3'])
    row['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
    evidence['observation'] = copy.deepcopy(row)
    for l in [lab] + others:
        l.tools.close()
    return row, evidence


def volume_verify(cases):
    """Read actual retained tool volumes in a separate offline readonly container."""
    checked, total, approval_checks, tool_signatures = [], 0, 0, []
    for case in cases:
        count = 0
        parts = [case['primary']] + case['replicas']
        roots = [(part['tool_root'], part['mailbox']) for part in parts]
        extra = case['intervention']
        if 'split_tool_root' in extra:
            roots.append((extra['split_tool_root'], extra['split_tool_mailbox']))
        for root, expected in roots:
            p = Path(root)
            assert p.parent == Path('/sandbox') and p.name.startswith('test-')
            with sqlite3.connect(f'file:{p / "state.sqlite3"}?mode=ro', uri=True) as db:
                rows = db.execute('SELECT action_id,recipient,mime,mime_sha256 FROM mailbox').fetchall()
                assert sorted((r[0], r[1], r[3]) for r in rows) == sorted((r['action_id'], r['recipient'], r['mime_sha256']) for r in expected)
                for aid, recipient, mime, sha in rows:
                    assert hashlib.sha256(mime).hexdigest() == sha
                    assert recipient == 'alice@inbox.chainguard.invalid'
                    assert db.execute("SELECT state FROM executions WHERE action_id=?", (aid,)).fetchone()[0] == 'COMPLETED'
                    if case['observation']['group'] == 'C':
                        from Crypto.Cipher import AES
                        from chainguard_gateway.crypto import commit
                        key = (p / 'experiment-tool.key').read_bytes()
                        encrypted = db.execute('SELECT data FROM chain_mail WHERE action_id=?', (aid,)).fetchone()[0]
                        cipher = AES.new(key, AES.MODE_GCM, nonce=encrypted[:16])
                        cipher.update(aid.encode())
                        original = json.loads(cipher.decrypt_and_verify(encrypted[32:], encrypted[16:32]))
                        assert commit('result', original['result_salt'], original['result']) == original['receipt']['result_commit']
                        assert commit('evidence', original['evidence_salt'], original['evidence']) == original['receipt']['evidence_index_commit']
                        assert sha == original['evidence']['mime_sha256']
                        deployment = json.loads(Path('/sandbox/public/deployment.json').read_text())
                        domain = dict(name='ChainGuard AuditRegistry', version='1', chainId=str(deployment['chainId']),
                                      verifyingContract=deployment['contracts']['AuditRegistry']['address'].lower())
                        from chainguard_gateway.chain_crypto import recover_receipt
                        tool_signatures.append(dict(action_id=aid, signer=recover_receipt(original['receipt'], domain, original['tool_signature']),
                            digest=digest('ExecutionReceipt', original['receipt'], domain), tool_root=root))
                count += len(rows)
        # Independently decrypt and verify exact B intent signatures and current
        # organizations from the actual readonly gateway databases, including the
        # administrator takeover case. No permit issuance/execution API is called.
        if case['observation']['group'] == 'B':
            from chainguard_gateway.approvals import inspect_approvals
            from chainguard_gateway.authorization import signatures
            from chainguard_gateway.crypto import recover_intent, commit
            for part in parts:
                store = CentralStore(Path(part['tool_root']) / 'gateway')
                with sqlite3.connect(f'file:{store.root / "state.sqlite3"}?mode=ro', uri=True) as db:
                    db.row_factory = sqlite3.Row
                    aid = part['record']['action_id']
                    stored = db.execute('SELECT data FROM actions WHERE action_id=?', (aid,)).fetchone()[0]
                    data = store.unseal('action/' + aid, stored)
                    intent = data['intent']
                    assert commit('params', data['salt'], data['params']) == intent['params_commit']
                    domain = store.meta(db, 'domain')
                    assert recover_intent(intent, domain, data['requester_signature']) == intent['requester']
                    result = inspect_approvals(intent, domain, signatures(store, db, aid),
                        lambda addr: store.actor(db, address=addr), excluded=[store.meta(db, 'audit_signer')])
                    assert result['approval_count'] == 2 and result['independent_org_count'] == 2
                    approval_checks += 1
        assert count == case['observation']['mailbox_count']
        checked.append(dict(sample_id=case['observation']['sample_id'], group=case['observation']['group'], mail_count=count))
        total += count
    return dict(status='PASS', network='none', sqlite='mode=ro', cases=len(checked), mail_count=total,
                b_exact_double_approval_checks=approval_checks, tool_signatures=tool_signatures, checked=checked)


def main():
    require_container()
    assert os.geteuid() == 10001 and os.statvfs('/').f_flag & os.ST_RDONLY
    plan = validate_plan(json.loads((ROOT / 'evaluation/bc_live_plan.json').read_text()))
    config = json.loads(Path('/sandbox/experiment.private.json').read_text())
    public = Path('/sandbox/public')
    public.mkdir(mode=0o700)
    tx = Transactions([f'http://node{i}:8545' for i in range(1, 5)], config['relay_key'], public)
    chain = fresh_deployment(config, tx)
    dump(public / 'deployment.json', config['deployment'])
    rows = []
    for i, case in enumerate(schedule(plan)):
        row, evidence = case_run(plan, config, case, tx, public)
        row['evidence_file'] = f'case-{i:04d}.json'
        dump(public / row['evidence_file'], evidence)
        rows.append(row)
        with (public / 'traces.jsonl').open('a', encoding='utf8') as f:
            f.write(json.dumps(row) + '\n')
            f.flush()
            os.fsync(f.fileno())
        print(json.dumps({k: row.get(k) for k in ['sample_id', 'group', 'error', 'error_code', 'mailbox_count', 'final_states']}), flush=True)
        if row['error']:
            raise RuntimeError('Actual observation failed; stop and retain all evidence')
    export(public, rows, plan)
    dump(public / 'finished.json', dict(status='PASS', cases=len(rows), chain=chain.healthy()))


if __name__ == '__main__':
    main()
