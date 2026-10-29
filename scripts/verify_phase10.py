"""Independent readonly verification of new interactive tasks, four Besu and original MIME."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import sys
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'gateway/src'),str(ROOT/'sandbox_tools/src'),str(ROOT/'agent/src')]
from chainguard_gateway.audit_verify import make_chain,verify_action
from chainguard_gateway.phase10_bridge import DockerBridge
from chainguard_gateway.phase10_store import OperationsStore


def verify(deployment,run):
    assert deployment['status']=='PASS' and run['status']=='PASS'
    config=json.loads(Path(deployment['config_path']).read_text(encoding='utf8'))
    bridge=DockerBridge(config); chain=make_chain(config['deployment'],[f'http://127.0.0.1:{p}' for p in range(8545,8549)])
    # No token refresh, calls, signing, fault, reserve, advance or dispatch operations.
    original={r['action_id']:r for r in bridge.snapshot()}
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(deployment['audit_url']+'/audit-api/v1/actions',timeout=20) as response: public=json.load(response)['actions']
    store=OperationsStore(config['private_root']); receipts={}; results=[]
    for expected in [run['normal'],{'id':run['unknown']['id'],'record':run['recovered']['record']}]:
        id,record=expected['id'],expected['record']; current=original[record['action_id']]
        assert current['state']=='FINALIZED_OK' and current['intent']==record['intent']
        entry=next(a for a in public if a['sample_id']==id)
        assert entry['action_id']==record['action_id'] and entry['intent']==current['intent']
        verified=verify_action(chain,entry); assert verified['status']=='VERIFIED'
        assert verified['tool_signature_valid'] and len({a['organization'] for a in verified['approvals']})==2
        observation=bridge.observe(record['action_id'],include_mime=True)
        assert observation['status']=='VERIFIED' and observation['mail_count']==1
        assert observation['receipt']==current['receipt'] and observation['tool_signature']==current['tool_signature']
        job=store.get(id); attempt=job['attempt']['arguments']; message=observation['messages'][0]
        assert message['recipient']==attempt['to'][0] and message['subject']==attempt['subject'] and message['body'].rstrip('\r\n')==attempt['body'].rstrip('\r\n')
        events=store.events(id); models=[e['exchange'] for e in events if e['kind']=='MODEL_EXCHANGE']
        assert models and all(e['http_status']==200 and e['request']['model']=='deepseek-flash' for e in models)
        humans=[e for e in events if e['kind']=='HUMAN_APPROVAL']
        assert {e['role'] for e in humans}=={'biz','security'}
        assert all(e['intent_digest']==humans[0]['intent_digest'] for e in humans)
        for tx in verified['transactions']:
            observed=[node.call('eth_getTransactionReceipt',[tx['tx_hash']]) for node in chain.nodes]
            assert all(r==observed[0] and r['status']=='0x1' for r in observed)
            for node,r in zip(chain.nodes,observed):
                block=node.call('eth_getBlockByNumber',[r['blockNumber'],False]); assert block['hash']==r['blockHash'] and tx['tx_hash'] in block['transactions']
            receipts[tx['tx_hash']]=observed
        # Public serialization contains no raw task/mail/model data or private salts.
        raw=json.dumps(entry)
        for forbidden in ['params_salt','result_salt','evidence_salt','mime_b64','api_key','relay_key','signing.key','task_text','MODEL_EXCHANGE']:
            assert forbidden not in raw
        assert attempt['body'] not in raw
        results.append({'business_task_id':id,'action_id':record['action_id'],'verification':verified,'mail_count':1,
            'mime_sha256':message['mime_sha256'],'mime_matches_actual_model_arguments':True,'model_requests':len(models),'distinct_human_roles':sorted({e['role'] for e in humans})})
    assert run['missing_approval']['mail_count']==0 and run['missing_approval']['no_reservation']
    assert run['unauthorized']['result']['error_code']=='UNAUTHORIZED_SCOPE' and not run['unauthorized']['agent_attempted_tool']
    assert run['replay']['same_action'] and run['replay']['no_new_mail']
    assert run['unknown']['record']['state']=='UNKNOWN' and run['unknown']['record']['receipt'] is None
    assert run['unknown']['tool_observation']['mail_count']==1 and run['unknown']['audit']['status']=='PENDING_RECEIPT'
    frozen=[]
    for name in ['phase0-freeze.json','phase3-policy-freeze.json']:
        for file,sha in json.loads((ROOT/'config'/name).read_text())['files'].items():
            assert hashlib.sha256((ROOT/file).read_bytes()).hexdigest()==sha;frozen.append(file)
    return {'status':'PASS','checked_at_utc':datetime.now(timezone.utc).isoformat(),'new_interactive_tasks':results,
        'transactions':len(receipts),'node_receipts':4*len(receipts),'receipts':receipts,'original_gateway_state_read':True,
        'original_tool_volume_readonly':True,'original_mime_verified':True,'public_projection_no_plaintext':True,
        'frozen_distinct_files':len(set(frozen)),'snapshot':chain.healthy(),'no_new_tool_dispatch':True}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--deployment',type=Path,required=True);p.add_argument('--browser-run',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    if a.out.exists():raise ValueError('New verification output required')
    result=verify(json.loads(a.deployment.read_text(encoding='utf8')),json.loads(a.browser_run.read_text(encoding='utf8')))
    a.out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({k:result[k] for k in ['status','transactions','node_receipts','original_mime_verified']}))
