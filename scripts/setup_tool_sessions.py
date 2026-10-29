"""Deploy additive tool/session/audit contracts and public pins; preserve original registries."""
import argparse
import json
from pathlib import Path
import secrets
import sys
import time
from eth_abi import encode
from eth_account import Account
from eth_utils import keccak

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'gateway/src'),str(ROOT/'sandbox_tools/src'),str(ROOT/'agent/src'),str(ROOT/'scripts')]
from chain import RPC
from chainguard_gateway.chain_rpc import Chain
from chainguard_gateway.phase10_bridge import DockerBridge
from chainguard_gateway.crypto import label

def setup(config,out,*,conversation=False,review_builtins=False):
    config=config.resolve();out=out.resolve()
    if not config.is_relative_to(ROOT/'.local/phase10') or out.exists() or not out.is_relative_to(ROOT/'results'/('conversations' if conversation else 'sessions')):raise ValueError('Private runtime and new feature results directory required')
    out.mkdir(parents=True);c=json.loads(config.read_text(encoding='utf8'));b=DockerBridge(c)
    if c['image']!=('chainguard/conversations:0.10.7' if conversation else 'chainguard/tool-sessions:0.10.6'):raise ValueError('Run tested feature upgrade first')
    report=dict(status='RUNNING',transactions=[],original_registries_changed=False)
    def save():(out/'setup.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    save()
    rpc=RPC(8545);chain=Chain(c['deployment'],[f'http://127.0.0.1:{p}' for p in range(8545,8549)])
    private=config.parent/'tool-sessions.private.json'
    if not private.exists():
        with private.open('x',encoding='utf8') as f:json.dump(dict(anchor=secrets.token_hex(32),review_relay=secrets.token_hex(32)),f)
    material=json.loads(private.read_text());publisher=Account.from_key(material['anchor']).address.lower()
    if conversation and 'conversation_anchor' not in material:
        material['conversation_anchor']=secrets.token_hex(32)
        private.write_text(json.dumps(material),encoding='utf8')
    def deploy(name,args):
        artifact=json.loads((ROOT/f'artifacts/contracts/{name}.sol/{name}.json').read_text())
        key=json.loads((ROOT/'.local/phase4/accounts.private.json').read_text())['sender'];account=Account.from_key(key)
        data=artifact['bytecode']+args.hex()
        tx=dict(chainId=c['deployment']['chainId'],nonce=int(rpc.call('eth_getTransactionCount',[account.address,'pending']),16),gas=5000000,gasPrice=0,value=0,data=data)
        raw=bytes(Account.sign_transaction(tx,key).raw_transaction);tx_hash='0x'+keccak(raw).hex()
        item=dict(contract=name,tx_hash=tx_hash,state='PREPARED',raw_transaction='0x'+raw.hex());report['transactions'].append(item);save()
        assert rpc.call('eth_sendRawTransaction',['0x'+raw.hex()])==tx_hash
        deadline=time.monotonic()+45;receipt=None
        while time.monotonic()<deadline:
            receipt=rpc.call('eth_getTransactionReceipt',[tx_hash])
            if receipt:break
            time.sleep(.25)
        if not receipt:raise RuntimeError('Pending original deployment; restore using retained same raw transaction/hash')
        assert receipt['status']=='0x1';receipts=[]
        for node in chain.nodes:
            r=node.call('eth_getTransactionReceipt',[tx_hash]);assert r==receipt;receipts.append(r)
        code=rpc.call('eth_getCode',[receipt['contractAddress'],'latest'])
        item.update(state='CONFIRMED',receipts=receipts);save()
        return dict(address=receipt['contractAddress'].lower(),codeHash='0x'+keccak(bytes.fromhex(code[2:])).hex(),deployment_tx=tx_hash)
    try:
        report['before']=chain.healthy()
        policy=c.get('tool_sessions')
        if not policy:
            registry=deploy('ToolAdmissionRegistry',encode(['address','bytes32'],[c['deployment']['contracts']['PolicyRegistry']['address'],bytes.fromhex(label('org','OrgB_Security')[2:])]))
            anchor=deploy('LowRiskAuditAnchor',encode(['address'],[publisher]))
            policy=dict(deployment=c['deployment'],registry=registry,anchor=anchor,batch_seconds=300,batch_size=50)
            (config.parent/'runtime.before-tool-sessions.json').write_bytes(config.read_bytes())
            c['tool_sessions']=policy;config.write_text(json.dumps(c,indent=2)+'\n',encoding='utf8')
        if conversation and not policy.get('conversation'):
            policy['conversation']=deploy('ConversationSessionRegistry',encode(['address','address'],[c['deployment']['contracts']['PolicyRegistry']['address'],Account.from_key(material['conversation_anchor']).address]))
            c['tool_sessions']=policy;config.write_text(json.dumps(c,indent=2)+'\n',encoding='utf8')
        code="import json,sys;from chainguard_gateway.phase6_server import load;r,c=load();p=r/'tool-sessions.json';t=p.with_suffix('.new');t.write_text(json.dumps(json.load(sys.stdin)));t.chmod(0o600);t.replace(p)"
        for kind in ['gateway','tool','requester','biz','security']:
            b.docker(['exec','-i',c['containers'][kind],'python','-c',code],policy)
        keycode="import json,sys,os;from chainguard_gateway.phase6_server import load;r,c=load();v=json.load(sys.stdin);[( (r/n).write_bytes(bytes.fromhex(k)),os.chmod(r/n,0o600)) for n,k in v.items() if not (r/n).exists()]"
        keys={'session-anchor.key':material['anchor'],'session-review-relay.key':material['review_relay']}
        if conversation:keys['conversation-anchor.key']=material['conversation_anchor']
        b.docker(['exec','-i',c['containers']['gateway'],'python','-c',keycode],keys)
        audit=Path(c['audit_config']);ac=json.loads(audit.read_text());ac['tool_sessions']=policy;audit.write_text(json.dumps(ac,indent=2)+'\n',encoding='utf8')
        b.docker(['restart',c['containers']['gateway']])
        if review_builtins:
            from chainguard_gateway.conversation_grants import builtin_revision
            from chainguard_gateway.default_tools import READ_TOOLS
            from chainguard_gateway.session_grants import ToolPolicy,ADMISSION_ABI
            from chainguard_gateway.chain_rpc import Contract
            policy_view=ToolPolicy(policy,['http://127.0.0.1:8545','http://127.0.0.1:8547'])
            report['builtin_reviews']=[]
            for name in READ_TOOLS:
                snapshot=policy_view.snapshot();epoch=Contract('ToolAdmissionRegistry',policy['registry']['address'],policy_view.chain.rpc,ADMISSION_ABI).call('epoch',block=hex(int(snapshot['number'])))
                now=int(time.time());m=dict(revision=builtin_revision(name),riskLevel=1,enabled=True,nonce=secrets.randbits(52),epoch=epoch,issuedAt=now,expiresAt=now+300)
                signed=b.call('security',dict(op='sign-tool-review',message=m))
                evidence=b.admission_submit(dict(message=m,signature=signed['signature']))
                report['builtin_reviews'].append(dict(name=name,revision=m['revision'],risk_level='LOW',evidence=evidence));save()
        report.update(status='PASS',policy=policy,after=chain.healthy(),existing_tools_require_explicit_risk_review=True)
        save();return report
    except Exception as error:report.update(status='FAIL',error_type=type(error).__name__);save();raise

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--conversation',action='store_true');p.add_argument('--review-builtins',action='store_true');a=p.parse_args()
    r=setup(a.config,a.out,conversation=a.conversation,review_builtins=a.review_builtins);print(json.dumps(dict(status=r['status'],registry=r['policy']['registry']['address'],anchor=r['policy']['anchor']['address'])))
