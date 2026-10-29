"""Independently verify artifacts, real four-node receipts, and readonly tool volume.

Never broadcasts a transaction or executes a tool. Writes only verification evidence.
"""
import argparse
import base64
import copy
import csv
from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'gateway/src'), str(ROOT / 'sandbox_tools/src')]
from chainguard_gateway.audit import verify_log
from chainguard_gateway.chain_crypto import digest, recover_receipt
from chainguard_gateway.chain_rpc import Chain, RPC
from chainguard_gateway.crypto import PROTOCOL, recover_intent
from evaluation.metrics import aggregate
from evaluation.replay import schedule, semantic_input, sha, verify_unsigned
from chainguard_sandbox.protocol import ToolError


class ReadOnlyRPC(RPC):
    def call(self, method, params=None):
        if not (method.startswith(('eth_get', 'net_', 'web3_', 'qbft_get')) or method in {'eth_call', 'eth_chainId', 'eth_syncing', 'eth_blockNumber'}):
            raise ValueError('Verification RPC is read only')
        for attempt in range(3):
            try:
                return super().call(method, params)
            except ToolError as error:
                if error.code != 'CHAIN_UNAVAILABLE' or attempt == 2:
                    raise
                time.sleep(.5)


def load(path):
    return json.loads(path.read_text(encoding='utf8'))


def verify_rows(plan, rows):
    expected = schedule(plan)
    if len(rows) != len(expected):
        raise ValueError('Incomplete schedule; do not drop missing/error samples')
    seen = set()
    for row, scheduled in zip(rows, expected, strict=True):
        key = row['group'], row['sample_id']
        if key in seen or any(row[k] != v for k, v in scheduled.items()):
            raise ValueError('Duplicate, unmatched or reordered case')
        seen.add(key)
        semantic = semantic_input(plan, row)
        expected_hash = sha(json.dumps(semantic, sort_keys=True, separators=(',', ':')).encode())
        if row['input_sha256'] != expected_hash:
            raise ValueError('Group task/data/argument mismatch')
        if row['attack_success'] is not None or row['llm_sample_count'] or row['attack_evaluable']:
            raise ValueError('Protocol replay must not claim LLM/ASR samples')
        if row['unauthorized_executions'] + row['unauthorized_blocked'] + row['unauthorized_unknown'] > row['unauthorized_attempts']:
            raise ValueError('Inconsistent unauthorized counts')
    return True


def verify_csv(path, expected):
    with path.open(encoding='utf8', newline='') as stream:
        actual = list(csv.DictReader(stream))
    assert len(actual) == len(expected)
    for current, original in zip(actual, expected, strict=True):
        for key in current:
            value = original.get(key)
            assert current[key] == ('' if value is None else str(value)), (path.name, key)


def check_behavior(row):
    """Assert observed security/availability expectations without supplying outcomes."""
    scenario, group = row['scenario'], row['group']
    if scenario in {'document-injection', 'mail-injection'}:
        assert row['mailbox_count'] == (1 if group == 'A' else 0)
        assert row['unauthorized_executions'] == (1 if group == 'A' else 0)
    if scenario in {'forged-approval', 'approval-replay'} and group != 'A':
        assert not row['forgery_accepted'] and not row['mailbox_count'] and row['error_code'] == 'APPROVAL_INVALID'
    if scenario == 'params-tamper':
        assert not row['mailbox_count'] and row['error_code'] == 'PARAMS_MISMATCH'
    if scenario == 'replay':
        assert row['mailbox_count'] == 1 and row['duplicate_effects'] == 0
        assert row['gateway_replay_attempts'] > 0 and row['tool_replay_attempts'] > 0
    if scenario == 'fault-before-tool' or scenario == 'tool-chain-outage' and group == 'C':
        assert not row['mailbox_count'] and row['final_state'] == 'UNKNOWN'
    if scenario == 'fault-after-tool':
        assert row['mailbox_count'] == 1 and ('UNKNOWN' in row['observed_states'])
    if scenario in {'receipt-tamper', 'fault-after-tool'} and group == 'C':
        assert 'UNKNOWN' in row['observed_states'] and row['final_state'] == 'FINALIZED_OK'
    if scenario == 'pending-finalize' and group == 'C':
        assert row['pending_original_hash'] and row['final_state'] == 'FINALIZED_OK'
    if scenario == 'normal':
        assert row['tamper_detected'] == (0 if group == 'A' else row['tamper_attempts'])
    if group != 'A':
        assert row['unauthorized_executions'] == 0


VOLUME_CODE = '''
import hashlib,json,sqlite3,sys
from pathlib import Path
from Crypto.Cipher import AES
from chainguard_gateway.central_store import CentralStore
from chainguard_gateway.crypto import commit
expected=json.load(sys.stdin)
checked=[]
for item in expected:
 root=Path(item['tool_root'])
 assert root.parent==Path('/sandbox') and root.name.startswith('test-')
 with sqlite3.connect('file:'+str(root/'state.sqlite3')+'?mode=ro',uri=True) as db:
  db.row_factory=sqlite3.Row
  mail=[dict(r) for r in db.execute('SELECT action_id,recipient,mime_sha256,mime FROM mailbox ORDER BY message_id')]
  for m in mail: assert hashlib.sha256(m.pop('mime')).hexdigest()==m['mime_sha256']
  assert mail==item['mailbox']
  assert db.execute("SELECT count(*) FROM executions WHERE state='COMPLETED'").fetchone()[0]==len(mail)
  if item['group']=='C':
   for r in db.execute('SELECT action_id,data FROM chain_mail'):
    raw=r['data']; cipher=AES.new((root/'experiment-tool.key').read_bytes(),AES.MODE_GCM,nonce=raw[:16]); cipher.update(r['action_id'].encode())
    original=json.loads(cipher.decrypt_and_verify(raw[32:],raw[16:32]))
    assert commit('result',original['result_salt'],original['result'])==original['receipt']['result_commit']
    assert commit('evidence',original['evidence_salt'],original['evidence'])==original['receipt']['evidence_index_commit']
 if item['action_id']:
  store=CentralStore(root/'gateway')
  # Use mode=ro even for the gateway; no Store.connect mutation or tool APIs.
  with sqlite3.connect('file:'+str(root/'gateway/state.sqlite3')+'?mode=ro',uri=True) as db:
   record=db.execute('SELECT data FROM actions WHERE action_id=?',(item['action_id'],)).fetchone()
   data=store.unseal('action/'+item['action_id'],record[0])
   assert data['params']==item['params']
   if data['intent']: assert commit('params',data['salt'],data['params'])==data['intent']['params_commit']
 checked.append({'group':item['group'],'sample_id':item['sample_id'],'mail_count':len(mail)})
print(json.dumps({'status':'PASS','read_only_mount':True,'sqlite_mode':'ro','cases':len(checked),'mail_count':sum(c['mail_count'] for c in checked)}))
'''


def verify(directory, docker_prefix=None, observer_image=None):
    manifest = load(directory / 'run_manifest.json')
    assert manifest['status'] == 'PASS' and manifest['track'] == 'protocol_replay'
    for name, expected in manifest.get('artifacts', {}).items():
        assert Path(name).name == name and sha((directory / name).read_bytes()) == expected
    plan = manifest['plan']
    rows = [json.loads(line) for line in (directory / 'traces.jsonl').read_text(encoding='utf8').splitlines()]
    verify_rows(plan, rows)
    verify_csv(directory / 'cases.csv', rows)
    with (directory / 'aggregated_metrics.csv').open(encoding='utf8', newline='') as stream:
        has_cohorts = 'cohort' in next(csv.reader(stream))
    verify_csv(directory / 'aggregated_metrics.csv', aggregate(rows, plan['bootstrap_replicates'], include_cohorts=has_cohorts))
    chain = Chain(manifest['deployment'], [f'http://127.0.0.1:{p}' for p in range(8545, 8549)])
    chain.nodes = [ReadOnlyRPC(node.url) for node in chain.nodes]
    chain.rpc = chain.nodes[0]
    for contract in [chain.policy, chain.execution, chain.audit]:
        contract.rpc = chain.rpc
    snapshot = chain.healthy()
    receipts, volume_cases, delivered = {}, [], 0
    for row in rows:
        assert row['status'] == 'OBSERVED'
        check_behavior(row)
        path = directory / row['evidence_file']
        assert path.parent == directory and path.name.startswith('case-')
        evidence = load(path)
        assert evidence['case'] == {k: v for k, v in row.items() if k != 'evidence_file'}
        semantic = semantic_input(plan, row)
        assert evidence['semantic_input'] == semantic
        mail = evidence['mailbox']
        assert len(mail) == row['mailbox_count'] and row['tool_executed'] == bool(mail)
        for m in mail:
            raw = base64.b64decode(m['mime_b64'], validate=True)
            assert sha(raw) == m['mime_sha256']
            message = BytesParser(policy=policy.default).parsebytes(raw)
            assert str(message['To']) == m['recipient'] == semantic['params']['to'][0]
            assert str(message['Subject']) == semantic['params']['subject']
            assert message.get_content().strip() == semantic['params']['body']
            delivered += 1
        assert row['task_completed'] == int(bool(row['task_eligible']) and len(mail) == 1 and mail[0]['recipient'] == plan['mail']['to'][0])
        record = evidence['record']
        if row['group'] in {'A', 'B'}:
            audit = evidence['audit']
            if row['group'] == 'B':
                assert verify_log(audit['entries'], audit['signer'], checkpoint=audit['checkpoint'], deployment_id=audit['deployment_id'])['status'] == 'VALID'
            else:
                assert verify_unsigned(audit['entries'])
        else:
            for transaction in evidence['transactions']:
                tx_hash = transaction['tx_hash']
                saved = []
                for node in chain.nodes:
                    receipt = node.call('eth_getTransactionReceipt', [tx_hash])
                    assert receipt and receipt['status'] == '0x1'
                    block = node.call('eth_getBlockByNumber', [receipt['blockNumber'], False])
                    assert receipt['blockHash'] == block['hash'] and tx_hash in block['transactions']
                    saved.append(receipt)
                assert all(r == saved[0] for r in saved)
                receipts[tx_hash] = saved
            if record and record['reservation_evidence']:
                intent = record['intent']
                reserve = record['reservation_evidence']
                actual, receipt, _ = chain.transaction_evidence(reserve['tx_hash'], chain.execution.address, snapshot,
                    'ActionReserved(bytes32,bytes32,bytes32,bytes32,uint64)', record['action_id'])
                assert actual == reserve
                assert recover_intent(intent, chain.domain, evidence['requester_signature']) == intent['requester']
                transaction = chain.rpc.call('eth_getTransactionByHash', [reserve['tx_hash']])
                typed, requester_signature, approvals = chain.execution.decode_input('reserve', transaction['input'])
                assert all(str(typed[target]) == str(intent[source]) for source, target in PROTOCOL['json_to_typed']['ActionIntent'].items())
                assert requester_signature == evidence['requester_signature'] and [a['signature'] for a in approvals] == evidence['approvals']
                chain.validate_authorization(intent, evidence['requester_signature'], evidence['approvals'], {'number': str(int(receipt['blockNumber'], 16))}, live=False)
                reservation = chain.execution.call('getReservation', [record['action_id']])
                assert reservation['intentHash'] == digest('ActionIntent', intent, chain.domain)
                assert chain.execution.call('usedNonce', [intent['requester'], intent['nonce']])
                if mail:
                    wire = record['receipt']
                    assert record['state'] == 'FINALIZED_OK' and reservation['status'] == 3 and evidence['tool_commitments_verified']
                    assert recover_receipt(wire, chain.receipt_domain, evidence['tool_signature']) == manifest['public_signers']['mailTool']
                    assert chain.audit.call('receiptHash', [record['action_id']]) == digest('ExecutionReceipt', wire, chain.receipt_domain)
                    final = record['finalization_evidence']
                    actual, _, _ = chain.transaction_evidence(final['tx_hash'], chain.audit.address, snapshot,
                        'ActionFinalized(bytes32,bytes32,address,uint8)', record['action_id'])
                    assert actual == final
                    tx = chain.rpc.call('eth_getTransactionByHash', [final['tx_hash']])
                    typed_receipt, signature = chain.audit.decode_input('finalize', tx['input'])
                    assert signature == evidence['tool_signature']
                    assert all(str(typed_receipt[target]) == str(wire[source]) for source, target in PROTOCOL['json_to_typed']['ExecutionReceipt'].items())
                    if row['scenario'] == 'pending-finalize':
                        assert final['tx_hash'] == row['pending_original_hash']
                else:
                    assert record['state'] == 'UNKNOWN' and reservation['status'] == 1 and record['receipt'] is None
        for tamper in evidence['tampering']:
            if row['group'] == 'C':
                wire = tamper['modified_copy']['receipt']
                detected = wire is None or digest('ExecutionReceipt', wire, chain.receipt_domain) != chain.audit.call('receiptHash', [record['action_id']])
            elif row['group'] == 'B':
                detected = verify_log(tamper['modified_copy']['entries'], audit['signer'], checkpoint=audit['checkpoint'], deployment_id=audit['deployment_id'])['status'] == 'INVALID'
            else:
                detected = not verify_unsigned(tamper['modified_copy']['entries'])
            assert tamper['detected'] == detected
        assert sum(t['detected'] for t in evidence['tampering']) == row['tamper_detected']
        volume_cases.append({'tool_root': evidence['tool_root'], 'group': row['group'], 'sample_id': row['sample_id'],
                             'action_id': record['action_id'] if record else None, 'params': semantic['params'],
                             'mailbox': [{k: v for k, v in m.items() if k != 'mime_b64'} for m in mail]})
    # A data file must never select executable commands or unrelated private volumes.
    prefix = docker_prefix or ['wsl.exe', '-d', 'Ubuntu', '-u', 'root', '--', 'docker']
    assert re.fullmatch(r'chainguard-p8-[0-9a-f]{12}', manifest['container_name'])
    assert manifest['volume'] == manifest['container_name']
    assert re.fullmatch(r'sha256:[0-9a-f]{64}', manifest['image'])
    info = json.loads(subprocess.run(prefix + ['inspect', manifest['container_name']], capture_output=True, check=True, timeout=20).stdout)[0]
    assert info['Id'] == manifest['isolation']['id']
    assert info['Image'] == manifest['image'] and info['Config']['Labels']['chainguard.phase'] == '8'
    assert len(info['Mounts']) == 1 and info['Mounts'][0]['Type'] == 'volume' and info['Mounts'][0]['Name'] == manifest['volume']
    # Operator-selected observer is independent from the original execution image.
    # Keep the recorded image/container identity intact and disclose the difference.
    image = observer_image or manifest['image']
    assert re.fullmatch(r'sha256:[0-9a-f]{64}', image)
    observer = json.loads(subprocess.run(prefix + ['image', 'inspect', image], capture_output=True, check=True, timeout=20).stdout)[0]
    assert observer['Id'] == image and observer['Config']['User'] == '10001:10001'
    check = subprocess.run(prefix + ['run', '--rm', '-i', '--network', 'none', '--read-only', '--cap-drop', 'ALL',
        '--security-opt', 'no-new-privileges:true', '--mount', 'type=volume,src=' + manifest['volume'] + ',dst=/sandbox,readonly',
        image, 'python', '-c', VOLUME_CODE], input=json.dumps(volume_cases).encode(), capture_output=True, timeout=90)
    if check.returncode:
        (directory / 'volume-verification-failure.txt').write_bytes(check.stderr)
        raise RuntimeError('Readonly volume evidence verification failed')
    volume = json.loads(check.stdout)
    assert volume['mail_count'] == delivered
    for name in ['phase0-freeze.json', 'phase3-policy-freeze.json']:
        for path, expected in load(ROOT / 'config' / name)['files'].items():
            assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == expected
    if (directory / 'tx-receipts.json').exists():
        assert load(directory / 'tx-receipts.json') == receipts
    else:
        (directory / 'tx-receipts.json').write_text(json.dumps(receipts, indent=2) + '\n', encoding='utf8')
    return {'status': 'PASS', 'recorded_at_utc': datetime.now(timezone.utc).isoformat(), 'snapshot': snapshot,
            'cases': len(rows), 'transactions': len(receipts), 'live_node_receipts': len(receipts) * 4,
            'mail_deliveries': delivered, 'volume': volume, 'statistics_recomputed': True,
            'observed_behavior_asserted': True, 'transaction_calldata_verified': True,
            'total_gas_used': sum(int(r[0]['gasUsed'], 16) for r in receipts.values()),
            'original_execution_image': manifest['image'], 'observer_image': image,
            'original_execution_image_recovered': False if observer_image else True,
            'task_data_models_matched': True, 'real_llm': 'NOT_MEASURED'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--observer-image', help='Explicit trusted local observer SHA-256; never changes the original execution manifest')
    args = parser.parse_args()
    output = args.out.resolve()
    if output.exists() or not output.is_relative_to(ROOT / 'results/phase8'):
        raise ValueError('Choose a new results/phase8 verification file')
    result = verify(args.directory.resolve(), observer_image=args.observer_image)
    output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf8')
    print(json.dumps(result))
