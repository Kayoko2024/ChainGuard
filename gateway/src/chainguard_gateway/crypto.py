"""Frozen ActionIntent/commitment implementation; audit signatures are distinct."""

import json
import re
import secrets

from eth_account import Account
from eth_account.messages import encode_defunct, encode_typed_data
from eth_utils import keccak
from eth_keys.exceptions import BadSignature

from .canonical import ROOT, canonical, validate
from chainguard_sandbox.protocol import ToolError

PROTOCOL = json.loads((ROOT / "spec/eip712.json").read_text())
CURVE_N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141


def random_id():
    return "0x" + secrets.token_hex(32)


def label(kind, name):
    return "0x" + keccak(text=f"ChainGuard/{kind}/{name}").hex()


def commit(kind, salt, value):
    validate("Bytes32", salt)
    if kind not in {"params", "result", "evidence"}:
        raise ToolError("SCHEMA_INVALID")
    return "0x" + keccak(f"ChainGuard/{kind}/v1".encode() + b"\0" + bytes.fromhex(salt[2:]) + canonical(value)).hex()


def typed_intent(intent, domain):
    validate("ActionIntent", intent)
    return {"types": {"EIP712Domain": PROTOCOL["types"]["EIP712Domain"], "ActionIntent": PROTOCOL["types"]["ActionIntent"]},
            "primaryType": "ActionIntent", "domain": domain,
            "message": {typed: intent[wire] for wire, typed in PROTOCOL["json_to_typed"]["ActionIntent"].items()}}


def recover_intent(intent, domain, signature):
    validate("Signature", signature)
    data = bytes.fromhex(signature[2:])
    if not 0 < int.from_bytes(data[32:64]) <= CURVE_N // 2:
        raise ToolError("APPROVAL_INVALID")
    try:
        return Account.recover_message(encode_typed_data(full_message=typed_intent(intent, domain)), signature=data).lower()
    except (ValueError, TypeError, BadSignature):
        raise ToolError("APPROVAL_INVALID") from None


def sign_audit(key, data):
    return "0x" + Account.sign_message(encode_defunct(primitive=data), key).signature.hex()


def recover_audit(data, signature):
    try:
        if re.fullmatch(r"0x[0-9a-f]{130}", signature) is None:
            raise ValueError()
        raw = bytes.fromhex(signature[2:])
        if raw[-1] not in (27, 28) or not 0 < int.from_bytes(raw[32:64]) <= CURVE_N // 2:
            raise ValueError()
        return Account.recover_message(encode_defunct(primitive=data), signature=raw).lower()
    except (ValueError, TypeError, BadSignature):
        raise ToolError("RECEIPT_INVALID") from None
