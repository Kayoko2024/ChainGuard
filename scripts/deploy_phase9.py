"""One command: verify public evidence, locked React build, restricted audit Compose."""
import argparse
from datetime import datetime,timezone
import hashlib
import io
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tarfile
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from run_phase3_container import context_archive


def run(command,output,name,*,data=None,timeout=300,cwd=ROOT,env=None):
    result=subprocess.run(command,cwd=cwd,input=data,capture_output=True,timeout=timeout,env=env)
    (output/name).write_bytes(result.stdout+result.stderr)
    if result.returncode:
        raise RuntimeError('Command failed; see '+name)
    return result.stdout


def build_archive():
    original,names=context_archive()
    # Only frozen protocol/runtime and public static assets; no tests or private volumes.
    extras={p.relative_to(ROOT).as_posix() for p in (ROOT/'dashboard/dist').rglob('*') if p.is_file()}
    extras.add('dashboard/Dockerfile')
    extras.update('results/phase5/besu-run-01/'+n+'.abi.json' for n in ['PolicyRegistry','ExecutionRegistry','AuditRegistry'])
    out=io.BytesIO()
    with tarfile.open(fileobj=io.BytesIO(original)) as source,tarfile.open(fileobj=out,mode='w') as target:
        for item in source:
            if item.name.startswith(('gateway/integration/','sandbox_tools/tests/')):continue
            target.addfile(item,source.extractfile(item))
        for name in sorted(extras):
            p=ROOT/name
            if p.is_symlink():raise ValueError('No symlink build input')
            raw=p.read_bytes();info=tarfile.TarInfo(name);info.size=len(raw);info.mode=0o644;info.mtime=0
            target.addfile(info,io.BytesIO(raw))
    return out.getvalue()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle',type=Path,help='Existing complete experiment; old historical state can be unavailable')
    parser.add_argument('--protocol',type=Path,help='Existing recent verified protocol run')
    parser.add_argument('--out',type=Path)
    parser.add_argument('--port',type=int,default=8080)
    parser.add_argument('--no-cache',action='store_true')
    args=parser.parse_args()
    output=(args.out or ROOT/'results/phase9/deployments'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')).resolve()
    if output.exists() or not output.is_relative_to(ROOT/'results/phase9') or not 1024<=args.port<=65535:
        raise ValueError('Choose new phase9 output and local port')
    output.mkdir(parents=True)
    prefix=['wsl.exe','-d','Ubuntu','-u','root','--','docker']
    suffix=secrets.token_hex(5);volume='chainguard-audit-public-'+suffix
    image='chainguard/audit-console:0.9.0'
    manifest=dict(status='RUNNING',read_only=True,volume=volume,project='chainguard-audit-'+suffix,
                  port=args.port,url=f'http://127.0.0.1:{args.port}',started_at_utc=datetime.now(timezone.utc).isoformat())
    def save(): (output/'deployment.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf8')
    save()
    try:
        # Recover the existing network without resetting data; maintain original WSL session.
        from chain import Chain
        ops=Chain(argparse.Namespace(wsl_distro='Ubuntu',wsl_user='root'))
        ops.wsl_session()
        run(prefix+['compose','--env-file',ops.path(ROOT/'.local/phase4/compose.env'),'-f',ops.path(ROOT/'chain/compose.yaml'),'up','-d','--wait'],output,'chain-up.txt',timeout=180)
        ops.wait_healthy()
        if args.bundle and args.protocol:raise ValueError('Choose only one evidence source')
        if args.bundle:
            source_args=['--bundle',str(args.bundle)]
        else:
            protocol=args.protocol
            if protocol is None:
                protocol=ROOT/'results/phase8/phase9'/suffix
                print('Generating fresh REAL protocol/tool/chain evidence',flush=True)
                run([sys.executable,'scripts/run_phase9_protocol.py','--out',str(protocol)],output,'real-demo-run.txt',timeout=1500)
            manifest['protocol_source']=str(protocol)
            source_args=['--protocol',str(protocol)]
        run([sys.executable,'scripts/export_audit.py',*source_args,'--out',str(output/'public')],output,'export.txt')
        run(['npm.cmd','ci','--ignore-scripts','--no-audit','--no-fund'],output,'npm-ci.txt',cwd=ROOT/'dashboard')
        run(['npm.cmd','test'],output,'frontend-tests.txt',cwd=ROOT/'dashboard')
        run(['npm.cmd','run','build'],output,'frontend-build.txt',cwd=ROOT/'dashboard')
        archive=build_archive()
        manifest['build_context_sha256']=hashlib.sha256(archive).hexdigest()
        build=prefix+['build','--network','none','-f','dashboard/Dockerfile','-t',image]
        if args.no_cache:build+=['--no-cache']
        run(build+['-'],output,'docker-build.txt',data=archive)
        manifest['image']=json.loads(run(prefix+['image','inspect',image],output,'image.json'))[0]['Id']
        run(prefix+['volume','create','--label','chainguard.phase=9-public',volume],output,'volume.txt')
        public=io.BytesIO()
        with tarfile.open(fileobj=public,mode='w') as tar:
            for name in ['catalog.json','catalog.sha256']:
                raw=(output/'public'/name).read_bytes();info=tarfile.TarInfo(name);info.size=len(raw);info.mode=0o444;info.mtime=0
                tar.addfile(info,io.BytesIO(raw))
        run(prefix+['run','--rm','-i','--network','none','--user','0:0','--read-only','--mount','type=volume,src='+volume+',dst=/audit',
            image,'python','-c',"import sys,tarfile; t=tarfile.open(fileobj=sys.stdin.buffer,mode='r|'); t.extractall('/audit',filter='data')"],output,'seed-public.txt',data=public.getvalue())
        env=dict(os.environ,CHAINGUARD_AUDIT_VOLUME=volume,CHAINGUARD_AUDIT_PORT=str(args.port),CHAINGUARD_AUDIT_PROJECT=manifest['project'])
        # WSL reads explicit env-file; Windows process env is not assumed to cross WSL.
        envfile=output/'compose.env'
        envfile.write_text('\n'.join(f'{k}={env[k]}' for k in ['CHAINGUARD_AUDIT_VOLUME','CHAINGUARD_AUDIT_PORT','CHAINGUARD_AUDIT_PROJECT'])+'\n')
        def wslpath(p):
            p=p.resolve();return '/mnt/'+p.drive[0].lower()+p.as_posix()[2:]
        compose=prefix+['compose','--env-file',wslpath(envfile),'-f',wslpath(ROOT/'dashboard/compose.yaml')]
        run(compose+['config'],output,'compose-resolved.yaml')
        run(compose+['up','-d','--wait'],output,'compose-up.txt',timeout=120)
        manifest['compose_file']=str(ROOT/'dashboard/compose.yaml')
        manifest['compose_env']=str(envfile)
        ids=run(compose+['ps','-q'],output,'container-id.txt').decode().strip()
        manifest['container_id']=ids
        info=json.loads(run(prefix+['inspect',ids],output,'container-inspect.json'))[0]
        if info['Config']['User']!='10001:10001' or not info['HostConfig']['ReadonlyRootfs'] or len(info['Mounts'])!=1 or info['Mounts'][0]['RW']:
            raise RuntimeError('Restricted audit deployment invariant failed')
        run([sys.executable,'scripts/smoke_audit.py','--url',manifest['url'],'--out',str(output/'smoke.json')],output,'smoke.txt',timeout=180)
        run(['node','tests/browser-smoke.mjs',manifest['url'],str(output/'browser.json')],output,'browser.txt',cwd=ROOT/'dashboard',timeout=180)
        manifest.update(status='PASS',finished_at_utc=datetime.now(timezone.utc).isoformat())
        save();print(json.dumps({'status':'PASS','url':manifest['url'],'output':str(output)}))
    except Exception as error:
        manifest.update(status='FAIL',failure=type(error).__name__);save();raise


if __name__=='__main__':main()
