"""Frozen wire structs for actual chain domains; no private keys in an Agent."""
from eth_account import Account
from eth_account.messages import encode_typed_data
from eth_utils import keccak
from eth_keys.exceptions import BadSignature

from .canonical import validate
from .crypto import PROTOCOL, CURVE_N
from chainguard_sandbox.protocol import ToolError


def typed(kind, value, domain):
    validate(kind, value)
    return {"types": {"EIP712Domain": PROTOCOL["types"]["EIP712Domain"], kind: PROTOCOL["types"][kind]},
            "primaryType": kind, "domain": domain,
            "message": {target: value[source] for source, target in PROTOCOL["json_to_typed"][kind].items()}}


def digest(kind, value, domain):
    message = encode_typed_data(full_message=typed(kind, value, domain))
    return "0x" + keccak(b"\x19" + message.version + message.header + message.body).hex()


def sign_receipt(key, value, domain):
    return "0x" + Account.sign_message(encode_typed_data(full_message=typed("ExecutionReceipt", value, domain)), key).signature.hex()


def recover_receipt(value, domain, signature):
    validate("Signature", signature)
    raw = bytes.fromhex(signature[2:])
    if not 0 < int.from_bytes(raw[32:64]) <= CURVE_N // 2:
        raise ToolError("RECEIPT_INVALID")
    try:
        return Account.recover_message(encode_typed_data(full_message=typed("ExecutionReceipt", value, domain)), signature=raw).lower()
    except (ValueError, TypeError, BadSignature):
        raise ToolError("RECEIPT_INVALID") from None
