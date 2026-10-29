"""Readonly evidence/privacy checks plus restart of only the new Web processes."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'gateway/src'),str(ROOT/'sandbox_tools/src'),str(ROOT/'agent/src')]
from chainguard_gateway.phase10_bridge import DockerBridge
from chainguard_gateway.phase10_store import OperationsStore
from chainguard_agent.local_config import load_local_env


def main():
    p=argparse.ArgumentParser();p.add_argument('--deployment',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    if a.out.exists():raise ValueError('New evidence directory required')
    a.out.mkdir(parents=True)
    deployment=json.loads(a.deployment.read_text(encoding='utf8'));config=json.loads(Path(deployment['config_path']).read_text())
    bridge=DockerBridge(config);store=OperationsStore(config['private_root'])
    def summary():
        return {'records':bridge.snapshot(),'models':{j['id']:len([e for e in store.events(j['id']) if e['kind']=='MODEL_EXCHANGE']) for j in store.jobs()},
            'mail':{r['action_id']:bridge.observe(r['action_id'])['mail_count'] for r in bridge.snapshot()}}
    before=summary()
    with (a.out/'restart.txt').open('wb') as log:
        r=subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'scripts/restart_phase10.ps1'),'-Config',deployment['config_path']],
            stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,cwd=ROOT,timeout=60)
    assert r.returncode==0
    after=summary();assert before==after,'Restart changed original actions, side effects or model request count'
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(deployment['audit_url']+'/audit-api/v1/actions',timeout=20) as response: public=json.load(response)
    expected={'interactive-'+j['id'][2:] for j in store.jobs()}
    assert public['read_only'] and expected<={r['entry_id'] for r in public['actions']}
    assert all(r['entry_id'] in expected or r['entry_id'].startswith('batch-') and r.get('batch_observation') for r in public['actions'])
    local={};load_local_env(ROOT/'.env.local',local);key=local.get('CHAINGUARD_LLM_API_KEY','').encode()
    files=[]
    for directory in ['console/src','console/dist','gateway/src','scripts','docs']:
        files.extend(p for p in (ROOT/directory).rglob('*') if p.is_file() and p.suffix in {'.py','.js','.jsx','.mjs','.json','.html','.css','.md','.ps1'})
    files.extend(p for p in (ROOT/'results/phase10').rglob('*.json') if p.is_file())
    if key:
        assert not any(key in p.read_bytes() for p in files),'Key found in public source/evidence'
        assert key not in json.dumps(public).encode()
    ignored=subprocess.run(['git','check-ignore','.env.local','.local/phase10','.local/phase10-public'],cwd=ROOT,capture_output=True,check=True).stdout
    assert len(ignored.splitlines())==3
    image=json.loads(bridge.docker(['image','inspect',config['image']]))[0]
    isolates={}
    for kind,name in config['containers'].items():
        info=json.loads(bridge.docker(['inspect',name]))[0]
        assert info['Config']['User']=='10001:10001' and info['HostConfig']['ReadonlyRootfs']
        assert len(info['Mounts'])==1 and info['Mounts'][0]['Type']=='volume'
        assert not info['HostConfig']['PortBindings']
        isolates[kind]={'image_id':info['Image'],'read_only_root':True,'nonroot':True,'volume':info['Mounts'][0]['Name'],'published_ports':False}
    # Directly verify that the Agent's own container lacks signer/relay/admin/LLM keys.
    boundary=json.loads(bridge.docker(['exec',config['containers']['agent'],'python','-c',
        "import json,os; from chainguard_gateway.phase6_server import load; r,c=load(); print(json.dumps({'signing_key_absent':not (r/'signing.key').exists(),'relay_key_absent':not (r/'relay.key').exists(),'jwt_signing_key_absent':not (r/'jwt.key').exists(),'llm_key_absent':not bool(os.environ.get('CHAINGUARD_LLM_API_KEY')),'token_subjects':sorted(json.loads((r/'tokens.json').read_text()))}))"]))
    assert boundary['signing_key_absent'] and boundary['relay_key_absent'] and boundary['jwt_signing_key_absent'] and boundary['llm_key_absent'] and boundary['token_subjects']==['agent']
    source_paths=[*ROOT.glob('gateway/src/chainguard_gateway/phase10_*.py'),*ROOT.glob('scripts/*phase10*.*'),*ROOT.glob('console/src/*'),*ROOT.glob('console/tests/*'),ROOT/'console/package.json',ROOT/'console/package-lock.json',ROOT/'dashboard/src/main.jsx',ROOT/'dashboard/src/format.mjs']
    result={'status':'PASS','restart_original_actions_unchanged':True,'restart_no_model_retry':True,'restart_mail_counts_unchanged':True,
        'original_actions':len(after['records']),'actual_total_local_mail':sum(after['mail'].values()),'audit_public_entries':public['total'],
        'public_sources_current_key_absent':True,'public_files_scanned':len(files),'private_paths_git_ignored':True,'isolates':isolates,
        'agent_boundary':boundary,'observer_image_id':image['Id'],'sources':{p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths}}
    (a.out/'delivery.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
    print(json.dumps({k:result[k] for k in ['status','restart_original_actions_unchanged','restart_mail_counts_unchanged','audit_public_entries']}))


if __name__=='__main__':main()
