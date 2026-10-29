"""Pinned Besu reads and ABI encoding. HTTP evidence never grants permission."""
import json
from functools import lru_cache
from pathlib import Path
import time
import urllib.request

from eth_abi import encode, decode
from eth_abi.exceptions import DecodingError
from eth_utils import keccak

from .canonical import canonical, validate, ROOT
from .chain_crypto import digest
from .crypto import PROTOCOL, label, recover_intent
from .approvals import inspect_approvals
from .mail_window import mail_lifetime
from chainguard_sandbox.protocol import ToolError

ZERO = "0x" + "00" * 32
STATES = ("NONE", "RESERVED", "UNKNOWN", "FINALIZED_OK", "FINALIZED_ERROR", "FINALIZED_REJECTED")


@lru_cache(maxsize=1)
def rpc_transport():
    # build_opener also creates an HTTPSHandler/SSLContext for HTTP endpoints.
    # Rebuilding it for each periodic policy snapshot retains native TLS memory
    # in handler cycles until a full GC (not accounted for by Python's GC budget).
    # The transport is stateless across requests; no RPC data or verdict is cached.
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def abi_type(p):
    return "(" + ",".join(abi_type(c) for c in p["components"]) + ")" + p["type"][5:] if p["type"].startswith("tuple") else p["type"]


def pack(p, value):
    if p["type"].endswith("[]"):
        return [pack(dict(p, type=p["type"][:-2]), item) for item in value]
    if p["type"] == "tuple":
        return tuple(pack(c, value[c["name"]] if isinstance(value, dict) else value[i]) for i, c in enumerate(p["components"]))
    if p["type"].startswith("bytes") and isinstance(value, str):
        return bytes.fromhex(value.removeprefix("0x"))
    if p["type"].startswith("uint"):
        return int(value)
    return value


def unpack(p, value):
    if p["type"].endswith("[]"):
        return [unpack(dict(p, type=p["type"][:-2]), item) for item in value]
    if p["type"] == "tuple":
        return {c["name"]: unpack(c, item) for c, item in zip(p["components"], value, strict=True)}
    return "0x" + value.hex() if isinstance(value, bytes) else value


class RPC:
    def __init__(self, url):
        self.url = url
        self.opener = rpc_transport()

    def call(self, method, params=None):
        request = urllib.request.Request(self.url, canonical({"jsonrpc": "2.0", "id": 1, "method": method, "params": params or []}),
                                         {"Content-Type": "application/json", "Host": "localhost"})
        try:
            with self.opener.open(request, timeout=3) as response:
                result = json.load(response)
            if result.get("id") != 1 or result.get("jsonrpc") != "2.0" or "error" in result:
                raise ValueError()
            return result["result"]
        except (OSError, ValueError, KeyError, TimeoutError):
            raise ToolError("CHAIN_UNAVAILABLE") from None


class Contract:
    def __init__(self, name, address, rpc, abi=None):
        self.address, self.rpc = address.lower(), rpc
        self.abi = abi or json.loads((ROOT / f"results/phase5/besu-run-01/{name}.abi.json").read_text())

    def function(self, name):
        return next(e for e in self.abi if e.get("type") == "function" and e.get("name") == name)

    def data(self, name, args):
        fn = self.function(name)
        signature = name + "(" + ",".join(abi_type(p) for p in fn["inputs"]) + ")"
        return "0x" + (keccak(text=signature)[:4] + encode([abi_type(p) for p in fn["inputs"]],
            [pack(p, v) for p, v in zip(fn["inputs"], args, strict=True)])).hex()

    def decode_input(self, name, data):
        fn = self.function(name)
        if data[:10] != self.data(name, [pack_default(p) for p in fn["inputs"]])[:10]:
            raise ToolError("RESERVATION_UNCONFIRMED")
        try:
            return [unpack(p, v) for p, v in zip(fn["inputs"], decode([abi_type(p) for p in fn["inputs"]], bytes.fromhex(data[10:])), strict=True)]
        except (ValueError, TypeError, DecodingError):
            raise ToolError("RESERVATION_UNCONFIRMED") from None

    def call(self, name, args=(), block="latest"):
        fn = self.function(name)
        raw = self.rpc.call("eth_call", [{"to": self.address, "data": self.data(name, args)}, block])
        try:
            result = [unpack(p, v) for p, v in zip(fn["outputs"], decode([abi_type(p) for p in fn["outputs"]], bytes.fromhex(raw[2:])), strict=True)]
            return result[0] if len(result) == 1 else result
        except (ValueError, TypeError, DecodingError):
            raise ToolError("CHAIN_UNAVAILABLE") from None


def pack_default(p):
    if p["type"].endswith("[]"): return []
    if p["type"] == "tuple": return {c["name"]: pack_default(c) for c in p["components"]}
    if p["type"].startswith("bytes"): return "0x" + "00" * (int(p["type"][5:]) if p["type"][5:] else 0)
    if p["type"] == "address": return "0x" + "00" * 20
    if p["type"] == "bool": return False
    return 0


class Chain:
    def __init__(self, deployment, urls):
        self.config = deployment
        self.mail_lifetime = mail_lifetime(deployment)
        self.nodes = [RPC(u) for u in urls]
        if len(self.nodes) < 2 or len(set(urls)) != len(urls): raise ValueError("Two independent node endpoints required")
        self.rpc = self.nodes[0]
        self.policy = Contract("PolicyRegistry", deployment["contracts"]["PolicyRegistry"]["address"], self.rpc)
        self.execution = Contract("ExecutionRegistry", deployment["contracts"]["ExecutionRegistry"]["address"], self.rpc)
        self.audit = Contract("AuditRegistry", deployment["contracts"]["AuditRegistry"]["address"], self.rpc)
        self.domain = {"name": "ChainGuard ExecutionRegistry", "version": "1", "chainId": str(deployment["chainId"]), "verifyingContract": self.execution.address}
        self.receipt_domain = dict(self.domain, name="ChainGuard AuditRegistry", verifyingContract=self.audit.address)

    def healthy(self):
        heights = []
        expected = sorted(v.lower() for v in self.config["validators"])
        for node in self.nodes:
            if int(node.call("eth_chainId"), 16) != self.config["chainId"] or node.call("eth_syncing") is not False:
                raise ToolError("CHAIN_UNAVAILABLE")
            if node.call("eth_getBlockByNumber", ["0x0", False])["hash"] != self.config["genesisHash"]:
                raise ToolError("CHAIN_UNAVAILABLE")
            if sorted(v.lower() for v in node.call("qbft_getValidatorsByBlockNumber", ["latest"])) != expected:
                raise ToolError("CHAIN_UNAVAILABLE")
            if int(node.call("net_peerCount"),16) != 3: raise ToolError("CHAIN_UNAVAILABLE")
            heights.append(int(node.call("eth_blockNumber"),16))
        height = min(heights)
        blocks = [n.call("eth_getBlockByNumber", [hex(height), False]) for n in self.nodes]
        if len({b["hash"] for b in blocks}) != 1 or abs(int(time.time()) - int(blocks[0]["timestamp"],16)) > 10:
            raise ToolError("CHAIN_UNAVAILABLE")
        for name, item in self.config["contracts"].items():
            for node in self.nodes:
                code = node.call("eth_getCode", [item["address"], hex(height)])
                if "0x" + keccak(bytes.fromhex(code[2:])).hex() != item["codeHash"]: raise ToolError("CHAIN_UNAVAILABLE")
        block = hex(height)
        if self.mail_lifetime != 120:
            window = Contract('PolicyRegistry', self.policy.address, self.rpc, abi=[
                {'type':'function','name':name,'inputs':[],'outputs':[{'type':kind}]} for name,kind in [('sourcePolicy','address'),('mailLifetime','uint64')]])
            if (window.call('sourcePolicy',block=block) != self.config['contracts']['SourcePolicyRegistry']['address'].lower() or
                    window.call('mailLifetime',block=block) != self.mail_lifetime):
                raise ToolError('CHAIN_UNAVAILABLE')
        if (self.execution.call("auditRegistry", block=block) != self.audit.address or
            self.execution.call("policyRegistry", block=block) != self.policy.address or
            self.audit.call("executionRegistry", block=block) != self.execution.address or
            self.audit.call("policyRegistry", block=block) != self.policy.address): raise ToolError("CHAIN_UNAVAILABLE")
        return {"number": str(height), "hash": blocks[0]["hash"], "timestamp": str(int(blocks[0]["timestamp"],16))}

    def actor(self, address, scope, block):
        roles = [role for role in ("REQUESTER", "AGENT", "BUSINESS_APPROVER", "SECURITY_APPROVER", "HUMAN_APPROVER", "TOOL_SIGNER")
                 if self.policy.call("hasRole", [label("role",role),address], block)]
        org = self.policy.call("orgOf", [address], block)
        return {"address":address, "organization":org, "active":org != ZERO and not self.policy.call("isSignerRevoked",[address],block),
                "roles":roles, "resource_scopes":["ORG_A_INTERNAL_MAIL"] if self.policy.call("hasScope",[address,scope],block) else []}

    def validate_authorization(self, intent, requester_signature, approvals, snapshot, *, live=True, complete=True):
        validate("ActionIntent",intent)
        if intent["risk"] != 2 or intent["tool_id"] != label("tool","mail.send") or intent["resource_scope"] != label("scope","ORG_A_INTERNAL_MAIL"):
            raise ToolError("POLICY_DENY")
        now, block = int(time.time()), hex(int(snapshot["number"]))
        if live and not int(intent["issued_at"]) <= now < int(intent["expires_at"]): raise ToolError("RESERVATION_EXPIRED")
        rule = self.policy.call("getEffectiveRule",[intent["policy_id"]],block)
        if (self.policy.call("paused",block=block) or not rule["enabled"] or rule["policyEpoch"] != int(intent["policy_epoch"]) or
            rule["toolId"] != intent["tool_id"] or rule["resourceScope"] != intent["resource_scope"] or rule["risk"] != 2 or
            not 0 < int(intent["expires_at"]) - int(intent["issued_at"]) <= min(rule["maxLifetime"],self.mail_lifetime)):
            raise ToolError("POLICY_REVOKED")
        if not self.policy.call("isRequesterAuthorized",[intent["requester"],intent["resource_scope"]],block) or not self.policy.call("isAgentAuthorized",[intent["requester"],intent["agent"]],block):
            raise ToolError("FORBIDDEN")
        if requester_signature and recover_intent(intent,self.domain,requester_signature) != intent["requester"]:
            raise ToolError("APPROVAL_INVALID")
        return inspect_approvals(intent,self.domain,approvals,lambda a:self.actor(a,intent["resource_scope"],block),require_complete=complete)

    def transaction_evidence(self, tx_hash, registry, snapshot, expected_event, action_id):
        receipts = [n.call("eth_getTransactionReceipt",[tx_hash]) for n in self.nodes]
        if not all(receipts): raise ToolError("RESERVATION_UNCONFIRMED")
        receipt = receipts[0]
        if any(r != receipt for r in receipts) or receipt["status"] != "0x1" or receipt["to"].lower() != registry.lower():
            raise ToolError("RESERVATION_UNCONFIRMED")
        if int(receipt["blockNumber"],16) > int(snapshot["number"]): raise ToolError("RESERVATION_UNCONFIRMED")
        for node in self.nodes:
            block = node.call("eth_getBlockByNumber",[receipt["blockNumber"],False])
            if block["hash"] != receipt["blockHash"] or tx_hash not in block["transactions"]: raise ToolError("RESERVATION_UNCONFIRMED")
        logs = [log for log in receipt["logs"] if log["address"].lower()==registry.lower() and log["topics"][0]=="0x"+keccak(text=expected_event).hex() and log["topics"][1]==action_id]
        if len(logs)!=1: raise ToolError("RESERVATION_UNCONFIRMED")
        return {"chain_id":str(self.config["chainId"]),"registry":registry.lower(),"tx_hash":tx_hash,
                "block_hash":receipt["blockHash"],"block_number":str(int(receipt["blockNumber"],16))},receipt,logs[0]

    def reservation(self, intent, evidence):
        validate("ChainEvidence",evidence)
        snap = self.healthy()
        actual, receipt, event = self.transaction_evidence(evidence["tx_hash"],self.execution.address,snap,
            "ActionReserved(bytes32,bytes32,bytes32,bytes32,uint64)",intent["action_id"])
        if actual != evidence: raise ToolError("RESERVATION_UNCONFIRMED")
        block = hex(int(snap["number"]))
        reservation = self.execution.call("getReservation",[intent["action_id"]],block)
        typed_intent = {target:int(intent[source]) if next(f["type"] for f in PROTOCOL["types"]["ActionIntent"] if f["name"]==target).startswith("uint") else intent[source]
                        for source,target in PROTOCOL["json_to_typed"]["ActionIntent"].items()}
        if reservation["status"] != 1 or reservation["intent"] != typed_intent or reservation["intentHash"] != digest("ActionIntent",intent,self.domain):
            raise ToolError("RESERVATION_UNCONFIRMED")
        if event["topics"][2]!=intent["task_id"] or decode(["bytes32","bytes32","uint64"],bytes.fromhex(event["data"][2:])) != (bytes.fromhex(intent["tool_id"][2:]),bytes.fromhex(intent["params_commit"][2:]),int(intent["policy_epoch"])):
            raise ToolError("RESERVATION_UNCONFIRMED")
        tx = self.rpc.call("eth_getTransactionByHash",[evidence["tx_hash"]])
        if not tx or tx["to"].lower()!=self.execution.address: raise ToolError("RESERVATION_UNCONFIRMED")
        stored, requester_signature, approvals = self.execution.decode_input("reserve",tx["input"])
        if stored!=typed_intent: raise ToolError("PARAMS_MISMATCH")
        signatures = [a["signature"] for a in approvals]
        recovered = [recover_intent(intent,self.domain,s) for s in signatures]
        if recovered != reservation["approvers"]: raise ToolError("APPROVAL_INVALID")
        self.validate_authorization(intent,requester_signature,signatures,snap)
        if not self.execution.call("usedNonce",[intent["requester"],intent["nonce"]],block): raise ToolError("RESERVATION_UNCONFIRMED")
        return snap
