"""One command: real restricted A/B/C protocol replay, evidence verification, statistics.

Requires the existing stage5 Besu deployment, local signer files and cached wheels.
Never resets the chain, deletes volumes or falls back to host side effects.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import secrets
import subprocess
import sys
import tarfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'gateway/src'), str(ROOT / 'sandbox_tools/src')]
from chain import Chain as Operations, RPC
from run_phase6 import find_signers
from run_phase3_container import context_archive
from evaluation.metrics import export
from evaluation.replay import schedule, validate_plan
from eth_account import Account

IMAGE = 'chainguard/protocol-lab:0.8.0'


def load(path):
    return json.loads(path.read_text(encoding='utf8'))


def dump(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf8')


def hash_sources():
    paths = []
    for folder in ['evaluation', 'gateway/src', 'sandbox_tools/src', 'agent/src', 'contracts', 'scripts']:
        paths.extend(p for p in (ROOT / folder).rglob('*') if p.is_file() and p.suffix in {'.py', '.sol', '.json', '.cjs', '.md'} and '__pycache__' not in p.parts)
    paths += [ROOT / p for p in ['package-lock.json', 'requirements-dev.lock', 'gateway/central-test.lock',
                               'chain/compose.yaml', 'chain/genesis-template.json', 'chain/image.lock.json', 'evaluation/phase8.Dockerfile']]
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(set(paths))}


def build_context():
    original, names = context_archive()
    extras = {p.relative_to(ROOT).as_posix() for p in (ROOT / 'evaluation').rglob('*')
              if p.is_file() and p.suffix in {'.py', '.json'} and '__pycache__' not in p.parts}
    extras.add('evaluation/phase8.Dockerfile')
    extras.update('results/phase5/besu-run-01/' + name + '.abi.json' for name in ['PolicyRegistry', 'ExecutionRegistry', 'AuditRegistry'])
    stream = io.BytesIO()
    with tarfile.open(fileobj=io.BytesIO(original)) as source, tarfile.open(fileobj=stream, mode='w') as target:
        for item in source:
            target.addfile(item, source.extractfile(item))
        for name in sorted(extras - set(names)):
            data = (ROOT / name).read_bytes()
            item = tarfile.TarInfo(name)
            item.size, item.mode, item.mtime = len(data), 0o644, 0
            target.addfile(item, io.BytesIO(data))
    return stream.getvalue(), sorted(set(names) | extras)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--wsl-distro', default='Ubuntu')
    parser.add_argument('--track', choices=['protocol_replay', 'real_llm'], default='protocol_replay')
    args = parser.parse_args()
    if args.track != 'protocol_replay':
        command=[sys.executable,str(ROOT/'scripts/run_real_experiments.py')]
        if args.out:
            command.extend(['--out',str(args.out)])
        raise SystemExit(subprocess.run(command,cwd=ROOT).returncode)
    plan = validate_plan(load(ROOT / 'evaluation/phase8_plan.json'))
    output = (args.out or ROOT / 'results/phase8/runs' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')).resolve()
    if output.exists() or not output.is_relative_to(ROOT / 'results/phase8'):
        raise ValueError('Choose a NEW results/phase8 subdirectory')
    output.mkdir(parents=True)
    prefix = ['wsl.exe', '-d', args.wsl_distro, '-u', 'root', '--', 'docker']
    lab = 'chainguard-p8-' + secrets.token_hex(6)
    manifest = {'status': 'RUNNING', 'track': 'protocol_replay', 'formal_llm_experiment_complete': False,
                'started_at_utc': datetime.now(timezone.utc).isoformat(), 'plan': plan, 'schedule': schedule(plan),
                'plan_sha256': hashlib.sha256((ROOT / 'evaluation/phase8_plan.json').read_bytes()).hexdigest(),
                'sources': hash_sources(), 'model': plan['model'], 'llm_sample_count': 0,
                'container_name': lab, 'volume': lab, 'docker_prefix': prefix,
                'scope': plan['latency_scope'], 'public_signers': {},
                'reproduce': '& ./.venv/Scripts/python.exe scripts/run_phase8.py',
                'limitations': ['No real LLM/ASR; phase7 prerequisite incomplete',
                    'R2 mail only; local SQLite atomic mailbox; same-host four validators and trusted test signers',
                    'Service-layer integration; no HTTP/mTLS/model latency or process-isolation claim',
                    'A uses frozen task policy in shadow; B/C enforce it',
                    'Scenario-cluster resampling; small exploratory tails; no population zero-risk claim']}
    def docker(*command, data=None, timeout=60):
        result = subprocess.run(prefix + list(command), input=data, capture_output=True, timeout=timeout)
        if result.returncode:
            # Docker diagnostics contain no stdin/config data. Avoid dumping keys or raw transactions.
            (output / 'docker-error.txt').write_bytes(result.stderr)
            raise RuntimeError('Docker ' + command[0] + ' failed; see docker-error.txt')
        return result.stdout
    created = False
    try:
        for filename in ['phase0-freeze.json', 'phase3-policy-freeze.json']:
            for name, expected in load(ROOT / 'config' / filename)['files'].items():
                if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
                    raise RuntimeError('Frozen source drift: ' + name)
        ops = Operations(argparse.Namespace(wsl_distro=args.wsl_distro, wsl_user='root'))
        ops.wsl_session()
        manifest['before'] = ops.wait_healthy()
        phase5 = load(ROOT / 'results/phase5/besu-run-01/report.json')
        deployment = {'chainId': 20261026, 'contracts': phase5['contracts'],
                      'genesisHash': manifest['before']['nodes'][0]['genesis_hash'],
                      'validators': manifest['before']['nodes'][0]['validators']}
        keys = find_signers(phase5)
        relay_key = load(ROOT / '.local/phase4/accounts.private.json')['sender']
        signers = {k: v.lower() for k, v in phase5['publicSigners'].items()}
        signers.update(executor=Account.from_key(relay_key).address.lower(), auditor=Account.create().address.lower())
        manifest['public_signers'] = signers
        manifest['deployment'] = deployment
        config = {'deployment': deployment, 'signers': signers, 'relay_key': relay_key, 'tool_key': keys['mailTool'],
                  'signing_keys': {k: keys[k] for k in ['requester', 'biz', 'security']}}
        archive, names = build_context()
        manifest['build_context'] = {'sha256': hashlib.sha256(archive).hexdigest(), 'files': names}
        dump(output / 'run_manifest.json', manifest)
        with (output / 'build.txt').open('wb') as log:
            result = subprocess.run(prefix + ['build', '--network', 'none', '-f', 'evaluation/phase8.Dockerfile', '-t', IMAGE, '-'],
                                    input=archive, stdout=log, stderr=subprocess.STDOUT, timeout=300)
        if result.returncode:
            raise RuntimeError('Offline image build failed')
        manifest['image'] = json.loads(docker('image', 'inspect', IMAGE))[0]['Id']
        manifest['docker_version'] = json.loads(docker('version', '--format', '{{json .}}'))
        info = json.loads(docker('info', '--format', '{{json .}}'))
        manifest['environment'] = {k: info.get(k) for k in ['OperatingSystem', 'KernelVersion', 'Architecture', 'NCPU', 'MemTotal', 'Driver', 'ServerVersion']}
        manifest['environment'].update(host_os=platform.platform(), host_python=sys.version.split()[0], cpu=platform.processor(),
                                       disk_usage=subprocess.check_output(['wsl.exe', '-d', args.wsl_distro, '--', 'df', '-B1', '/var/lib/docker'], timeout=30).decode())
        manifest['qbft'] = load(ROOT / 'chain/genesis-template.json')['genesis']['config']['qbft']
        docker('volume', 'create', '--label', 'chainguard.phase=8', lab)
        mount = 'type=volume,src=' + lab + ',dst=/sandbox'
        docker('run', '--rm', '--network', 'none', '--user', '0:0', '--read-only', '--mount', mount, IMAGE,
               'python', '-c', 'import os; os.chown("/sandbox",10001,10001); os.chmod("/sandbox",0o700)')
        docker('run', '--rm', '-i', '--network', 'none', '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges:true', '--mount', mount,
               IMAGE, 'python', '-c', 'import os,sys; p="/sandbox/experiment.private.json"; f=os.open(p,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600); os.write(f,sys.stdin.buffer.read()); os.close(f)',
               data=json.dumps(config).encode())
        docker('create', '--name', lab, '--label', 'chainguard.phase=8', '--read-only', '--network', 'chainguard_qbft',
               '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges:true', '--pids-limit', '128', '--memory', '768m', '--cpus', '2',
               '--tmpfs', '/tmp:rw,noexec,nosuid,size=32m', '--mount', mount, IMAGE)
        created = True
        inspect = json.loads(docker('inspect', lab))[0]
        manifest['isolation'] = {'id': inspect['Id'], 'user': inspect['Config']['User'], 'read_only': inspect['HostConfig']['ReadonlyRootfs'],
                                 'cap_drop': inspect['HostConfig']['CapDrop'], 'security_opt': inspect['HostConfig']['SecurityOpt'],
                                 'mounts': inspect['Mounts'], 'networks': list(inspect['NetworkSettings']['Networks']),
                                 'port_bindings': inspect['HostConfig']['PortBindings']}
        assert manifest['isolation']['user'] == '10001:10001' and manifest['isolation']['read_only']
        assert all(m['Type'] == 'volume' for m in inspect['Mounts']) and not manifest['isolation']['port_bindings']
        dump(output / 'run_manifest.json', manifest)
        print('Starting actual protocol experiments: ' + str(len(manifest['schedule'])) + ' matched rows', flush=True)
        with (output / 'execution.txt').open('wb') as log:
            process = subprocess.Popen(prefix + ['start', '-a', lab], stdout=log, stderr=subprocess.STDOUT)
            deadline = time.monotonic() + 1500
            while process.poll() is None:
                if time.monotonic() > deadline:
                    docker('stop', '--time', '5', lab)
                    raise TimeoutError('Experiment time limit; evidence volume retained')
                time.sleep(2)
        manifest['container_exit'] = json.loads(docker('inspect', lab))[0]['State']
        public = docker('cp', lab + ':/sandbox/public/.', '-', timeout=60)
        with tarfile.open(fileobj=io.BytesIO(public)) as tar:
            for item in tar:
                name = Path(item.name).name
                if item.isfile() and (name == 'traces.jsonl' or name.startswith('case-') and name.endswith('.json')):
                    (output / name).write_bytes(tar.extractfile(item).read())
        rows = [json.loads(line) for line in (output / 'traces.jsonl').read_text().splitlines()]
        export(output, rows, plan['bootstrap_replicates'])
        manifest['after'] = ops.health()
        manifest['case_count'] = len(rows)
        manifest['observed_mail_count'] = sum(r['mailbox_count'] for r in rows)
        manifest['error_count'] = sum(r['status'] == 'ERROR' for r in rows)
        manifest['status'] = 'PASS' if process.returncode == 0 and manifest['container_exit']['ExitCode'] == 0 and not manifest['error_count'] and len(rows) == len(manifest['schedule']) else 'FAIL'
        dump(output / 'run_manifest.json', manifest)
        if manifest['status'] != 'PASS':
            raise RuntimeError('Actual experiment failed; partial rows and failures preserved')
        from verify_phase8 import verify
        verification = verify(output, prefix)
        dump(output / 'verification.json', verification)
        manifest['verification'] = verification
        manifest['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
        manifest['artifacts'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir() if p.is_file() and p.name != 'run_manifest.json'}
        dump(output / 'run_manifest.json', manifest)
        print(json.dumps({'status': manifest['status'], 'cases': len(rows), 'mail': manifest['observed_mail_count'], 'output': str(output), 'real_llm': 'NOT_MEASURED'}))
    except Exception as error:
        manifest.update(status='FAIL', failure=type(error).__name__ + ': ' + str(error), finished_at_utc=datetime.now(timezone.utc).isoformat())
        dump(output / 'run_manifest.json', manifest)
        raise
    finally:
        if created:
            docker('stop', '--time', '5', lab)


if __name__ == '__main__':
    main()
