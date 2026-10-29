"""Read-only independent model-run evidence, four-node and original-volume checks."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'gateway/src'), str(ROOT / 'sandbox_tools/src')]
from verify_phase8 import ReadOnlyRPC, VOLUME_CODE, verify_csv
from chainguard_gateway.chain_rpc import Chain
from chainguard_gateway.chain_crypto import digest, recover_receipt
from chainguard_gateway.crypto import PROTOCOL, recover_intent
from chainguard_gateway.audit import verify_log
from evaluation.replay import verify_unsigned
from evaluation.live_results import messages, observations, judged_rows, live_metrics
from evaluation.live_plan import schedule as live_schedule, make_case, rule_for


def load(path):
    return json.loads(path.read_text(encoding='utf8'))


def observer_for(prefix, execution_image, observer_image=None):
    """An operator may explicitly pin a read-only observer; never fall back silently."""
    image = execution_image if observer_image is None else observer_image
    if not isinstance(image, str) or not re.fullmatch(r'sha256:[0-9a-f]{64}', image):
        raise ValueError('Observer must be an explicit full SHA-256 image ID')
    inspected = json.loads(subprocess.run(prefix + ['image', 'inspect', image],
        capture_output=True, check=True, timeout=20).stdout)[0]
    if inspected['Id'] != image or inspected['Config']['User'] != '10001:10001':
        raise ValueError('Observer identity or non-root user mismatch')
    return image


def verify(directory, observer_image=None):
    manifest = load(directory / 'run_manifest.json')
    assert manifest['track'] == 'real_llm'
    for name, expected in manifest.get('artifacts', {}).items():
        assert Path(name).name == name and hashlib.sha256((directory/name).read_bytes()).hexdigest() == expected
    cases = [load(p) for p in sorted(directory.glob('live-case-*.json'))]
    assert len(cases) == len(manifest['schedule']) == manifest['case_count']
    if manifest.get('schedule_version') == 2:
        assert manifest['schedule'] == live_schedule(manifest['plan'], manifest['groups'])
    chain = Chain(manifest['deployment'], [f'http://127.0.0.1:{p}' for p in range(8545, 8549)])
    chain.nodes = [ReadOnlyRPC(node.url) for node in chain.nodes]
    chain.rpc = chain.nodes[0]
    for contract in [chain.policy, chain.execution, chain.audit]:
        contract.rpc = chain.rpc
    snapshot = chain.healthy()
    receipts, volume_cases, delivered, reads, pairs = {}, [], 0, 0, {}
    for case, scheduled in zip(cases, manifest['schedule'], strict=True):
        row, evidence = case['row'], case['evidence']
        if manifest.get('schedule_version') == 2:
            assert all(row[k] == scheduled[k] for k in ['scenario', 'group', 'sample_id'])
            assert evidence['case'] == make_case(manifest['plan'], scheduled, load(ROOT / 'agent/fixtures/acceptance.json'))
        else:
            assert [row['scenario'], row['group']] == scheduled
        assert row['status'] in ({'OBSERVED', 'ERROR'} if manifest.get('schedule_version') == 2 else {'OBSERVED'})
        semantic = {k: v for k, v in evidence['case'].items() if k != 'group'}
        assert hashlib.sha256(json.dumps(semantic, sort_keys=True).encode()).hexdigest() == row['input_sha256']
        key = row['sample_id']
        assert pairs.setdefault(key, row['input_sha256']) == row['input_sha256']
        observed = observations(case['events'], case['model_exchanges'], evidence,
                                rule_for(evidence['case']) or manifest['plan']['authorized_mail'])
        for name, value in observed.items():
            if name in row:
                assert row[name] == value
        assert all(e['request']['model'] == manifest['plan']['model'] for e in case['model_exchanges'])
        for exchange in case['model_exchanges']:
            assert all(exchange['request'][k] == v for k, v in manifest['plan']['parameters'].items())
            assert exchange['request']['parallel_tool_calls'] is False
        actual = messages(evidence)
        assert len(actual) == row['mailbox_count']
        delivered += len(actual)
        reads += observed['read_count']
        if not row.get('error_code'):
            assert observed['read_count'] >= 1, 'Model must actually observe the injected source'
        assert evidence['deletes'] == 0
        if row['group'] in {'A','B'}:
            audit = evidence['audit']
            if row['group'] == 'B':
                assert verify_log(audit['entries'], audit['signer'], checkpoint=audit['checkpoint'], deployment_id=audit['deployment_id'])['status'] == 'VALID'
            else:
                assert verify_unsigned(audit['entries'])
        else:
            for tx in evidence['transactions']:
                saved = []
                for node in chain.nodes:
                    receipt = node.call('eth_getTransactionReceipt', [tx['tx_hash']])
                    assert receipt and receipt['status'] == '0x1'
                    block = node.call('eth_getBlockByNumber', [receipt['blockNumber'], False])
                    assert block['hash'] == receipt['blockHash'] and tx['tx_hash'] in block['transactions']
                    saved.append(receipt)
                assert all(r == saved[0] for r in saved)
                receipts[tx['tx_hash']] = saved
            for action in evidence['action_evidence']:
                record = action['record']
                if not record['reservation_evidence']:
                    continue
                reserve, intent = record['reservation_evidence'], record['intent']
                actual_reserve, receipt, _ = chain.transaction_evidence(reserve['tx_hash'], chain.execution.address, snapshot,
                    'ActionReserved(bytes32,bytes32,bytes32,bytes32,uint64)', record['action_id'])
                assert actual_reserve == reserve
                assert recover_intent(intent, chain.domain, action['requester_signature']) == intent['requester']
                tx = chain.rpc.call('eth_getTransactionByHash', [reserve['tx_hash']])
                typed, signature, approvals = chain.execution.decode_input('reserve', tx['input'])
                assert all(str(typed[target]) == str(intent[source]) for source, target in PROTOCOL['json_to_typed']['ActionIntent'].items())
                assert signature == action['requester_signature'] and [a['signature'] for a in approvals] == action['approvals']
                chain.validate_authorization(intent, signature, action['approvals'], {'number': str(int(receipt['blockNumber'],16))}, live=False)
                reservation = chain.execution.call('getReservation', [record['action_id']])
                assert reservation['intentHash'] == digest('ActionIntent', intent, chain.domain)
                assert chain.execution.call('usedNonce', [intent['requester'], intent['nonce']])
                if any(m['action_id'] == record['action_id'] for m in actual):
                    wire = record['receipt']
                    assert record['state'] == 'FINALIZED_OK' and reservation['status'] == 3
                    assert recover_receipt(wire, chain.receipt_domain, action['tool_signature']) == manifest['public_signers']['mailTool']
                    assert chain.audit.call('receiptHash', [record['action_id']]) == digest('ExecutionReceipt', wire, chain.receipt_domain)
                    final = record['finalization_evidence']
                    check, _, _ = chain.transaction_evidence(final['tx_hash'], chain.audit.address, snapshot,
                        'ActionFinalized(bytes32,bytes32,address,uint8)', record['action_id'])
                    assert check == final
                    final_tx = chain.rpc.call('eth_getTransactionByHash', [final['tx_hash']])
                    typed_receipt, tool_signature = chain.audit.decode_input('finalize', final_tx['input'])
                    assert tool_signature == action['tool_signature']
                    assert all(str(typed_receipt[target]) == str(wire[source]) for source, target in PROTOCOL['json_to_typed']['ExecutionReceipt'].items())
        action = evidence['action_evidence'][0] if evidence['action_evidence'] else None
        volume_cases.append(dict(tool_root=evidence['tool_root'], group=row['group'], sample_id=row['sample_id'],
            action_id=action['record']['action_id'] if action else None, params=action['params'] if action else None,
            mailbox=[{k:v for k,v in m.items() if k != 'mime_b64'} for m in evidence['mailbox']],
            reads=evidence['reads'], document=evidence['case']['document']))
    prefix = ['wsl.exe','-d','Ubuntu','-u','root','--','docker']
    assert re.fullmatch(r'chainguard-live-[0-9a-f]{12}', manifest['container_name'])
    assert manifest['volume'] == manifest['container_name'] and re.fullmatch(r'sha256:[0-9a-f]{64}', manifest['image'])
    info = json.loads(subprocess.run(prefix + ['inspect',manifest['container_name']],capture_output=True,check=True,timeout=20).stdout)[0]
    assert info['Id'] == manifest['isolation']['id'] and info['Image'] == manifest['image']
    assert info['Config']['Labels']['chainguard.phase'] == '8-live' and info['Config']['User'] == '10001:10001'
    assert len(info['Mounts']) == 1 and info['Mounts'][0]['Name'] == manifest['volume'] and info['Mounts'][0]['Type'] == 'volume'
    image = observer_for(prefix, manifest['image'], observer_image)
    code = VOLUME_CODE.replace("WHERE state='COMPLETED'", "WHERE state='COMPLETED' AND tool_name='mail.send'")
    extra = """
 with sqlite3.connect('file:'+str(root/'state.sqlite3')+'?mode=ro',uri=True) as reads_db:
  reads_db.row_factory=sqlite3.Row
  assert [dict(r) for r in reads_db.execute("SELECT action_id,state FROM executions WHERE tool_name='doc.read'")]==item['reads']
  assert all(r['state']=='COMPLETED' for r in item['reads'])
  assert reads_db.execute("SELECT count(*) FROM executions WHERE tool_name='doc.delete'").fetchone()[0]==0
  stored=reads_db.execute('SELECT filename FROM documents WHERE doc_id=?',(item['document']['doc_id'],)).fetchone()
  assert stored and re.fullmatch('[0-9a-f]{48}\\.test',stored['filename'])
  content=(root/'documents'/stored['filename']).read_bytes()
  assert content==item['document']['content'].encode()
"""
    code = 'import re\n' + code.replace(" checked.append(", extra + " checked.append(")
    result = subprocess.run(prefix + ['run','--rm','-i','--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true',
        '--mount','type=volume,src='+manifest['volume']+',dst=/sandbox,readonly',image,'python','-c',code],input=json.dumps(volume_cases).encode(),capture_output=True,timeout=90)
    if result.returncode:
        (directory/'volume-verification-failure.txt').write_bytes(result.stderr)
        raise RuntimeError('Readonly volume verification failed')
    volume = json.loads(result.stdout)
    assert volume['mail_count'] == delivered
    statistics_verified = False
    if (directory/'official-judgements.json').exists():
        judgments = load(directory/'official-judgements.json')
        rows = judged_rows(cases, judgments)
        assert rows == [json.loads(line) for line in (directory/'traces.jsonl').read_text(encoding='utf8').splitlines()]
        verify_csv(directory/'cases.csv', rows)
        verify_csv(directory/'aggregated_metrics.csv', live_metrics(rows,manifest['plan']['bootstrap_replicates']))
        statistics_verified = True
    for name in ['phase0-freeze.json','phase3-policy-freeze.json']:
        for path, expected in load(ROOT/'config'/name)['files'].items():
            assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest() == expected
    if (directory/'tx-receipts.json').exists():
        assert load(directory/'tx-receipts.json') == receipts
    else:
        (directory/'tx-receipts.json').write_text(json.dumps(receipts,indent=2)+'\n',encoding='utf8')
    return dict(status='PASS', cases=len(cases), mail_deliveries=delivered, real_reads=reads,
        transactions=len(receipts), four_node_receipts=4*len(receipts), snapshot=snapshot, volume=volume, statistics_recomputed=statistics_verified,
        original_execution_image=manifest['image'], observer_image=image,
        original_execution_image_recovered=image == manifest['image'])


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--observer-image',help='Explicit trusted local observer SHA-256; leaves the original execution manifest unchanged')
    args=parser.parse_args()
    if args.out.exists():
        raise ValueError('Choose a new verification output file')
    args.out.write_text(json.dumps(verify(args.directory.resolve(), observer_image=args.observer_image),indent=2)+'\n',encoding='utf8')
