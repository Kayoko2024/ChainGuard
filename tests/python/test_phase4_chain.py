"""Configuration/encoding safety tests, separate from real network acceptance."""
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tomllib

import pytest
from eth_account import Account

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('chain_operations', ROOT / 'scripts/chain.py')
chain = importlib.util.module_from_spec(spec)
spec.loader.exec_module(chain)
pull_spec = importlib.util.spec_from_file_location('besu_pull', ROOT / 'scripts/pull_besu_image.py')
pull = importlib.util.module_from_spec(pull_spec)
pull_spec.loader.exec_module(pull)


def test_genesis_consensus_and_fixture_separation():
    template = chain.load(ROOT / 'chain/genesis-template.json')
    assert template['blockchain']['nodes'] == {'generate': True, 'count': 4}
    config = template['genesis']['config']
    assert config['chainId'] == chain.CHAIN_ID != 31337
    assert config['qbft'] == {'blockperiodseconds': 2, 'epochlength': 30000, 'requesttimeoutseconds': 4}
    assert config['londonBlock'] == 0 and config['zeroBaseFee'] is True
    assert template['genesis']['alloc'] == {}  # Real accounts generated at init.
    assert bytes.fromhex(template['genesis']['mixHash'][2:]) == b'ctical byzantine fault tolerance'


def test_rpc_api_surface_has_no_admin_or_personal():
    config = tomllib.loads((ROOT / 'chain/node.toml').read_text())
    assert set(config['rpc-http-api']) == {'ETH', 'NET', 'WEB3', 'QBFT'}
    assert '*' not in config['host-allowlist']
    assert config['rpc-ws-enabled'] is False
    assert config['graphql-http-enabled'] is False
    assert config['discovery-enabled'] is False
    assert config['max-peers'] == 3
    assert config['sync-min-peers'] <= 3 and config['bootnodes'] == []
    assert config['node-private-key-file'] == '/var/lib/besu/key'


def test_image_lock_is_content_pinned():
    lock = chain.load(ROOT / 'chain/image.lock.json')
    assert lock['besu_version'] == '25.10.0'
    assert lock['official_repository'] == 'docker.io/hyperledger/besu'
    for name in ['manifest_digest', 'index_digest', 'image_id']:
        assert lock[name].startswith('sha256:') and len(lock[name]) == 71
    assert lock['compose_image'] == lock['image_id']


def test_official_content_digest_rejects_tampering():
    import hashlib
    content = b'official-registry-encoding-test'
    digest = 'sha256:' + hashlib.sha256(content).hexdigest()
    pull.verify(content, digest)
    with pytest.raises(ValueError, match='digest mismatch'):
        pull.verify(content + b'tampered', digest)


def test_private_key_archive_has_only_explicit_file():
    # Synthetic data tests tar metadata only; network tests use Besu-generated keys.
    result = chain.archive({'key': b'encoding-test'})
    with tarfile.open(fileobj=io.BytesIO(result)) as tar:
        member, = tar.getmembers()
        assert member.name == 'key' and member.mode == 0o600
        assert member.uid == member.gid == 1000
        assert tar.extractfile(member).read() == b'encoding-test'


def test_transaction_signing_binds_chain_and_sender():
    signer, receiver = Account.create(), Account.create()
    tx = {'chainId': chain.CHAIN_ID, 'nonce': 0, 'to': receiver.address, 'value': 1, 'gas': 21000, 'gasPrice': 0}
    valid = Account.sign_transaction(tx, signer.key)
    wrong = Account.sign_transaction({**tx, 'chainId': chain.CHAIN_ID+1}, signer.key)
    assert Account.recover_transaction(valid.raw_transaction) == signer.address
    assert valid.hash != wrong.hash


@pytest.fixture
def receipt_example():
    # These fixtures only test rejection logic. They are never emitted as evidence.
    receipt = {'transactionHash': '0x'+'11'*32, 'status': '0x1', 'gasUsed': '0x5208', 'from': '0x'+'22'*20, 'to': '0x'+'33'*20, 'blockHash': '0x'+'44'*32, 'blockNumber': '0x7'}
    block = {'hash': receipt['blockHash'], 'number': receipt['blockNumber'], 'transactions': [receipt['transactionHash']]}
    return receipt, block


def test_receipt_block_membership(receipt_example):
    receipt, block = receipt_example
    chain.validate_receipt(receipt, receipt['transactionHash'], receipt['from'], receipt['to'], block)


@pytest.mark.parametrize('field,value', [('status', '0x0'), ('gasUsed', '0x0'), ('transactionHash', '0x'+'55'*32), ('from', '0x'+'00'*20), ('to', '0x'+'00'*20), ('blockHash', '0x'+'66'*32), ('blockNumber', '0x8')])
def test_bad_receipt_is_not_confirmation(receipt_example, field, value):
    receipt, block = receipt_example
    args = (receipt['transactionHash'], receipt['from'], receipt['to'], block)
    with pytest.raises(ValueError):
        chain.validate_receipt({**receipt, field: value}, *args)


def test_missing_receipt_is_not_confirmation(receipt_example):
    receipt, block = receipt_example
    with pytest.raises(ValueError):
        chain.validate_receipt(None, receipt['transactionHash'], receipt['from'], receipt['to'], block)


def test_block_omitting_transaction_is_not_confirmation(receipt_example):
    receipt, block = receipt_example
    with pytest.raises(ValueError):
        chain.validate_receipt(receipt, receipt['transactionHash'], receipt['from'], receipt['to'], {**block, 'transactions': []})
