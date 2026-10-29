"""Display-cache consistency and timing idempotency; synthetic RPC unit data."""
from types import SimpleNamespace
import pytest
from chainguard_gateway.chain_indexer import ChainEventIndexer
from chainguard_gateway.phase10_store import OperationsStore
from chainguard_gateway.transaction_metrics import TransactionMetrics
from chainguard_sandbox.protocol import ToolError


def test_event_cache_requires_all_four_nodes_and_commits_cursor_with_events(tmp_path):
    store=OperationsStore(tmp_path);address='0x'+'11'*20
    event=dict(transactionHash='0x'+'22'*32,logIndex='0x0',blockNumber='0x9',blockHash='0x'+'99'*32,address=address,topics=['0x'+'33'*32],data='0x',removed=False)
    class Node:
        mismatch=False
        def call(self,method,args=None):
            if method=='eth_blockNumber':return '0xa'
            if method=='eth_getBlockByNumber':return dict(hash='hash-'+args[0])
            if method=='eth_getLogs':return [] if self.mismatch else [event]
    nodes=[Node() for _ in range(4)];chain=SimpleNamespace(nodes=nodes,healthy=lambda:{},config={'contracts':{'ExecutionRegistry':{'address':address}}})
    index=ChainEventIndexer(store,chain);nodes[3].mismatch=True
    with pytest.raises(ToolError,match='CHAIN_UNAVAILABLE'):index.tick()
    assert store.cached('chain_event_cursor') is None
    nodes[3].mismatch=False;index.tick();index.tick()
    with store.db() as db:assert db.execute('SELECT count(*) FROM indexed_chain_events').fetchone()[0]==1
    assert store.cached('chain_event_cursor')['height']==10
    assert ChainEventIndexer(store,chain).store.cached('chain_event_cursor')['checked_nodes']==4


def test_transaction_measurement_preserves_first_submission_and_confirmation(tmp_path,capfd):
    from chainguard_gateway.chain_store import ChainStore
    store=ChainStore.create(tmp_path/'chain');metrics=TransactionMetrics(store)
    metrics.submitted('tx','action','reserve')
    with store.connect() as db:first=db.execute('SELECT submitted_at_ms FROM transaction_metrics').fetchone()[0]
    metrics.submitted('tx','action','reserve')
    with store.transaction() as db:metrics.confirmed(db,'tx')
    with store.connect() as db:original=tuple(db.execute('SELECT * FROM transaction_metrics').fetchone())
    import json
    line=json.loads(capfd.readouterr().err.strip())
    assert line['event']=='FOUR_NODE_RECEIPT_VERIFIED' and line['submitted_at_ms']==first
    assert line['confirmed_at_ms']>=first and 'params' not in line
    with store.transaction() as db:metrics.confirmed(db,'tx')
    with store.connect() as db:assert tuple(db.execute('SELECT * FROM transaction_metrics').fetchone())==original
    assert capfd.readouterr().err==''
    assert original[3]==first and original[5]>=0


def test_audit_rpc_allows_read_only_event_queries_but_rejects_writes(monkeypatch):
    from chainguard_gateway.audit_verify import AuditRPC
    from chainguard_gateway.chain_rpc import RPC
    calls=[]
    monkeypatch.setattr(RPC,'call',lambda self,method,params=None:calls.append((method,params)) or [])
    node=AuditRPC('http://unit.invalid')
    assert node.call('eth_getLogs',[{'fromBlock':'0x1','toBlock':'0x2'}])==[]
    assert calls[0][0]=='eth_getLogs'
    for method in ('eth_sendRawTransaction','eth_sendTransaction','admin_addPeer'):
        with pytest.raises(ValueError,match='read only'):node.call(method,[])
    assert len(calls)==1


def test_listener_backfills_known_receipts_after_restart_without_cursor(tmp_path):
    store=OperationsStore(tmp_path);address='0x'+'11'*20;queries=[]
    store.cache('records',{'action':dict(reservation_evidence=dict(block_number='12'),finalization_evidence=dict(block_number='14'))})
    class Node:
        def call(self,method,args=None):
            if method=='eth_blockNumber':return hex(1500)
            if method=='eth_getBlockByNumber':return dict(hash='hash-'+args[0])
            if method=='eth_getLogs':queries.append(args[0]);return []
    chain=SimpleNamespace(nodes=[Node() for _ in range(4)],healthy=lambda:{},config={'contracts':{'ExecutionRegistry':{'address':address}}})
    index=ChainEventIndexer(store,chain);index.tick()
    assert all(q['fromBlock']==hex(12) and q['toBlock']==hex(511) for q in queries)
    assert index.tick() is True
    assert store.cached('chain_event_cursor')['height']==1011


def test_event_rpc_does_not_block_business_projection_worker(tmp_path):
    import threading
    from chainguard_gateway.phase10_service import Operations
    entered=threading.Event();release=threading.Event();projected=threading.Event()
    def index():entered.set();release.wait(3)
    ops=Operations.__new__(Operations);ops.stop=threading.Event();ops.store=OperationsStore(tmp_path)
    ops.event_indexer=SimpleNamespace(tick=index)
    ops.sync=lambda:projected.set();ops.tick=lambda:None
    events=threading.Thread(target=ops.event_worker);business=threading.Thread(target=ops.worker)
    try:
        events.start();assert entered.wait(1)
        business.start();assert projected.wait(1)
    finally:
        ops.stop.set();release.set();events.join(3);business.join(3)
