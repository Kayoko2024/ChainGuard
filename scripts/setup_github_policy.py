"""Deploy additive R0 policy to existing Besu. Keep frozen registries/volumes intact.

Public repository admission only. Private keys stay in ignored local material.
Run update_default_tools --feature github-policy --apply before this command.
"""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import subprocess
import sys
import time
from eth_abi import encode
from eth_account import Account
from eth_account.messages import encode_typed_data
from eth_utils import keccak,to_checksum_address

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'gateway/src'),str(ROOT/'sandbox_tools/src'),str(ROOT/'scripts')]
from chain import RPC
from run_phase6 import find_signers
from chainguard_gateway.chain_rpc import Contract,Chain
from chainguard_gateway.github_policy import RULE_TYPES,RepositoryPolicy,repository_hash
from chainguard_gateway.phase10_bridge import DockerBridge
from chainguard_gateway.phase10_store import OperationsStore
from update_default_tools import require_idle

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    config=a.config.resolve();out=a.out.resolve()
    if not config.is_relative_to(ROOT/'.local/phase10') or out.exists() or not out.is_relative_to(ROOT/'results/github'):raise ValueError('Existing private runtime and a new results/github path required')
    out.mkdir(parents=True);c=json.loads(config.read_text());b=DockerBridge(c);rpc=RPC(8545)
    report={'status':'RUNNING','original_registries_changed':False,'github_token_used':False,'transactions':[]}
    def save():(out/'setup.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    def tx(data,to=None):
        key=json.loads((ROOT/'.local/phase4/accounts.private.json').read_text())['sender'];sender=Account.from_key(key).address
        value=dict(chainId=c['deployment']['chainId'],nonce=int(rpc.call('eth_getTransactionCount',[sender,'pending']),16),gas=5000000,gasPrice=0,value=0,data=data)
        if to:value['to']=to_checksum_address(to)
        signed=Account.sign_transaction(value,key)
        expected='0x'+keccak(signed.raw_transaction).hex()
        item={'tx_hash':expected,'status':'SUBMITTING'};report['transactions'].append(item);save()
        actual=rpc.call('eth_sendRawTransaction',['0x'+signed.raw_transaction.hex()]);assert actual==expected
        item['status']='BROADCAST';save();deadline=time.monotonic()+45
        while time.monotonic()<deadline:
            receipt=rpc.call('eth_getTransactionReceipt',[actual])
            if receipt:break
            time.sleep(.25)
        else:raise RuntimeError('Transaction pending; recover original hash, never resend blindly')
        receipts=[]
        for port in range(8545,8549):
            node=RPC(port)
            while time.monotonic()<deadline:
                other=node.call('eth_getTransactionReceipt',[actual])
                if other:break
                time.sleep(.25)
            assert other==receipt and receipt['status']=='0x1'
            block=node.call('eth_getBlockByNumber',[receipt['blockNumber'],False]);assert block['hash']==receipt['blockHash'] and actual in block['transactions']
            receipts.append(other)
        item.update(status='CONFIRMED',receipts=receipts);save();return receipt
    try:
        if c['image']!='chainguard/github-policy:0.10.4':raise ValueError('Upgrade to tested github-policy image first')
        # Read-only policy recheck/config repair does not restart a running service.
        # UNKNOWN remains unchanged; it is never marked settled to bypass this guard.
        if not c.get('github_policy') or c['github_reader']['image']!=c['image']:
            require_idle(OperationsStore(c['private_root']).jobs(),b.snapshot())
        before=Chain(c['deployment'],['http://127.0.0.1:8545','http://127.0.0.1:8547']).healthy();report['before']=before
        if c.get('github_policy'):
            policy=c['github_policy'];report['already_deployed']=True
        else:
            artifact=json.loads((ROOT/'artifacts/contracts/RepositoryReadPolicy.sol/RepositoryReadPolicy.json').read_text())
            (out/'RepositoryReadPolicy.artifact.json').write_text(json.dumps(artifact,indent=2)+'\n')
            registry=c['deployment']['contracts']['PolicyRegistry']['address']
            receipt=tx(artifact['bytecode']+encode(['address'],[registry]).hex());address=receipt['contractAddress']
            code=rpc.call('eth_getCode',[address,'latest']);assert code!='0x'
            item={'address':address,'codeHash':'0x'+keccak(bytes.fromhex(code[2:])).hex()}
            contract=Contract('RepositoryReadPolicy',address,rpc,abi=artifact['abi'])
            now=int(rpc.call('eth_getBlockByNumber',['latest',False])['timestamp'],16)
            message=dict(repositoryHash=repository_hash('microsoft/vscode'),enabled=True,nonce=1,epoch=1,issuedAt=now,expiresAt=now+3600)
            domain=dict(name='ChainGuard RepositoryReadPolicy',version='1',chainId=c['deployment']['chainId'],verifyingContract=address)
            keys=find_signers(json.loads((ROOT/'results/phase5/besu-run-01/report.json').read_text()))
            signed=encode_typed_data(domain_data=domain,message_types=RULE_TYPES,message_data=message)
            signatures=['0x'+Account.sign_message(signed,keys[k]).signature.hex() for k in ['govA','govB']]
            assert contract.call('ruleDigest',list(message.values()))=='0x'+Account.sign_message(signed,keys['govA']).message_hash.hex()
            report['governance']={'domain':domain,'message':message,'signatures':signatures,'signers':[Account.from_key(keys[k]).address for k in ['govA','govB']]};save()
            governed=tx(contract.data('setRepository',list(message.values())+signatures),address)
            policy=dict(contract=item,deployment=c['deployment'],deployment_tx=receipt['transactionHash'],governance_tx=governed['transactionHash'])
            (config.parent/'runtime.before-github-policy.json').write_bytes(config.read_bytes())
            c['github_policy']=policy;config.write_text(json.dumps(c,indent=2)+'\n')
        # Only public config, no key/token, is installed in these two services.
        write="import json,sys;from pathlib import Path;ROOT;p=r/'github-policy.json';t=p.with_suffix('.new');t.write_text(json.dumps(json.load(sys.stdin)));t.chmod(0o600);t.replace(p)"
        for name,root_code in [(c['containers']['tool'],'from chainguard_gateway.phase6_server import load;r,_=load()'),(c['github_reader']['container'],"r=Path('/sandbox')")]:
            b.docker(['exec','-i',name,'python','-c',write.replace('ROOT',root_code)],policy)
        report['tool_independent_check']=json.loads(b.docker(['exec',c['containers']['tool'],'python','-c',"import json;from chainguard_gateway.phase6_server import load;from chainguard_sandbox.storage import Store;from chainguard_gateway.github_policy import configured_check;r,c=load();print(json.dumps(configured_check(Store(r),'microsoft/vscode#1')))"]))
        reader=c['github_reader'];old=json.loads(b.docker(['inspect',reader['container']]))[0]
        if old['Config']['Image']!=c['image']:
            backup=reader['container']+'-before-'+out.name;report['reader_rollback']=backup;save()
            b.docker(['stop',reader['container']]);b.docker(['rename',reader['container'],backup])
            for network in old['NetworkSettings']['Networks']:b.docker(['network','disconnect',network,backup])
            b.docker(['create','--name',reader['container'],'--network',reader['egress_network'],'--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true','--pids-limit','64','--memory','256m','--cpus','1','--tmpfs','/tmp:rw,noexec,nosuid,size=16m','--mount','type=volume,src='+reader['volume']+',dst=/sandbox',c['image'],'python','-m','chainguard_gateway.github_reader','serve'])
            b.docker(['network','connect','--alias','github-reader',reader['private_network'],reader['container']])
            b.docker(['network','connect','chainguard_qbft',reader['container']]);b.docker(['start',reader['container']])
            c['github_reader']['image']=c['image'];config.write_text(json.dumps(c,indent=2)+'\n')
        proof=RepositoryPolicy(policy,['http://127.0.0.1:8545','http://127.0.0.1:8547'])
        report.update(allowed=proof.check('microsoft/vscode#1'),denied=proof.check('facebook/react#1'),policy=policy)
        assert report['allowed']['allowed'] and not report['denied']['allowed']
        report.update(status='PASS',completed_at_utc=datetime.now(timezone.utc).isoformat());save()
        print(json.dumps({'status':'PASS','contract':policy['contract']['address'],'governance_tx':policy['governance_tx']}))
    except Exception as error:report.update(status='FAIL',error_type=type(error).__name__);save();raise
if __name__=='__main__':main()
