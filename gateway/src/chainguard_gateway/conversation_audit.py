"""Cumulative LOW-only session checkpoints with durable signed transaction outbox."""
import json
import re
import time
from eth_account import Account
from eth_utils import keccak,to_checksum_address
from .batch_audit import merkle,leaf,parent
from .canonical import canonical
from .chain_rpc import Contract
from .conversation_grants import ABI
from .session_grants import hash_json
from chainguard_sandbox.protocol import ToolError


def unfinished(access,db,sid):
    rows=db.execute("SELECT c.id,c.data FROM conversation_calls c LEFT JOIN conversation_low_logs l ON c.id=l.call_id WHERE c.state='STARTED' AND l.call_id IS NULL").fetchall()
    return [r['id'] for r in rows if access.open(r['id'],r['data']).get('session_id')==sid]


def check(log,proof,batch):
    try:
        index=log['sequence']-1;count=batch['count']
        if log['schema'] not in {2,3} or log['risk_level']!='LOW' or log['session_id']!=batch['session_id'] or not 0<=index<count or log['tool_name'] in {'mail.send','doc.delete'}:return False
        if log['schema']==3 and (not isinstance(log.get('grant_digest'),str) or not re.fullmatch(r'0x[0-9a-f]{64}',log['grant_digest']) or log['grant_digest']=='0x'+'00'*32):return False
        value=leaf(log);size=count
        for p in proof:
            if size<=1 or set(p)!={'hash','left'} or type(p['left']) is not bool or p['left']!=bool(index%2):return False
            if index%2==0 and index+1==size and p['hash']!=value:return False
            value=parent(p['hash'],value) if p['left'] else parent(value,p['hash']);index//=2;size=(size+1)//2
        return size==1 and value==batch['root']
    except (TypeError,KeyError,ValueError):return False


def verify(policy,batch,tx_hash):
    snapshot=policy.snapshot();receipts=[];address=policy.config['conversation']['address']
    for node in policy.chain.nodes:
        receipt=node.call('eth_getTransactionReceipt',[tx_hash])
        if not receipt:raise ToolError('CHAIN_UNAVAILABLE')
        if receipt['status']!='0x1' or receipt['to'].lower()!=address.lower():raise ToolError('RECEIPT_INVALID')
        block=node.call('eth_getBlockByNumber',[receipt['blockNumber'],False])
        if block['hash']!=receipt['blockHash'] or tx_hash not in block['transactions']:raise ToolError('RECEIPT_INVALID')
        contract=Contract('ConversationSessionRegistry',address,node,ABI)
        actual=contract.call('checkpoints',[batch['session_id'],batch['index']],receipt['blockNumber'])
        if actual!=[batch['root'],batch['count'],int(receipt['blockNumber'],16),batch['closed']]:raise ToolError('RECEIPT_INVALID')
        previous=contract.call('checkpoints',[batch['session_id'],batch['index']-1],receipt['blockNumber'])
        if previous[0]!=batch['previous_root']:raise ToolError('RECEIPT_INVALID')
        tx=node.call('eth_getTransactionByHash',[tx_hash])
        args=[batch['session_id'],batch['index'],batch['root'],batch['count'],batch['previous_root'],batch['closed']]
        if tx['input']!=contract.data('anchor',args) or tx['from'].lower()!=contract.call('publisher',block=receipt['blockNumber']):raise ToolError('RECEIPT_INVALID')
        receipts.append(receipt)
    if len({r['blockHash'] for r in receipts})!=1:raise ToolError('CHAIN_UNAVAILABLE')
    return dict(chain_id=str(policy.config['deployment']['chainId']),contract=address,tx_hash=tx_hash,block_number=str(int(receipts[0]['blockNumber'],16)),block_hash=receipts[0]['blockHash'],checked_nodes=len(receipts))


class Publisher:
    def __init__(self,access,key):self.access,self.key=access,key
    def flush(self,*,force=False,session_id=None):
        access=self.access;policy=access.policy;policy.snapshot();rpc=policy.chain.rpc;account=Account.from_key(self.key)
        contract=Contract('ConversationSessionRegistry',policy.config['conversation']['address'],rpc,ABI)
        if contract.call('publisher')!=account.address.lower():raise ToolError('FORBIDDEN')
        with access.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute("SELECT * FROM conversation_checkpoints WHERE state!='ANCHORED' ORDER BY rowid LIMIT 1").fetchone()
            if not row:
                sessions=[r[0] for r in db.execute('SELECT DISTINCT session_id FROM conversation_low_logs')]
                chosen=None
                for sid in sessions:
                    if session_id and sid!=session_id:continue
                    prior=db.execute('SELECT data FROM conversation_checkpoints WHERE session_id=? ORDER BY rowid DESC LIMIT 1',(sid,)).fetchone()
                    prior=json.loads(prior[0]) if prior else None
                    rows=db.execute('SELECT data FROM conversation_low_logs WHERE session_id=? ORDER BY sequence',(sid,)).fetchall();logs=[json.loads(r[0]) for r in rows]
                    # Closing authorization cannot seal a final prefix while a
                    # previously claimed LOW call still has no outcome record.
                    closed=db.execute('SELECT 1 FROM conversation_closed WHERE session_id=?',(sid,)).fetchone() is not None and not unfinished(access,db,sid)
                    old_count=prior['count'] if prior else 0
                    # A renewal fixes an audit boundary without closing the
                    # session. Roots remain cumulative prefixes across epochs.
                    boundary=db.execute('SELECT MIN(end_sequence) FROM conversation_epochs WHERE session_id=? AND end_sequence>?',(sid,old_count)).fetchone()[0]
                    if boundary is not None:
                        closed=closed and boundary==len(logs)
                        logs=logs[:boundary]
                    if prior and prior['closed'] or len(logs)==old_count and not closed:continue
                    if not force and boundary is None and not closed and len(logs)-old_count<50 and time.time()-logs[old_count]['timestamp']<300:continue
                    if len(logs)>100000:raise ToolError('CONTEXT_LIMIT')
                    root,proofs=merkle(logs)
                    chosen=dict(session_id=sid,index=prior['index']+1 if prior else 1,root=root,count=len(logs),previous_root=prior['root'] if prior else '0x'+'00'*32,closed=closed,proofs=proofs)
                    break
                if chosen is None:return {'status':'IDLE'}
                batch=chosen;id=hash_json({k:v for k,v in batch.items() if k!='proofs'})
                # One dedicated account and a single serialized outbox across all sessions.
                tx=dict(chainId=policy.config['deployment']['chainId'],nonce=int(rpc.call('eth_getTransactionCount',[account.address,'pending']),16),gas=500000,gasPrice=0,value=0,to=to_checksum_address(contract.address),data=contract.data('anchor',[batch['session_id'],batch['index'],batch['root'],batch['count'],batch['previous_root'],batch['closed']]))
                raw=bytes(Account.sign_transaction(tx,self.key).raw_transaction);tx_hash='0x'+keccak(raw).hex()
                db.execute('INSERT INTO conversation_checkpoints VALUES (?,?,?,?,?,?)',(id,batch['session_id'],canonical(batch).decode(),raw,tx_hash,'PREPARED'))
            else:batch=json.loads(row['data']);id=row['id'];raw=row['raw'];tx_hash=row['tx_hash']
        receipt=rpc.call('eth_getTransactionReceipt',[tx_hash])
        if receipt is None:
            if rpc.call('eth_getTransactionByHash',[tx_hash]) is None:
                if rpc.call('eth_sendRawTransaction',['0x'+raw.hex()])!=tx_hash:raise ToolError('CHAIN_UNAVAILABLE')
            return dict(status='PENDING',tx_hash=tx_hash)
        if receipt['status']!='0x1':raise ToolError('BATCH_TRANSACTION_REVERTED')
        batch['evidence']=verify(policy,batch,tx_hash)
        with access.connect() as db:db.execute("UPDATE conversation_checkpoints SET state='ANCHORED',data=? WHERE id=?",(canonical(batch).decode(),id))
        return dict(status='ANCHORED',tx_hash=tx_hash,evidence=batch['evidence'])


def observations(access,sid):
    with access.connect() as db:
        logs=[json.loads(r[0]) for r in db.execute('SELECT data FROM conversation_low_logs WHERE session_id=? ORDER BY sequence',(sid,))]
        checkpoints=db.execute('SELECT * FROM conversation_checkpoints WHERE session_id=? ORDER BY rowid DESC',(sid,)).fetchall()
        epochs={r['digest']:dict(r) for r in db.execute('SELECT * FROM conversation_epochs WHERE session_id=?',(sid,))}
    result=[]
    for log in logs:
        covered=next((r for r in checkpoints if json.loads(r['data'])['count']>=log['sequence']),None)
        observation=dict(log=log,status='PENDING_BATCH')
        if log.get('grant_digest') in epochs:observation['authorization_epoch']=epochs[log['grant_digest']]
        if covered:
            b=json.loads(covered['data']);observation.update(status=covered['state'],batch={k:v for k,v in b.items() if k!='proofs'},proof=b['proofs'][log['sequence']-1],leaf_index=log['sequence']-1,tx_hash=covered['tx_hash'])
        result.append(observation)
    return result
