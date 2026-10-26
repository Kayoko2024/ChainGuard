"""Create stage7 metadata after checking actual tests and protected sources."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/phase7'


def load(path): return json.loads(path.read_text(encoding='utf8'))
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,value): path.write_text(json.dumps(value,indent=2)+'\n',encoding='utf8')


def main():
    for name in ['source-manifest.json','evidence-manifest.json','integrity.json']:
        if (OUT/name).exists(): raise ValueError('Keep existing snapshots; choose a separate review for future changes')
    frozen={}
    for name in ['phase0-freeze','phase3-policy-freeze']:
        sources=load(ROOT/f'config/{name}.json')['files']
        for path,expected in sources.items(): assert sha(ROOT/path)==expected,path
        frozen[name]=len(sources)
    previous=load(ROOT/'results/phase5/source-manifest.json')
    for name in ['PolicyRegistry','ExecutionRegistry','AuditRegistry']:
        path=f'contracts/{name}.sol'; assert sha(ROOT/path)==previous[path],path
    old=load(ROOT/'results/phase6/source-manifest.json')
    changed=[p for p,h in old.items() if sha(ROOT/p)!=h]
    expected={'README.md','pyproject.toml',*[f'docs/{n}.md' for n in ['architecture','contracts','decisions','progress','handoff']]}
    assert set(changed)<=expected,changed
    tests=ET.parse(OUT/'final-pytest-02.xml').findall('.//testsuite')
    passed=sum(int(t.attrib['tests']) for t in tests)
    assert passed==175 and all(int(t.attrib['failures'])==int(t.attrib['errors'])==int(t.attrib.get('skipped',0))==0 for t in tests)
    assert '71 passing' in (OUT/'final-hardhat.txt').read_text(encoding='utf-8-sig')
    run=load(OUT/'final-run-02/report.json'); verify=load(OUT/'final-verification.json')
    assert run['status']==verify['status']=='PASS'
    assert len(run['transactions'])==8 and len(run['tool_effects']['mailbox'])==4 and verify['live_receipts']==32
    assert load(OUT/'agentdojo-check-final.json')['status']=='PASS'
    paths=set()
    for directory in ['agent','evaluation']:
        paths.update(p for p in (ROOT/directory).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
    paths.update(ROOT/p for p in ['AGENTS.md','README.md','.env.example','pyproject.toml',
        'gateway/src/chainguard_gateway/phase7_server.py','sandbox_tools/src/chainguard_sandbox/read_broker.py',
        'sandbox_tools/tests/test_read_broker.py','scripts/run_phase7.py','scripts/verify_phase7.py','scripts/write_phase7_report.py',
        'spec/agent/interfaces.json'])
    paths.update((ROOT/'docs').glob('phase7-*.md'))
    paths.update(ROOT/f'docs/{n}.md' for n in ['architecture','contracts','decisions','progress','handoff'])
    source={p.relative_to(ROOT).as_posix():sha(p) for p in sorted(paths)}
    # Existing artifacts are evidence, never private runtime config or keys.
    evidence={p.relative_to(ROOT).as_posix():sha(p) for p in sorted(OUT.rglob('*')) if p.is_file()}
    write(OUT/'source-manifest.json',source); write(OUT/'evidence-manifest.json',evidence)
    write(OUT/'integrity.json',{'status':'PASS','recorded_at_utc':datetime.now(timezone.utc).isoformat(),
        'stage7_current_scope':'TECHNICAL_ACCEPTANCE_PASSED_AWAITING_USER','pytest_passed':passed,'hardhat_passed':71,
        'read_broker_container_tests':6,'frozen_sources':frozen,'original_contracts_unchanged':3,
        'phase6_source_changes_expected':changed,'source_files':len(source),'evidence_files':len(evidence),
        'run':'results/phase7/final-run-02','verification':'results/phase7/final-verification.json',
        'llm_sample_count':0,'attack_success':None,'real_llm_attack_test_completed':False,
        'phase7_required_followup':'Run a configured real LLM before formal stage8 A/B/C',
        'git_head_exists':False,'snapshot_is_independent_trust_root':False})
    print(f'Stage7 integrity PASS: {len(source)} source files, {len(evidence)} evidence files; protected 21+8 and 3 contracts unchanged.')


if __name__=='__main__': main()
