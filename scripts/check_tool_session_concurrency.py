"""Race two real OrgB reviews in separate business processes; no Agent or tool dispatch."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / p) for p in ['gateway/src', 'sandbox_tools/src', 'agent/src']]
from chainguard_gateway.phase10_bridge import DockerBridge
from chainguard_gateway.phase10_service import Operations
from chainguard_gateway.phase10_store import OperationsStore, PublicStore
from chainguard_gateway.session_grants import ToolPolicy
from chainguard_gateway.session_runtime import message_digest


def worker(config, work, index, cleanup=False):
    c = json.loads(config.read_text(encoding='utf8'))
    attempts = []

    class Bridge(DockerBridge):
        def call(self, kind, value):
            result = super().call(kind, value)
            if not cleanup and kind == 'security' and value.get('op') == 'sign-tool-review':
                ready = work / f'ready-{index}.json'
                if not ready.exists():
                    ready.write_text(json.dumps({'epoch': value['message']['epoch']}))
                    deadline = time.monotonic() + 45
                    while not all((work / f'ready-{i}.json').exists() for i in range(2)):
                        if time.monotonic() > deadline:
                            raise TimeoutError('Second real business signer did not arrive')
                        time.sleep(.1)
            return result

        def admission_submit(self, value):
            domain = ToolPolicy(c['tool_sessions'], ['http://127.0.0.1:8545', 'http://127.0.0.1:8547']).domain
            entry = {'digest': message_digest('ToolReview', value['message'], domain), 'epoch': value['message']['epoch']}
            attempts.append(entry)
            try:
                result = super().admission_submit(value)
                entry.update(status='CONFIRMED', evidence=result)
                return result
            except Exception as error:
                entry.update(status=getattr(error, 'code', type(error).__name__))
                raise

    store = OperationsStore(work / str(index))
    ops = Operations(store, PublicStore(work / f'public-{index}.sqlite3'), Bridge(c), c)
    if cleanup:
        item = ops.custom_registry.listing()[0]
        if item['state'] == 'ACTIVE':
            rev = item['manifest']['revision']
            ops.set_custom_active(rev, rev, False, 'LOW')
        return
    report = dict(status='RUNNING', process_id=os.getpid(), attempts=attempts)
    try:
        import secrets
        tool = ops.register_custom(dict(name='custom.race_' + secrets.token_hex(4), label='Concurrent review test',
            description='Synthetic local query only', adapter='dataset.lookup', key_field='id',
            output_fields=['id'], records=[{'id': 'A'}]))
        admitted = ops.set_custom_active(tool['revision'], tool['revision'], True, 'LOW')
        report.update(status='PASS', revision=tool['revision'], admission=admitted['admission'])
    finally:
        (work / f'worker-{index}.json').write_text(json.dumps(report, indent=2), encoding='utf8')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--worker', type=int, choices=[0, 1], help=argparse.SUPPRESS)
    p.add_argument('--cleanup', action='store_true', help=argparse.SUPPRESS)
    a = p.parse_args()
    if a.worker is not None:
        worker(a.config, a.out, a.worker, a.cleanup)
        return
    if a.out.exists() or not a.out.resolve().is_relative_to(ROOT / 'results/sessions'):
        raise ValueError('New results/sessions directory required')
    a.out.mkdir(parents=True)
    import secrets
    work = ROOT / '.local/sessions' / ('concurrency-' + secrets.token_hex(12))
    work.mkdir(parents=True)
    report = dict(status='RUNNING', private_root=str(work), real_llm=False, tool_dispatched=False)
    children, logs = [], []
    def save():
        (a.out / 'concurrency.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
    save()
    env = dict(os.environ, PYTHONUTF8='1')
    command = [sys.executable, str(Path(__file__).resolve()), '--config', str(a.config.resolve()), '--out', str(work)]
    try:
        for i in range(2):
            log = (a.out / f'worker-{i}.txt').open('wb')
            logs.append(log)
            children.append(subprocess.Popen(command + ['--worker', str(i)], cwd=ROOT, env=env,
                stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW))
        for child in children:
            assert child.wait(timeout=140) == 0, 'Real review process failed; original log retained'
        workers = [json.loads((work / f'worker-{i}.json').read_text(encoding='utf8')) for i in range(2)]
        report['workers'] = workers
        assert all(w['status'] == 'PASS' for w in workers)
        assert len({w['process_id'] for w in workers}) == 2
        assert len({json.loads((work / f'ready-{i}.json').read_text())['epoch'] for i in range(2)}) == 1
        attempts = [r for w in workers for r in w['attempts']]
        assert len(attempts) == 3
        assert sorted(r['status'] for r in attempts) == ['ADMISSION_REVIEW_REVERTED', 'CONFIRMED', 'CONFIRMED']
        c = json.loads(a.config.read_text(encoding='utf8'))
        b = DockerBridge(c)
        # Public transaction metadata only, read the relay journal with SQLite mode=ro.
        code = "import json,sys,sqlite3;from chainguard_gateway.phase6_server import load;r,c=load();d=sqlite3.connect('file:'+str(r/'state.sqlite3')+'?mode=ro',uri=True);ids=json.load(sys.stdin);print(json.dumps([d.execute('SELECT id,tx_hash FROM session_review_txs WHERE id=?',(i,)).fetchone() for i in ids]))"
        txs = json.loads(b.docker(['exec', '-i', c['containers']['gateway'], 'python', '-c', code], [r['digest'] for r in attempts]))
        policy = ToolPolicy(c['tool_sessions'], [f'http://127.0.0.1:{port}' for port in range(8545, 8549)])
        rows = []
        for digest, tx_hash in txs:
            receipts = [n.call('eth_getTransactionReceipt', [tx_hash]) for n in policy.chain.nodes]
            assert all(receipts) and all(r == receipts[0] for r in receipts)
            transactions = [n.call('eth_getTransactionByHash', [tx_hash]) for n in policy.chain.nodes]
            for node, receipt, tx in zip(policy.chain.nodes, receipts, transactions):
                block = node.call('eth_getBlockByNumber', [receipt['blockNumber'], False])
                assert block['hash'] == receipt['blockHash'] and tx_hash in block['transactions']
                assert tx['to'].lower() == c['tool_sessions']['registry']['address'].lower()
            rows.append(dict(digest=digest, tx_hash=tx_hash, nonce=int(transactions[0]['nonce'], 16),
                status=int(receipts[0]['status'], 16), node_receipts=receipts))
        assert len({row['nonce'] for row in rows}) == 3
        assert sorted(row['status'] for row in rows) == [0, 1, 1]
        report.update(status='PASS', transactions=rows, same_initial_epoch=True, distinct_durable_nonces=True,
            confirmed_revert_reapproved=True, checked_nodes=4)
        save()
    except Exception as error:
        report.update(status='FAIL', error_type=type(error).__name__)
        raise
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=10)
        for log in logs:
            log.close()
        cleanup = []
        for i in range(2):
            if (work / str(i)).exists():
                with (a.out / f'cleanup-{i}.txt').open('wb') as log:
                    result = subprocess.run(command + ['--worker', str(i), '--cleanup'], cwd=ROOT, env=env,
                        stdout=log, stderr=subprocess.STDOUT, timeout=75, creationflags=subprocess.CREATE_NO_WINDOW)
                cleanup.append(result.returncode == 0)
        report['test_tools_disabled'] = len(cleanup) == 2 and all(cleanup)
        if not report['test_tools_disabled']:
            report['status'] = 'FAIL'
        save()
    assert report['status'] == 'PASS'
    print(json.dumps(dict(status='PASS',business_processes=2,review_transactions=3,four_node_receipts=12,tool_dispatched=False)))


if __name__ == '__main__':
    main()
