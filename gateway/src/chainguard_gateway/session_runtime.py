"""Trusted stdio controls only. Keys remain in the existing separated role volumes."""
import json
import secrets
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from eth_account import Account
from eth_utils import keccak,to_checksum_address
from .canonical import canonical
from .session_grants import configured_access,ToolPolicy,ADMISSION_ABI,TYPES,sign,typed
from .chain_rpc import Contract
from .batch_audit import BatchPublisher,observations
from chainguard_sandbox.protocol import ToolError

def message_digest(kind,message,domain):
    m=typed(kind,message,domain);return '0x'+keccak(b'\x19'+m.version+m.header+m.body).hex()

def access_for(root,c):
    if root.name.startswith('test-'):
        from chainguard_sandbox.storage import Store
        from chainguard_sandbox.custom_library import CustomLibrary
        store=Store(root);library=CustomLibrary(store)
        adapter=SimpleNamespace(root=root,connect=store.connect,seal=library.seal,unseal=library.open)
    else:
        from .chain_store import ChainStore
        adapter=ChainStore(root)
    return configured_access(adapter,c['rpc_urls'])

def control(root,c,op,value):
    if op in {'sign-session','sign-tool-review','sign-tool-use'}:
        if op=='sign-session' and c['subject']!='requester' or op=='sign-tool-review' and c['subject']!='security' or op=='sign-tool-use' and c['subject'] not in {'biz','security'}:raise ToolError('FORBIDDEN')
        kind={'sign-session':'SessionGrant','sign-tool-review':'ToolReview','sign-tool-use':'ToolUseApproval'}[op]
        policy=ToolPolicy(json.loads((root/'tool-sessions.json').read_text()),c.get('rpc_urls',['http://node1:8545','http://node3:8545']))
        if kind=='SessionGrant' and value['message']['requester']!=c['address']:raise ToolError('FORBIDDEN')
        if value.get('digest') and message_digest(kind,value['message'],policy.domain)!=value['digest']:raise ToolError('PARAMS_MISMATCH')
        return {'signature':sign(kind,value['message'],policy.domain,(root/'signing.key').read_bytes()),'signer':c['address']}
    access=access_for(root,c)
    if not access:raise ToolError('SESSION_NOT_CONFIGURED')
    if op=='session-install':return access.install(value)
    if op=='session-list':
        with access.connect() as db:ids=[r[0] for r in db.execute('SELECT id FROM session_calls ORDER BY rowid')]
        return {'calls':[access.call(id) for id in ids],'observations':observations(access)}
    if op=='session-review':
        item=access.call(value['call_id'])
        return dict(item,digest=message_digest('ToolUseApproval',item['approval'],access.policy.domain))
    if op=='session-approve':return access.approve(value['call_id'],value['signature'])
    if op=='session-flush':return BatchPublisher(access,(root/'session-anchor.key').read_bytes()).flush(force=value.get('force',False))
    if op=='admission-submit':return submit_review(access,root,value)
    raise ToolError('FORBIDDEN')

def submit_review(access,root,value):
    policy=access.policy;policy.snapshot();rpc=policy.chain.rpc
    contract=Contract('ToolAdmissionRegistry',policy.config['registry']['address'],rpc,ADMISSION_ABI)
    data=contract.data('review',[value['message'][n] for n,_ in TYPES['ToolReview']]+[value['signature']])
    id=message_digest('ToolReview',value['message'],policy.domain)
    with access.connect() as db:
        db.execute('CREATE TABLE IF NOT EXISTS session_review_txs(id TEXT PRIMARY KEY,raw BLOB,tx_hash TEXT)')
        db.execute('BEGIN IMMEDIATE');old=db.execute('SELECT * FROM session_review_txs WHERE id=?',(id,)).fetchone()
        if old:raw=old['raw'];tx_hash=old['tx_hash']
        else:
            import rlp
            key=(root/'session-review-relay.key').read_bytes();account=Account.from_key(key)
            # Reserve relay nonces in the same durable transaction as raw bytes.
            # eth_pending alone misses another process's prepared-but-not-yet-broadcast tx.
            db.execute('CREATE TABLE IF NOT EXISTS session_review_cursor(slot INTEGER PRIMARY KEY,next_nonce INTEGER)')
            cursor=db.execute('SELECT next_nonce FROM session_review_cursor WHERE slot=1').fetchone()
            previous=max((int.from_bytes(rlp.decode(r[0])[0],'big') for r in db.execute('SELECT raw FROM session_review_txs')),default=-1)+1 if cursor is None else cursor[0]
            nonce=max(previous,int(rpc.call('eth_getTransactionCount',[account.address,'pending']),16))
            tx=dict(chainId=policy.config['deployment']['chainId'],nonce=nonce,gas=600000,gasPrice=0,to=to_checksum_address(contract.address),value=0,data=data)
            raw=bytes(Account.sign_transaction(tx,key).raw_transaction);tx_hash='0x'+keccak(raw).hex()
            db.execute('INSERT INTO session_review_txs VALUES (?,?,?)',(id,raw,tx_hash))
            db.execute('INSERT INTO session_review_cursor VALUES (1,?) ON CONFLICT(slot) DO UPDATE SET next_nonce=excluded.next_nonce',(nonce+1,))
    receipt=rpc.call('eth_getTransactionReceipt',[tx_hash])
    if receipt is None:
        if rpc.call('eth_getTransactionByHash',[tx_hash]) is None:rpc.call('eth_sendRawTransaction',['0x'+raw.hex()])
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            receipt=rpc.call('eth_getTransactionReceipt',[tx_hash])
            if receipt:break
            time.sleep(.25)
    if not receipt:raise ToolError('CHAIN_UNAVAILABLE')
    if receipt['status']!='0x1':raise ToolError('ADMISSION_REVIEW_REVERTED')
    receipts=[n.call('eth_getTransactionReceipt',[tx_hash]) for n in policy.chain.nodes]
    if any(r!=receipt for r in receipts):raise ToolError('CHAIN_UNAVAILABLE')
    return dict(tx_hash=tx_hash,block_number=str(int(receipt['blockNumber'],16)),block_hash=receipt['blockHash'],checked_nodes=len(receipts))

def start_batch_worker(root,c,stop):
    if not (root/'tool-sessions.json').exists():return None
    access=access_for(root,c);publisher=BatchPublisher(access,(root/'session-anchor.key').read_bytes())
    def run():
        while not stop.is_set():
            try:publisher.flush()
            except Exception:pass  # Durable PREPARED + original bytes remain pending; observable via session-list.
            if access.policy.config.get('conversation'):
                try:
                    from .conversation_runtime import access_for as conversation_access
                    from .conversation_audit import Publisher
                    Publisher(conversation_access(root,c),(root/'conversation-anchor.key').read_bytes()).flush()
                except Exception:pass  # Original outbox remains queryable; never synthesizes an anchor.
            stop.wait(5)
    thread=threading.Thread(target=run,daemon=True);thread.start();return thread
