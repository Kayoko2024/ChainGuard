"""Verify original evidence first, then export a public audit-only catalog."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'gateway/src'),str(ROOT/'sandbox_tools/src')]
from chainguard_gateway.audit_projection import export_catalog
from verify_phase8 import verify as verify_protocol
from verify_live_agent import verify as verify_live


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle',type=Path)
    parser.add_argument('--protocol',type=Path)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    output=args.out.resolve()
    if output.exists() or not output.is_relative_to(ROOT/'results/phase9'):
        raise ValueError('Choose a new results/phase9 directory')
    if bool(args.bundle)==bool(args.protocol):raise ValueError('Choose exactly one bundle or protocol run')
    bundle=(args.bundle or args.protocol).resolve()
    if not bundle.is_relative_to(ROOT/'results'):
        raise ValueError('Source must be local experiment evidence')
    source=[('protocol',bundle/'protocol'),('model',bundle/'real-abc')] if args.bundle else [('protocol',bundle)]
    checks={}
    checks['protocol']=verify_protocol(source[0][1])
    if args.bundle:checks['model']=verify_live(source[1][1])
    catalog=export_catalog(output,source)
    (output/'export-verification.json').write_text(json.dumps(checks,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'status':'PASS','entries':len(catalog['actions']),'output':str(output)}))


if __name__=='__main__':
    main()
