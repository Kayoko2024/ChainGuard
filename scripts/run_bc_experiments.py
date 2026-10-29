"""One command for new, isolated B/C mechanism interventions and verification.

Does not call an LLM, mutate existing governance, pause validators, or touch UI
volumes. Keys enter only the fresh private Docker volume over stdin.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import io
import inspect
import json
from pathlib import Path
import secrets
import subprocess
import sys
import tarfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'gateway/src'), str(ROOT / 'sandbox_tools/src')]
from eth_account import Account
from chainguard_gateway.chain_rpc import Chain, RPC, Contract
from chainguard_gateway.chain_crypto import recover_receipt, digest
from chainguard_gateway.crypto import PROTOCOL, recover_intent
from chainguard_gateway.audit import verify_log
from evaluation.bc_live import validate_plan, schedule, export, volume_verify, recover_chain_metadata, verify_observation
from run_phase8 import build_context


def dump(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf8')


def build_archive():
    original, names = build_context()
    extras = ['spec/phase5/governance.json'] + [f'artifacts/contracts/{n}.sol/{n}.json' for n in ['PolicyRegistry', 'ExecutionRegistry', 'AuditRegistry']]
    out = io.BytesIO()
    with tarfile.open(fileobj=io.BytesIO(original)) as source, tarfile.open(fileobj=out, mode='w') as target:
        for member in source:
            target.addfile(member, source.extractfile(member))
        for name in extras:
            if name not in names:
                data = (ROOT / name).read_bytes()
                member = tarfile.TarInfo(name)
                member.size, member.mode, member.mtime = len(data), 0o644, 0
                target.addfile(member, io.BytesIO(data))
    return out.getvalue(), sorted(set(names + extras))


def verify(out, docker, image, volume, plan, write_out=None):
    from evaluation.bc_live import metrics
    destination = write_out or out
    rows = [json.loads(line) for line in (out / 'traces.jsonl').read_text().splitlines()]
    metrics(rows, plan)
    assert all(not r['error'] for r in rows)
    cases = [json.loads((out / r['evidence_file']).read_text()) for r in rows]
    deployment = json.loads((out / 'deployment.json').read_text())
    chain = Chain(deployment, [f'http://127.0.0.1:{p}' for p in range(8545, 8549)])
    chain.healthy()
    hashes, signatures = set(), 0
    for row, case in zip(rows, cases):
        verify_observation(row, case['observation'])
        parts = [case['primary']] + case['replicas']
        count = sum(len(p['mailbox']) for p in parts) + len(case['intervention'].get('split_tool_mailbox', []))
        assert count == row['mailbox_count']
        for part in parts:
            for item in part.get('transactions', []):
                hashes.add(item['tx_hash'])
            if row['group'] == 'B':
                a = part['audit']
                assert verify_log(a['entries'], a['signer'], checkpoint=a['checkpoint'], deployment_id=a['deployment_id'])['status'] == 'VALID'
            elif part['record'] and part['record'].get('receipt'):
                record = part['record']
                signer = recover_receipt(record['receipt'], chain.receipt_domain, part['tool_signature'])
                assert signer == chain.audit.call('receiptSigner', [record['action_id']])
                assert digest('ExecutionReceipt', record['receipt'], chain.receipt_domain) == chain.audit.call('receiptHash', [record['action_id']])
                signatures += 1
        if row['scenario'] == 'directory-takeover':
            if row['group'] == 'B':
                assert row['unauthorized_expansion'] and count == 1
                assert not case['intervention']['directory_substitution']['honest_approval_keys_used']
            else:
                assert not row['unauthorized_expansion'] and count == 0
                assert len(case['intervention']['approval_rejections']) == 2
        if row['scenario'] in {'shared-state-race', 'split-state-race', 'split-tool-delivery'}:
            assert row['duplicate_effect'] == (count > 1)
        if row['scenario'] == 'shared-state-race':
            assert count == 1
        if row['scenario'] == 'history-withheld':
            assert row['history_detected']
            if row['group'] == 'B':
                assert not row['metadata_recovered'] and row['full_replica_recovered']
            else:
                recovered = recover_chain_metadata(chain, row['action_id'])
                assert recovered == case['intervention']['recovered_public_metadata']
        if row['scenario'] in {'dependency-outage', 'one-rpc-outage'}:
            assert case['intervention']['mail_before_recovery'] == 0
            assert count == 1 and row['recovered_after_outage']
    for item in json.loads((out / 'setup-transactions.json').read_text()):
        hashes.add(item['tx_hash'])
    receipts = []
    for h in sorted(hashes):
        nodes = [n.call('eth_getTransactionReceipt', [h]) for n in chain.nodes]
        assert all(nodes) and all(r == nodes[0] for r in nodes)
        tx = chain.rpc.call('eth_getTransactionByHash', [h])
        for node, receipt in zip(chain.nodes, nodes):
            block = node.call('eth_getBlockByNumber', [receipt['blockNumber'], False])
            assert block['hash'] == receipt['blockHash'] and h in block['transactions']
        if tx['to'] == chain.audit.address and nodes[0]['status'] == '0x1':
            wire, sig = chain.audit.decode_input('finalize', tx['input'])
            receipt = {s: str(wire[t]) if isinstance(wire[t], int) and t not in {'schemaVersion', 'outcome'} else wire[t]
                       for s, t in PROTOCOL['json_to_typed']['ExecutionReceipt'].items()}
            assert recover_receipt(receipt, chain.receipt_domain, sig) == chain.audit.call('receiptSigner', [receipt['action_id']])
            assert digest('ExecutionReceipt', receipt, chain.receipt_domain) == chain.audit.call('receiptHash', [receipt['action_id']])
        if tx['to'] == chain.execution.address and nodes[0]['status'] == '0x1':
            wire, requester_sig, approvals = chain.execution.decode_input('reserve', tx['input'])
            intent = {s: str(wire[t]) if isinstance(wire[t], int) and t not in {'schemaVersion', 'risk'} else wire[t]
                      for s, t in PROTOCOL['json_to_typed']['ActionIntent'].items()}
            assert recover_intent(intent, chain.domain, requester_sig) == intent['requester']
            original = chain.execution.call('getReservation', [intent['action_id']])
            assert original['intentHash'] == digest('ActionIntent', intent, chain.domain)
            assert original['approvers'] == [recover_intent(intent, chain.domain, a['signature']) for a in approvals]
            assert chain.execution.call('usedNonce', [intent['requester'], intent['nonce']])
            block = chain.rpc.call('eth_getBlockByNumber', [nodes[0]['blockNumber'], False])
            chain.validate_authorization(intent, requester_sig, [a['signature'] for a in approvals],
                dict(number=str(int(nodes[0]['blockNumber'], 16)), timestamp=str(int(block['timestamp'], 16))), live=False)
        receipts.append(dict(tx_hash=h, nodes=nodes))
    dump(destination / 'tx-receipts.json', receipts)
    # Pin execution dependencies to the original image; transmit this observer's
    # pure readonly verification source explicitly. No source/image replacement
    # is implied, and no original evidence file is edited.
    code = ('import json,sys,sqlite3,hashlib\nfrom pathlib import Path\n'
            'from chainguard_gateway.central_store import CentralStore\n'
            'from chainguard_gateway.chain_crypto import digest\n' + inspect.getsource(volume_verify) +
            '\nprint(json.dumps(volume_verify(json.load(sys.stdin))))\n')
    dump(destination / 'observer-source.json', dict(sha256=hashlib.sha256(code.encode()).hexdigest(), source=code))
    raw = docker('run', '--rm', '-i', '--network', 'none', '--read-only', '--cap-drop', 'ALL',
        '--security-opt', 'no-new-privileges:true', '--mount', f'type=volume,src={volume},dst=/sandbox,readonly',
        image, 'python', '-c', code, data=json.dumps(cases).encode())
    volume_result = json.loads(raw)
    unanchored = []
    for sig in volume_result['tool_signatures']:
        assert sig['signer'] == chain.audit.call('receiptSigner', [sig['action_id']])
        if sig['digest'] != chain.audit.call('receiptHash', [sig['action_id']]):
            # A second independent tool store can produce another valid signed
            # effect. One anchored receipt cannot prove absence of that effect.
            unanchored.append(sig)
    volume_result['extra_signed_receipts_not_anchored'] = unanchored
    dump(destination / 'volume-verification.json', volume_result)
    return dict(status='PASS', cases=len(rows), mail_count=volume_result['mail_count'],
                transactions=len(receipts), node_receipts=len(receipts) * 4, signed_finalized_records=signatures,
                b_exact_double_approval_checks=volume_result['b_exact_double_approval_checks'],
                independent_tool_signature_checks=len(volume_result['tool_signatures']),
                extra_signed_receipts_not_anchored=len(unanchored),
                independently_read_original_volume=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--verify-source', type=Path, help='Only reverify retained real evidence/volume in a new directory; no reexecution')
    args = parser.parse_args()
    out = args.out.resolve()
    if out.exists() or not out.is_relative_to(ROOT / 'results/phase8'):
        raise ValueError('Choose a NEW results/phase8 directory')
    out.mkdir(parents=True)
    prefix = ['wsl.exe', '-d', 'Ubuntu', '-u', 'root', '--', 'docker']
    name = 'chainguard-bc-' + secrets.token_hex(6)
    image = 'chainguard/bc-lab:' + name.rsplit('-', 1)[-1]
    manifest = dict(status='RUNNING', started_at_utc=datetime.now(timezone.utc).isoformat(),
                    container_name=name, volume=name, llm_samples=0, ASR='NOT_MEASURED')
    def save():
        dump(out / 'run_manifest.json', manifest)
    def docker(*command, data=None, timeout=180):
        r = subprocess.run(prefix + list(command), input=data, capture_output=True, timeout=timeout)
        if r.returncode:
            # Diagnostics contain no stdin/private config; never print raw command/config.
            (out / 'docker-error.txt').write_bytes(r.stderr)
            raise RuntimeError('Docker command failed; see retained docker-error.txt')
        return r.stdout
    created = False
    try:
        if args.verify_source:
            source = args.verify_source.resolve()
            old = json.loads((source / 'run_manifest.json').read_text())
            plan = validate_plan(old['plan'])
            original_hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir() if p.is_file()}
            manifest.update(track='readonly_reverification', source_directory=str(source), source_status=old['status'],
                model_or_tool_reexecuted=False, sources=original_hashes, observer_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                observer_module_sha256=hashlib.sha256((ROOT / 'evaluation/bc_live.py').read_bytes()).hexdigest())
            save()
            result = verify(source, docker, old['image'], old['volume'], plan, out)
            rows = [json.loads(line) for line in (source / 'traces.jsonl').read_text().splitlines()]
            export(out, rows, plan)
            # Keep the four standard artifacts together; these are byte-identical
            # trace copies, not a second experiment or newly created samples.
            (out / 'traces.jsonl').write_bytes((source / 'traces.jsonl').read_bytes())
            assert original_hashes == {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir() if p.is_file()}
            dump(out / 'verification.json', result)
            manifest.update(status='PASS', verification=result, source_files_unchanged=True,
                finished_at_utc=datetime.now(timezone.utc).isoformat(), artifacts={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file() and p.name != 'run_manifest.json'})
            save()
            print(json.dumps(result))
            return
        plan = validate_plan(json.loads((ROOT / 'evaluation/bc_live_plan.json').read_text()))
        manifest.update(plan=plan, schedule=schedule(plan), plan_sha256=hashlib.sha256((ROOT / 'evaluation/bc_live_plan.json').read_bytes()).hexdigest(),
            observer_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            observer_module_sha256=hashlib.sha256((ROOT / 'evaluation/bc_live.py').read_bytes()).hexdigest(),
            status_meaning='PASS means executed and independently verified evidence, not all attacks blocked',
            scope='R2 sandbox mechanism interventions; no LLM or new ASR; same-host existing four validators, new registry addresses',
            untested=['actual validator shutdown/chain halt', 'independent organizations/hosts',
                      'production B+ multi-party directory governance', 'full validator ledger storage cost'])
        original = json.loads((ROOT / '.local/phase10/20261026T123255815352Z/runtime.json').read_text())['deployment']
        current = Chain(original, [f'http://127.0.0.1:{p}' for p in range(8545, 8549)])
        manifest['before'] = current.healthy()
        manifest['original_governance_before'] = dict(epoch=current.policy.call('governanceEpoch'), paused=current.policy.call('paused'))
        names = ['govA', 'govB', 'requester', 'agent', 'biz', 'security', 'mailTool', 'executor', 'auditor', 'rogue_biz', 'rogue_security']
        keys = {n: Account.create().key.hex() for n in names}
        relay_key, relay2_key = Account.create().key.hex(), Account.create().key.hex()
        signers = {n: Account.from_key(k).address.lower() for n, k in keys.items()}
        manifest['public_signers'] = signers
        # Besu's configured zero gas price permits new test EOAs with zero balance.
        # No original account/private key is used or changed by this experiment.
        config = dict(deployment=original, signers=signers, signing_keys=keys,
                      relay_key=relay_key, relay2_key=relay2_key, tool_key=keys['mailTool'])
        archive, files = build_archive()
        manifest['build_context'] = dict(sha256=hashlib.sha256(archive).hexdigest(), files=files)
        manifest['core_sources'] = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for folder in ['gateway/src', 'sandbox_tools/src', 'contracts', 'spec'] for p in (ROOT / folder).rglob('*')
            if p.is_file() and p.suffix in {'.py', '.sol', '.json'}}
        save()
        with (out / 'build.txt').open('wb') as f:
            result = subprocess.run(prefix + ['build', '--network', 'none', '-f', 'evaluation/phase8.Dockerfile', '-t', image, '-'],
                                    input=archive, stdout=f, stderr=subprocess.STDOUT, timeout=300)
        if result.returncode:
            raise RuntimeError('Offline image build failed')
        manifest['image'] = json.loads(docker('image', 'inspect', image))[0]['Id']
        image = manifest['image']
        docker('volume', 'create', '--label', 'chainguard.experiment=bc', name)
        mount = f'type=volume,src={name},dst=/sandbox'
        docker('run', '--rm', '--network', 'none', '--user', '0:0', '--read-only', '--mount', mount, image,
               'python', '-c', 'import os;os.chown("/sandbox",10001,10001);os.chmod("/sandbox",0o700)')
        docker('run', '--rm', '-i', '--network', 'none', '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges:true',
               '--mount', mount, image, 'python', '-c',
               'import os,sys;f=os.open("/sandbox/experiment.private.json",os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.write(f,sys.stdin.buffer.read());os.close(f)',
               data=json.dumps(config).encode())
        docker('create', '--name', name, '--label', 'chainguard.experiment=bc', '--read-only', '--network', 'chainguard_qbft',
               '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges:true', '--pids-limit', '128', '--memory', '768m', '--cpus', '2',
               '--tmpfs', '/tmp:rw,noexec,nosuid,size=32m', '--mount', mount, image, 'python', '-m', 'evaluation.bc_live')
        created = True
        inspect = json.loads(docker('inspect', name))[0]
        manifest['isolation'] = {k: inspect['HostConfig'][k] for k in ['ReadonlyRootfs', 'CapDrop', 'SecurityOpt', 'PortBindings']}
        manifest['isolation'].update(user=inspect['Config']['User'], mounts=inspect['Mounts'], networks=list(inspect['NetworkSettings']['Networks']))
        assert inspect['Config']['User'] == '10001:10001' and inspect['HostConfig']['ReadonlyRootfs']
        assert all(m['Type'] == 'volume' for m in inspect['Mounts']) and not inspect['HostConfig']['PortBindings']
        save()
        print('Running ' + str(len(manifest['schedule'])) + ' actual observations in fresh isolated registries/volume', flush=True)
        with (out / 'execution.txt').open('wb') as f:
            process = subprocess.Popen(prefix + ['start', '-a', name], stdout=f, stderr=subprocess.STDOUT)
            deadline = time.monotonic() + 1200
            while process.poll() is None:
                if time.monotonic() > deadline:
                    docker('stop', '--time', '5', name)
                    raise TimeoutError('Evidence retained; never blindly redispatch')
                time.sleep(1)
        manifest['container_exit'] = json.loads(docker('inspect', name))[0]['State']['ExitCode']
        data = docker('cp', name + ':/sandbox/public/.', '-')
        with tarfile.open(fileobj=io.BytesIO(data)) as tar:
            for member in tar:
                if member.isfile() and Path(member.name).name == member.name.removeprefix('./'):
                    (out / Path(member.name).name).write_bytes(tar.extractfile(member).read())
        if process.returncode or manifest['container_exit']:
            raise RuntimeError('Actual experiment stopped on failure; original observations retained')
        rows = [json.loads(line) for line in (out / 'traces.jsonl').read_text().splitlines()]
        export(out, rows, plan)
        result = verify(out, docker, image, name, plan)
        dump(out / 'verification.json', result)
        manifest['verification'] = result
        manifest['original_governance_after'] = dict(epoch=current.policy.call('governanceEpoch'), paused=current.policy.call('paused'))
        assert manifest['original_governance_before'] == manifest['original_governance_after']
        assert all(hashlib.sha256((ROOT / p).read_bytes()).hexdigest() == h for p, h in manifest['core_sources'].items())
        manifest.update(status='PASS', finished_at_utc=datetime.now(timezone.utc).isoformat(), after=current.healthy())
        manifest['artifacts'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file() and p.name != 'run_manifest.json'}
        save()
        print(json.dumps(result), flush=True)
    except Exception as e:
        manifest.update(status='FAIL', failure=type(e).__name__ + ': ' + str(e), finished_at_utc=datetime.now(timezone.utc).isoformat())
        save()
        raise
    finally:
        if created:
            docker('stop', '--time', '5', name)


if __name__ == '__main__':
    main()
