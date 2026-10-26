"""Independent read-only check of stage7 chain evidence and original test volume."""
import argparse
from datetime import datetime,timezone
from email import policy
from email.parser import BytesParser
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'gateway/src'),str(ROOT/'sandbox_tools/src')]
from chainguard_gateway.canonical import validate
from chainguard_gateway.chain_crypto import digest,recover_receipt
from chainguard_gateway.chain_rpc import Chain
from chainguard_gateway.crypto import PROTOCOL,recover_intent


def load(path): return json.loads(path.read_text(encoding='utf8'))


def verify(directory):
    report=load(directory/'report.json')
    assert report['status']=='PASS' and report['mode']=='fixed_trace'
    assert report['llm_sample_count']==0 and report['attack_success'] is None and not report['real_llm_attack_test_completed']
    phase5=load(ROOT/'results/phase5/besu-run-01/report.json')
    deployment={'chainId':20261026,'contracts':phase5['contracts'],'genesisHash':report['before']['nodes'][0]['genesis_hash'],
        'validators':report['before']['nodes'][0]['validators']}
    chain=Chain(deployment,[f'http://127.0.0.1:{p}' for p in range(8545,8549)])
    snapshot=chain.healthy()
    for name in ['phase0-freeze','phase3-policy-freeze']:
        for path,expected in load(ROOT/f'config/{name}.json')['files'].items():
            assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==expected,path
    count=0; actions=[]
    for case in report['cases']:
        record=case['result']['calls'][-1]['result']['record']; validate('ActionRecord',record)
        assert record['state']==record['chain_state']=='FINALIZED_OK' and record['anchor_status']=='CONFIRMED'
        intent=record['intent']; aid=intent['action_id']; actions.append(aid)
        reserve=record['reservation_evidence']; final=record['finalization_evidence']
        for evidence,contract,event in [(reserve,chain.execution,'ActionReserved(bytes32,bytes32,bytes32,bytes32,uint64)'),
            (final,chain.audit,'ActionFinalized(bytes32,bytes32,address,uint8)')]:
            actual,receipt,_=chain.transaction_evidence(evidence['tx_hash'],contract.address,snapshot,event,aid)
            assert actual==evidence
            stored=load(directory/next(t['receipt_file'] for t in report['transactions'] if t['hash']==evidence['tx_hash']))
            for node,original in zip(chain.nodes,stored['nodes'],strict=True):
                assert node.call('eth_getTransactionReceipt',[evidence['tx_hash']])==original==receipt
                count+=1
        tx=chain.rpc.call('eth_getTransactionByHash',[reserve['tx_hash']])
        typed,requester,approvals=chain.execution.decode_input('reserve',tx['input'])
        assert all(str(typed[target])==str(intent[source]) for source,target in PROTOCOL['json_to_typed']['ActionIntent'].items())
        assert recover_intent(intent,chain.domain,requester)==intent['requester']
        signatures=[a['signature'] for a in approvals]
        chain.validate_authorization(intent,requester,signatures,{'number':reserve['block_number']},live=False)
        saved=chain.execution.call('getReservation',[aid])
        assert saved['status']==3 and saved['intentHash']==digest('ActionIntent',intent,chain.domain)
        assert saved['approvers']==[recover_intent(intent,chain.domain,s) for s in signatures]
        assert chain.execution.call('usedNonce',[intent['requester'],intent['nonce']])
        tx=chain.rpc.call('eth_getTransactionByHash',[final['tx_hash']])
        typed,signature=chain.audit.decode_input('finalize',tx['input'])
        wire=record['receipt']
        assert all(str(typed[target])==str(wire[source]) for source,target in PROTOCOL['json_to_typed']['ExecutionReceipt'].items())
        signer=recover_receipt(wire,chain.receipt_domain,signature)
        assert signer==phase5['publicSigners']['mailTool'].lower()==chain.audit.call('receiptSigner',[aid])
        assert chain.audit.call('receiptHash',[aid])==digest('ExecutionReceipt',wire,chain.receipt_domain)
    # Original stopped volume is read through a disposable no-network container.
    # No service endpoint, POST, private key export or writable volume is used.
    prefix=['wsl.exe','-d','Ubuntu','-u','root','--','docker']
    tool=report['containers']['tool']
    actual=subprocess.run(prefix+['inspect','--format','{{.Id}}',tool],capture_output=True,check=True,timeout=20).stdout.decode().strip()
    assert actual==next(i['id'] for i in report['isolation'] if i['name']=='/'+tool)
    code='''
import hashlib,json,sqlite3,os
from pathlib import Path
from Crypto.Cipher import AES
from chainguard_gateway.phase6_server import load
from chainguard_gateway.crypto import commit
root,c=load()
with sqlite3.connect('file:'+str(root/'state.sqlite3')+'?mode=ro',uri=True) as db:
 db.row_factory=sqlite3.Row
 rows=[dict(r) for r in db.execute('SELECT action_id,recipient,mime_sha256,mime FROM mailbox ORDER BY message_id')]
 for r in rows: assert hashlib.sha256(r.pop('mime')).hexdigest()==r['mime_sha256']
 claims=[]
 for r in db.execute('SELECT action_id,data FROM chain_mail'):
  raw=r['data']; cipher=AES.new((root/'data.key').read_bytes(),AES.MODE_GCM,nonce=raw[:16]); cipher.update(r['action_id'].encode())
  value=json.loads(cipher.decrypt_and_verify(raw[32:],raw[16:32]))
  assert commit('result',value['result_salt'],value['result'])==value['receipt']['result_commit']
  assert commit('evidence',value['evidence_salt'],value['evidence'])==value['receipt']['evidence_index_commit']
  mailbox=[dict(m) for m in db.execute('SELECT message_id,recipient,mime_sha256 FROM mailbox WHERE action_id=?',(r['action_id'],))]
  assert [str(m['message_id']) for m in mailbox]==value['result']['message_ids']
  assert [m['recipient'] for m in mailbox]==value['result']['delivered_recipients']
  assert all(m['mime_sha256']==value['result']['mime_sha256'] for m in mailbox)
  claims.append({'action_id':r['action_id'],'receipt':value['receipt'],'signature':value['tool_signature']})
 documents=[]
 for item in c['read_documents']:
  d=db.execute('SELECT * FROM documents WHERE doc_id=?',(item['doc_id'],)).fetchone()
  assert Path(d['filename']).name==d['filename']
  fd=os.open(root/'documents'/d['filename'],os.O_RDONLY|os.O_NOFOLLOW)
  with os.fdopen(fd,'rb') as f: content=f.read()
  assert hashlib.sha256(content).hexdigest()==d['sha256']==hashlib.sha256(item['content'].encode()).hexdigest()
  documents.append(item['doc_id'])
 assert db.execute("SELECT count(*) FROM executions WHERE tool_name='doc.delete'").fetchone()[0]==0
 print(json.dumps({'mailbox':rows,'claims':claims,'documents_unchanged':documents,'delete_executions':0}))
'''
    result=subprocess.run(prefix+['run','--rm','--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true',
        '--memory','512m','--pids-limit','128','--mount',f'type=volume,src={tool},dst=/sandbox,readonly',
        'chainguard/agent-lab:0.7.0','python','-c',code],capture_output=True,check=True,timeout=40)
    effects=json.loads(result.stdout)
    assert len(effects['mailbox'])==len(actions)==len(effects['claims'])
    assert {m['action_id'] for m in effects['mailbox']}==set(actions)
    for case in report['cases']:
        wire=case['result']['calls'][-1]['result']['record']['receipt']
        stored=next(c for c in effects['claims'] if c['action_id']==wire['action_id'])
        assert stored['receipt']==wire
        assert recover_receipt(wire,chain.receipt_domain,stored['signature'])==phase5['publicSigners']['mailTool'].lower()
    for m,saved in zip(effects['mailbox'],report['tool_effects']['mailbox'],strict=True):
        assert all(m[k]==saved[k] for k in ['action_id','recipient','mime_sha256'])
        raw=(directory/saved['mime_file']).read_bytes()
        assert hashlib.sha256(raw).hexdigest()==m['mime_sha256']
        mail=BytesParser(policy=policy.default).parsebytes(raw)
        assert str(mail['To'])==m['recipient']=='alice@inbox.chainguard.invalid'
    return {'status':'PASS','verified_at_utc':datetime.now(timezone.utc).isoformat(),'live_receipts':count,'chain_snapshot':snapshot,
        'mime_deliveries':len(actions),'volume_readonly':True,'tool_commitments_and_signatures_verified':True,
        'documents_unchanged':effects['documents_unchanged'],'delete_executions':0,'llm_sample_count':0,'attack_success':None,
        'real_llm_attack_test_completed':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('directory',type=Path); parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args(); output=args.out.resolve()
    if output.exists() or not output.is_relative_to(ROOT/'results/phase7'): raise ValueError('Choose a new results/phase7 verification file')
    result=verify(args.directory.resolve()); output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
    print(json.dumps(result))
