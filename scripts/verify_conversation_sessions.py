"""Read-only proof/commitment/MIME verification. No model, signing or dispatch."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from Crypto.Cipher import AES
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/p) for p in ['gateway/src','sandbox_tools/src','agent/src']]
from chainguard_gateway.phase10_bridge import DockerBridge
from chainguard_gateway.audit_verify import make_chain
from chainguard_gateway.phase10_audit import verify_live_entry
from chainguard_gateway.session_grants import hash_json
from chainguard_gateway.canonical import canonical

OBSERVER='''import sys,json,sqlite3,hashlib
from pathlib import Path
from Crypto.Cipher import AES
from chainguard_gateway.session_grants import hash_json
from chainguard_gateway.canonical import canonical
v=json.load(sys.stdin);kind=v['kind'];root=Path(json.loads(Path('/sandbox/root.json').read_text())['root']);assert root.resolve().is_relative_to('/sandbox')
key=(root/('custom-data.key' if kind=='tool' else 'data.key')).read_bytes();n=16 if kind=='tool' else 12
def opened(id,blob):
 c=AES.new(key,AES.MODE_GCM,nonce=blob[:n]);c.update(('conversation/'+id).encode());return json.loads(c.decrypt_and_verify(blob[n+16:],blob[n:n+16]))
db=sqlite3.connect('file:'+str(root/'state.sqlite3')+'?mode=ro',uri=True);db.row_factory=sqlite3.Row;checks=[]
for log in v['logs']:
 row=db.execute('SELECT * FROM conversation_calls WHERE id=?',(log['call_id'],)).fetchone();assert row and row['state']=='DONE';p=opened(log['call_id'],row['data']);result=p['result']
 assert row['request_hash']==hash_json(p['request'])
 if kind=='gateway':
  assert log['params_hash']==hash_json(dict(salt=p['params_salt'],arguments=p['request']['arguments']))
  assert log['result_hash']==hash_json(dict(salt=p['result_salt'],result=result))
 if result.get('tool_name')=='doc.read':
  actual=db.execute('SELECT * FROM executions WHERE action_id=?',(result['read_execution_id'],)).fetchone() if kind=='tool' else None
  assert hashlib.sha256(canonical(result['data'])).hexdigest()==result['sha256']
  if kind=='tool':
   assert actual and actual['state']=='COMPLETED' and actual['tool_name']=='doc.read'
   original=json.loads(actual['result_json']);assert hashlib.sha256(result['data']['content'].encode()).hexdigest()==original['sha256']
 checks.append(dict(call_id=log['call_id'],task_id=log['task_id'],result_hash=hash_json(result),verified=True))
print(json.dumps(dict(status='PASS',kind=kind,checks=checks)))
'''

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    if a.out.exists():raise ValueError('New output directory required')
    a.out.mkdir(parents=True);source=json.loads((a.source/'smoke.json').read_text(encoding='utf8'))
    if source['status']!='PASS':raise ValueError('A completed source run is required')
    c=json.loads(Path(source['private_runtime']).read_text());b=DockerBridge(c)
    report=dict(status='RUNNING',model_or_tool_reexecuted=False,source=str(a.source),checks=[])
    def save():(a.out/'verification.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    save()
    try:
        with sqlite3.connect('file:'+Path(c['public_db']).as_posix()+'?mode=ro',uri=True) as db:rows=[json.loads(r[0]) for r in db.execute('SELECT data FROM actions')]
        chain=make_chain(c['deployment'],[f'http://127.0.0.1:{port}' for port in range(8545,8549)]);chain.tool_sessions=c['tool_sessions']
        logs=[]
        for row in rows:
            if not row.get('conversation_observation') and not row.get('action_id'):continue
            proof=verify_live_entry(chain,row);assert proof['status'] in {'VERIFIED','BATCH_VERIFIED'}
            item=dict(entry_id=row['entry_id'],verification=proof['status'],evidence=proof.get('evidence'),transactions=proof.get('transactions'))
            if row.get('action_id'):
                observed=b.observe(row['action_id'],include_mime=True);assert observed['status']=='VERIFIED' and observed['mail_count']==1
                item['mail_count']=observed['mail_count'];item['mime_sha256']=[m['mime_sha256'] for m in observed['messages']]
            else:
                observation=row['conversation_observation']
                # This harness closes every LOW session. An earlier, valid
                # open checkpoint is not evidence of completed session sealing.
                assert observation['batch']['closed'] is True
                item['session_closed_checkpoint']=True
                item['session_id']=observation['log']['session_id']
                logs.append(observation['log'])
            report['checks'].append(item);save()
        results=[]
        for kind in ['gateway','tool']:
            args=['run','--rm','-i','--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true','--mount','type=volume,src='+c['containers'][kind]+',dst=/sandbox,readonly',c['image'],'python','-c',OBSERVER]
            process=subprocess.run(b.prefix+args,input=canonical(dict(kind=kind,logs=logs)),capture_output=True,timeout=45)
            if process.returncode:
                (a.out/(kind+'-observer.stderr.txt')).write_bytes(process.stderr)
                raise RuntimeError('Read-only observer failed: '+kind+'; diagnostic retained')
            result=json.loads(process.stdout);assert result['status']=='PASS';results.append(result)
        assert results[0]['checks']==results[1]['checks'];report['independent_gate_commitments']=results
        # Verify persisted model requests really contain the preceding assistant response.
        private=Path(c['private_root']);key=(private/'operations.key').read_bytes()
        def opened(id,blob):
            cipher=AES.new(key,AES.MODE_GCM,nonce=blob[:16]);cipher.update(id.encode());return json.loads(cipher.decrypt_and_verify(blob[32:],blob[16:32]))
        with sqlite3.connect('file:'+(private/'operations.sqlite3').as_posix()+'?mode=ro',uri=True) as db:
            jobs={r[0]:opened(r[0],r[1]) for r in db.execute('SELECT id,data FROM jobs')}
            first,second=source['runs'];assert jobs[first]['agent_output']
            events=[opened(second,r[0]) for r in db.execute('SELECT data FROM events WHERE job_id=? ORDER BY id',(second,))]
            exchanges=[e for e in events if e['kind']=='MODEL_EXCHANGE'];assert exchanges
            assert any(m['role']=='assistant' and m.get('content')==jobs[first]['agent_output'] for m in exchanges[0]['exchange']['request']['messages'])
        report.update(status='PASS',memory_in_actual_model_request=True,new_model_calls=0,new_tool_calls=0,new_transactions=0);save()
    except Exception as e:report.update(status='FAIL',error_type=type(e).__name__);save();raise
    print(json.dumps(dict(status='PASS',records=len(report['checks']),low_logs=len(logs),reexecuted=False)))

if __name__=='__main__':main()
