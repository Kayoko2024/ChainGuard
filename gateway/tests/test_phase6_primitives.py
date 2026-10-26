"""Unit checks only. Real Besu/tool/mTLS acceptance runs in the phase6 lab."""
import json
from pathlib import Path

from eth_account import Account
from eth_account.messages import encode_typed_data
from eth_abi import decode
from eth_utils import keccak
import pytest

from chainguard_gateway.canonical import ROOT
from chainguard_gateway.chain_crypto import digest, sign_receipt, recover_receipt
from chainguard_gateway.chain_rpc import Contract, abi_type
from chainguard_gateway.chain_store import ChainStore
from chainguard_gateway.crypto import PROTOCOL, CURVE_N
from chainguard_sandbox.protocol import ToolError
from chainguard_gateway.chain_service import ChainService
from chainguard_gateway.chain_transport import service_identity
from types import SimpleNamespace


@pytest.fixture
def vector():
    return json.loads((ROOT/'spec/vectors/eip712-v1.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('kind',['ActionIntent','ExecutionReceipt'])
def test_frozen_digest_and_actual_abi_roundtrip(vector,kind):
    v=vector['vectors'][kind]
    typed=v['typed_data']
    wire={source:typed['message'][target] for source,target in PROTOCOL['json_to_typed'][kind].items()}
    assert digest(kind,wire,typed['domain'])==v['expected']['digest']
    registry='ExecutionRegistry' if kind=='ActionIntent' else 'AuditRegistry'
    fn='intentDigest' if kind=='ActionIntent' else 'receiptDigest'
    contract=Contract(registry,typed['domain']['verifyingContract'],None)
    encoded=contract.data(fn,[typed['message']])
    parsed=contract.decode_input(fn,encoded)[0]
    assert [dict(name=c['name'],type=c['type']) for c in contract.function(fn)['inputs'][0]['components']]==PROTOCOL['types'][kind]
    assert {k:str(value) if isinstance(value,int) else value for k,value in parsed.items()}=={k:str(value) if isinstance(value,int) else value for k,value in typed['message'].items()}


def test_tool_receipt_signing_and_high_s_rejection(vector):
    v=vector['vectors']['ExecutionReceipt']['typed_data']
    wire={source:v['message'][target] for source,target in PROTOCOL['json_to_typed']['ExecutionReceipt'].items()}
    key=Account.create()
    signature=sign_receipt(key.key,wire,v['domain'])
    assert recover_receipt(wire,v['domain'],signature)==key.address.lower()
    wrong=dict(wire,result_commit='0x'+'99'*32)
    assert recover_receipt(wrong,v['domain'],signature)!=key.address.lower()
    raw=bytes.fromhex(signature[2:])
    high=raw[:32]+(CURVE_N-int.from_bytes(raw[32:64])).to_bytes(32,'big')+bytes([27 if raw[-1]==28 else 28])
    with pytest.raises(ToolError,match='RECEIPT_INVALID'): recover_receipt(wire,v['domain'],'0x'+high.hex())


def test_chain_store_encryption_and_transaction_rollback(tmp_path):
    store=ChainStore.create(tmp_path/'gateway')
    secret={'body':'local-private-body','salt':'local-private-salt'}
    encrypted=store.seal('receipt',secret)
    assert b'local-private' not in encrypted
    assert store.unseal('receipt',encrypted)==secret
    with pytest.raises(ToolError,match='STATE_CONFLICT'): store.unseal('other',encrypted)
    with pytest.raises(RuntimeError):
        with store.transaction() as db:
            store.event(db,None,'MUST_ROLL_BACK',{})
            raise RuntimeError()
    with store.connect() as db: assert db.execute('SELECT count(*) FROM chain_events').fetchone()[0]==0


def test_reserve_abi_contains_original_requester_and_all_approvals(vector):
    v=vector['vectors']['ActionIntent']
    contract=Contract('ExecutionRegistry',v['typed_data']['domain']['verifyingContract'],None)
    signatures=[s['signature'] for s in v['signatures']]
    payload=contract.data('reserve',[v['typed_data']['message'],signatures[0],[{'signature':s} for s in signatures[1:]]])
    parsed=contract.decode_input('reserve',payload)
    assert parsed[0]['nonce']==9007199254740993
    assert parsed[1]==signatures[0]
    assert [a['signature'] for a in parsed[2]]==signatures[1:]
    with pytest.raises(ToolError,match='RESERVATION_UNCONFIRMED'): contract.decode_input('reserve','0x00000000'+payload[10:])


class OutboxRPC:
    """Unit-only transport failure injection; never used as chain acceptance evidence."""
    def __init__(self):
        self.sent=[]
        self.drop=True
        self.pending=None
        self.receipt=None
        self.consumed=4

    def call(self,method,args):
        if method=='eth_getTransactionCount': return hex(self.consumed)
        if method=='eth_getTransactionReceipt': return self.receipt
        if method=='eth_getTransactionByHash': return self.pending
        if method=='eth_sendRawTransaction':
            self.sent.append(args[0])
            if self.drop: raise ToolError('CHAIN_UNAVAILABLE')
            self.pending={'hash':'0x'+keccak(bytes.fromhex(args[0][2:])).hex()}
            return self.pending['hash']
        raise AssertionError(method)


def outbox_service(tmp_path):
    store=ChainStore.create(tmp_path/'gateway')
    rpc=OutboxRPC()
    chain=SimpleNamespace(rpc=rpc,config={'chainId':20261026},healthy=lambda:None)
    return ChainService(store,chain,None,Account.create().key,'0x'+'11'*20),rpc


def test_outbox_prebroadcast_restart_resubmits_identical_signed_bytes(tmp_path):
    service,rpc=outbox_service(tmp_path)
    contract=Contract('ExecutionRegistry','0x'+'22'*20,None)
    action='0x'+'33'*32
    with pytest.raises(ToolError,match='CHAIN_UNAVAILABLE'):
        service._transaction(action,'reserve',contract,'usedNonce',['0x'+'44'*20,'7'])
    with service.store.connect() as db:
        original=dict(db.execute('SELECT * FROM chain_transactions').fetchone())
    assert original['state']=='SENDING' and original['nonce']==4
    restarted=ChainService(service.store,service.chain,None,service.relayer.key,service.tool_signer)
    rpc.drop=False
    tx_hash,receipt=restarted._transaction(action,'reserve',contract,'usedNonce',['0x'+'44'*20,'7'])
    assert receipt is None and tx_hash==original['tx_hash']
    assert rpc.sent[0]==rpc.sent[1]
    restarted._transaction(action,'reserve',contract,'usedNonce',['0x'+'44'*20,'7'])
    assert len(rpc.sent)==2 # Found pending: only query; no further broadcast.
    with service.store.connect() as db:
        assert db.execute('SELECT count(*) FROM chain_transactions').fetchone()[0]==1


def test_outbox_never_replaces_consumed_nonce_or_resubmits_mined_transaction(tmp_path):
    service,rpc=outbox_service(tmp_path)
    contract=Contract('ExecutionRegistry','0x'+'22'*20,None)
    action='0x'+'33'*32
    with pytest.raises(ToolError): service._transaction(action,'reserve',contract,'usedNonce',['0x'+'44'*20,'7'])
    rpc.consumed=5
    with pytest.raises(ToolError,match='STATE_CONFLICT'):
        service._transaction(action,'reserve',contract,'usedNonce',['0x'+'44'*20,'7'])
    assert len(rpc.sent)==1
    rpc.receipt={'unit_only':'receipt-observed'}
    assert service._transaction(action,'reserve',contract,'usedNonce',['0x'+'44'*20,'7'])[1]==rpc.receipt
    assert len(rpc.sent)==1


@pytest.mark.parametrize('dispatched,expected',[(False,'RESERVED'),(True,'UNKNOWN')])
def test_restart_distinguishes_waiting_reservation_from_uncertain_dispatch(tmp_path,dispatched,expected):
    service,rpc=outbox_service(tmp_path)
    aid,tid='0x'+'33'*32,'0x'+'55'*32
    with service.store.transaction() as db:
        db.execute('INSERT INTO tasks(task_id,requester,agent,data) VALUES (?,?,?,?)',(tid,'r','a',b''))
        db.execute('INSERT INTO actions(action_id,task_id,tool_name,state,data) VALUES (?,?,?,?,?)',
            (aid,tid,'mail.send','RESERVED',service.store.seal('action/'+aid,{'dispatch_started':dispatched})))
    ChainService(service.store,service.chain,None,service.relayer.key,service.tool_signer)
    with service.store.connect() as db: assert service.store.action(db,aid)[0]['state']==expected
    assert not rpc.sent


def test_internal_identity_requires_verified_peer_and_independent_bearer():
    request=SimpleNamespace(scope={},headers={'x-client-fingerprint':'expected','authorization':'Bearer secret'})
    with pytest.raises(ToolError,match='AUTH_REQUIRED'): service_identity(request,'expected','secret')
    request.scope['chainguard_peer_fingerprint']='wrong'
    with pytest.raises(ToolError,match='FORBIDDEN'): service_identity(request,'expected','secret')
    request.scope['chainguard_peer_fingerprint']='expected'
    request.headers['authorization']='Bearer wrong'
    with pytest.raises(ToolError,match='AUTH_REQUIRED'): service_identity(request,'expected','secret')
    request.headers['authorization']='Bearer secret'
    service_identity(request,'expected','secret')
