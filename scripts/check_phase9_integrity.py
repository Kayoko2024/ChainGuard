"""Compare all pre-stage9 source hashes and the frozen protocol; never regenerate locks."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def check(root=ROOT):
    baseline=root/'results/phase8/complete-experiment-01/protocol/run_manifest.json'
    original=json.loads(baseline.read_text(encoding='utf8'))['sources']
    frozen={}
    for name in ['phase0-freeze.json','phase3-policy-freeze.json']:
        frozen.update(json.loads((root/'config'/name).read_text(encoding='utf8'))['files'])
    changed=[]
    for name,expected in {**original,**frozen}.items():
        path=root/name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
            changed.append(name)
    return dict(status='FAIL' if changed else 'PASS',checked_at_utc=datetime.now(timezone.utc).isoformat(),
        baseline='results/phase8/complete-experiment-01/protocol/run_manifest.json',
        original_source_files=len(original),frozen_files=len(frozen),changed=changed,
        scope='All sources present in the actual phase8 manifest, plus phase0/phase3 frozen inputs. Additions are not execution authority.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    if args.out.exists():raise ValueError('Use a new output file')
    result=check()
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
    print(json.dumps(result))
    raise SystemExit(0 if result['status']=='PASS' else 1)
