"""Recompute observations in a new evidence copy; never rerun models or tools."""
import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts'), str(ROOT / 'gateway/src'), str(ROOT / 'sandbox_tools/src')]
from evaluation.live_results import observations, export_live
from evaluation.live_plan import rule_for
from verify_live_agent import verify


def load(path):
    return json.loads(path.read_text(encoding='utf8'))


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf8')


def reobserve_case(original, plan):
    case = copy.deepcopy(original)
    observed = observations(case['events'], case['model_exchanges'], case['evidence'],
                            rule_for(case['evidence']['case']) or plan['authorized_mail'])
    for key, value in observed.items():
        if key not in {'unauthorized_calls', 'local_attack_success'}:
            case['row'][key] = value
    return case


def reanalyze(source, output):
    source, output = source.resolve(), output.resolve()
    if not source.is_relative_to(ROOT / 'results') or not output.is_relative_to(ROOT / 'results/phase8'):
        raise ValueError('Use an existing results source and a new phase8 output directory')
    if output.exists() or output.is_relative_to(source):
        raise ValueError('Never overwrite original evidence or copy recursively into it')
    manifest = load(source / 'run_manifest.json')
    if manifest['status'] not in {'PASS', 'PARTIAL'} or manifest['track'] != 'real_llm':
        raise ValueError('Only complete real-model executions can be reanalyzed')
    originals = {p.name: p.read_bytes() for p in source.iterdir() if p.is_file()}
    for name, digest in manifest['artifacts'].items():
        assert hashlib.sha256(originals[name]).hexdigest() == digest
    cases = [load(p) for p in sorted(source.glob('live-case-*.json'))]
    assert len(cases) == manifest['case_count'] == len(manifest['schedule'])
    shutil.copytree(source, output)
    manifest.pop('artifacts', None)
    manifest['status'] = 'REANALYZING'
    manifest['reanalysis'] = dict(
        source=source.relative_to(ROOT).as_posix(), model_or_tool_reexecuted=False,
        source_files={name: hashlib.sha256(raw).hexdigest() for name, raw in originals.items()},
        analysis_sources={name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in
            ['scripts/reanalyze_live_agent.py', 'evaluation/live_results.py', 'evaluation/metrics.py',
             'evaluation/effect_goals.py', 'evaluation/judge_real_effects.py']})
    dump(output / 'run_manifest.json', manifest)
    try:
        for path, original in zip(sorted(output.glob('live-case-*.json')), cases, strict=True):
            dump(path, reobserve_case(original, manifest['plan']))
        # These derived artifacts must be rebuilt after observations change.
        # Source originals remain byte-for-byte intact in their original directory.
        for name in ['official-judgements.json', 'traces.jsonl', 'cases.csv', 'aggregated_metrics.csv']:
            candidate = (output / name).resolve()
            assert candidate.parent == output
            candidate.unlink(missing_ok=True)
        dump(output / 'verification.json', verify(output))
        judge = subprocess.run([str(ROOT / '.local/phase7-agentdojo-venv/Scripts/python.exe'),
                                str(ROOT / 'evaluation/judge_real_effects.py'), str(output)],
                               capture_output=True, timeout=120)
        (output / 'reanalysis-judge.txt').write_bytes(judge.stdout + judge.stderr)
        if judge.returncode:
            raise RuntimeError('Original official judge failed; original evidence retained')
        export_live(output, [load(p) for p in sorted(output.glob('live-case-*.json'))],
                    load(output / 'official-judgements.json'), manifest['plan']['bootstrap_replicates'])
        dump(output / 'verification.json', verify(output))
        assert all((source / name).read_bytes() == raw for name, raw in originals.items())
        manifest.update(status='PARTIAL' if any(c['row']['error_code'] for c in cases) else 'PASS',
                        reanalyzed_at_utc=datetime.now(timezone.utc).isoformat())
        manifest['artifacts'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in output.iterdir() if p.is_file() and p.name != 'run_manifest.json'}
        dump(output / 'run_manifest.json', manifest)
        return manifest['status']
    except Exception as error:
        manifest.update(status='FAIL', reanalysis_error=type(error).__name__)
        dump(output / 'run_manifest.json', manifest)
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(dict(status=reanalyze(args.source, args.out), output=str(args.out))))
