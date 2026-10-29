"""Add an isolated public-GitHub-only egress service; preserve original tool networks/keys."""
import argparse
import json
from pathlib import Path
import secrets
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    config=a.config.resolve();out=a.out.resolve()
    if not config.is_relative_to(ROOT/'.local/phase10') or out.exists() or not out.is_relative_to(ROOT/'results/github'):raise ValueError('Existing private runtime and new GitHub results path required')
    out.mkdir(parents=True);c=json.loads(config.read_text());prefix=['wsl.exe','-d','Ubuntu','-u','root','--','docker']
    def docker(args,data=None):
        r=subprocess.run(prefix+args,input=json.dumps(data).encode() if data is not None else None,capture_output=True,timeout=45)
        if r.returncode:(out/'docker-error.txt').write_bytes(r.stderr);raise RuntimeError('Docker setup failed; diagnostics retained')
        return r.stdout
    report={'status':'RUNNING','published_ports':False,'chain_redeployed':False,'mail_tool_direct_egress_added':False}
    try:
        # Fail before creating networks/volumes when called before the image upgrade.
        docker(['run','--rm','--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true',c['image'],'python','-c','import chainguard_gateway.github_reader'])
        if c.get('github_reader'):
            docker(['start',c['github_reader']['container']])
            report.update(status='PASS',already_configured=True,reader=c['github_reader'])
        else:
            name='chainguard-github-'+secrets.token_hex(5);private=name+'-private';egress=name+'-egress';token=secrets.token_hex(32)
            docker(['network','create','--internal',private]);docker(['network','create',egress]);docker(['volume','create',name])
            mount='type=volume,src='+name+',dst=/sandbox';image=c['image']
            docker(['run','--rm','--network','none','--user','0:0','--read-only','--mount',mount,image,'python','-c',"import os; os.chown('/sandbox',10001,10001); os.chmod('/sandbox',0o700)"])
            docker(['run','--rm','-i','--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true','--mount',mount,image,'python','-m','chainguard_gateway.github_reader','init'],{'token':token})
            docker(['exec','-i',c['containers']['tool'],'python','-c',"import sys,json; from chainguard_gateway.phase6_server import load; r,c=load(); p=r/'github-reader.json'; f=p.open('x'); json.dump(json.load(sys.stdin),f); f.close(); p.chmod(0o600)"],{'token':token})
            docker(['create','--name',name,'--network',egress,'--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true','--pids-limit','64','--memory','256m','--cpus','1','--tmpfs','/tmp:rw,noexec,nosuid,size=16m','--mount',mount,image,'python','-m','chainguard_gateway.github_reader','serve'])
            docker(['network','connect','--alias','github-reader',private,name]);docker(['network','connect',private,c['containers']['tool']]);docker(['start',name])
            reader={'container':name,'volume':name,'private_network':private,'egress_network':egress,'image':image}
            c['github_reader']=reader;config.write_text(json.dumps(c,indent=2)+'\n')
            report.update(status='PASS',reader=reader,token_in_tool_and_reader_private_volumes_only=True)
        docker(['exec',report['reader']['container'],'python','-c',"import socket,time\nfor attempt in range(20):\n try:\n  s=socket.create_connection(('127.0.0.1',8080),timeout=1);s.close();break\n except OSError:time.sleep(.25)\nelse:raise RuntimeError('GitHub reader startup failed')"])
        report['listener_ready']=True
    except Exception as error:report.update(status='FAIL',error_type=type(error).__name__);raise
    finally:(out/'setup.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'reader':report['reader']['container']}))
if __name__=='__main__':main()
