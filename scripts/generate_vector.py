"""Create a NEW public protocol fixture; never write or print signing private keys.

Normal reproduction verifies the checked-in fixture. Running this script rotates its
ephemeral signers/signatures and is an intentional fixture revision, not a test step.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import rfc8785
from eth_account import Account
from eth_account.messages import encode_typed_data
from eth_utils import keccak

ROOT = Path(__file__).resolve().parents[1]


def hx(raw):
    return "0x" + bytes(raw).hex()


def commitment(kind, value, salt):
    canonical = rfc8785.dumps(value)
    preimage = f"ChainGuard/{kind}/v1".encode() + b"\0" + bytes.fromhex(salt[2:]) + canonical
    return {"value": value, "salt": salt, "canonical_utf8": canonical.decode(), "canonical_utf8_hex": hx(canonical), "preimage_hex": hx(preimage), "commitment": hx(keccak(preimage))}


def type_string(name, fields):
    return name + "(" + ",".join(f"{field['type']} {field['name']}" for field in fields) + ")"


def main():
    protocol = json.loads((ROOT / "spec/eip712.json").read_text())
    identities = {role: Account.create() for role in ["requester", "agent", "business", "security", "tool"]}
    params = commitment("params", {"to": ["report@inbox.chainguard.invalid"], "subject": "ChainGuard 测试摘要", "body": "仅用于本地沙箱；Cafe\u0301 不做 Unicode 归一化。"}, hx(bytes(range(1, 33))))
    result = commitment("result", {"mailbox_id": "local-message-0001", "accepted": True}, hx(bytes(range(33, 65))))
    evidence = commitment("evidence", {"record_id": "local-evidence-0001", "schema_version": 1}, hx(bytes(range(65, 97))))
    label = lambda namespace, value: hx(keccak(text=namespace + "/" + value))
    issued = int(datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc).timestamp())
    intent = {
        "schema_version": 1, "action_id": hx(bytes(range(97, 129))), "task_id": hx(bytes(range(129, 161))),
        "requester": identities["requester"].address.lower(), "agent": identities["agent"].address.lower(),
        "tool_id": label("ChainGuard/tool", "mail.send"), "resource_scope": label("ChainGuard/scope", "ORG_A_INTERNAL_MAIL"),
        "params_commit": params["commitment"], "policy_id": label("ChainGuard/policy", "POLICY_R2_MAIL"),
        "policy_epoch": "3", "nonce": "9007199254740993", "issued_at": str(issued), "expires_at": str(issued + 120), "risk": 2,
    }
    receipt = {
        "schema_version": 1, "action_id": intent["action_id"], "params_commit": intent["params_commit"],
        "result_commit": result["commitment"], "evidence_index_commit": evidence["commitment"], "executed_at": str(issued + 12), "outcome": 0,
    }
    fixture = {"fixture_version": 1, "purpose": "Cryptographic test data only. No business operation, deployment or transaction is asserted.", "chain_id": "31337", "observation_time": str(issued + 10), "commitments": {"params": params, "result": result, "evidence": evidence}, "intent_json": intent, "receipt_json": receipt, "vectors": {}}
    for name, payload, verifier in [("ActionIntent", intent, "0x1111111111111111111111111111111111111111"), ("ExecutionReceipt", receipt, "0x2222222222222222222222222222222222222222")]:
        config = protocol["domains"][name]
        domain = {"name": config["name"], "version": config["version"], "chainId": "31337", "verifyingContract": verifier}
        message = {typed: payload[wire] for wire, typed in protocol["json_to_typed"][name].items()}
        typed = {"types": {"EIP712Domain": protocol["types"]["EIP712Domain"], name: protocol["types"][name]}, "primaryType": name, "domain": domain, "message": message}
        signable = encode_typed_data(full_message=typed)
        digest = keccak(b"\x19" + signable.version + signable.header + signable.body)
        roles = ["requester", "business", "security"] if name == "ActionIntent" else ["tool"]
        signatures = [{"fixture_role": role, "signer": identities[role].address.lower(), "signature": hx(Account.sign_message(signable, identities[role].key).signature)} for role in roles]
        type_text = type_string(name, protocol["types"][name])
        fixture["vectors"][name] = {"typed_data": typed, "expected": {"type_string": type_text, "type_hash": hx(keccak(text=type_text)), "domain_separator": hx(signable.header), "struct_hash": hx(signable.body), "digest": hx(digest)}, "signatures": signatures}
    edge = {"\ue000": "BMP", "😀": "astral", "z": "e\u0301"}
    fixture["jcs_edge_case"] = {"input": edge, "canonical_utf8_hex": hx(rfc8785.dumps(edge))}
    destination = ROOT / "spec/vectors/eip712-v1.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(fixture, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Public golden vector created; private keys were not persisted")


if __name__ == "__main__":
    main()
