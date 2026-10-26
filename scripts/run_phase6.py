"""Real four-Besu + distinct R2 gateway/tool volumes and TLS fault acceptance."""
import argparse
import base64
from datetime import datetime,timezone
from email import policy
from email.parser import BytesParser
import hashlib
import io
import json
import os
from pathlib import Path
import secrets
import ssl
import subprocess
import sys
import tarfile
import time

from eth_account import Account

from run_phase3_container import context_archive
from chain import Chain as ChainOperations,RPC as HostRPC,RpcError,load as load_json

ROOT=Path(__file__).resolve().parents[1]
IMAGE='chainguard/r2-lab:0.6.0'


def dump(path,data):
    path.write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')


def build_context():
    old,names=context_archive()
    result=io.BytesIO()
    extras={'gateway/phase6.Dockerfile','scripts/build_specs.py'}
    extras.update(p.relative_to(ROOT).as_posix() for p in (ROOT/'gateway/tests').glob('test_phase6*.py'))
    extras.update(f'results/phase5/besu-run-01/{name}.abi.json' for name in ['PolicyRegistry','ExecutionRegistry','AuditRegistry'])
    with tarfile.open(fileobj=io.BytesIO(old)) as source,tarfile.open(fileobj=result,mode='w') as target:
        for item in source:
            target.addfile(item,source.extractfile(item))
        for name in sorted(extras-set(names)):
            data=(ROOT/name).read_bytes()
            item=tarfile.TarInfo(name)
            item.mode,item.size,item.mtime=0o644,len(data),0
            target.addfile(item,io.BytesIO(data))
    return result.getvalue(),sorted(set(names)|extras)


def tls_material(directory,distro):
    directory.mkdir(parents=True)
    def wsl_path(path): return '/mnt/'+str(path)[0].lower()+'/'+str(path)[3:].replace('\\','/')
    def openssl(*args):
        result=subprocess.run(['wsl.exe','-d',distro,'-u','root','--exec','openssl',*args],capture_output=True,timeout=40)
        if result.returncode: raise RuntimeError('Local test TLS certificate generation failed')
    openssl('req','-x509','-newkey','rsa:2048','-nodes','-keyout',wsl_path(directory/'ca.key'),'-out',wsl_path(directory/'ca.pem'),'-subj','/CN=ChainGuard Phase6 Test CA','-days','2',
            '-addext','basicConstraints=critical,CA:TRUE','-addext','keyUsage=critical,keyCertSign,cRLSign')
    for name,san,usage in [('gateway-server','DNS:phase6-gateway','serverAuth'),('tool-server','DNS:phase6-tool,DNS:phase6-proxy','serverAuth'),
                           ('gateway-client','DNS:gateway-service','clientAuth'),('tool-client','DNS:tool-service','clientAuth'),('operator','DNS:local-operator','clientAuth')]:
        extension=directory/(name+'.ext')
        extension.write_text('subjectAltName='+san+'\nextendedKeyUsage='+usage+'\nbasicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nsubjectKeyIdentifier=hash\nauthorityKeyIdentifier=keyid,issuer\n',encoding='ascii')
        openssl('req','-new','-newkey','rsa:2048','-nodes','-keyout',wsl_path(directory/(name+'.key')),'-out',wsl_path(directory/(name+'.csr')),'-subj','/CN='+name)
        openssl('x509','-req','-in',wsl_path(directory/(name+'.csr')),'-CA',wsl_path(directory/'ca.pem'),'-CAkey',wsl_path(directory/'ca.key'),'-CAcreateserial',
                '-out',wsl_path(directory/(name+'.pem')),'-days','2','-extfile',wsl_path(extension))


def find_signers(report):
    for file in (ROOT/'.local/phase5').glob('*/accounts.private.json'):
        keys=load_json(file)
        if Account.from_key(keys['requester']).address.lower()==report['publicSigners']['requester'].lower(): return keys
    raise RuntimeError('Original local phase5 signer material missing; restore it, do not regenerate roles')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wsl-distro',default='Ubuntu')
    parser.add_argument('--out',type=Path)
    parser.add_argument('--stop-after',action='store_true',help='Stop only the three new lab containers after evidence; preserve volumes')
    args=parser.parse_args()
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output=(args.out or ROOT/'results/phase6/runs'/stamp).resolve()
    if not output.is_relative_to(ROOT/'results/phase6') or output.exists(): raise RuntimeError('Use a new results/phase6 output subdirectory')
    output.mkdir(parents=True)
    prefix=['wsl.exe','-d',args.wsl_distro,'-u','root','--','docker']
    lab='chainguard-p6-'+secrets.token_hex(5)
    volumes={kind:lab+'-'+kind for kind in ['gateway','tool','qa']}
    containers=dict(volumes)
    created=[]
    report={'status':'RUNNING','recorded_at_utc':datetime.now(timezone.utc).isoformat(),'containers':containers,'volumes':volumes,'network':lab,
            'scope':'real R2 local mailbox; no R3/Agent/front-end'}
    def docker(*command,data=None,timeout=90):
        result=subprocess.run(prefix+list(command),input=data,capture_output=True,timeout=timeout)
        if result.returncode:
            (output/'last-docker.stderr.bin').write_bytes(result.stderr)
            (output/'last-docker.stdout.bin').write_bytes(result.stdout)
            raise RuntimeError('Docker command failed: '+command[0]+'; retained private-free stderr diagnostic')
        return result.stdout
    def lab_command(command,*,timeout=110):
        result=docker('exec',containers['qa'],'python','gateway/integration/phase6_lab.py',command,timeout=timeout)
        (output/(command+'.txt')).write_bytes(result)
        print(result.decode('utf-8').strip(),flush=True)
        return json.loads(result)
    def node_receipts(tx_hash):
        deadline=time.monotonic()+40
        while True:
            rows=[HostRPC(port).call('eth_getTransactionReceipt',[tx_hash]) for port in range(8545,8549)]
            if all(rows):
                assert all(r==rows[0] for r in rows)
                for port,row in zip(range(8545,8549),rows):
                    block=HostRPC(port).call('eth_getBlockByNumber',[row['blockNumber'],False])
                    assert row['blockHash']==block['hash'] and tx_hash in block['transactions']
                return rows
            if time.monotonic()>deadline: raise RuntimeError('Missing committed four-node receipt')
            time.sleep(0.3)
    try:
        ops=ChainOperations(argparse.Namespace(wsl_distro=args.wsl_distro,wsl_user='root'))
        report['before']=ops.health()
        phase5=load_json(ROOT/'results/phase5/besu-run-01/report.json')
        for name,item in phase5['contracts'].items():
            from eth_utils import keccak
            code=HostRPC(8545).call('eth_getCode',[item['address'],'latest'])
            assert '0x'+keccak(bytes.fromhex(code[2:])).hex()==item['codeHash']
        keys=find_signers(phase5)
        archive,names=build_context()
        dump(output/'build-context.json',{'sha256':hashlib.sha256(archive).hexdigest(),'files':names})
        with (output/'build.txt').open('wb') as log:
            build=subprocess.run(prefix+['build','--network','none','-f','gateway/phase6.Dockerfile','-t',IMAGE,'-'],input=archive,stdout=log,stderr=subprocess.STDOUT,timeout=300)
        if build.returncode: raise RuntimeError('Offline phase6 build failed; see build.txt')
        private=ROOT/'.local/phase6'/stamp
        tls=private/'tls'
        tls_material(tls,args.wsl_distro)
        jwt_key=secrets.token_bytes(32)
        to_tool,to_authority=secrets.token_hex(32),secrets.token_hex(32)
        signers={k:v.lower() for k,v in phase5['publicSigners'].items()}
        relay_key=load_json(ROOT/'.local/phase4/accounts.private.json')['sender']
        relayer=Account.from_key(relay_key).address.lower()
        deployment={'chainId':20261026,'contracts':phase5['contracts'],'genesisHash':report['before']['nodes'][0]['genesis_hash'],
                    'validators':report['before']['nodes'][0]['validators']}
        fingerprint=lambda name:hashlib.sha256(ssl.PEM_cert_to_DER_cert((tls/(name+'.pem')).read_text())).hexdigest()
        def files(mapping): return {target:base64.b64encode((tls/source).read_bytes()).decode() for target,source in mapping.items()}
        shared={'ca.pem':'ca.pem'}
        roles={'requester':['REQUESTER'],'agent':['AGENT'],'biz':['BUSINESS_APPROVER'],'security':['SECURITY_APPROVER'],'reconciler':['RECONCILER'],'executor':[]}
        actors=[{'subject':name,'address':signers[name] if name!='executor' else relayer,'organization':'OrgB_Security' if name in ['security','reconciler'] else 'OrgA_Business',
                 'roles':role,'active':True,'allowed_tools':['mail.send'],'resource_scopes':['ORG_A_INTERNAL_MAIL'],'allowed_document_ids':[],
                 'allowed_recipients':['alice@inbox.chainguard.invalid','bob@inbox.chainguard.invalid'],'max_risk':2} for name,role in roles.items()]
        configs={
          'gateway':{'deployment':deployment,'rpc_urls':['http://phase6-proxy:18545','http://phase6-proxy:18547'],'jwt_key':jwt_key.hex(),'relay_key':relay_key,'actors':actors,
            'tool_signer':signers['mailTool'],'authority_fingerprint':fingerprint('tool-client'),'authority_token':to_authority,
            'tool_client':{'url':'https://phase6-proxy:8443','certificate':'gateway-client.pem','key':'gateway-client.key','token':to_tool},
            'files':files({**shared,'server.pem':'gateway-server.pem','server.key':'gateway-server.key','gateway-client.pem':'gateway-client.pem','gateway-client.key':'gateway-client.key'})},
          'tool':{'deployment':deployment,'rpc_urls':['http://phase6-proxy:18546','http://phase6-proxy:18548'],'tool_key':keys['mailTool'],'data_key':secrets.token_hex(32),
            'gateway_fingerprint':fingerprint('gateway-client'),'gateway_token':to_tool,
            'authority_client':{'url':'https://phase6-gateway:8443','certificate':'tool-client.pem','key':'tool-client.key','token':to_authority},
            'files':files({**shared,'server.pem':'tool-server.pem','server.key':'tool-server.key','tool-client.pem':'tool-client.pem','tool-client.key':'tool-client.key'})},
          'qa':{'deployment':deployment,'signers':signers,'signing_keys':{k:keys[k] for k in ['requester','biz','security']},'gateway_fingerprint':fingerprint('gateway-client'),
            'tool_client':{'url':'https://phase6-tool:8443','certificate':'gateway-client.pem','key':'gateway-client.key','token':to_tool},
            'files':files({**shared,'operator.pem':'operator.pem','operator.key':'operator.key','proxy.pem':'tool-server.pem','proxy.key':'tool-server.key',
                           'gateway-client.pem':'gateway-client.pem','gateway-client.key':'gateway-client.key'})}}
        sys.path[:0]=[str(ROOT/'gateway/src'),str(ROOT/'sandbox_tools/src')]
        from chainguard_gateway.identity import issue_token
        configs['qa']['tokens']={name:issue_token(jwt_key,name,lifetime=900) for name in roles}
        docker('network','create','--internal','--label','chainguard.phase=6',lab)
        for kind in ['qa','tool','gateway']:
            docker('volume','create','--label','chainguard.phase=6',volumes[kind])
            mount='type=volume,src='+volumes[kind]+',dst=/sandbox'
            docker('run','--rm','--network','none','--user','0:0','--read-only','--mount',mount,IMAGE,'python','-c',
                   'import os; os.chown("/sandbox",10001,10001); os.chmod("/sandbox",0o700)')
            docker('run','--rm','-i','--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true','--mount',mount,
                   IMAGE,'python','-m','chainguard_gateway.phase6_server','init',kind,data=json.dumps(configs[kind]).encode())
            command=['python','gateway/integration/phase6_lab.py','proxy'] if kind=='qa' else ['python','-m','chainguard_gateway.phase6_server','serve',kind]
            docker('run','-d','--name',containers[kind],'--label','chainguard.phase=6','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true',
                   '--pids-limit','128','--memory','1024m' if kind=='qa' else '512m','--cpus','2','--tmpfs','/tmp:rw,noexec,nosuid,size=32m','--mount',mount,
                   '--network',lab,'--network-alias','phase6-proxy' if kind=='qa' else 'phase6-'+kind,IMAGE,*command)
            created.append(containers[kind])
            if kind=='qa': docker('network','connect','chainguard_qbft',containers[kind])
        # All RPC calls traverse only the test proxy to actual Besu; gateway and tool have distinct configured node pairs.
        lab_command('normal')
        unknown=lab_command('unknown')
        marker={'chainId':20261026,'nonce':int(HostRPC(8545).call('eth_getTransactionCount',[signers['reconciler'],'pending']),16),
                'gasPrice':0,'gas':1000000,'to':bytes.fromhex(deployment['contracts']['AuditRegistry']['address'][2:]),'value':0}
        from chainguard_gateway.chain_rpc import Contract
        marker['data']=Contract('AuditRegistry',deployment['contracts']['AuditRegistry']['address'],None).data('markUnknown',[unknown['action_id'],'0x'+secrets.token_hex(32)])
        signed=Account.sign_transaction(marker,keys['reconciler'])
        marker_hash=HostRPC(8545).call('eth_sendRawTransaction',['0x'+signed.raw_transaction.hex().removeprefix('0x')])
        marker_receipts=node_receipts(marker_hash)
        assert marker_receipts[0]['status']=='0x1'
        dump(output/'mark-unknown-receipt.json',{'hash':marker_hash,'nodes':marker_receipts})
        docker('restart',containers['gateway'])
        time.sleep(2)
        lab_command('recover-unknown')
        lab_command('pending')
        docker('restart',containers['gateway'])
        time.sleep(2)
        lab_command('recover-pending')
        lab_command('prebroadcast')
        docker('restart',containers['gateway'])
        time.sleep(2)
        lab_command('recover-prebroadcast')
        lab_command('tool-outage')
        # Tool restart must retain the original receipt/unique mailbox actionId.
        docker('restart',containers['tool'])
        time.sleep(2)
        lab_command('post-restart')
        acceptance=lab_command('export')
        report['cases']=acceptance['cases']
        report['fault_events']=acceptance['events']
        # Export only synthetic local MIME and public commitments/signatures, never keys/salts or encrypted DB snapshots.
        export_code='''
import base64,json
from Crypto.Cipher import AES
from chainguard_gateway.phase6_server import load
from chainguard_sandbox.storage import Store
from chainguard_gateway.crypto import commit
root,_=load()
store=Store(root)
with store.connect() as db:
 rows=[dict(r) for r in db.execute("SELECT action_id,recipient,mime,mime_sha256 FROM mailbox ORDER BY message_id")]
 for r in rows:r["mime"]=base64.b64encode(r["mime"]).decode()
 verified=[]
 for r in db.execute("SELECT action_id,data FROM chain_mail"):
  raw=r["data"]; cipher=AES.new(store.private_read("data.key"),AES.MODE_GCM,nonce=raw[:16]); cipher.update(r["action_id"].encode())
  original=json.loads(cipher.decrypt_and_verify(raw[32:],raw[16:32]))
  assert commit("result",original["result_salt"],original["result"])==original["receipt"]["result_commit"]
  assert commit("evidence",original["evidence_salt"],original["evidence"])==original["receipt"]["evidence_index_commit"]
  actual=[dict(x) for x in db.execute("SELECT message_id,recipient,mime_sha256 FROM mailbox WHERE action_id=?",(r["action_id"],))]
  assert [str(x["message_id"]) for x in actual]==original["result"]["message_ids"]
  assert [x["recipient"] for x in actual]==original["result"]["delivered_recipients"]
  assert all(x["mime_sha256"]==original["result"]["mime_sha256"] for x in actual)
  verified.append({"action_id":r["action_id"],"result_commit_matches":True,"evidence_commit_matches":True,"mailbox_result_matches":True})
 print(json.dumps({"mailbox":rows,"claims":len(verified),"commitment_checks":verified}))
'''
        mailbox=json.loads(docker('exec',containers['tool'],'python','-c',export_code))
        assert mailbox['claims']==4 and len(mailbox['mailbox'])==4
        counts={}
        for index,row in enumerate(mailbox['mailbox'],1):
            counts[row['action_id']]=counts.get(row['action_id'],0)+1
            mime=base64.b64decode(row.pop('mime'))
            assert hashlib.sha256(mime).hexdigest()==row['mime_sha256']
            parsed=BytesParser(policy=policy.default).parsebytes(mime)
            assert parsed['To']=='alice@inbox.chainguard.invalid'
            assert 'Synthetic local test message.' in parsed.get_content()
            name=f'mail-{index}.eml'
            (output/name).write_bytes(mime)
            row['mime_file']=name
        for name in ['normal','unknown','pending','prebroadcast']: assert counts[report['cases'][name]['action_id']]==1
        assert report['cases']['tool-outage']['action_id'] not in counts
        report['mailbox']=mailbox
        from chainguard_gateway.chain_crypto import recover_receipt,digest
        receipt_domain={'name':'ChainGuard AuditRegistry','version':'1','chainId':'20261026','verifyingContract':deployment['contracts']['AuditRegistry']['address'].lower()}
        for name in ['normal','unknown','pending','prebroadcast']:
            case=report['cases'][name]
            final=case.get('recovered_record',case.get('record'))
            # Signature also verified by both the gateway and AuditRegistry; check independently again here.
            status_code='''
import json
from chainguard_gateway.phase6_server import load
from chainguard_sandbox.storage import Store
from chainguard_sandbox.chain_mail import ChainMailTool
from chainguard_gateway.chain_rpc import Chain
root,c=load()
tool=ChainMailTool(Store(root),Chain(c["deployment"],c["rpc_urls"]),None,(root/"signing.key").read_bytes(),(root/"data.key").read_bytes())
print(json.dumps(tool.status(ACTION_ID)))
'''.replace('ACTION_ID',repr(case['action_id']))
            original=json.loads(docker('exec',containers['tool'],'python','-c',status_code))
            assert original['receipt']==final['receipt']
            assert recover_receipt(original['receipt'],receipt_domain,original['tool_signature'])==signers['mailTool']
            case['tool_signature']=original['tool_signature']
            case['receipt_digest']=digest('ExecutionReceipt',original['receipt'],receipt_domain)
        events=report['fault_events']
        for name in ['normal','unknown','pending','prebroadcast','tool-outage']:
            aid=report['cases'][name]['action_id']
            assert sum(e['event']=='tool_execute_http' and e['action_id']==aid for e in events)==1
        journal_code='''
import json
from chainguard_gateway.phase6_server import load
from chainguard_gateway.chain_store import ChainStore
root,_=load()
with ChainStore(root).connect() as db:
 print(json.dumps({"transactions":[dict(r) for r in db.execute("SELECT action_id,kind,nonce,tx_hash,state FROM chain_transactions")],"events":[json.loads(r[0]) for r in db.execute("SELECT data FROM chain_events WHERE event='INTERNAL_WAIT'")]}))
'''
        journal=json.loads(docker('exec',containers['gateway'],'python','-c',journal_code))
        assert not journal['events'],journal['events']
        report['transactions']=[]
        for index,tx in enumerate(journal['transactions'],1):
            rows=node_receipts(tx['tx_hash'])
            assert rows[0]['status']=='0x1'
            tx['receipt_file']=f'tx-{index:02d}-{tx["kind"]}.json'
            dump(output/tx['receipt_file'],{'hash':tx['tx_hash'],'nodes':rows})
            report['transactions'].append(tx)
        assert len(journal['transactions'])==9 # 5 real reservations; only 4 sends/finalizations.
        assert all(t['state']=='CONFIRMED' for t in journal['transactions'])
        for name in ['normal','unknown','pending','prebroadcast']:
            aid=report['cases'][name]['action_id']
            assert sum(t['action_id']==aid and t['kind']=='audit' for t in journal['transactions'])==1
        pending_id=report['cases']['pending']['action_id']
        pending_hash=next(t['tx_hash'] for t in journal['transactions'] if t['action_id']==pending_id and t['kind']=='audit')
        assert next(e['tx_hash'] for e in events if e['event']=='audit_broadcast_response_lost')==pending_hash
        # Exercise the deployed replay guards with real reverted transactions too.
        from chainguard_gateway.chain_crypto import typed
        from chainguard_gateway.crypto import PROTOCOL,random_id
        from eth_account.messages import encode_typed_data
        execution=Contract('ExecutionRegistry',deployment['contracts']['ExecutionRegistry']['address'],None)
        normal=report['cases']['normal']['record']
        original_tx=HostRPC(8545).call('eth_getTransactionByHash',[normal['reservation_evidence']['tx_hash']])
        reused=dict(normal['intent'],action_id=random_id())
        action_domain={'name':'ChainGuard ExecutionRegistry','version':'1','chainId':'20261026','verifyingContract':execution.address}
        signatures={name:'0x'+Account.sign_message(encode_typed_data(full_message=typed('ActionIntent',reused,action_domain)),keys[name]).signature.hex()
                    for name in ['requester','biz','security']}
        reused_typed={target:reused[source] for source,target in PROTOCOL['json_to_typed']['ActionIntent'].items()}
        nonce_payload=execution.data('reserve',[reused_typed,signatures['requester'],[{'signature':signatures[n]} for n in ['biz','security']]])
        report['replay_transactions']=[]
        for kind,payload in [('action',original_tx['input']),('nonce',nonce_payload)]:
            try:
                HostRPC(8545).call('eth_call',[{'to':execution.address,'data':payload},'latest'])
            except RpcError as error:
                assert error.error.get('data')=='0x'+keccak(text='AlreadyReserved()')[:4].hex(),error.error
            else: raise AssertionError('Replay unexpectedly accepted')
            replay={'chainId':20261026,'nonce':int(HostRPC(8545).call('eth_getTransactionCount',[relayer,'pending']),16),
                    'gasPrice':0,'gas':8000000,'to':bytes.fromhex(execution.address[2:]),'value':0,'data':payload}
            signed=Account.sign_transaction(replay,relay_key)
            tx_hash=HostRPC(8545).call('eth_sendRawTransaction',['0x'+signed.raw_transaction.hex().removeprefix('0x')])
            rows=node_receipts(tx_hash)
            assert rows[0]['status']=='0x0'
            filename='replay-'+kind+'-receipt.json'
            dump(output/filename,{'hash':tx_hash,'nodes':rows,'expected_error':'AlreadyReserved()'})
            report['replay_transactions'].append({'kind':kind,'tx_hash':tx_hash,'receipt_file':filename,'status':'REVERTED','error':'AlreadyReserved()'})
        report['after']=ops.health()
        assert report['after']['common_height']>report['before']['common_height']
        inspections=json.loads(docker('inspect',*created))
        report['isolation']=[{'name':r['Name'],'id':r['Id'],'readonly':r['HostConfig']['ReadonlyRootfs'],'user':r['Config']['User'],
                              'cap_drop':r['HostConfig']['CapDrop'],'security_options':r['HostConfig']['SecurityOpt'],'ports':r['NetworkSettings']['Ports'],
                              'mounts':[{'type':m['Type'],'name':m.get('Name'),'destination':m['Destination']} for m in r['Mounts']]} for r in inspections]
        assert all(r['readonly'] and r['user']=='10001:10001' and 'ALL' in r['cap_drop'] and all(m['type'] in {'volume','tmpfs'} for m in r['mounts']) for r in report['isolation'])
        assert all(not r['State']['OOMKilled'] and r['State']['Running'] for r in inspections)
        report['resources']=[json.loads(line) for line in docker('stats','--no-stream','--format','{{json .}}',*created).decode().splitlines()]
        report['status']='PASS'
        print('Real R2 mail.send acceptance PASS; 4 MIME deliveries, 5 reservations, 4 audit confirmations, UNKNOWN and both broadcast-outage recoveries.',flush=True)
    except BaseException as error:
        report['status']='FAIL'
        report['error']={'type':type(error).__name__,'message':str(error)}
        raise
    finally:
        if created:
            try:
                states=json.loads(docker('inspect',*created,timeout=15))
                report['container_states']=[{'name':r['Name'],'state':r['State']} for r in states]
            except Exception: pass
        for name in created:
            try:
                logs=subprocess.run(prefix+['logs','--tail','120',name],capture_output=True,timeout=10)
                (output/(name+'.txt')).write_bytes(logs.stdout+logs.stderr)
            except Exception: pass
        report['completed_at_utc']=datetime.now(timezone.utc).isoformat()
        dump(output/'report.json',report)
        if report['status']!='PASS' or args.stop_after:
            for name in created:
                subprocess.run(prefix+['stop',name],capture_output=True,timeout=30)
        # Preserve all new private volumes/evidence and the original QBFT network.


if __name__=='__main__': main()
