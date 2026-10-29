"""Upgrade the existing local phase10 containers, preserving volumes and rollback containers."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'gateway/src'),str(ROOT/'sandbox_tools/src'),str(ROOT/'agent/src')]
from run_phase7 import build_context
from phase10_resources import service_limits
from chainguard_gateway.phase10_store import OperationsStore

def retained_name(name,feature,out,kind='before'):
    # Different evidence parents often both use "upgrade-01". Preserve both.
    run=hashlib.sha256(str(Path(out).resolve()).encode()).hexdigest()[:12]
    return f'{name}-{kind}-{feature}-{Path(out).name}-{run}'


def require_unused_names(planned,existing):
    if set(planned)&set(existing):raise ValueError('Retained container name already exists; use a new evidence directory')


def stop_and_retain(docker,name,backup):
    docker(['stop',name])
    try:docker(['rename',name,backup])
    except Exception:
        # Rename can fail before the rollback list is populated.
        docker(['start',name])
        raise


def require_idle(jobs,actions,now=None,*,allow_waiting=False):
    now=time.time() if now is None else now
    busy={'QUEUED','AGENT_RUNNING','RESERVING','RESERVED','EXECUTING','UNKNOWN','EXECUTION_RECORDED'}
    if any(j['state'] in busy for j in jobs) or any(
        r['state'] in busy or not allow_waiting and r['state']=='AWAITING_APPROVAL' and int(r['intent']['expires_at'])>now for r in actions):
        raise ValueError('Active jobs/actions must settle before upgrade')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--apply',action='store_true')
    p.add_argument('--feature',choices=['default','custom','github','github-policy','http','sessions','conversations','mail-window','resilience','performance','read-capability','renewal'],default='default')
    a=p.parse_args();out=a.out.resolve();config=a.config.resolve()
    evidence=ROOT/'results'/('maintenance' if a.feature in {'resilience','performance','read-capability'} else 'lifetime' if a.feature=='mail-window' else 'conversations' if a.feature in {'conversations','renewal'} else 'sessions' if a.feature=='sessions' else 'http-tools' if a.feature=='http' else 'github' if a.feature.startswith('github') else 'custom-tools' if a.feature=='custom' else 'default-tools')
    if out.exists() or not out.is_relative_to(evidence): raise ValueError('New feature evidence output required')
    if not config.is_relative_to(ROOT/'.local/phase10'): raise ValueError('Existing private phase10 config required')
    out.mkdir(parents=True);c=json.loads(config.read_text());prefix=['wsl.exe','-d','Ubuntu','-u','root','--','docker']
    report={'status':'RUNNING','volumes_preserved':True,'chain_redeployed':False,'business_tasks_created':0}
    def save(): (out/'upgrade.json').write_text(json.dumps(report,indent=2)+'\n')
    def docker(args,data=None,timeout=90):
        r=subprocess.run(prefix+args,input=data,capture_output=True,timeout=timeout)
        if r.returncode:
            (out/'docker-error.bin').write_bytes(r.stderr);(out/'docker-output.bin').write_bytes(r.stdout)
            raise RuntimeError('Docker operation failed; retained private-free diagnostics')
        return r.stdout
    originals=[];replacements=[]
    try:
        archive,names=build_context()
        (out/'build-context.json').write_text(json.dumps({'files':names,'sha256':hashlib.sha256(archive).hexdigest()},indent=2))
        image='chainguard/conversation-renewal:0.10.12' if a.feature=='renewal' else 'chainguard/read-capability:0.10.11' if a.feature=='read-capability' else 'chainguard/interactive:0.10.10' if a.feature=='performance' else 'chainguard/resilience:0.10.9' if a.feature=='resilience' else 'chainguard/mail-window:0.10.8' if a.feature=='mail-window' else 'chainguard/conversations:0.10.7' if a.feature=='conversations' else 'chainguard/tool-sessions:0.10.6' if a.feature=='sessions' else 'chainguard/http-tools:0.10.5' if a.feature=='http' else 'chainguard/github-policy:0.10.4' if a.feature=='github-policy' else 'chainguard/github-tools:0.10.3' if a.feature=='github' else 'chainguard/custom-tools:0.10.2' if a.feature=='custom' else 'chainguard/default-tools:0.10.1'
        with (out/'build.txt').open('wb') as log:
            r=subprocess.run(prefix+['build','--network','none','-f','agent/phase7.Dockerfile','-t',image,'-'],input=archive,stdout=log,stderr=subprocess.STDOUT,timeout=300)
        if r.returncode: raise RuntimeError('Build failed')
        report['image_id']=json.loads(docker(['image','inspect',image]))[0]['Id']
        patterns=['test_default_library.py','test_custom_library.py','test_github_library.py','test_http_library.py'] if a.feature in {'http','sessions','conversations','mail-window','resilience','performance','read-capability','renewal'} else ['test_default_library.py','test_custom_library.py','test_github_library.py'] if a.feature.startswith('github') else ['test_default_library.py','test_custom_library.py'] if a.feature=='custom' else ['test_default_library.py']
        raw=docker(['run','--rm','--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true',
            '--memory','512m','--pids-limit','128','--tmpfs','/sandbox:rw,noexec,nosuid,size=64m,mode=0700,uid=10001,gid=10001',image,
            'python','-c',"import unittest,sys; suite=unittest.TestSuite(unittest.defaultTestLoader.discover('sandbox_tools/tests',pattern=p) for p in "+repr(patterns)+"); result=unittest.TextTestRunner(stream=sys.stdout,verbosity=2).run(suite); sys.exit(not result.wasSuccessful())"])
        (out/'sandbox-unit.txt').write_bytes(raw)
        report['sandbox_tests']='PASS'
        if a.apply:
            store=OperationsStore(c['private_root'])
            snapshot=json.loads(docker(['exec','-i',c['containers']['gateway'],'python','-m','chainguard_gateway.phase10_client','snapshot']))
            if not snapshot['ok']: raise ValueError('Original gateway state unavailable')
            # UI scheduler state can lag the authoritative C action state.
            jobs=store.jobs()
            if a.feature in {'http','sessions','conversations','mail-window','resilience','performance','read-capability','renewal'}:
                # A completed R0 transport failure has no C action to reconcile.
                # Keep it UNKNOWN and never rerun it. All C/in-flight guards remain.
                action_tasks={r['task_id'] for r in snapshot['result']}
                settled=[j for j in jobs if j['state']=='UNKNOWN' and 'mail.send' not in j.get('allowed_tools',['mail.send']) and j.get('grant',{}).get('task_id') not in action_tasks]
                report['preserved_read_unknown_jobs']=[j['id'] for j in settled]
                jobs=[j for j in jobs if j not in settled]
            # Transport-only maintenance preserves the deployment/signatures and
            # can retain unexecuted pending approvals; all in-flight HIGH guards stay.
            require_idle(jobs,snapshot['result'],allow_waiting=a.feature in {'resilience','performance','read-capability','renewal'})
            targets=[c['containers']['tool']] if a.feature in {'http','read-capability'} else list(c['containers'].values())
            before=json.loads(docker(['inspect',*targets]))
            planned=[retained_name(item['Name'].lstrip('/'),a.feature,out) for item in before]
            existing=docker(['ps','-a','--format','{{.Names}}']).decode().splitlines()
            require_unused_names(planned,existing)
            (config.parent/('runtime.before-'+a.feature+'-tools-'+out.name+'.json')).write_bytes(config.read_bytes())
            report['containers']=[]
            for item in before:
                name=item['Name'].lstrip('/'); backup=retained_name(name,a.feature,out)
                host=item['HostConfig'];mounts=item['Mounts'];networks=item['NetworkSettings']['Networks']
                if not host['ReadonlyRootfs'] or len(mounts)!=1 or mounts[0]['Type']!='volume' or mounts[0]['Destination']!='/sandbox':
                    raise ValueError('Unexpected existing sandbox topology')
                stop_and_retain(docker,name,backup);originals.append((name,backup))
                # Detach the stopped rollback copy to avoid duplicate DNS aliases.
                for network in networks: docker(['network','disconnect',network,backup])
                first=next(iter(networks))
                args=['create','--name',name,'--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true',
                    '--pids-limit',str(host['PidsLimit']),*service_limits(next(k for k,v in c['containers'].items() if v==name),host['Memory']),'--cpus','2',
                    '--tmpfs','/tmp:rw,noexec,nosuid,size=32m','--mount','type=volume,src='+mounts[0]['Name']+',dst=/sandbox','--network',first]
                for alias in networks[first].get('Aliases') or []: args+=['--network-alias',alias]
                args+=['--label','chainguard.phase=10',image,*item['Config']['Cmd']]
                docker(args);replacements.append(name)
                for network,settings in list(networks.items())[1:]:
                    connect=['network','connect']
                    for alias in settings.get('Aliases') or []: connect+=['--alias',alias]
                    docker(connect+[network,name])
                docker(['start',name])
                report['containers'].append({'name':name,'rollback':backup,'volume':mounts[0]['Name'],'original_image':item['Image']})
            c['image']=image;config.write_text(json.dumps(c,indent=2)+'\n');report['applied']=True
        report['status']='PASS';save();print(json.dumps({'status':'PASS','image':image,'applied':a.apply}))
    except Exception as e:
        report.update(status='FAIL',error_type=type(e).__name__);save()
        # Preserve both versions. Restore original aliases/containers on upgrade failure.
        if originals:
            for name in replacements:
                failed=retained_name(name,a.feature,out,'failed')
                docker(['stop',name]);docker(['rename',name,failed])
                item=next(i for i in before if i['Name'].lstrip('/')==name)
                for network in item['NetworkSettings']['Networks']: docker(['network','disconnect',network,failed])
            for name,backup in originals:
                docker(['rename',backup,name])
                item=next(i for i in before if i['Name'].lstrip('/')==name)
                for network,settings in item['NetworkSettings']['Networks'].items():
                    args=['network','connect']
                    for alias in settings.get('Aliases') or []: args+=['--alias',alias]
                    docker(args+[network,name])
                docker(['start',name])
        raise

if __name__=='__main__':main()
