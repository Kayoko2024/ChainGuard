"""Real fixed-trace Agent -> stage6 gateway -> four Besu -> isolated tools acceptance."""
import argparse
import base64
from datetime import datetime,timezone
import hashlib
import io
import json
from pathlib import Path
import secrets
import ssl
import subprocess
import sys
import tarfile

from eth_account import Account
from run_phase6 import ROOT,build_context as phase6_context,tls_material,find_signers
from chain import Chain as ChainOperations,RPC,load

IMAGE='chainguard/agent-lab:0.7.0'


def build_context():
    old,names=phase6_context(); out=io.BytesIO()
    extra={p.relative_to(ROOT).as_posix() for p in (ROOT/'agent').rglob('*') if p.is_file() and p.suffix in {'.py','.json','.Dockerfile'}}
    extra.add('agent/phase7.Dockerfile')
    with tarfile.open(fileobj=io.BytesIO(old)) as source,tarfile.open(fileobj=out,mode='w') as target:
        for item in source: target.addfile(item,source.extractfile(item))
        for name in sorted(extra-set(names)):
            raw=(ROOT/name).read_bytes(); item=tarfile.TarInfo(name); item.size=len(raw); item.mode=0o644; item.mtime=0
            target.addfile(item,io.BytesIO(raw))
    return out.getvalue(),sorted(set(names)|extra)


def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--out',type=Path,required=True); parser.add_argument('--stop-after',action='store_true')
    parser.add_argument('--fixture',type=Path,default=Path('agent/fixtures/phase7.json'))
    args=parser.parse_args(); output=args.out.resolve()
    fixture_path=args.fixture.resolve()
    if not fixture_path.is_relative_to(ROOT/'agent/fixtures') or fixture_path.suffix!='.json': raise ValueError('Explicit test fixture required')
    fixture_name=fixture_path.relative_to(ROOT).as_posix()
    if output.exists() or not output.is_relative_to(ROOT/'results/phase7'): raise ValueError('Choose a new results/phase7 directory')
    output.mkdir(parents=True)
    prefix=['wsl.exe','-d','Ubuntu','-u','root','--','docker']
    lab='chainguard-p7-'+secrets.token_hex(5)
    containers={k:lab+'-'+k for k in ['gateway','tool','operator','runner']}
    created=[]
    report={'status':'RUNNING','mode':'fixed_trace','llm_sample_count':0,'attack_success':None,'real_llm_attack_test_completed':False,
        'containers':containers,'volumes':containers,'cases':[]}
    def dump(name,value): (output/name).write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
    def docker(*cmd,data=None,timeout=90):
        result=subprocess.run(prefix+list(cmd),input=data,capture_output=True,timeout=timeout)
        if result.returncode:
            (output/'last-docker.stderr.bin').write_bytes(result.stderr); (output/'last-docker.stdout.bin').write_bytes(result.stdout)
            raise RuntimeError('Docker '+cmd[0]+' failed; see retained diagnostics')
        return result.stdout or result.stderr
    def command(kind,cmd,body=None,timeout=90):
        result=docker('exec','-i',containers[kind],'python','agent/integration/lab.py',cmd,data=json.dumps(body).encode() if body else None,timeout=timeout)
        return json.loads(result)
    try:
        operations=ChainOperations(argparse.Namespace(wsl_distro='Ubuntu',wsl_user='root'))
        report['before']=operations.health()
        old=load(ROOT/'results/phase5/besu-run-01/report.json'); keys=find_signers(old)
        fixture=load(fixture_path); report['fixture_file']=fixture_name
        report['fixture_sha256']=hashlib.sha256(fixture_path.read_bytes()).hexdigest()
        report['provenance']=fixture.get('provenance')
        archive,names=build_context(); dump('build-context.json',{'sha256':hashlib.sha256(archive).hexdigest(),'files':names})
        with (output/'build.txt').open('wb') as log:
            result=subprocess.run(prefix+['build','--network','none','-f','agent/phase7.Dockerfile','-t',IMAGE,'-'],input=archive,stdout=log,stderr=subprocess.STDOUT,timeout=300)
        if result.returncode: raise RuntimeError('Offline build failed')
        unit=docker('run','--rm','--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true',
            '--memory','512m','--pids-limit','128','--tmpfs','/sandbox:rw,noexec,nosuid,size=64m,mode=0700,uid=10001,gid=10001',
            IMAGE,'python','-m','unittest','discover','-s','sandbox_tools/tests','-p','test_read_broker.py','-v')
        (output/'read-broker-unit.txt').write_bytes(unit)
        stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'); private=ROOT/'.local/phase7'/stamp
        tls=private/'tls'; tls_material(tls,'Ubuntu')
        wsl=lambda p:'/mnt/'+str(p)[0].lower()+'/'+str(p)[3:].replace('\\','/')
        def openssl(*cmd):
            result=subprocess.run(['wsl.exe','-d','Ubuntu','-u','root','--exec','openssl',*cmd],capture_output=True,timeout=40)
            if result.returncode: raise RuntimeError('Agent test certificate generation failed')
        (tls/'agent.ext').write_text('extendedKeyUsage=clientAuth\nbasicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature\n',encoding='ascii')
        openssl('req','-new','-newkey','rsa:2048','-nodes','-keyout',wsl(tls/'agent.key'),'-out',wsl(tls/'agent.csr'),'-subj','/CN=untrusted-agent')
        openssl('x509','-req','-in',wsl(tls/'agent.csr'),'-CA',wsl(tls/'ca.pem'),'-CAkey',wsl(tls/'ca.key'),'-CAcreateserial','-out',wsl(tls/'agent.pem'),'-days','2','-extfile',wsl(tls/'agent.ext'))
        fp=lambda name:hashlib.sha256(ssl.PEM_cert_to_DER_cert((tls/name).read_text())).hexdigest()
        def files(mapping): return {dst:base64.b64encode((tls/src).read_bytes()).decode() for dst,src in mapping.items()}
        signers={k:v.lower() for k,v in old['publicSigners'].items()}
        relay_key=load(ROOT/'.local/phase4/accounts.private.json')['sender']; relayer=Account.from_key(relay_key).address.lower()
        jwt=secrets.token_bytes(32); tool_token,authority_token=secrets.token_hex(32),secrets.token_hex(32)
        sys.path[:0]=[str(ROOT/'gateway/src'),str(ROOT/'sandbox_tools/src')]
        from chainguard_gateway.identity import issue_token
        roles={'requester':['REQUESTER'],'agent':['AGENT'],'biz':['BUSINESS_APPROVER'],'security':['SECURITY_APPROVER'],'executor':[]}
        actors=[{'subject':n,'address':signers[n] if n!='executor' else relayer,'organization':'OrgB_Security' if n=='security' else 'OrgA_Business',
            'roles':r,'active':True,'allowed_tools':['mail.send'],'resource_scopes':['ORG_A_INTERNAL_MAIL'],'allowed_document_ids':[],
            'allowed_recipients':['alice@inbox.chainguard.invalid','bob@inbox.chainguard.invalid'],'max_risk':2} for n,r in roles.items()]
        deployment={'chainId':20261026,'contracts':old['contracts'],'genesisHash':report['before']['nodes'][0]['genesis_hash'],'validators':report['before']['nodes'][0]['validators']}
        configs={
            'gateway':{'deployment':deployment,'rpc_urls':['http://node1:8545','http://node3:8545'],'jwt_key':jwt.hex(),'relay_key':relay_key,'actors':actors,
                'tool_signer':signers['mailTool'],'authority_fingerprint':fp('tool-client.pem'),'authority_token':authority_token,'operator_fingerprint':fp('operator.pem'),
                'tool_client':{'url':'https://phase6-tool:8443','certificate':'client.pem','key':'client.key','token':tool_token},
                'files':files({'ca.pem':'ca.pem','server.pem':'gateway-server.pem','server.key':'gateway-server.key','client.pem':'gateway-client.pem','client.key':'gateway-client.key'})},
            'tool':{'deployment':deployment,'rpc_urls':['http://node2:8545','http://node4:8545'],'tool_key':keys['mailTool'],'data_key':secrets.token_hex(32),
                'gateway_fingerprint':fp('gateway-client.pem'),'gateway_token':tool_token,'read_documents':fixture['documents'],
                'authority_client':{'url':'https://phase6-gateway:8443','certificate':'client.pem','key':'client.key','token':authority_token},
                'files':files({'ca.pem':'ca.pem','server.pem':'tool-server.pem','server.key':'tool-server.key','client.pem':'tool-client.pem','client.key':'tool-client.key'})},
            'operator':{'fixture_file':fixture_name,'tokens':{n:issue_token(jwt,n,lifetime=900) for n in roles if n!='agent'},'signing_keys':{n:keys[n] for n in ['requester','biz','security']},
                'agent_address':signers['agent'],'domain':{'name':'ChainGuard ExecutionRegistry','version':'1','chainId':'20261026','verifyingContract':old['contracts']['ExecutionRegistry']['address'].lower()},
                'files':files({'ca.pem':'ca.pem','client.pem':'operator.pem','client.key':'operator.key'})},
            'runner':{'mode':'fixed_trace','fixture_file':fixture_name,'agent_token':issue_token(jwt,'agent',lifetime=900),
                'files':files({'ca.pem':'ca.pem','client.pem':'agent.pem','client.key':'agent.key'})}}
        for network in [lab+'-agent',lab+'-tools']: docker('network','create','--internal',network)
        for kind in ['gateway','tool','operator','runner']:
            docker('volume','create',containers[kind]); mount='type=volume,src='+containers[kind]+',dst=/sandbox'
            docker('run','--rm','--network','none','--user','0:0','--read-only','--mount',mount,IMAGE,'python','-c','import os; os.chown("/sandbox",10001,10001); os.chmod("/sandbox",0o700)')
            docker('run','--rm','-i','--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true','--mount',mount,
                IMAGE,'python','-m','chainguard_gateway.phase7_server','init',kind if kind in {'gateway','tool'} else 'qa',data=json.dumps(configs[kind]).encode())
            if kind in {'gateway','tool'}: cmd=['python','-m','chainguard_gateway.phase7_server','serve',kind]
            elif kind=='operator': cmd=['python','agent/integration/lab.py','operator']
            else: cmd=['python','-c','import time; time.sleep(86400)']
            network=lab+'-tools' if kind=='tool' else lab+'-agent'
            alias='phase6-'+kind if kind in {'tool','gateway'} else kind
            docker('run','-d','--name',containers[kind],'--label','chainguard.phase=7','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true',
                '--pids-limit','128','--memory','512m','--cpus','2','--tmpfs','/tmp:rw,noexec,nosuid,size=32m','--mount',mount,'--network',network,'--network-alias',alias,IMAGE,*cmd)
            created.append(containers[kind])
            if kind in {'gateway','tool'}: docker('network','connect','chainguard_qbft',containers[kind])
            if kind=='gateway': docker('network','connect','--alias','phase6-gateway',lab+'-tools',containers[kind])
        import time
        for _ in range(80):
            try:
                command('operator','health')
                break
            except RuntimeError: time.sleep(0.25)
        else: raise RuntimeError('Gateway readiness deadline exceeded')
        tasks=command('operator','prepare')
        for name,item in tasks.items():
            grant_code='''
import json,sys
from chainguard_gateway.phase6_server import load
from chainguard_sandbox.storage import Store
from chainguard_sandbox.read_broker import ReadBroker
root,c=load(); store=Store(root); value=json.load(sys.stdin)
ReadBroker(store).grant(store.private_read('operator.key').decode(),value['task_id'],value['agent'],[value['source']],int(value['expires_at']))
print('granted')
'''
            docker('exec','-i',containers['tool'],'python','-c',grant_code,data=json.dumps(dict(item,agent=signers['agent'])).encode())
            result=command('runner','run',{'case_id':name,'task_id':item['task_id']})
            report['cases'].append(result); dump(name+'.json',result)
            print(name+': PASS',flush=True)
        # Repeat exact trace after runner restart: persisted results, no second mail.
        first=fixture['cases'][0]['case_id']
        docker('restart',containers['runner']); command('runner','run',{'case_id':first,'task_id':tasks[first]['task_id']})
        normal=report['cases'][0]['result']['calls'][-1]['result']['record']
        chain_network=json.loads(docker('network','inspect','chainguard_qbft'))[0]
        node1=next(n for n in chain_network['Containers'].values() if 'node1' in n['Name'])['IPv4Address'].split('/')[0]
        tool_network=json.loads(docker('inspect',containers['tool']))[0]['NetworkSettings']['Networks']
        tool_ip=tool_network[lab+'-tools']['IPAddress']
        report['boundaries']=command('runner','boundaries',{'task_id':tasks[first]['task_id'],'action_id':normal['action_id'],
            'blocked_addresses':[['node1',node1,8545],['tool',tool_ip,8443]]})
        events=command('runner','events')
        for filename,selected in [('agent_attempts.jsonl',[e for e in events if e['event']=='AGENT_ATTEMPT']),('policy_decisions.jsonl',[e for e in events if e['event']=='POLICY_RESULT'])]:
            (output/filename).write_text(''.join(json.dumps(e)+'\n' for e in selected),encoding='utf-8')
        export='''
import base64,json
from chainguard_gateway.phase6_server import load
from chainguard_sandbox.storage import Store
from chainguard_sandbox.resources import Resources
root,c=load(); store=Store(root)
with store.connect() as db:
 rows=[dict(r) for r in db.execute('SELECT message_id,action_id,recipient,mime,mime_sha256 FROM mailbox ORDER BY message_id')]
 for r in rows:r['mime']=base64.b64encode(r['mime']).decode()
 reads=[dict(r) for r in db.execute("SELECT action_id,tool_name,state FROM executions WHERE tool_name='doc.read'")]
 documents=[]
 for item in c['read_documents']:
  document=Resources(store).lookup(db,item['doc_id']); data=Resources(store).read_verified(document)
  documents.append({'doc_id':item['doc_id'],'sha256':document['sha256'],'still_exists':True})
 print(json.dumps({'mailbox':rows,'reads':reads,'documents':documents,
    'delete_executions':db.execute("SELECT count(*) FROM executions WHERE tool_name='doc.delete'").fetchone()[0]}))
'''
        effects=json.loads(docker('exec',containers['tool'],'python','-c',export))
        assert len(effects['mailbox'])==len(tasks) and len(effects['reads'])==len(tasks) and effects['delete_executions']==0
        assert all(m['recipient']=='alice@inbox.chainguard.invalid' for m in effects['mailbox'])
        for index,mail in enumerate(effects['mailbox'],1):
            raw=base64.b64decode(mail.pop('mime')); assert hashlib.sha256(raw).hexdigest()==mail['mime_sha256']
            mail['mime_file']=f'mail-{index}.eml'; (output/mail['mime_file']).write_bytes(raw)
        report['tool_effects']=effects; report['sandbox_attack_effect_observed']=False
        actual=[dict(m,tool_name='mail.send',tool_executed=True,agent_attempted_tool=False,policy_verdict=None,attack_success=None) for m in effects['mailbox']]
        (output/'tool_effects.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in actual),encoding='utf-8')
        report['transactions']=[]
        for case in report['cases']:
            record=case['result']['calls'][-1]['result']['record']
            assert sum(m['action_id']==record['action_id'] for m in effects['mailbox'])==1
            for kind in ['reservation_evidence','finalization_evidence']:
                evidence=record[kind]; receipts=[RPC(p).call('eth_getTransactionReceipt',[evidence['tx_hash']]) for p in range(8545,8549)]
                assert all(r==receipts[0] and r['status']=='0x1' for r in receipts)
                for p,r in zip(range(8545,8549),receipts):
                    block=RPC(p).call('eth_getBlockByNumber',[r['blockNumber'],False])
                    assert block['hash']==r['blockHash'] and evidence['tx_hash'] in block['transactions']
                filename=case['case_id']+'-'+kind+'.json'; dump(filename,{'hash':evidence['tx_hash'],'nodes':receipts})
                report['transactions'].append({'case_id':case['case_id'],'kind':kind,'hash':evidence['tx_hash'],'receipt_file':filename})
        report['after']=operations.health()
        report['isolation']=json.loads(docker('inspect',*created))
        # Do not export Config.Env or any runtime configuration; only public isolation evidence.
        report['isolation']=[{'name':r['Name'],'id':r['Id'],'user':r['Config']['User'],'readonly':r['HostConfig']['ReadonlyRootfs'],
            'networks':list(r['NetworkSettings']['Networks']),'mounts':[{'type':m['Type'],'name':m.get('Name'),'destination':m['Destination']} for m in r['Mounts']],
            'cap_drop':r['HostConfig']['CapDrop'],'oom':r['State']['OOMKilled']} for r in report['isolation']]
        assert all(r['user']=='10001:10001' and r['readonly'] and not r['oom'] and 'ALL' in r['cap_drop'] for r in report['isolation'])
        report['status']='PASS'; print(f'Fixed trace acceptance PASS; {len(tasks)} real local MIME, {len(report["transactions"])} Besu transactions; real LLM attack testing NOT COMPLETED.',flush=True)
    except BaseException as error:
        report['status']='FAIL'; report['error']={'type':type(error).__name__,'message':str(error)}; raise
    finally:
        for name in created:
            log=subprocess.run(prefix+['logs','--tail','100',name],capture_output=True,timeout=15)
            (output/(name+'.txt')).write_bytes(log.stdout+log.stderr)
        report['completed_at_utc']=datetime.now(timezone.utc).isoformat(); dump('report.json',report)
        if report['status']!='PASS' or args.stop_after:
            for name in created: subprocess.run(prefix+['stop','--timeout','2',name],capture_output=True,timeout=15)


if __name__=='__main__': main()
