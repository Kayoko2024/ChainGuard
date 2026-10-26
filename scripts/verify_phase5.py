"""Independent read-only Python verification of a real phase5 Besu run."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from eth_abi import encode
from eth_account import Account
from eth_account.messages import encode_typed_data
from eth_utils import keccak

from chain import RPC

ROOT = Path(__file__).resolve().parents[1]


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def hex_bytes(value):
    return bytes.fromhex(value.removeprefix("0x"))


def digest_fixture(report, spec, kind):
    action = kind == "ActionIntent"
    entry = report["intentFixture"] if action else report["receiptFixture"]
    message = entry["value"] if action else entry["data"]
    registry = "ExecutionRegistry" if action else "AuditRegistry"
    domain = {"name": spec["domains"][kind]["name"], "version": "1", "chainId": report["chainId"],
              "verifyingContract": report["contracts"][registry]["address"]}
    types = {"EIP712Domain": spec["types"]["EIP712Domain"], kind: spec["types"][kind]}
    typed = encode_typed_data(full_message={"domain": domain, "types": types, "primaryType": kind, "message": message})
    digest = "0x" + keccak(b"\x19" + typed.version + typed.header + typed.body).hex()
    if action:
        pairs = [(entry["requesterSignature"], report["publicSigners"]["requester"])]
        pairs += [(v["signature"], report["publicSigners"][role]) for v, role in zip(entry["approvals"], ["biz", "security"], strict=True)]
    else:
        pairs = [(entry["signature"], report["publicSigners"]["mailTool"])]
    for signature, address in pairs:
        require(Account.recover_message(typed, signature=signature).lower() == address.lower(), "Python recovered wrong signer")
    fields = spec["types"][kind]
    tuple_type = "(" + ",".join(f["type"] for f in fields) + ")"
    values = [hex_bytes(message[f["name"]]) if f["type"] == "bytes32" else int(message[f["name"]])
              if f["type"].startswith("uint") else message[f["name"]] for f in fields]
    method = "intentDigest" if action else "receiptDigest"
    data = "0x" + (keccak(text=f"{method}({tuple_type})")[:4] + encode([tuple_type], [values])).hex()
    for port in range(8545, 8549):
        actual = RPC(port).call("eth_call", [{"to": domain["verifyingContract"], "data": data}, "latest"])
        require(actual == digest, f"Python/Solidity digest mismatch on port {port}")
    return {"digest": digest, "domain": domain, "signatures_verified": len(pairs), "nodes_verified": 4}


def verify(folder):
    report = load(folder / "report.json")
    require(report["status"] == "PASS" and report["chainId"] == 20261026, "Run is not a passed real deployment")
    frozen_paths = set()
    frozen_entries = 0
    for name in ("config/phase0-freeze.json", "config/phase3-policy-freeze.json"):
        for file, digest in load(ROOT / name)["files"].items():
            frozen_paths.add(file)
            frozen_entries += 1
            require(hashlib.sha256((ROOT / file).read_bytes()).hexdigest() == digest, f"Frozen file drift: {file}")
    for file, digest in report["sourceSha256"].items():
        require(hashlib.sha256((ROOT / file).read_bytes()).hexdigest() == digest, f"Deployment source drift: {file}")
    verified_receipts = 0
    for i, tx in enumerate(report["transactions"], 1):
        saved = load(folder / f"tx-{i:02d}-{tx['name']}.json")
        require(len(saved["nodes"]) == 4, "Missing four-node saved receipts")
        for index, port in enumerate(range(8545, 8549)):
            rpc = RPC(port)
            require(int(rpc.call("eth_chainId"), 16) == 20261026, "Wrong chain")
            actual = rpc.call("eth_getTransactionReceipt", [tx["hash"]])
            require(actual == saved["nodes"][index], "Live receipt differs from saved evidence")
            require(int(actual["status"], 16) == tx["expectedStatus"], "Unexpected receipt status")
            block = rpc.call("eth_getBlockByNumber", [actual["blockNumber"], False])
            require(block["hash"] == actual["blockHash"] and tx["hash"] in block["transactions"], "Wrong canonical block")
            verified_receipts += 1
    for entry in report["contracts"].values():
        for port in range(8545, 8549):
            code = RPC(port).call("eth_getCode", [entry["address"], "latest"])
            require(code != "0x" and "0x" + keccak(hex_bytes(code)).hex() == entry["codeHash"], "Deployed runtime code hash mismatch")
    spec = load(ROOT / "spec/eip712.json")
    result = {"status": "PASS", "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
              "transactions": len(report["transactions"]), "live_receipts_verified": verified_receipts,
              "action_intent": digest_fixture(report, spec, "ActionIntent"),
              "execution_receipt": digest_fixture(report, spec, "ExecutionReceipt"),
              "frozen_manifest_entries": frozen_entries, "frozen_unique_files": len(frozen_paths),
              "boundary": report["scope"]}
    output = folder / "python-verification.json"
    # Preserve previous verifier observations if this read-only check is repeated.
    if output.exists():
        output = folder / ("python-verification-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".json")
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_directory", type=Path)
    args = parser.parse_args()
    verify(args.run_directory.resolve())
