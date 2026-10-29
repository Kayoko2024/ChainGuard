"""One command: API preflight -> real C prerequisite -> real A/B/C -> protocol track.

Tracks keep separate samples, metrics, artifacts and original failure evidence.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path)
    parser.add_argument('--plan',type=Path,default=ROOT/'evaluation/live_plan.json')
    parser.add_argument('--model-only',action='store_true',help='Run API/C/ABC, retaining the protocol track as a separate optional run')
    args=parser.parse_args()
    output=(args.out or ROOT/'results/phase8/experiments'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')).resolve()
    if output.exists() or not output.is_relative_to(ROOT/'results/phase8'):
        raise ValueError('Choose a new results/phase8 directory')
    output.mkdir(parents=True)
    manifest=dict(status='RUNNING',tracks_separate=True,started_at_utc=datetime.now(timezone.utc).isoformat(),steps=[])
    steps=[('preflight',['scripts/check_deepseek.py','--out',str(output/'preflight')]),
           ('phase7-real-prerequisite',['scripts/run_live_agent.py','--plan',str(args.plan),'--groups','C','--out',str(output/'phase7-real')]),
           ('real-abc',['scripts/run_live_agent.py','--plan',str(args.plan),'--prerequisite',str(output/'phase7-real'),'--out',str(output/'real-abc')]),
           ('protocol',['scripts/run_phase8.py','--out',str(output/'protocol')])]
    if args.model_only: steps=steps[:-1]
    def save():
        (output/'run_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf8')
    save()
    for name,arguments in steps:
        print('Running '+name,flush=True)
        with (output/(name+'.txt')).open('wb') as log:
            result=subprocess.run([sys.executable]+arguments,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
        manifest['steps'].append(dict(name=name,arguments=arguments,exit_code=result.returncode))
        save()
        if result.returncode:
            manifest.update(status='FAIL',failed_step=name)
            save()
            print(json.dumps({'status':'FAIL','step':name,'output':str(output)}),flush=True)
            return result.returncode
    children=['phase7-real','real-abc']+([] if args.model_only else ['protocol'])
    manifest.update(status='PASS',completed_at_utc=datetime.now(timezone.utc).isoformat(),
                    reports={'real_llm':'real-abc/report.md',**({} if args.model_only else {'protocol':'protocol/report.md'})},
                    child_manifest_sha256={name:hashlib.sha256((output/name/'run_manifest.json').read_bytes()).hexdigest() for name in children})
    save()
    (output/'report.md').write_text('# ChainGuard experiment bundle\n\n- [Real DeepSeek A/B/C](real-abc/report.md)\n'+('' if args.model_only else '- [Deterministic protocol/fault/performance](protocol/report.md)\n')+'\nTracks are verified separately. Do not pool prerequisites, protocol or earlier runs into model ASR.\n',encoding='utf8')
    print(json.dumps({'status':'PASS','output':str(output)}),flush=True)
    return 0


if __name__=='__main__':
    raise SystemExit(main())
