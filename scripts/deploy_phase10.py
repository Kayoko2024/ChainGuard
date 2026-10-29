"""Provision persistent R2 UI services using original gateway/tool/core and four Besu."""
import argparse
import base64
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import ssl
import socket
import subprocess
import sys
import time

from run_phase7 import build_context
from phase10_resources import service_limits
from run_phase6 import tls_material,find_signers
from chain import Chain as ChainOperations,load
from eth_account import Account

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'gateway/src'),str(ROOT/'sandbox_tools/src'),str(ROOT/'agent/src')]
from chainguard_gateway.identity import issue_token
from chainguard_gateway.phase10_api import password_hash
from chainguard_gateway.phase10_store import PublicStore


def start_services(config_path,output):
    c=load(config_path)
    args=['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'scripts/start_phase10.ps1'),'-Config',str(config_path)]
    # Persistent child processes must not inherit communicate() anonymous pipes.
    with (output/'start.txt').open('wb') as log:
        p=subprocess.run(args,cwd=ROOT,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,timeout=30)
    if p.returncode: raise RuntimeError('Start services failed')


def main():
    p=argparse.ArgumentParser(); p.add_argument('--out',type=Path,required=True); p.add_argument('--port',type=int,default=8090); p.add_argument('--audit-port',type=int,default=8091)
    a=p.parse_args(); out=a.out.resolve()
    if out.exists() or not out.is_relative_to(ROOT/'results/phase10'): raise ValueError('New phase10 output required')
    if a.port==a.audit_port or not all(1024<=port<=65535 for port in [a.port,a.audit_port]): raise ValueError('Separate local ports required')
    for port in [a.port,a.audit_port]:
        with socket.socket() as check:
            try: check.bind(('127.0.0.1',port))
            except OSError: raise ValueError('Port already in use; restart the existing phase10 config or choose unused ports') from None
    out.mkdir(parents=True)
    private=ROOT/'.local/phase10'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'); private.mkdir(parents=True)
    lab='chainguard-p10-'+secrets.token_hex(5); kinds=['gateway','tool','requester','biz','security','agent']
    containers={k:lab+'-'+k for k in kinds}; image='chainguard/interactive-r2:0.10.0'
    prefix=['wsl.exe','-d','Ubuntu','-u','root','--','docker']
    report={'status':'RUNNING','containers':containers,'image':image,'port':a.port,'audit_port':a.audit_port,'new_business_tasks_created':0}
    def save(): (out/'deployment.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    def docker(*cmd,data=None,timeout=90):
        r=subprocess.run(prefix+list(cmd),input=data,capture_output=True,timeout=timeout)
        if r.returncode:
            (out/'last-docker.stderr.bin').write_bytes(r.stderr); raise RuntimeError('Docker command failed; see diagnostics')
        return r.stdout
    save()
    try:
        ops=ChainOperations(argparse.Namespace(wsl_distro='Ubuntu',wsl_user='root')); ops.wsl_session(); report['before']=ops.wait_healthy()
        with (out/'history-configuration.txt').open('wb') as log:
            history=subprocess.run([sys.executable,str(ROOT/'scripts/enable_audit_history.py'),'--out',str(out/'history')],
                cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,timeout=600)
        if history.returncode: raise RuntimeError('Observer history configuration failed')
        archive,names=build_context()
        (out/'build-context.json').write_text(json.dumps({'files':names,'sha256':hashlib.sha256(archive).hexdigest()},indent=2)+'\n')
        with (out/'build.txt').open('wb') as log:
            r=subprocess.run(prefix+['build','--network','none','-f','agent/phase7.Dockerfile','-t',image,'-'],input=archive,stdout=log,stderr=subprocess.STDOUT,timeout=300)
        if r.returncode: raise RuntimeError('Offline image build failed')
        old=load(ROOT/'results/phase5/besu-run-01/report.json'); keys=find_signers(old); tls=private/'tls'; tls_material(tls,'Ubuntu')
        # A dedicated Agent client cert cannot use the trusted reviewer extension.
        wp=lambda path:'/mnt/'+str(path)[0].lower()+'/'+str(path)[3:].replace('\\','/')
        (tls/'agent.ext').write_text('extendedKeyUsage=clientAuth\nbasicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature\n')
        for cmd in [
            ['req','-new','-newkey','rsa:2048','-nodes','-keyout',wp(tls/'agent.key'),'-out',wp(tls/'agent.csr'),'-subj','/CN=untrusted-agent'],
            ['x509','-req','-in',wp(tls/'agent.csr'),'-CA',wp(tls/'ca.pem'),'-CAkey',wp(tls/'ca.key'),'-CAcreateserial','-out',wp(tls/'agent.pem'),'-days','7','-extfile',wp(tls/'agent.ext')]]:
            r=subprocess.run(['wsl.exe','-d','Ubuntu','-u','root','--exec','openssl',*cmd],capture_output=True,timeout=40)
            if r.returncode: raise RuntimeError('Client TLS generation failed')
        def files(mapping): return {dst:base64.b64encode((tls/src).read_bytes()).decode() for dst,src in mapping.items()}
        fp=lambda name:hashlib.sha256(ssl.PEM_cert_to_DER_cert((tls/name).read_text())).hexdigest()
        signers={k:v.lower() for k,v in old['publicSigners'].items()}; relay=load(ROOT/'.local/phase4/accounts.private.json')['sender']
        signers['executor']=Account.from_key(relay).address.lower()
        deployment={'chainId':20261026,'contracts':old['contracts'],'genesisHash':report['before']['nodes'][0]['genesis_hash'],'validators':report['before']['nodes'][0]['validators']}
        domain={'name':'ChainGuard ExecutionRegistry','version':'1','chainId':'20261026','verifyingContract':old['contracts']['ExecutionRegistry']['address'].lower()}
        jwt=secrets.token_bytes(32); tool_token,authority_token=secrets.token_hex(32),secrets.token_hex(32)
        roles={'requester':['REQUESTER'],'agent':['AGENT'],'biz':['BUSINESS_APPROVER'],'security':['SECURITY_APPROVER'],'executor':[]}
        actors=[{'subject':name,'address':signers[name],'organization':'OrgB_Security' if name=='security' else 'OrgA_Business','roles':role,
            'active':True,'allowed_tools':['mail.send'],'resource_scopes':['ORG_A_INTERNAL_MAIL'],'allowed_document_ids':[],
            'allowed_recipients':['alice@inbox.chainguard.invalid','bob@inbox.chainguard.invalid'],'max_risk':2} for name,role in roles.items()]
        configs={
            'gateway':{'deployment':deployment,'rpc_urls':['http://node1:8545','http://node3:8545'],'jwt_key':jwt.hex(),'relay_key':relay,'actors':actors,
                'tool_signer':signers['mailTool'],'authority_fingerprint':fp('tool-client.pem'),'authority_token':authority_token,'operator_fingerprint':fp('operator.pem'),
                'tool_client':{'url':'https://phase6-tool:8443','certificate':'client.pem','key':'client.key','token':tool_token},
                'files':files({'ca.pem':'ca.pem','server.pem':'gateway-server.pem','server.key':'gateway-server.key','client.pem':'gateway-client.pem','client.key':'gateway-client.key'})},
            'tool':{'deployment':deployment,'rpc_urls':['http://node2:8545','http://node4:8545'],'tool_key':keys['mailTool'],'data_key':secrets.token_hex(32),'tool_signer':signers['mailTool'],
                'gateway_fingerprint':fp('gateway-client.pem'),'gateway_token':tool_token,'read_documents':[],
                'authority_client':{'url':'https://phase6-gateway:8443','certificate':'client.pem','key':'client.key','token':authority_token},
                'files':files({'ca.pem':'ca.pem','server.pem':'tool-server.pem','server.key':'tool-server.key','client.pem':'tool-client.pem','client.key':'tool-client.key'})}}
        for kind in ['requester','biz','security','agent']:
            mapping={'ca.pem':'ca.pem','client.pem':'agent.pem' if kind=='agent' else 'operator.pem','client.key':'agent.key' if kind=='agent' else 'operator.key'}
            material=files(mapping)
            token_map={kind:issue_token(jwt,kind,900)}
            if kind=='requester': token_map['executor']=issue_token(jwt,'executor',900)
            material['tokens.json']=base64.b64encode(json.dumps(token_map).encode()).decode()
            if kind!='agent': material['signing.key']=base64.b64encode(bytes.fromhex(keys[kind].removeprefix('0x'))).decode()
            configs[kind]={'subject':kind,'address':signers[kind],'organization':'OrgB_Security' if kind=='security' else 'OrgA_Business','domain':domain,'files':material}
        for network in [lab+'-agent',lab+'-tools']: docker('network','create','--internal',network)
        for kind in kinds:
            docker('volume','create','--label','chainguard.phase=10',containers[kind]); mount='type=volume,src='+containers[kind]+',dst=/sandbox'
            docker('run','--rm','--network','none','--user','0:0','--read-only','--mount',mount,image,'python','-c',"import os; os.chown('/sandbox',10001,10001); os.chmod('/sandbox',0o700)")
            docker('run','--rm','-i','--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true','--mount',mount,image,
                'python','-m','chainguard_gateway.phase7_server','init',kind if kind in {'gateway','tool'} else 'qa',data=json.dumps(configs[kind]).encode())
            command=['python','-m','chainguard_gateway.phase10_client','gateway'] if kind=='gateway' else ['python','-m','chainguard_gateway.phase7_server','serve','tool'] if kind=='tool' else ['python','-c','import time; time.sleep(31536000)']
            network=lab+'-tools' if kind=='tool' else lab+'-agent'
            docker('run','-d','--name',containers[kind],'--label','chainguard.phase=10','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true',
                '--pids-limit','128',*service_limits(kind),'--cpus','2','--tmpfs','/tmp:rw,noexec,nosuid,size=32m','--mount',mount,
                '--network',network,'--network-alias','phase6-'+kind,image,*command)
            if kind in {'gateway','tool'}: docker('network','connect','chainguard_qbft',containers[kind])
            if kind=='gateway': docker('network','connect','--alias','phase6-gateway',lab+'-tools',containers[kind])
        for _ in range(40):
            try:
                raw=docker('exec','-i',containers['requester'],'python','-m','chainguard_gateway.phase10_client','call',data=b'{"op":"health"}')
                if json.loads(raw)['ok']: break
            except Exception: pass
            time.sleep(.5)
        else: raise RuntimeError('Gateway readiness failed')
        creds={}; access=[]
        for role,org in [('requester','OrgA_Requester'),('biz','OrgA_Business'),('security','OrgB_Security')]:
            password=secrets.token_urlsafe(16); salt=secrets.token_hex(16)
            creds[role]={'salt':salt,'hash':password_hash(password,salt),'organization':org}
            access.append(role+' : '+password)
        (private/'access.local.txt').write_text('ChainGuard local test identities; do not commit/share.\n'+'\n'.join(access)+'\n',encoding='utf8')
        public_dir=ROOT/'.local/phase10-public'/lab; public=PublicStore(public_dir/'actions.sqlite3')
        config={'repo':str(ROOT),'private_root':str(private/'business'),'public_db':str(public.path),'port':a.port,'containers':containers,'image':image,
            'deployment':deployment,'signers':signers,'credentials':creds}
        config_path=private/'runtime.json'; config_path.write_text(json.dumps(config,indent=2)+'\n',encoding='utf8')
        audit={'public_db':str(public.path),'deployment':deployment,'port':a.audit_port,'static':str(ROOT/'dashboard/dist')}
        (public_dir/'audit.json').write_text(json.dumps(audit,indent=2)+'\n',encoding='utf8')
        config['audit_config']=str(public_dir/'audit.json'); config_path.write_text(json.dumps(config,indent=2)+'\n',encoding='utf8')
        for folder in ['console','dashboard']:
            for cmd in [['npm.cmd','ci','--ignore-scripts','--no-audit','--no-fund'],['npm.cmd','run','build']]:
                r=subprocess.run(cmd,cwd=ROOT/folder,capture_output=True,timeout=180)
                (out/(folder+'-'+('install' if cmd[1]=='ci' else 'build')+'.txt')).write_bytes(r.stdout+r.stderr)
                if r.returncode: raise RuntimeError('Frontend build failed')
        start_services(config_path,out)
        report.update(status='PASS',config_path=str(config_path),audit_config=str(public_dir/'audit.json'),
            access_file=str(private/'access.local.txt'),business_url=f'http://127.0.0.1:{a.port}',audit_url=f'http://127.0.0.1:{a.audit_port}',
            deployment=deployment,signers=signers,private_state_in_git_ignored_directory=True)
        save(); print(json.dumps({'status':'PASS','business':report['business_url'],'audit':report['audit_url'],'access_file':report['access_file']}))
    except Exception as error:
        report.update(status='FAIL',error_type=type(error).__name__); save(); raise


if __name__=='__main__': main()
