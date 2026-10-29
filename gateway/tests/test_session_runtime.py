"""Relay journal tests; RPC fixtures are unit tests, never deployment evidence."""
import contextlib
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
import rlp
from eth_utils import keccak

from chainguard_gateway.phase10_store import OperationsStore
from chainguard_gateway.session_grants import SessionAccess
from chainguard_gateway.session_runtime import submit_review
from chainguard_sandbox.protocol import ToolError


def relay(tmp_path):
    store = OperationsStore(tmp_path)
    (tmp_path / 'session-review-relay.key').write_bytes(bytes.fromhex('29' * 32))

    @contextlib.contextmanager
    def connect():
        db = sqlite3.connect(tmp_path / 'relay.sqlite3', isolation_level=None, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            yield db
        finally:
            db.close()

    class RPC:
        def __init__(self):
            self.sent = []
            self.receipts = {}
            self.fail_before = False
            self.status = '0x1'
            self.lock = threading.Lock()

        def call(self, method, args):
            with self.lock:
                if method == 'eth_getTransactionCount':
                    # Deliberately stale: an unbroadcast journal entry is invisible to RPC.
                    return '0x0'
                if method == 'eth_getTransactionReceipt':
                    return self.receipts.get(args[0])
                if method == 'eth_getTransactionByHash':
                    return None
                if method == 'eth_sendRawTransaction':
                    self.sent.append(args[0])
                    if self.fail_before:
                        raise ToolError('CHAIN_UNAVAILABLE')
                    tx_hash = '0x' + keccak(bytes.fromhex(args[0][2:])).hex()
                    self.receipts[tx_hash] = {'status': self.status, 'transactionHash': tx_hash,
                        'blockNumber': '0x1', 'blockHash': '0x' + '42' * 32}
                    return tx_hash
                raise AssertionError(method)

    rpc = RPC()
    policy = SimpleNamespace(
        snapshot=lambda: {}, domain=dict(name='ChainGuard ToolAdmissionRegistry', version='1',
            chainId=20261026, verifyingContract='0x' + '23' * 20),
        config=dict(registry=dict(address='0x' + '23' * 20), deployment=dict(chainId=20261026)),
        chain=SimpleNamespace(rpc=rpc, nodes=[rpc, rpc]))
    adapter = SimpleNamespace(connect=connect, seal=store.seal, unseal=store.open)
    return SessionAccess(adapter, policy), rpc, adapter, policy


def review(n):
    return dict(message=dict(revision='0x' + f'{n:064x}', riskLevel=1, enabled=True,
        nonce=n, epoch=1, issuedAt=1, expiresAt=301), signature='0x' + '00' * 65)


def test_parallel_relay_instances_reserve_distinct_durable_nonces(tmp_path):
    access, rpc, adapter, policy = relay(tmp_path)

    def run(n):
        # Separate gate objects, connections, and locks; only the durable DB is shared.
        return submit_review(SessionAccess(adapter, policy), tmp_path, review(n))

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(run, range(1, 9)))
    assert len({r['tx_hash'] for r in results}) == 8
    assert sorted(int.from_bytes(rlp.decode(bytes.fromhex(raw[2:]))[0], 'big')
        for raw in rpc.sent) == list(range(8))
    with access.connect() as db:
        assert db.execute('SELECT next_nonce FROM session_review_cursor').fetchone()[0] == 8


def test_unbroadcast_review_survives_restart_and_reuses_original_bytes(tmp_path):
    access, rpc, adapter, policy = relay(tmp_path)
    rpc.fail_before = True
    with pytest.raises(ToolError, match='CHAIN_UNAVAILABLE'):
        submit_review(access, tmp_path, review(1))
    original = rpc.sent[0]
    rpc.fail_before = False
    # Another process prepares a different review before the first one recovers.
    submit_review(SessionAccess(adapter, policy), tmp_path, review(2))
    result = submit_review(SessionAccess(adapter, policy), tmp_path, review(1))
    assert rpc.sent == [original, rpc.sent[1], original]
    assert int.from_bytes(rlp.decode(bytes.fromhex(rpc.sent[1][2:]))[0], 'big') == 1
    assert result['tx_hash'] == '0x' + keccak(bytes.fromhex(original[2:])).hex()


def test_confirmed_revert_never_replaces_the_original_signed_review(tmp_path):
    access, rpc, adapter, policy = relay(tmp_path)
    rpc.status = '0x0'
    for gate in [access, SessionAccess(adapter, policy)]:
        with pytest.raises(ToolError, match='ADMISSION_REVIEW_REVERTED'):
            submit_review(gate, tmp_path, review(1))
    assert len(rpc.sent) == 1
    with access.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM session_review_txs').fetchone()[0] == 1
        assert db.execute('SELECT next_nonce FROM session_review_cursor').fetchone()[0] == 1
