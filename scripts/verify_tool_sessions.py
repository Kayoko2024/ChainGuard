"""Read-only verification of original encrypted calls, tool records and four-node Merkle anchors."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'gateway/src'),str(ROOT/'sandbox_tools/src'),str(ROOT/'agent/src')]
from chainguard_gateway.phase10_bridge import DockerBridge
from chainguard_gateway.session_grants import hash_json,ToolPolicy
from chainguard_gateway.batch_audit import check_proof,verify_batch
from chainguard_gateway.canonical import canonical

OBSERVER='''import json,sys,sqlite3
from pathlib import Path
from Crypto.Cipher import AES
root=Path(json.loads(Path('/sandbox/root.json').read_text())['root']);key=(root/'custom-data.key').read_bytes()
def open_call(id,blob):
 c=AES.new(key,AES.MODE_GCM,nonce=blob[:16]);c.update(('session/'+id).encode());return json.loads(c.decrypt_and_verify(blob[32:],blob[16:32]))
with sqlite3.connect('file:'+str(root/'state.sqlite3')+'?mode=ro',uri=True) as db:
 db.row_factory=sqlite3.Row;result=[]
 for id in json.load(sys.stdin):
  row=db.execute('SELECT * FROM session_calls WHERE id=?',(id,)).fetchone()
  if not row:raise ValueError('Missing original tool call')
  value=open_call(id,row['data']);actual=value.get('result');read=db.execute('SELECT * FROM custom_tool_reads WHERE id=?',(actual['read_execution_id'],)).fetchone() if actual and actual.get('read_execution_id') else None
  result.append(dict(call_id=id,state=row['state'],value=value,read=dict(read) if read else None))
 print(json.dumps(result))
'''

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',type=Path,required=True);p.add_argument('--source',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    if a.out.exists() or not a.out.resolve().is_relative_to(ROOT/'results/sessions'):raise ValueError('New results/sessions output required')
    a.out.mkdir(parents=True);source=json.loads((a.source/'smoke.json').read_text());c=json.loads(a.config.read_text());b=DockerBridge(c)
    assert source['status']=='PASS' and source['policy']==c['tool_sessions']
    evidence=list(source['batch_evidence'])
    if source.get('web_acceptance'):evidence.append(source['web_acceptance']['batch'])
    ids=[x['log']['call_id'] for x in evidence];snapshot=b.session_snapshot();gateway={r['call_id']:r for r in snapshot['calls']}
    args=['run','--rm','-i','--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true','--mount','type=volume,src='+c['containers']['tool']+',dst=/sandbox,readonly',c['image'],'python','-c',OBSERVER]
    tool={r['call_id']:r for r in json.loads(b.docker(args,ids))}
    policy=ToolPolicy(c['tool_sessions'],[f'http://127.0.0.1:{p}' for p in range(8545,8549)]);rows=[]
    for observation in evidence:
        id=observation['log']['call_id'];g=gateway[id];t=tool[id];log=observation['log']
        assert check_proof(log,observation['proof'],observation['batch']['root'])
        assert hash_json({'salt':g['params_salt'],'arguments':g['request']['arguments']})==log['params_hash']
        assert hash_json({'salt':g['result_salt'],'result':g['audit_result']})==log['result_hash']
        actual=t['value']['result'];read=t['read'];assert t['state']=='DONE' and actual['trust']=='untrusted' and read
        assert hashlib.sha256(canonical(actual['data'])).hexdigest()==actual['sha256']==read['result_sha256']
        assert read['arguments_sha256']==hashlib.sha256(canonical(t['value']['request']['arguments'])).hexdigest()
        assert read['task_id']==g['request']['task_id'] and read['revision']==g['request']['revision']
        if g['state']=='DONE':assert g['result']==actual
        else:assert g['state']=='STARTED' and log['outcome']=='UNKNOWN'
        verified=verify_batch(policy,observation['batch'],observation['tx_hash'])
        wrong=dict(log,result_hash='0x'+'00'*32);assert not check_proof(wrong,observation['proof'],observation['batch']['root'])
        rows.append(dict(call_id=id,gateway_state=g['state'],tool_state=t['state'],original_read_execution_id=actual['read_execution_id'],merkle_verified=True,original_tool_read_verified=True,evidence=verified))
    report=dict(status='PASS',source=str(a.source),model_or_tool_reexecuted=False,read_only_mount=True,sqlite_mode='ro',calls=rows)
    (a.out/'verification.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8');print(json.dumps(dict(status='PASS',calls=len(rows),reexecuted=False)))

if __name__=='__main__':main()
