"""Independently validate saved real-network evidence; never manufacture results."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile
import xml.etree.ElementTree as ET

import rlp
from eth_utils import to_checksum_address

from chain import CHAIN_ID, ROOT, EVIDENCE, load, validate_receipt, write


def main():
    report = load(EVIDENCE / 'network-acceptance.json')
    deployment = load(EVIDENCE / 'deployment.json')
    genesis = load(EVIDENCE / 'genesis.json')
    if report['status'] != 'PASS':
        raise ValueError('Real network acceptance did not pass')
    assert genesis['config']['chainId'] == deployment['chain_id'] == CHAIN_ID
    assert hashlib.sha256((EVIDENCE / 'genesis.json').read_bytes()).hexdigest() == deployment['genesis_sha256']
    extra = rlp.decode(bytes.fromhex(genesis['extraData'][2:]))
    assert len(extra) == 5 and len(extra[0]) == 32
    assert sorted(to_checksum_address(v) for v in extra[1]) == sorted(deployment['validators'])
    assert len(extra[1]) == 4
    for key in ['growth', 'three_node_growth']:
        growth = report[key]
        assert growth['after']['common_height'] >= growth['before']['common_height'] + 2
        for side in ['before', 'after']:
            nodes = growth[side]['nodes']
            assert len(nodes) == (4 if key == 'growth' else 3)
            assert all(n['chain_id'] == CHAIN_ID and n['peer_count'] == len(nodes)-1 for n in nodes)
    containers = report['containers']
    assert len({row['id'] for row in containers}) == 4
    assert all(c['health'] == 'healthy' and c['user'] == '1000:1000' and c['readonly_rootfs'] for c in containers)
    for container in containers:
        assert all(binding['HostIp'] == '127.0.0.1' for bindings in container['ports'].values() if bindings for binding in bindings)
        data, = [m for m in container['mounts'] if m['Destination'] == '/var/lib/besu']
        assert data['Type'] == 'volume'
    assert report['restart']['before_started_at'] != report['restart']['after_started_at']
    assert report['restart']['same_persistent_mounts']
    assert report['receipt_after_restart'] == report['transfer']['nodes'][0]['receipt']
    lifecycle = load(EVIDENCE / 'lifecycle.json')
    assert lifecycle['status'] == 'PASS'
    assert set(lifecycle['before_container_ids']).isdisjoint(lifecycle['after_container_ids'])
    assert lifecycle['after']['nodes'][0]['genesis_hash'] == lifecycle['before']['nodes'][0]['genesis_hash']
    assert all(row == report['transfer']['nodes'][0]['receipt'] for row in lifecycle['receipts_after_full_recreation'])
    assert not report['stopped_validator']['running']
    assert len(report['restored']['nodes']) == 4
    tx = report['transfer']
    assert len(tx['nodes']) == 4 and tx['transaction']['chainId'] == CHAIN_ID
    assert tx['negative_rpc']['wrong_chain_id'] and tx['negative_rpc']['no_unlocked_accounts']
    for node in tx['nodes']:
        validate_receipt(node['receipt'], tx['transaction_hash'], tx['sender'], tx['receiver'], node['block'])
        assert int(node['balances_wei']['sender']) == int(tx['before']['sender']) - int(tx['transaction']['value'])
        assert int(node['balances_wei']['receiver']) == int(tx['before']['receiver']) + int(tx['transaction']['value'])
        assert node['sender_nonce'] == tx['before']['nonce'] + 1
        # QBFT committed block contains a quorum of commit seals. This structural
        # check does not claim independent cryptographic validation of the header.
        block_extra = rlp.decode(bytes.fromhex(node['block']['extraData'][2:]))
        assert len(block_extra) == 5 and len(block_extra[4]) >= 3
        assert all(len(seal) == 65 for seal in block_extra[4])
    suites = ET.parse(EVIDENCE / 'pytest.xml').getroot().findall('testsuite')
    assert suites and all(int(s.attrib['failures']) == 0 and int(s.attrib['errors']) == 0 and int(s.attrib['skipped']) == 0 for s in suites)
    pytest_count = sum(int(s.attrib['tests']) for s in suites)
    hardhat = (EVIDENCE / 'hardhat.txt').read_text(encoding='utf-8-sig')
    assert '41 passing' in hardhat
    # Guard against accidental export of local account keys into ANY phase4 evidence.
    private_path = ROOT / '.local/phase4/accounts.private.json'
    if private_path.exists():
        private = load(private_path)
        secrets = list(private.values())
        with tarfile.open(ROOT / '.local/phase4/generated.private.tar') as tar:
            secrets.extend(tar.extractfile(m).read().decode().strip().removeprefix('0x') for m in tar.getmembers() if m.isfile() and m.name.endswith('/key'))
        assert len(secrets) == 6
        for path in EVIDENCE.iterdir():
            if path.is_file():
                content = path.read_bytes().lower()
                assert not any(secret.lower().encode() in content for secret in secrets), 'Private key in ' + path.name
        visible = subprocess.run(['git', 'ls-files', '--cached', '--others', '--exclude-standard'], cwd=ROOT, capture_output=True, check=True).stdout.decode('utf-8').splitlines()
        assert not any(p.startswith('.local/') for p in visible)
        for name in visible:
            path = ROOT / name.strip('"')
            if path.is_file() and (name.startswith(('chain/', 'scripts/', 'docs/phase4', 'results/phase4', 'tests/python/test_phase4')) or name == 'README.md'):
                assert not any(secret.lower().encode() in path.read_bytes().lower() for secret in secrets), 'Private key in source ' + name
    source_paths = [ROOT/'README.md', *sorted((ROOT/'chain').glob('*')), *sorted((ROOT/'docs').glob('phase4-*')), *sorted((ROOT/'scripts').glob('*phase4*')), ROOT/'scripts/chain.py', ROOT/'scripts/chain.ps1', ROOT/'scripts/pull_besu_image.py', ROOT/'scripts/read_qbft_reference.py', ROOT/'tests/python/test_phase4_chain.py']
    source_manifest = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths if p.is_file()}
    write(EVIDENCE / 'source-manifest.json', source_manifest)
    receipt = tx['nodes'][0]['receipt']
    write(EVIDENCE / 'transaction-receipt.json', receipt)
    summary = {'acceptance': 'PHASE4_REAL_FOUR_VALIDATOR_QBFT_PASS', 'recorded_at_utc': datetime.now(timezone.utc).isoformat(), 'chain_id': CHAIN_ID, 'chain_id_hex': hex(CHAIN_ID), 'pytest_passed': pytest_count, 'hardhat_passed': 41, 'height_interval': [report['growth']['before']['common_height'], report['growth']['after']['common_height']], 'three_validator_height_interval': [report['three_node_growth']['before']['common_height'], report['three_node_growth']['after']['common_height']], 'transaction_hash': tx['transaction_hash'], 'receipt_status': receipt['status'], 'receipt_block_number': int(receipt['blockNumber'], 16), 'receipt_block_hash': receipt['blockHash'], 'gas_used': int(receipt['gasUsed'], 16), 'committed_seals_in_transfer_block': len(rlp.decode(bytes.fromhex(tx['nodes'][0]['block']['extraData'][2:]))[4]), 'network_left_running': True, 'contracts_deployed': False, 'evidence_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(EVIDENCE.iterdir()) if p.is_file() and p.name != 'summary.json'}}
    write(EVIDENCE / 'summary.json', summary)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
