"""Opt in to 24h mail approval; preserve old chain, identities, records and LOW registries.

Requires the tested mail-window image. No tools or model calls are made by this script.
"""
import argparse
import copy
import json
from pathlib import Path
import secrets
import sys
import time
import rlp
from eth_abi import encode
from eth_account import Account
from eth_account.messages import encode_typed_data
from eth_utils import keccak

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/p) for p in ['scripts','gateway/src','sandbox_tools/src','agent/src']]
from chainguard_gateway.chain_rpc import Chain
from chainguard_gateway.phase10_bridge import DockerBridge
from chainguard_gateway.crypto import label
from chainguard_gateway.phase10_store import OperationsStore
from update_default_tools import require_idle
from run_phase6 import find_signers


def require_mail_idle(jobs,actions):
    action_tasks={r['task_id'] for r in actions}
    # Preserve settled R0 transport UNKNOWN; it has no HIGH reservation to migrate.
    jobs=[j for j in jobs if not (j['state']=='UNKNOWN' and 'mail.send' not in j.get('allowed_tools',['mail.send']) and j.get('grant',{}).get('task_id') not in action_tasks)]
    require_idle(jobs,actions)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    config=a.config.resolve();out=a.out.resolve()
    if not config.is_relative_to(ROOT/'.local/phase10') or out.exists() or not out.is_relative_to(ROOT/'results/lifetime'):raise ValueError('Private runtime and new lifetime results required')
    out.mkdir(parents=True);c=json.loads(config.read_text(encoding='utf8'));b=DockerBridge(c)
    report=dict(status='RUNNING',transactions=[],old_records_preserved=True,LOW_deployment_changed=False)
    def save():(out/'setup.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    save();originals={};stopped=[]
    try:
        if c['image']!='chainguard/mail-window:0.10.8' or c['deployment'].get('mailApprovalWindow'):raise ValueError('Tested image and legacy starting deployment required')
        snapshot=b.snapshot();require_mail_idle(OperationsStore(c['private_root']).jobs(),snapshot)
        original=copy.deepcopy(c['deployment']);chain=Chain(original,[f'http://127.0.0.1:{port}' for port in range(8545,8549)])
        report['before']=chain.healthy();rpc=chain.rpc
        key=json.loads((ROOT/'.local/phase4/accounts.private.json').read_text())['sender'];sender=Account.from_key(key)
        private=config.parent/('mail-window-'+out.name);private.mkdir()
        phase5=json.loads((ROOT/'results/phase5/besu-run-01/report.json').read_text());keys=find_signers(phase5)
        nonce=int(rpc.call('eth_getTransactionCount',[sender.address,'pending']),16)
        predicted='0x'+keccak(rlp.encode([bytes.fromhex(sender.address[2:]),nonce]))[-20:].hex()
        issued=int(time.time());token=secrets.randbits(52)
        message=dict(sourcePolicy=chain.policy.address,mailLifetime=86400,nonce=token,issuedAt=issued,expiresAt=issued+3600)
        domain=dict(name='ChainGuard MailApprovalWindowPolicy',version='1',chainId=original['chainId'],verifyingContract=predicted)
        types={'MailApprovalWindow':[dict(name=n,type=t) for n,t in [('sourcePolicy','address'),('mailLifetime','uint64'),('nonce','uint64'),('issuedAt','uint64'),('expiresAt','uint64')]]}
        signatures=[bytes(Account.sign_message(encode_typed_data(domain,types,message),keys[role]).signature) for role in ['govA','govB']]
        report['window_authorization']=dict(domain=domain,message=message,signers=[Account.from_key(keys[r]).address for r in ['govA','govB']],signatures=['0x'+s.hex() for s in signatures]);save()
        def deploy(name,types,args):
            artifact=json.loads((ROOT/f'artifacts/contracts/{name}.sol/{name}.json').read_text())
            data=artifact['bytecode']+encode(types,args).hex()
            tx=dict(chainId=original['chainId'],nonce=int(rpc.call('eth_getTransactionCount',[sender.address,'pending']),16),gas=8000000,gasPrice=0,value=0,data=data)
            raw=bytes(Account.sign_transaction(tx,key).raw_transaction);tx_hash='0x'+keccak(raw).hex()
            (private/(name+'.transaction.json')).write_text(json.dumps(dict(tx_hash=tx_hash,raw='0x'+raw.hex())))
            item=dict(contract=name,tx_hash=tx_hash,state='PREPARED');report['transactions'].append(item);save()
            if rpc.call('eth_sendRawTransaction',['0x'+raw.hex()])!=tx_hash:raise ValueError('Broadcast hash mismatch')
            deadline=time.monotonic()+45;receipt=None
            while time.monotonic()<deadline:
                receipt=rpc.call('eth_getTransactionReceipt',[tx_hash])
                if receipt:break
                time.sleep(.25)
            if not receipt or receipt['status']!='0x1':raise ValueError('Deployment not confirmed; retain original transaction, do not redeploy blindly')
            receipts=[n.call('eth_getTransactionReceipt',[tx_hash]) for n in chain.nodes]
            if any(r!=receipt for r in receipts):raise ValueError('Four-node receipts disagree')
            code=rpc.call('eth_getCode',[receipt['contractAddress'],'latest'])
            item.update(state='CONFIRMED',receipts=receipts);save()
            return dict(address=receipt['contractAddress'].lower(),codeHash='0x'+keccak(bytes.fromhex(code[2:])).hex(),deployment_tx=tx_hash)
        policy=deploy('MailApprovalWindowPolicy',['address','uint64','uint64','uint64','bytes[]'],[chain.policy.address,token,issued,issued+3600,signatures])
        if policy['address']!=predicted:raise ValueError('Constructor signing domain mismatch')
        n=int(rpc.call('eth_getTransactionCount',[sender.address,'pending']),16)
        predicted_audit='0x'+keccak(rlp.encode([bytes.fromhex(sender.address[2:]),n+1]))[-20:].hex()
        execution=deploy('ExecutionRegistry',['address','address'],[policy['address'],predicted_audit])
        audit=deploy('AuditRegistry',['address','address','uint64'],[policy['address'],execution['address'],0])
        if audit['address']!=predicted_audit:raise ValueError('Immutable audit link mismatch')
        deployment=dict(original,contracts=dict(PolicyRegistry=policy,ExecutionRegistry=execution,AuditRegistry=audit,SourcePolicyRegistry=original['contracts']['PolicyRegistry']),
            mailApprovalWindow=dict(version=1,seconds=86400,source_policy=original['contracts']['PolicyRegistry']['address']),
            legacyDeployments=[original,*original.get('legacyDeployments',[])])
        new=Chain(deployment,[n.url for n in chain.nodes]);report['after']=new.healthy()
        rule=new.policy.call('getEffectiveRule',[label('policy','POLICY_R2_MAIL')]);assert rule['maxLifetime']==86400 and rule['enabled']
        assert chain.policy.call('getEffectiveRule',[label('policy','POLICY_R2_MAIL')])['maxLifetime']==120
        report.update(deployment=deployment,effective_rule=rule);save()
        # Check again after the deployments, before stopping any service.
        require_mail_idle(OperationsStore(c['private_root']).jobs(),b.snapshot())
        read="import json;from chainguard_gateway.phase6_server import load;r,c=load();print(json.dumps(c))"
        for kind in c['containers']:originals[kind]=json.loads(b.docker(['exec',c['containers'][kind],'python','-c',read]))
        backup=config.parent/('runtime.before-mail-window-'+out.name+'.json');backup.write_bytes(config.read_bytes())
        audit_path=Path(c['audit_config']);audit_original=audit_path.read_bytes();(private/'audit.before.json').write_bytes(audit_original)
        for kind in ['gateway','tool']:
            b.docker(['stop',c['containers'][kind]]);stopped.append(kind)
        # Mutate only pinned deployment/domain, never TaskGrants, intents or stored signatures.
        write="import json,sys;from chainguard_gateway.phase6_server import load;r,c=load();v=json.load(sys.stdin);p=r/'runtime.json';bak=r/'runtime.before-mail-window.json';assert not bak.exists();bak.write_bytes(p.read_bytes());q=r/'runtime.mail-window.new';q.write_text(json.dumps(v));q.chmod(0o600);q.replace(p)"
        for kind,old in originals.items():
            updated=copy.deepcopy(old)
            if 'deployment' in updated:updated['deployment']=deployment
            if 'domain' in updated:updated['domain']=new.domain
            # Helper runs on the same private volume; no secrets leave stdio/control plane.
            b.docker(['run','--rm','-i','--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true','--mount','type=volume,src='+c['containers'][kind]+',dst=/sandbox',c['image'],'python','-c',write],updated)
        c['deployment']=deployment;config.write_text(json.dumps(c,indent=2)+'\n',encoding='utf8')
        ac=json.loads(audit_original);ac['deployment']=deployment;audit_path.write_text(json.dumps(ac,indent=2)+'\n',encoding='utf8')
        for kind in reversed(stopped):b.docker(['start',c['containers'][kind]])
        stopped=[];b.last_refresh=0
        for _ in range(40):
            try:
                b.call('requester',{'op':'health'});break
            except Exception:time.sleep(.5)
        else:raise ValueError('Updated service not ready')
        report.update(status='PASS',task_lifetime_seconds=86400,mail_action_max_seconds=86400,old_awaiting_actions_explicitly_not_extended=True);save()
        print(json.dumps(dict(status='PASS',window_seconds=86400,contracts={n:v['address'] for n,v in deployment['contracts'].items()})))
    except Exception as e:
        report.update(status='FAIL',error_type=type(e).__name__,manual_recovery_required=bool(stopped or originals));save()
        # No silent rollback of signing domains once configuration has been changed.
        # Original configs/transactions are retained; stopped services stay closed on partial failure.
        raise


if __name__=='__main__':main()
