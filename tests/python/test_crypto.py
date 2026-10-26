import copy
import hashlib

import pytest
import rfc8785
from eth_abi import encode
from eth_account import Account
from eth_account.messages import encode_typed_data
from eth_utils import keccak

N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141


def raw(value):
    return bytes.fromhex(value[2:])


def test_jcs_salts_and_three_commitment_domains(vector):
    for kind, data in vector["commitments"].items():
        canonical = rfc8785.dumps(data["value"])
        assert canonical == raw(data["canonical_utf8_hex"])
        assert canonical.decode() == data["canonical_utf8"]
        preimage = f"ChainGuard/{kind}/v1".encode() + b"\0" + raw(data["salt"]) + canonical
        assert preimage == raw(data["preimage_hex"])
        assert keccak(preimage) == raw(data["commitment"])
        assert keccak(preimage) != hashlib.sha3_256(preimage).digest()
        assert keccak(preimage[:-1] + bytes([preimage[-1] ^ 1])) != raw(data["commitment"])
        changed_salt = bytes([raw(data["salt"])[0] ^ 1]) + raw(data["salt"])[1:]
        assert keccak(f"ChainGuard/{kind}/v1".encode() + b"\0" + changed_salt + canonical) != raw(data["commitment"])
    data = vector["commitments"]["params"]
    assert keccak(b"ChainGuard/result/v1\0" + raw(data["salt"]) + raw(data["canonical_utf8_hex"])) != raw(data["commitment"])
    edge = vector["jcs_edge_case"]
    assert rfc8785.dumps(edge["input"]) == raw(edge["canonical_utf8_hex"])
    assert rfc8785.dumps({"text": "é"}) != rfc8785.dumps({"text": "e\u0301"})


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), 2**64, "\ud800"])
def test_jcs_rejects_nonportable_values(invalid):
    with pytest.raises((ValueError, rfc8785.CanonicalizationError)):
        rfc8785.dumps({"invalid": invalid})


@pytest.mark.parametrize("kind", ["ActionIntent", "ExecutionReceipt"])
def test_eth_account_and_independent_abi_hashes_and_signatures(kind, vector, protocol):
    entry = vector["vectors"][kind]
    typed = entry["typed_data"]
    expected = entry["expected"]
    signed = encode_typed_data(full_message=typed)
    fields = protocol["types"][kind]
    types = ["bytes32"] + [field["type"] for field in fields]
    values = [raw(expected["type_hash"])]
    for field in fields:
        value = typed["message"][field["name"]]
        values.append(int(value) if field["type"].startswith("uint") else raw(value) if field["type"] == "bytes32" else value)
    assert keccak(encode(types, values)) == signed.body == raw(expected["struct_hash"])
    assert signed.header == raw(expected["domain_separator"])
    digest = keccak(b"\x19\x01" + signed.header + signed.body)
    assert digest == raw(expected["digest"])
    for signature in entry["signatures"]:
        sig = raw(signature["signature"])
        assert len(sig) == 65 and sig[-1] in (27, 28)
        assert 0 < int.from_bytes(sig[32:64]) <= N // 2
        assert Account.recover_message(signed, signature=sig).lower() == signature["signer"]


@pytest.mark.parametrize("kind", ["ActionIntent", "ExecutionReceipt"])
def test_every_signed_field_and_domain_component_is_bound(kind, vector, protocol):
    entry = vector["vectors"][kind]
    for field in protocol["types"][kind]:
        altered = copy.deepcopy(entry["typed_data"])
        original = altered["message"][field["name"]]
        if field["type"].startswith("uint"):
            altered["message"][field["name"]] = str(int(original) + 1)
        elif field["type"] == "address":
            altered["message"][field["name"]] = "0x3333333333333333333333333333333333333333"
        else:
            altered["message"][field["name"]] = "0x" + bytes([raw(original)[0] ^ 1]).hex() + original[4:]
        signed = encode_typed_data(full_message=altered)
        for sig in entry["signatures"]:
            assert Account.recover_message(signed, signature=sig["signature"]).lower() != sig["signer"], field["name"]
    for key, value in {"name": "Other Registry", "version": "2", "chainId": "31338", "verifyingContract": "0x4444444444444444444444444444444444444444"}.items():
        altered = copy.deepcopy(entry["typed_data"])
        altered["domain"][key] = value
        signed = encode_typed_data(full_message=altered)
        for sig in entry["signatures"]:
            assert Account.recover_message(signed, signature=sig["signature"]).lower() != sig["signer"], key
