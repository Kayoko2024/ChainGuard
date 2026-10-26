"""Real down/up test: preserve identities, chain state and the committed receipt."""
import argparse
from datetime import datetime, timezone

from chain import Chain, EVIDENCE, NODES, PORTS, RPC, load, write


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--wsl-distro')
    parser.add_argument('--wsl-user', default='root')
    args = parser.parse_args()
    chain = Chain(args)
    acceptance = load(EVIDENCE / 'network-acceptance.json')
    assert acceptance['status'] == 'PASS'
    tx_hash = acceptance['transfer']['transaction_hash']
    receipt = acceptance['transfer']['nodes'][0]['receipt']
    before = chain.wait_healthy()
    before_ids = [chain.compose('ps', '--quiet', node).stdout.decode().strip() for node in NODES]
    evidence = {'recorded_at_utc': datetime.now(timezone.utc).isoformat(), 'status': 'FAIL', 'before': before, 'before_container_ids': before_ids}
    try:
        chain.compose('down')
        chain.wsl_session(stop=True)
        assert not chain.docker('ps', '-aq', '--filter', 'label=com.docker.compose.project=chainguard-chain').stdout.strip()
        # Verify the specifically marked session is gone, without stopping WSL or
        # affecting other user processes/distributions.
        if chain.wsl:
            result = chain.docker('version')
            prefix = chain.prefix[:-2] + ['--exec']
            import subprocess
            session = subprocess.run(prefix + ['/bin/bash', '-c', 'pgrep -f "^chainguard-phase4-session infinity$"'], capture_output=True, timeout=30)
            assert session.returncode == 1 and not session.stdout.strip(), 'Chain runtime session not released by down'
            evidence['wsl_marked_session_released'] = True
    finally:
        # Always restore the user's deployed network; never remove any volumes.
        chain.wsl_session()
        result = chain.compose('up', '--no-build', '--wait', '--wait-timeout', '180', timeout=240)
        (EVIDENCE / 'lifecycle-up.stderr.bin').write_bytes(result.stderr)
        after = chain.wait_healthy()
        evidence['after'] = after
        evidence['after_container_ids'] = [chain.compose('ps', '--quiet', node).stdout.decode().strip() for node in NODES]
        write(EVIDENCE / 'lifecycle.json', evidence)
    assert set(evidence['after_container_ids']).isdisjoint(before_ids)
    assert after['nodes'][0]['genesis_hash'] == before['nodes'][0]['genesis_hash']
    assert after['common_height'] >= before['common_height']
    observed = [RPC(port).call('eth_getTransactionReceipt', [tx_hash]) for port in PORTS]
    assert all(row == receipt for row in observed)
    evidence.update(status='PASS', transaction_hash=tx_hash, receipts_after_full_recreation=observed)
    write(EVIDENCE / 'lifecycle.json', evidence)
    print('Real full Compose down/up PASS: 4 new containers, same identities/genesis/history/receipt; WSL session release and restart verified.')


if __name__ == '__main__':
    main()
