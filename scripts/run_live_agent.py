"""Real DeepSeek Agent Runner A/B/C over isolated real gateway/tool services."""
import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import random
import platform
import secrets
import subprocess
import sys
import tarfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'agent/src'), str(ROOT / 'gateway/src'), str(ROOT / 'sandbox_tools/src')]
from chainguard_agent.local_config import load_local_env, redact
from chainguard_agent.model import HTTPModelBackend, LLMConfig
from chainguard_agent.runner import AgentRunner
from chainguard_agent.proxy import ToolExecutionProxy
from chainguard_agent.central_proxy import CentralExecutionProxy
from chainguard_agent.journal import Journal
from chainguard_sandbox.protocol import ToolError
from run_phase8 import build_context, hash_sources, dump, load
from run_phase6 import find_signers
from chain import Chain as Operations
from eth_account import Account
from evaluation.live_results import observations, export_live
from evaluation.metrics import write_csv
from evaluation.live_plan import validate as validate_live_plan, schedule as live_schedule, make_case, rule_for

IMAGE = 'chainguard/live-agent-lab:0.8.0'


def build_live_context():
    old, names = build_context()
    result = io.BytesIO()
    with tarfile.open(fileobj=io.BytesIO(old)) as source, tarfile.open(fileobj=result, mode='w') as target:
        for item in source:
            target.addfile(item, source.extractfile(item))
        for path in sorted((ROOT / 'agent/src').rglob('*.py')):
            name = path.relative_to(ROOT).as_posix()
            raw = path.read_bytes()
            item = tarfile.TarInfo(name)
            item.size, item.mode, item.mtime = len(raw), 0o644, 0
            target.addfile(item, io.BytesIO(raw))
    return result.getvalue()


class Transport:
    def __init__(self, process):
        self.process = process

    def exchange(self, value):
        self.process.stdin.write(json.dumps(value) + '\n')
        self.process.stdin.flush()
        line = self.process.stdout.readline()
        if not line:
            raise ToolError('EXECUTION_UNKNOWN')
        response = json.loads(line)
        if not response['ok']:
            raise ToolError(response['error'])
        return response['result']

    def request(self, method, path, body=None, key=None):
        return self.exchange({'op': 'request', 'request': dict(method=method, path=path, body=body, key=key)})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--groups', nargs='+', choices=['A', 'B', 'C'], default=['A', 'B', 'C'])
    parser.add_argument('--prerequisite', type=Path)
    parser.add_argument('--plan', type=Path, default=ROOT / 'evaluation/live_plan.json')
    args = parser.parse_args()
    output = args.out.resolve()
    if output.exists() or not (output.is_relative_to(ROOT / 'results/phase7') or output.is_relative_to(ROOT / 'results/phase8')):
        raise ValueError('Choose a new phase7/phase8 results directory')
    load_local_env(ROOT / '.env.local')
    plan = validate_live_plan(load(args.plan))
    if len(args.groups) != len(set(args.groups)):
        raise ValueError('Duplicate experiment groups')
    if len(args.groups) > 1:
        if not args.prerequisite or load(args.prerequisite / 'run_manifest.json')['status'] != 'PASS' or load(args.prerequisite / 'verification.json')['status'] != 'PASS':
            raise ValueError('First finish and verify the real-model C prerequisite')
        if load(args.prerequisite/'run_manifest.json')['plan'] != plan:
            raise ValueError('Prerequisite and experiment must use the same frozen model/data settings')
    config = LLMConfig.from_env()
    if config.model != plan['model'] or config.base_url != plan['base_url']:
        raise ValueError('Live model must match the pinned plan')
    output.mkdir(parents=True)
    prefix = ['wsl.exe', '-d', 'Ubuntu', '-u', 'root', '--', 'docker']
    lab = 'chainguard-live-' + secrets.token_hex(6)
    manifest = {'status': 'RUNNING', 'track': 'real_llm', 'plan': plan, 'groups': args.groups,
                'started_at_utc': datetime.now(timezone.utc).isoformat(), 'sources': hash_sources(),
                'container_name': lab, 'volume': lab, 'llm_sample_count': 0,
                'scope': plan['latency_scope'], 'official_full_user_task': 'INCOMPATIBLE',
                'host': {'platform':platform.platform(),'python':sys.version,'cpu_count':os.cpu_count()},
                'schedule_version': 2, 'plan_sha256': hashlib.sha256(args.plan.read_bytes()).hexdigest(),
                'prerequisite': str(args.prerequisite) if args.prerequisite else None}
    def docker(*command, data=None, timeout=90):
        result = subprocess.run(prefix + list(command), input=data, capture_output=True, timeout=timeout)
        if result.returncode:
            (output / 'docker-error.txt').write_bytes(result.stderr)
            raise RuntimeError('Docker command failed; no model fallback')
        return result.stdout
    process = None
    try:
        ops = Operations(argparse.Namespace(wsl_distro='Ubuntu', wsl_user='root'))
        ops.wsl_session()
        manifest['before'] = ops.wait_healthy()
        phase5 = load(ROOT / 'results/phase5/besu-run-01/report.json')
        keys = find_signers(phase5)
        relay_key = load(ROOT / '.local/phase4/accounts.private.json')['sender']
        signers = {k: v.lower() for k, v in phase5['publicSigners'].items()}
        signers.update(executor=Account.from_key(relay_key).address.lower(), auditor=Account.create().address.lower())
        deployment = {'chainId': 20261026, 'contracts': phase5['contracts'], 'genesisHash': manifest['before']['nodes'][0]['genesis_hash'],
                      'validators': manifest['before']['nodes'][0]['validators']}
        private = dict(deployment=deployment, signers=signers, relay_key=relay_key, tool_key=keys['mailTool'],
                       signing_keys={k: keys[k] for k in ['requester', 'biz', 'security']})
        manifest.update(deployment=deployment, public_signers=signers)
        archive = build_live_context()
        with (output / 'build.txt').open('wb') as log:
            built = subprocess.run(prefix + ['build', '--network', 'none', '-f', 'evaluation/phase8.Dockerfile', '-t', IMAGE, '-'],
                                   input=archive, stdout=log, stderr=subprocess.STDOUT, timeout=300)
        if built.returncode:
            raise RuntimeError('Offline build failed')
        manifest['image'] = json.loads(docker('image', 'inspect', IMAGE))[0]['Id']
        manifest['docker_version'] = json.loads(docker('version','--format','{{json .}}'))
        docker('volume', 'create', '--label', 'chainguard.phase=8-live', lab)
        mount = 'type=volume,src=' + lab + ',dst=/sandbox'
        docker('run', '--rm', '--network', 'none', '--user', '0:0', '--read-only', '--mount', mount, IMAGE,
               'python', '-c', 'import os; os.chown("/sandbox",10001,10001); os.chmod("/sandbox",0o700)')
        docker('run', '--rm', '-i', '--network', 'none', '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges:true', '--mount', mount,
               IMAGE, 'python', '-c', 'import os,sys; f=os.open("/sandbox/experiment.private.json",os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600); os.write(f,sys.stdin.buffer.read()); os.close(f)', data=json.dumps(private).encode())
        docker('create', '-i', '--name', lab, '--label', 'chainguard.phase=8-live', '--read-only', '--network', 'chainguard_qbft', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges:true',
               '--memory', '768m', '--pids-limit', '128', '--cpus', '2', '--mount', mount, IMAGE, 'python', '-m', 'evaluation.live_bridge')
        inspected = json.loads(docker('inspect', lab))[0]
        manifest['isolation'] = dict(id=inspected['Id'], user=inspected['Config']['User'], host=inspected['HostConfig'])
        with (output / 'bridge-stderr.txt').open('w', encoding='utf8') as err:
            process = subprocess.Popen(prefix + ['start', '-a', '-i', lab], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=err, text=True, encoding='utf8', bufsize=1)
            transport = Transport(process)
            fixtures = load(ROOT / 'agent/fixtures/acceptance.json')
            schedule = live_schedule(plan, args.groups)
            manifest['schedule'] = schedule
            dump(output / 'run_manifest.json', manifest)
            rows = []
            for index, scheduled in enumerate(schedule):
                scenario, group = scheduled['scenario'], scheduled['group']
                item = make_case(plan, scheduled, fixtures)
                semantic = {k: v for k, v in item.items() if k != 'group'}
                task = transport.exchange({'op': 'prepare', 'case': item})
                journal = Journal(ROOT / '.local/live-agent' / lab / f'{index:04d}')
                # Journal stays in ignored .local, never public results.
                calls = []
                backend = HTTPModelBackend(config, parameters=plan['parameters'], recorder=calls.append)
                proxy = (ToolExecutionProxy(transport, journal, str(index), task['task_id'], mode='real_llm', wait_seconds=0) if group == 'C' else
                         CentralExecutionProxy(transport, journal, str(index), task['task_id']))
                started = time.perf_counter()
                error = None
                try:
                    result = AgentRunner(backend, proxy, plan['max_turns'], plan['max_calls']).run(item['task_text'])
                except Exception as failure:
                    result, error = None, type(failure).__name__
                elapsed = (time.perf_counter() - started) * 1000
                evidence = transport.exchange({'op': 'finish'})
                events = journal.events()
                attempted = [e for e in events if e['event'] == 'AGENT_ATTEMPT']
                verdicts = [e for e in events if e['event'] == 'POLICY_RESULT']
                row = {'group': group, 'scenario': scenario, 'sample_id': item['sample_id'], 'track': 'real_llm', 'llm_sample_count': 1,
                       'trial': scheduled['trial'],
                       'status': 'ERROR' if error else 'OBSERVED', 'error_code': error, 'input_sha256': hashlib.sha256(json.dumps(semantic, sort_keys=True).encode()).hexdigest(),
                       'elapsed_ms': elapsed, 'model_ms': sum(c['elapsed_ms'] for c in calls), 'model_requests': len(calls),
                       'agent_attempted_tool': [e['tool_name'] for e in attempted], 'policy_verdict': [e['policy_verdict'] for e in verdicts],
                       'tool_executed': bool(evidence['mailbox']), 'mailbox_count': len(evidence['mailbox']),
                       'task_eligible': 1, 'task_completed': 0, 'task_unknown': int(bool(error)), 'performance_eligible': not item['attack'],
                       'attack_evaluable': int(item['attack']), 'attack_success': None, 'attack_success_count': 0, 'attack_unknown': int(bool(error) and item['attack']),
                       'unauthorized_attempts': 0, 'unauthorized_executions': 0, 'unauthorized_blocked': 0, 'unauthorized_unknown': 0}
                if item.get('task_family'):
                    row.update(cluster_id=item['task_family'], attack_family=item['attack_family'])
                observed = observations(events, calls, evidence, rule_for(item))
                row.update({k: v for k, v in observed.items() if k not in {'unauthorized_calls','local_attack_success'}})
                row['task_unknown'] = int(bool(error) and not row['task_completed'])
                row['evidence_file'] = f'live-case-{index:04d}.json'
                row['llm_sample_count'] = int(any(c.get('http_status') == 200 for c in calls))
                public = redact({'row': row, 'result': result, 'events': events, 'model_exchanges': calls, 'evidence': evidence}, config.api_key)
                dump(output / f'live-case-{index:04d}.json', public)
                rows.append(row)
                (output/'traces.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows),encoding='utf8')
                write_csv(output/'cases.csv',rows)
                print(json.dumps({'scenario': scenario, 'group': group, 'model_requests': len(calls), 'mail': len(evidence['mailbox']), 'error': error}), flush=True)
            process.stdin.close()
            process.wait(timeout=20)
        manifest.update(case_count=len(rows), llm_sample_count=sum(r['llm_sample_count'] for r in rows), after=ops.wait_healthy())
        manifest['status'] = 'EXECUTED_PENDING_VERIFICATION'
        dump(output / 'run_manifest.json', manifest)
        if manifest['status'] == 'EXECUTED_PENDING_VERIFICATION':
            from verify_live_agent import verify
            dump(output / 'verification.json', verify(output))
            judge = subprocess.run([str(ROOT / '.local/phase7-agentdojo-venv/Scripts/python.exe'), str(ROOT / 'evaluation/judge_real_effects.py'), str(output)], capture_output=True, text=True)
            (output / 'judge-log.txt').write_text(judge.stdout + judge.stderr, encoding='utf8')
            if judge.returncode:
                raise RuntimeError('Original AgentDojo judging failed')
            export_live(output, [load(p) for p in sorted(output.glob('live-case-*.json'))], load(output / 'official-judgements.json'), plan['bootstrap_replicates'])
            dump(output / 'verification.json', verify(output))
            manifest.update(status='PASS' if all(r['status'] == 'OBSERVED' for r in rows) else 'PARTIAL', completed_at_utc=datetime.now(timezone.utc).isoformat(),
                            artifacts={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir() if p.is_file() and p.name != 'run_manifest.json'})
            dump(output / 'run_manifest.json', manifest)
        else:
            raise RuntimeError('Real model run failed; evidence retained, no fallback')
        print(json.dumps({'status': manifest['status'], 'output': str(output)}))
        return 0 if manifest['status'] == 'PASS' else 1
    except Exception as error:
        manifest.update(status='FAIL', failure=type(error).__name__)
        dump(output / 'run_manifest.json', manifest)
        raise
    finally:
        if process and process.poll() is None:
            process.terminate()
        subprocess.run(prefix + ['stop', '--time', '3', lab], capture_output=True, timeout=20)


if __name__ == '__main__':
    raise SystemExit(main())
