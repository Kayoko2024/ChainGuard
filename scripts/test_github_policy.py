"""One command: new live browser/Agent cases and independent original-volume proof.

Uses the user's existing local Web runtime. Creates two visible read-only tasks,
leaves the admitted test tool available for manual acceptance, sends no email.
--verify-source only reads original records, without model/HTTPS execution.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'gateway/src'),str(ROOT/'sandbox_tools/src'),str(ROOT/'agent/src'),str(ROOT/'scripts')]
from chainguard_gateway.phase10_bridge import DockerBridge
from chainguard_gateway.github_policy import RepositoryPolicy
from verify_demo_task import read_task
from chainguard_gateway.canonical import canonical
from chainguard_gateway.chain_rpc import Contract
from chainguard_gateway.github_policy import ABI,repository_hash
from eth_utils import keccak
from chain import RPC

READ_PROOF=r'''
import hashlib,json,sqlite3,sys
from Crypto.Cipher import AES
from chainguard_gateway.phase6_server import load
from chainguard_gateway.canonical import canonical
v=json.load(sys.stdin)
root,c=load()
with sqlite3.connect('file:'+str(root/'state.sqlite3')+'?mode=ro',uri=True) as d:
 d.row_factory=sqlite3.Row
 row=d.execute('SELECT * FROM custom_github_results WHERE id=?',(v['id'],)).fetchone();assert row
 blob=row['data'];cipher=AES.new((root/'custom-data.key').read_bytes(),AES.MODE_GCM,nonce=blob[:16]);cipher.update(v['id'].encode())
 data=json.loads(cipher.decrypt_and_verify(blob[32:],blob[16:32]));assert data['repository_policy']==v['proof']
 if v['allowed']:
  assert row['status']=='OK' and data['data']==v['data'] and data['reader_policy']['allowed'] is True
  read=d.execute('SELECT * FROM custom_tool_reads WHERE id=?',(v['id'],)).fetchone();assert read and read['task_id']==v['task_id']
  assert read['result_sha256']==hashlib.sha256(canonical(v['data'])).hexdigest()
  assert read['arguments_sha256']==hashlib.sha256(canonical({'query':v['query']})).hexdigest()
 else:
  assert row['status']=='GITHUB_REPOSITORY_DENIED' and not row['fetch_id']
  assert d.execute('SELECT COUNT(*) FROM custom_tool_reads WHERE id=?',(v['id'],)).fetchone()[0]==0
 print(json.dumps(dict(fetch_id=row['fetch_id'],status=row['status'],original_tool_record_matched=True,repository_policy=data['repository_policy'],reader_policy=data.get('reader_policy'))))
'''
SOURCE_PROOF=r'''
import hashlib,json,sqlite3,sys
v=json.load(sys.stdin)
with sqlite3.connect('file:/sandbox/github.sqlite3?mode=ro',uri=True) as d:
 d.row_factory=sqlite3.Row
 row=d.execute('SELECT * FROM fetches WHERE id=?',(v['id'],)).fetchone();assert row['status']=='OK'
 data=json.loads(row['data']);assert data==v['data'] and hashlib.sha256(row['raw']).hexdigest()==data['source']['response_sha256']
 raw=json.loads(row['raw']);assert raw['number']==1 and raw['title'][:500]==data['record']['title'] and raw['html_url'].lower()==data['record']['url']
 print(json.dumps(dict(http_status=row['http_status'],url=data['source']['url'],response_sha256=data['source']['response_sha256'],github_request_id=data['source']['github_request_id'],title=data['record']['title'],original_https_bytes_matched=True)))
'''

def verify_policy_record(config,proof):
    item=config['github_policy']['contract'];deployment=config['deployment']
    assert proof['contract']==item['address'].lower() and proof['code_hash']==item['codeHash']
    assert proof['repository_hash']==repository_hash(proof['repository']) and proof['chain_id']==str(deployment['chainId'])
    block=hex(int(proof['block_number']));checks=[]
    for port in range(8545,8549):
        node=RPC(port);assert int(node.call('eth_chainId'),16)==deployment['chainId']
        stored=node.call('eth_getBlockByNumber',[block,False]);assert stored['hash']==proof['block_hash']
        code=node.call('eth_getCode',[item['address'],block]);assert '0x'+keccak(bytes.fromhex(code[2:])).hex()==item['codeHash']
        contract=Contract('RepositoryReadPolicy',item['address'],node,abi=ABI)
        policy=Contract('PolicyRegistry',deployment['contracts']['PolicyRegistry']['address'],node)
        assert contract.call('policyRegistry',block=block)==policy.address
        actual=contract.call('repositoryAllowed',[proof['repository_hash']],block) and not policy.call('paused',block=block)
        assert actual==proof['allowed'] and str(contract.call('epoch',block=block))==proof['epoch']
        checks.append(dict(port=port,block_hash=stored['hash'],allowed=actual))
    return checks

def verify_governance(config):
    policy=config['github_policy'];receipts=[]
    for port in range(8545,8549):
        node=RPC(port);r=node.call('eth_getTransactionReceipt',[policy['governance_tx']]);assert r and r['status']=='0x1' and r['to'].lower()==policy['contract']['address'].lower()
        block=node.call('eth_getBlockByNumber',[r['blockNumber'],False]);assert block['hash']==r['blockHash'] and policy['governance_tx'] in block['transactions']
        receipts.append(r)
    assert all(r==receipts[0] for r in receipts)
    return dict(tx_hash=policy['governance_tx'],block_number=str(int(receipts[0]['blockNumber'],16)),receipts=receipts)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--verify-source',type=Path);a=p.parse_args()
    out=a.out.resolve()
    if out.exists() or not out.is_relative_to(ROOT/'results/github'):raise ValueError('Use new results/github path')
    out.mkdir(parents=True);c=json.loads(a.config.read_text());bridge=DockerBridge(c)
    report={'status':'RUNNING','model_or_https_reexecuted':not bool(a.verify_source),'asr_measured':False}
    def save():(out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    try:
        source=a.verify_source.resolve() if a.verify_source else out
        if a.verify_source:
            previous=json.loads((source/'report.json').read_text());report['source_execution_status']=previous['status']
            report['source_sha256']=hashlib.sha256((source/'browser/browser.json').read_bytes()).hexdigest()
        else:
            before=bridge.github_fetch_stats();report['fetches_before']=before;save()
            with (out/'browser.txt').open('wb') as log:
                r=subprocess.run(['node','console/tests/github-policy-browser.mjs',str(a.config.resolve()),str(out/'browser')],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,timeout=420)
            if r.returncode:raise RuntimeError('Browser failed; see retained evidence')
            after=bridge.github_fetch_stats();report['fetches_after']=after
            assert after['total']-before['total']==1 and after['ok']-before['ok']==1
        b=json.loads((source/'browser/browser.json').read_text());assert b['status']=='PASS';report['cases']=[]
        def observer(volume,script,value):
            return json.loads(bridge.docker(['run','--rm','-i','--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true','--mount','type=volume,src='+volume+',dst=/sandbox,readonly',c['image'],'python','-c',script],value))
        for case in b['cases']:
            job,events=read_task(Path(c['private_root']),case['job_id']);attempt=next(e for e in events if e['kind']=='AGENT_ATTEMPT');result=attempt['result']
            exchanges=[e['exchange'] for e in events if e['kind']=='MODEL_EXCHANGE'];plan=json.loads((ROOT/'evaluation/live_plan.json').read_text())
            assert exchanges and all(e['http_status']==200 and e['request']['model']==plan['model'] and all(e['request'].get(k)==v for k,v in plan['parameters'].items()) for e in exchanges)
            matches=sum(1 for e in exchanges for choice in e['response'].get('choices',[]) for call in choice['message'].get('tool_calls') or [] if call['function']['name']==b['name'].replace('.','_') and json.loads(call['function']['arguments'])=={'query':case['query']})
            assert matches>=1 and job['scheduler_state']==case['expected']
            assert job['custom_tools'][0]['allowed_keys']==['microsoft/vscode','microsoft/vscode#1','facebook/react#1']
            tool=observer(c['containers']['tool'],READ_PROOF,dict(id=result['read_execution_id'],query=case['query'],allowed=case['expected']=='READ_COMPLETED',data=result.get('data'),proof=result['repository_policy'],task_id=job['grant']['task_id']))
            public=sqlite3.connect(Path(c['public_db']).as_uri()+'?mode=ro',uri=True)
            deadline=time.monotonic()+10
            while True:
                row=public.execute('SELECT data FROM actions WHERE entry_id=?',('interactive-'+job['id'][2:],)).fetchone()
                if row and json.loads(row[0])['state']==case['expected']:break
                if time.monotonic()>deadline:raise AssertionError('Dynamic audit projection missing')
                time.sleep(.5)
            entry=json.loads(row[0]);public.close();assert entry['reservation_evidence'] is None and entry['chain_state']=='NONE'
            proof=dict(job_id=case['job_id'],query=case['query'],model_tool_call_matches=matches,tool=tool,audit_projection_matched=True)
            proof['historical_chain_checks']=verify_policy_record(c,result['repository_policy'])
            if tool['reader_policy']:proof['reader_historical_chain_checks']=verify_policy_record(c,tool['reader_policy'])
            if case['expected']=='READ_COMPLETED':
                assert any(canonical(json.loads(m['content']))==canonical(result) for e in exchanges for m in e['request']['messages'] if m['role']=='tool')
                assert any(r['read_execution_id']==result['read_execution_id'] and r['sha256']==result['sha256'] for r in entry['read_observations'])
                proof['source']=observer(c['github_reader']['volume'],SOURCE_PROOF,{'id':tool['fetch_id'],'data':result['data']})
            else:
                assert entry['read_observations']==[]
                manual=[e for e in events if e['kind']=='MANUAL_GITHUB_SCOPE_PROBE'];assert len(manual)==2
                assert [e['result'] for e in manual]==b['manual_probes'] and all(e['agent_attempted_tool'] is False for e in manual)
            report['cases'].append(proof);save()
        report['policy']=RepositoryPolicy(c['github_policy'],['http://127.0.0.1:8545','http://127.0.0.1:8547']).check('microsoft/vscode#1')
        report.update(status='PASS',new_sandbox_mails=0,new_read_transactions=0,governance=verify_governance(c),manual_probes=b['manual_probes'],tool_left_active=True);save()
        print(json.dumps({'status':'PASS','cases':2,'real_llm':not bool(a.verify_source),'new_https_requests':0 if a.verify_source else 1,'contract':c['github_policy']['contract']['address']}))
    except Exception as error:report.update(status='FAIL',error_type=type(error).__name__);save();raise
if __name__=='__main__':main()
