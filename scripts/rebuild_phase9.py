"""Fresh source/venv/npm/image rebuild; reuse only declared local chain and wheel cache."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.request
import urllib.error

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path)
    parser.add_argument('--deployment',type=Path,required=True,help='Existing successful deployment with public export')
    args=parser.parse_args()
    deployment_dir=args.deployment.resolve()
    deployment=json.loads((deployment_dir/'deployment.json').read_text(encoding='utf8'))
    if deployment['status']!='PASS':raise ValueError('Only a successful verified deployment may be rebuilt')
    # Verify the exact public catalog before creating any new environment/container.
    sys.path[:0]=[str(ROOT/'gateway/src'),str(ROOT/'sandbox_tools/src')]
    from chainguard_gateway.audit_console import load_catalog
    load_catalog(deployment_dir/'public/catalog.json')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output=(args.out or ROOT/'results/phase9/rebuilds'/stamp).resolve()
    if output.exists() or not output.is_relative_to(ROOT/'results/phase9'):raise ValueError('New phase9 result directory required')
    output.mkdir(parents=True)
    workspace=ROOT/'.local/phase9-clean'/stamp
    workspace.mkdir(parents=True,exist_ok=False)
    source=workspace/'source';source.mkdir()
    manifest=dict(status='RUNNING',source=str(source),steps=[],
        isolation='New source directory, Python venv, root/dashboard node_modules and no-cache image. Existing Windows/WSL/Docker/Besu and reviewed Linux wheels reused; not a fresh OS or fresh genesis.')
    def save():(output/'rebuild.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf8')
    save()
    ignored=shutil.ignore_patterns('node_modules','__pycache__','.pytest_cache','dist','build','*.key','*.pem','*.sqlite3','*.egg-info')
    try:
        for name in ['gateway','agent','sandbox_tools','evaluation','contracts','spec','config','scripts','tests','docs','dashboard','chain']:
            shutil.copytree(ROOT/name,source/name,ignore=ignored)
        for name in ['AGENTS.md','README.md','.gitignore','.dockerignore','.gitattributes','.env.example','.env.local.example','.node-version','.python-version',
                     'compose.yaml','package.json','package-lock.json','hardhat.config.cjs','pyproject.toml','requirements-dev.lock','requirements-dev.txt']:
            shutil.copyfile(ROOT/name,source/name)
        # Historical public records are unit fixtures only. No original tools/private stores.
        fixtures=['results/phase6/run-06/report.json', 'results/phase3/wheels.json']
        fixtures += [p.relative_to(ROOT).as_posix() for p in (ROOT/'results/phase5/besu-run-01').glob('*.abi.json')]
        fixtures += [next((ROOT/'results/phase8/complete-experiment-01/protocol').glob('case-*.json')).relative_to(ROOT).as_posix()]
        for name in fixtures:
            dest=source/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,dest)
        wheels=json.loads((ROOT/'results/phase3/wheels.json').read_text())
        cache=source/'.local/phase3-wheels';cache.mkdir(parents=True)
        for name,expected in wheels.items():
            original=ROOT/'.local/phase3-wheels'/name
            if hashlib.sha256(original.read_bytes()).hexdigest()!=expected:raise ValueError('Wheel cache mismatch')
            shutil.copyfile(original,cache/name)
        manifest['copied_files']={p.relative_to(source).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in source.rglob('*') if p.is_file() and '.local' not in p.relative_to(source).parts}
        environment={k:v for k,v in os.environ.items() if not k.startswith('CHAINGUARD_LLM_')}
        def command(name,args,cwd=source,timeout=600):
            with (output/(name+'.txt')).open('wb') as log:
                result=subprocess.run(args,cwd=cwd,env=environment,stdout=log,stderr=subprocess.STDOUT,timeout=timeout)
            manifest['steps'].append(dict(name=name,exit_code=result.returncode));save()
            if result.returncode:raise RuntimeError(name+' failed')
        command('new-venv',[sys.executable,'-m','venv',str(source/'.venv')])
        python=str(source/'.venv/Scripts/python.exe')
        command('locked-python',[python,'-m','pip','install','--disable-pip-version-check','-r','requirements-dev.lock'])
        command('editable-python',[python,'-m','pip','install','--disable-pip-version-check','--no-deps','--no-build-isolation','-e','.'])
        command('pip-check',[python,'-m','pip','check'])
        command('root-npm-ci',['npm.cmd','ci','--ignore-scripts','--no-audit','--no-fund'])
        command('pytest',[python,'-m','pytest','-q','--junitxml='+str(output/'pytest.xml')])
        command('hardhat',['npm.cmd','test'])
        command('spec',[python,'scripts/build_specs.py','--check'])
        command('policy',[python,'scripts/freeze_phase3_policy.py','--check'])
        command('dashboard-npm-ci',['npm.cmd','ci','--ignore-scripts','--no-audit','--no-fund'],cwd=source/'dashboard')
        command('dashboard-test',['npm.cmd','test'],cwd=source/'dashboard')
        command('dashboard-build',['npm.cmd','run','build'],cwd=source/'dashboard')
        # Build from the clean source's explicit allowlist, not its parent working tree.
        code="from deploy_phase9 import build_archive; import sys; sys.stdout.buffer.write(build_archive())"
        env=dict(environment,PYTHONPATH=str(source/'scripts'))
        archive=subprocess.run([python,'-c',code],cwd=source,env=env,capture_output=True,check=True).stdout
        image='chainguard/audit-clean:0.9.0'
        prefix=['wsl.exe','-d','Ubuntu','-u','root','--','docker']
        with (output/'clean-image.txt').open('wb') as log:
            result=subprocess.run(prefix+['build','--no-cache','--network','none','-f','dashboard/Dockerfile','-t',image,'-'],input=archive,stdout=log,stderr=subprocess.STDOUT,timeout=300)
        manifest['steps'].append(dict(name='no-cache-image',exit_code=result.returncode));save()
        if result.returncode:raise RuntimeError('Clean image build failed')
        manifest['image_id']=json.loads(subprocess.run(prefix+['image','inspect',image],capture_output=True,check=True).stdout)[0]['Id']
        # Reuse only the public, read-only evidence volume. No private/signer/tool volumes.
        probe="from pathlib import Path; import hashlib; p=Path('/audit/catalog.json'); assert hashlib.sha256(p.read_bytes()).hexdigest()==Path('/audit/catalog.sha256').read_text().strip(); print('Exact public catalog present')"
        command('public-volume-check',prefix+['run','--rm','--network','none','--read-only','--mount','type=volume,src='+deployment['volume']+',dst=/audit,readonly',image,'python','-c',probe])
        name='chainguard-audit-clean-'+stamp.lower()
        try:
            command('clean-start',prefix+['run','-d','--name',name,'--read-only','--network','chainguard_qbft','--cap-drop','ALL',
                '--security-opt','no-new-privileges:true','--pids-limit','128','--memory','512m','--cpus','2',
                '--tmpfs','/tmp:rw,noexec,nosuid,size=16m,uid=10001,gid=10001',
                '--mount','type=volume,src='+deployment['volume']+',dst=/audit,readonly',
                '-p','127.0.0.1:8081:8080',image])
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
            deadline=time.monotonic()+60
            while True:
                try:
                    with opener.open('http://127.0.0.1:8081/health/ready',timeout=3) as response:
                        if json.load(response)['status']=='ready':break
                except (OSError,ValueError):
                    pass
                if time.monotonic()>deadline:raise TimeoutError('Clean audit HTTP readiness timed out')
                time.sleep(.5)
            command('clean-http',[python,'scripts/smoke_audit.py','--url','http://127.0.0.1:8081','--out',str(output/'http.json')],timeout=180)
            command('clean-browser',['node','tests/browser-smoke.mjs','http://127.0.0.1:8081',str(output/'browser.json')],cwd=source/'dashboard',timeout=180)
        finally:
            diagnostic=subprocess.run(prefix+['logs',name],capture_output=True,timeout=20)
            (output/'clean-container.txt').write_bytes(diagnostic.stdout+diagnostic.stderr)
            subprocess.run(prefix+['stop','--time','3',name],capture_output=True,timeout=20)
        manifest.update(status='PASS',finished_at_utc=datetime.now(timezone.utc).isoformat());save()
        print(json.dumps({'status':'PASS','output':str(output)}))
    except Exception as error:
        manifest.update(status='FAIL',failure=type(error).__name__);save();raise


if __name__=='__main__':main()
