"""Record source/evidence hashes after checking frozen inputs and final image parity."""
import argparse
import hashlib
import json
from pathlib import Path

from run_phase6 import ROOT,build_context


def load(path): return json.loads(path.read_text(encoding='utf-8'))
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def record(run,verification,output):
    if not output.is_relative_to(ROOT/'results/phase6'): raise ValueError('Output must stay within results/phase6')
    targets=[output/name for name in ['source-manifest.json','evidence-manifest.json','integrity.json']]
    if any(p.exists() for p in targets): raise FileExistsError('Use a new integrity output directory')
    checks={}
    for name in ['phase0-freeze','phase3-policy-freeze']:
        entries=load(ROOT/f'config/{name}.json')['files']
        drift=[p for p,v in entries.items() if sha(ROOT/p)!=v]
        assert not drift,drift
        checks[name]={'matched':len(entries),'drift':drift}
    expected={'README.md',*(f'docs/{n}.md' for n in ['architecture','contracts','decisions','progress','handoff'])}
    for stage in ['phase4','phase5']:
        entries=load(ROOT/f'results/{stage}/source-manifest.json')
        if 'files' in entries: entries=entries['files']
        actual={p for p,v in entries.items() if sha(ROOT/p)!=v}
        assert actual<=expected,(stage,actual)
        checks[stage+'-source']={'unchanged':len(entries)-len(actual),'expected_document_updates':sorted(actual)}
        manifest=ROOT/f'results/{stage}/evidence-manifest.json'
        entries=load(manifest) if manifest.exists() else {}
        if 'files' in entries: entries=entries['files']
        # Phase4 evidence paths are repository-relative; phase5 uses names
        # relative to the manifest directory. Do not rewrite either old manifest.
        paths={p:(ROOT/p if p.startswith('results/') else manifest.parent/p) for p in entries}
        assert all(p.resolve().is_relative_to(ROOT) for p in paths.values())
        drift=[p for p,v in entries.items() if sha(paths[p])!=v]
        assert not drift,drift
        checks[stage+'-evidence']={'unchanged':len(entries),'drift':drift}
    archive,names=build_context()
    saved=load(run/'build-context.json')
    assert hashlib.sha256(archive).hexdigest()==saved['sha256']
    checks['final-container-source']={'archive_sha256':saved['sha256'],'source_matches_run':True,'files':len(names)}
    sources=['README.md','AGENTS.md','gateway/phase6.Dockerfile','gateway/integration/phase6_lab.py','gateway/tests/test_phase6_primitives.py',
        'sandbox_tools/src/chainguard_sandbox/chain_mail.py','scripts/run_phase6.py','scripts/verify_phase6.py','scripts/record_phase6_integrity.py']
    sources += [f'gateway/src/chainguard_gateway/{n}.py' for n in ['chain_crypto','chain_rpc','chain_store','chain_service','chain_api','chain_transport','phase6_server']]
    sources += [f'docs/{n}.md' for n in ['architecture','contracts','decisions','progress','handoff','phase6-design','phase6-contracts','phase6-runbook','phase6-acceptance']]
    public,verified=load(run/'report.json'),load(verification)
    assert public['status']==verified['status']=='PASS'
    checks['acceptance']={'run':run.relative_to(ROOT).as_posix(),'live_receipts':verified['live_receipts'],'mailbox_deliveries':verified['mime_deliveries']}
    for path in run.glob('*.json'):
        if path.name=='build-context.json': continue
        raw=path.read_text(encoding='utf-8')
        for field in ['private_key','signing_keys','params_salt','result_salt','evidence_salt','relay_key','jwt_key','tool_key']:
            assert json.dumps(field)+':' not in raw,(path,field)
    checks['public-export-field-check']='PASS; no prohibited key/salt JSON fields'
    excluded={p.resolve() for p in targets}
    evidence={p.relative_to(ROOT).as_posix():sha(p) for p in (ROOT/'results/phase6').rglob('*')
        if p.is_file() and p.resolve() not in excluded and p.name!='integrity-final.txt'}
    output.mkdir(parents=True,exist_ok=True)
    for path,value in zip(targets,[{p:sha(ROOT/p) for p in sorted(sources)},evidence,checks],strict=True):
        path.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
    return {'status':'PASS','checks':checks,'source_files':len(sources),'evidence_files':len(evidence)}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--verification',type=Path,required=True)
    parser.add_argument('--out',type=Path,default=ROOT/'results/phase6')
    args=parser.parse_args()
    print(json.dumps(record(args.run.resolve(),args.verification.resolve(),args.out.resolve()),indent=2))
