"""Read-only verification of a real phase6 run; never broadcasts or executes a tool."""
import argparse
from datetime import datetime, timezone
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


def load(path): return json.loads(path.read_text(encoding='utf-8'))


def verify(directory,tool_volume=False):
    report=load(directory/'report.json')
    assert report['status']=='PASS'
    phase5=load(ROOT/'results/phase5/besu-run-01/report.json')
    deployment={'chainId':20261026,'contracts':phase5['contracts'],
        'genesisHash':report['before']['nodes'][0]['genesis_hash'],'validators':report['before']['nodes'][0]['validators']}
    chain=Chain(deployment,[f'http://127.0.0.1:{p}' for p in range(8545,8549)])
    snapshot=chain.healthy()
    frozen={}
    for name in ['phase0-freeze','phase3-policy-freeze']:
        entries=load(ROOT/f'config/{name}.json')['files']
        for path,expected in entries.items():
            assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==expected,path
        frozen[name]=len(entries)
    verified=[]
    for name,case in report['cases'].items():
        record=case.get('recovered_record',case.get('record'))
        validate('ActionRecord',record)
        intent=record['intent']
        evidence=record['reservation_evidence']
        actual,receipt,_=chain.transaction_evidence(evidence['tx_hash'],chain.execution.address,snapshot,
            'ActionReserved(bytes32,bytes32,bytes32,bytes32,uint64)',case['action_id'])
        assert actual==evidence
        tx=chain.rpc.call('eth_getTransactionByHash',[evidence['tx_hash']])
        typed_intent,requester_signature,approvals=chain.execution.decode_input('reserve',tx['input'])
        assert all(str(typed_intent[target])==str(intent[source]) for source,target in PROTOCOL['json_to_typed']['ActionIntent'].items())
        assert recover_intent(intent,chain.domain,requester_signature)==intent['requester']
        # Historical authorization plus current immutable reservation; do not pretend
        # an expired original intent grants a fresh execution right today.
        chain.validate_authorization(intent,requester_signature,[a['signature'] for a in approvals],
            {'number':str(int(receipt['blockNumber'],16))},live=False)
        reservation=chain.execution.call('getReservation',[case['action_id']],hex(int(snapshot['number'])))
        assert reservation['intentHash']==digest('ActionIntent',intent,chain.domain)
        assert chain.execution.call('usedNonce',[intent['requester'],intent['nonce']])
        if name=='tool-outage':
            assert record['state']=='UNKNOWN' and reservation['status']==1 and record['receipt'] is None
        else:
            assert record['state']=='FINALIZED_OK' and reservation['status']==3
            wire=record['receipt']
            assert recover_receipt(wire,chain.receipt_domain,case['tool_signature'])==phase5['publicSigners']['mailTool'].lower()
            assert chain.audit.call('receiptHash',[case['action_id']])==digest('ExecutionReceipt',wire,chain.receipt_domain)==case['receipt_digest']
            assert chain.audit.call('receiptSigner',[case['action_id']])==phase5['publicSigners']['mailTool'].lower()
            final=record['finalization_evidence']
            actual,_,_=chain.transaction_evidence(final['tx_hash'],chain.audit.address,snapshot,
                'ActionFinalized(bytes32,bytes32,address,uint8)',case['action_id'])
            assert actual==final
            tx=chain.rpc.call('eth_getTransactionByHash',[final['tx_hash']])
            typed_receipt,signature=chain.audit.decode_input('reconcile' if name=='unknown' else 'finalize',tx['input'])
            assert all(str(typed_receipt[target])==str(wire[source]) for source,target in PROTOCOL['json_to_typed']['ExecutionReceipt'].items())
            assert signature==case['tool_signature']
        verified.append(name)
    files=[t['receipt_file'] for t in report['transactions']+report.get('replay_transactions',[])]+['mark-unknown-receipt.json']
    checked=0
    for filename in files:
        saved=load(directory/filename)
        for node,old in zip(chain.nodes,saved['nodes'],strict=True):
            current=node.call('eth_getTransactionReceipt',[saved['hash']])
            assert current==old
            block=node.call('eth_getBlockByNumber',[current['blockNumber'],False])
            assert block['hash']==current['blockHash'] and saved['hash'] in block['transactions']
            checked+=1
    mailbox=report['mailbox']['mailbox']
    expected={c['action_id'] for n,c in report['cases'].items() if n!='tool-outage'}
    assert len(mailbox)==len(expected) and {m['action_id'] for m in mailbox}==expected
    for mail in mailbox:
        raw=(directory/mail['mime_file']).read_bytes()
        assert hashlib.sha256(raw).hexdigest()==mail['mime_sha256']
        parsed=BytesParser(policy=policy.default).parsebytes(raw)
        assert str(parsed['To'])=='alice@inbox.chainguard.invalid'
        assert str(parsed['Message-ID'])==f"<{mail['action_id'][2:]}@inbox.chainguard.invalid>"
    volume_result=None
    if tool_volume:
        prefix=['wsl.exe','-d','Ubuntu','-u','root','--','docker']
        name=report['containers']['tool']
        actual=subprocess.run(prefix+['inspect','--format','{{.Id}}',name],capture_output=True,check=True,timeout=15).stdout.decode().strip()
        assert actual==next(i['id'] for i in report['isolation'] if i['name']=='/'+name)
        code='''
import hashlib,json,sqlite3
from Crypto.Cipher import AES
from chainguard_gateway.phase6_server import load
from chainguard_gateway.crypto import commit
root,c=load()
with sqlite3.connect('file:'+str(root/'state.sqlite3')+'?mode=ro',uri=True) as db:
 db.row_factory=sqlite3.Row
 rows=[dict(r) for r in db.execute('SELECT action_id,mime_sha256,mime FROM mailbox ORDER BY message_id')]
 for r in rows:
  assert hashlib.sha256(r.pop('mime')).hexdigest()==r['mime_sha256']
 for r in db.execute('SELECT action_id,data FROM chain_mail'):
  raw=r['data']; cipher=AES.new((root/'data.key').read_bytes(),AES.MODE_GCM,nonce=raw[:16]); cipher.update(r['action_id'].encode())
  saved=json.loads(cipher.decrypt_and_verify(raw[32:],raw[16:32]))
  assert commit('result',saved['result_salt'],saved['result'])==saved['receipt']['result_commit']
  assert commit('evidence',saved['evidence_salt'],saved['evidence'])==saved['receipt']['evidence_index_commit']
 print(json.dumps({'mailbox':rows,'claims':db.execute('SELECT count(*) FROM chain_mail').fetchone()[0]}))
'''
        result=subprocess.run(prefix+['exec',name,'python','-c',code],capture_output=True,check=True,timeout=25)
        volume_result=json.loads(result.stdout)
        assert volume_result['claims']==len(expected)
        assert volume_result['mailbox']==[{'action_id':m['action_id'],'mime_sha256':m['mime_sha256']} for m in mailbox]
    return {'status':'PASS','recorded_at_utc':datetime.now(timezone.utc).isoformat(),'snapshot':snapshot,
        'frozen_sources':frozen,'cases':verified,'live_receipts':checked,'mime_deliveries':len(mailbox),
        'tool_volume_verified':tool_volume,'tool_volume':volume_result}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    parser.add_argument('--tool-volume',action='store_true',help='Also read the original running tool SQLite volume; no writes/execute requests')
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    output=args.out.resolve()
    if output.exists() or not output.is_relative_to(ROOT/'results/phase6'): raise RuntimeError('Choose a new results/phase6 verification file')
    result=verify(args.directory.resolve(),args.tool_volume)
    output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))
