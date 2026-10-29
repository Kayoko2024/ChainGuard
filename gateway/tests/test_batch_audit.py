"""Threshold and lost-broadcast recovery unit tests. RPC fixtures are not chain evidence."""
import json
import time
from types import SimpleNamespace
import pytest
from eth_account import Account
from eth_utils import keccak
from chainguard_gateway.batch_audit import BatchPublisher
from chainguard_gateway.session_grants import SessionAccess
from chainguard_gateway.phase10_store import OperationsStore
from chainguard_sandbox.protocol import ToolError

KEY=bytes.fromhex('19'*32)
def fixture(tmp_path,monkeypatch,count,age=0):
    s=OperationsStore(tmp_path);access=SessionAccess(SimpleNamespace(connect=s.db,seal=s.seal,unseal=s.open),None)
    class RPC:
        raws=[];receipt=None;known=False;lose=False
        def call(self,method,args=None):
            if method=='eth_getTransactionCount':return '0x0'
            if method=='eth_getTransactionReceipt':return self.receipt
            if method=='eth_getTransactionByHash':return {} if self.known else None
            if method=='eth_sendRawTransaction':
                self.raws.append(args[0])
                if self.lose:raise ToolError('CHAIN_UNAVAILABLE')
                self.known=True;return '0x'+keccak(bytes.fromhex(args[0][2:])).hex()
            raise AssertionError(method)
    rpc=RPC();rpc.raws=[]
    policy=SimpleNamespace(snapshot=lambda:{},chain=SimpleNamespace(rpc=rpc),config=dict(anchor=dict(address='0x'+'21'*20),deployment=dict(chainId=20261026)))
    access.policy=policy
    class Contract:
        def __init__(self,*args):pass
        def call(self,name):assert name=='publisher';return Account.from_key(KEY).address.lower()
        def data(self,*args):return '0x1234'
    monkeypatch.setattr('chainguard_gateway.batch_audit.Contract',Contract)
    monkeypatch.setattr('chainguard_gateway.batch_audit.verify_batch',lambda *args:{'unit_fixture':True})
    with access.connect() as db:
        for i in range(count):
            log=dict(sequence=i+1,timestamp=int(time.time())-age,call_id=str(i))
            db.execute('INSERT INTO session_logs(call_id,data) VALUES (?,?)',(str(i),json.dumps(log)))
    return access,rpc

@pytest.mark.parametrize('count,age,expected',[(49,0,'WAITING'),(50,0,'PENDING'),(1,301,'PENDING'),(0,0,'IDLE')])
def test_threshold_50_or_300_seconds(tmp_path,monkeypatch,count,age,expected):
    a,rpc=fixture(tmp_path,monkeypatch,count,age);assert BatchPublisher(a,KEY).flush()['status']==expected
    assert len(rpc.raws)==(expected=='PENDING')

def test_restart_reuses_exact_signed_transaction_and_one_batch(tmp_path,monkeypatch):
    a,rpc=fixture(tmp_path,monkeypatch,3);rpc.lose=True
    with pytest.raises(ToolError,match='CHAIN_UNAVAILABLE'):BatchPublisher(a,KEY).flush(force=True)
    original=rpc.raws[0];rpc.lose=False
    assert BatchPublisher(a,KEY).flush(force=True)['status']=='PENDING'
    assert rpc.raws==[original,original]
    assert BatchPublisher(a,KEY).flush(force=True)['status']=='PENDING' and len(rpc.raws)==2
    rpc.receipt={'status':'0x1'}
    assert BatchPublisher(a,KEY).flush(force=True)['status']=='ANCHORED'
    assert BatchPublisher(a,KEY).flush(force=True)['status']=='IDLE'
    with a.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM session_batches').fetchone()[0]==1
        assert db.execute('SELECT COUNT(*) FROM session_logs WHERE batch_id IS NOT NULL').fetchone()[0]==3
