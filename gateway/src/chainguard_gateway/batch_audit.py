"""Ordered, domain-separated Merkle batches and durable same-byte transaction recovery."""
import json
import time
from eth_account import Account
from eth_utils import keccak,to_checksum_address
from .canonical import canonical
from .session_grants import ANCHOR_ABI,hash_json
from .chain_rpc import Contract
from chainguard_sandbox.protocol import ToolError

def leaf(value):return '0x'+keccak(b'\x00'+canonical(value)).hex()
def parent(a,b):return '0x'+keccak(b'\x01'+bytes.fromhex(a[2:])+bytes.fromhex(b[2:])).hex()
def merkle(logs):
    if not logs:raise ValueError('Empty batch')
    levels=[[leaf(log) for log in logs]]
    while len(levels[-1])>1:
        row=levels[-1];levels.append([parent(row[i],row[i+1] if i+1<len(row) else row[i]) for i in range(0,len(row),2)])
    proofs=[]
    for index in range(len(logs)):
        path=[];pos=index
        for row in levels[:-1]:
            other=pos^1;path.append({'hash':row[other] if other<len(row) else row[pos],'left':bool(pos%2)});pos//=2
        proofs.append(path)
    return levels[-1][0],proofs
def check_proof(log,proof,root):
    try:
        value=leaf(log)
        if len(proof)>6:return False
        for p in proof:
            if set(p)!={'hash','left'} or type(p['left']) is not bool:return False
            value=parent(p['hash'],value) if p['left'] else parent(value,p['hash'])
        return value==root
    except (ValueError,KeyError,TypeError):return False

class BatchPublisher:
    def __init__(self,access,key):self.access,self.key=access,key
    def flush(self,*,force=False):
        access=self.access;policy=access.policy;snapshot=policy.snapshot()
        rpc=policy.chain.rpc;account=Account.from_key(self.key);address=policy.config['anchor']['address']
        contract=Contract('LowRiskAuditAnchor',address,rpc,ANCHOR_ABI)
        if contract.call('publisher')!=account.address.lower():raise ToolError('FORBIDDEN')
        with access.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute("SELECT * FROM session_batches WHERE state!='ANCHORED' ORDER BY rowid LIMIT 1").fetchone()
            if not row:
                pending=db.execute('SELECT * FROM session_logs WHERE batch_id IS NULL ORDER BY sequence LIMIT 50').fetchall()
                if not pending:return {'status':'IDLE'}
                logs=[json.loads(r['data']) for r in pending]
                if not force and len(logs)<50 and time.time()-logs[0]['timestamp']<300:return {'status':'WAITING','pending':len(logs)}
                root,proofs=merkle(logs);id=hash_json({'root':root,'first':logs[0]['sequence'],'last':logs[-1]['sequence'],'publisher':account.address.lower()})
                batch=dict(id=id,root=root,count=len(logs),first=logs[0]['sequence'],last=logs[-1]['sequence'],proofs=proofs)
                tx=dict(chainId=policy.config['deployment']['chainId'],nonce=int(rpc.call('eth_getTransactionCount',[account.address,'pending']),16),gas=500000,gasPrice=0,value=0,to=to_checksum_address(address),data=contract.data('anchor',[id,root,len(logs),batch['first'],batch['last']]))
                signed=Account.sign_transaction(tx,self.key);raw=bytes(signed.raw_transaction);tx_hash='0x'+keccak(raw).hex()
                db.execute('INSERT INTO session_batches VALUES (?,?,?,?,?)',(id,canonical(batch).decode(),raw,tx_hash,'PREPARED'))
                db.executemany('UPDATE session_logs SET batch_id=? WHERE sequence=?',[(id,r['sequence']) for r in pending])
            else:
                batch=json.loads(row['data']);id=row['id'];raw=row['raw'];tx_hash=row['tx_hash']
        # This dedicated account is never shared with reserve/finalize relay nonces.
        receipt=rpc.call('eth_getTransactionReceipt',[tx_hash])
        if receipt is None:
            existing=rpc.call('eth_getTransactionByHash',[tx_hash])
            if existing is None:
                actual=rpc.call('eth_sendRawTransaction',['0x'+raw.hex()])
                if actual!=tx_hash:raise ToolError('CHAIN_UNAVAILABLE')
            return {'status':'PENDING','batch_id':id,'tx_hash':tx_hash}
        if receipt['status']!='0x1':raise ToolError('BATCH_TRANSACTION_REVERTED')
        evidence=verify_batch(policy,batch,tx_hash)
        batch.update(evidence=evidence)
        with access.connect() as db:db.execute("UPDATE session_batches SET state='ANCHORED',data=? WHERE id=?",(canonical(batch).decode(),id))
        return {'status':'ANCHORED','batch_id':id,'evidence':evidence}

def verify_batch(policy,batch,tx_hash):
    snapshot=policy.snapshot();receipts=[]
    for node in policy.chain.nodes:
        receipt=node.call('eth_getTransactionReceipt',[tx_hash])
        if not receipt or receipt['status']!='0x1' or receipt['to'].lower()!=policy.config['anchor']['address'].lower():raise ToolError('CHAIN_UNAVAILABLE')
        block=node.call('eth_getBlockByNumber',[receipt['blockNumber'],False])
        if block['hash']!=receipt['blockHash'] or tx_hash not in block['transactions']:raise ToolError('CHAIN_UNAVAILABLE')
        contract=Contract('LowRiskAuditAnchor',policy.config['anchor']['address'],node,ANCHOR_ABI)
        actual=contract.call('batches',[batch['id']],receipt['blockNumber'])
        if actual!=[batch['root'],batch['count'],batch['first'],batch['last']]:raise ToolError('RECEIPT_INVALID')
        tx=node.call('eth_getTransactionByHash',[tx_hash])
        if tx['input']!=contract.data('anchor',[batch['id'],batch['root'],batch['count'],batch['first'],batch['last']]) or tx['from'].lower()!=contract.call('publisher',block=receipt['blockNumber']):raise ToolError('RECEIPT_INVALID')
        receipts.append(receipt)
    if len({r['blockHash'] for r in receipts})!=1:raise ToolError('CHAIN_UNAVAILABLE')
    return dict(chain_id=str(policy.config['deployment']['chainId']),contract=policy.config['anchor']['address'],tx_hash=tx_hash,block_number=str(int(receipts[0]['blockNumber'],16)),block_hash=receipts[0]['blockHash'],checked_nodes=len(receipts))

def observations(access,task_id=None):
    with access.connect() as db:
        rows=db.execute('SELECT * FROM session_logs'+(' WHERE json_extract(data,\'$.task_id\')=?' if task_id else '')+' ORDER BY sequence',([task_id] if task_id else [])).fetchall()
        result=[]
        for row in rows:
            value={'log':json.loads(row['data']),'status':'PENDING_BATCH'}
            if row['batch_id']:
                b=db.execute('SELECT * FROM session_batches WHERE id=?',(row['batch_id'],)).fetchone();batch=json.loads(b['data'])
                value.update(status=b['state'],batch={k:v for k,v in batch.items() if k!='proofs'},proof=batch['proofs'][row['sequence']-batch['first']],tx_hash=b['tx_hash'])
            result.append(value)
    return result
