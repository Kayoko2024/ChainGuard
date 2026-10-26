"""Real signed append log with independent-checkpoint verification."""

import hashlib
import json

from eth_utils import keccak

from .canonical import canonical
from .crypto import recover_audit, sign_audit
from chainguard_sandbox.protocol import ToolError

ZERO = "0x" + "00" * 32


def event_hash(previous, event):
    return "0x" + keccak(b"ChainGuard/central-audit/v1\0" + bytes.fromhex(previous[2:]) + canonical(event)).hex()


def checkpoint_bytes(value):
    return b"ChainGuard/central-checkpoint/v1\0" + canonical(value)


class AuditLog:
    def __init__(self, store):
        self.store = store

    def append(self, db, event):
        tail = db.execute("SELECT * FROM audit ORDER BY sequence DESC LIMIT 1").fetchone()
        if self.store.meta(db, "group") == "B" and tail:
            verified = verify_log(self.entries(db), self.store.meta(db, "audit_signer"),
                                  checkpoint=self.store.meta(db, "checkpoint"), deployment_id=self.store.meta(db, "deployment_id"))
            if verified["status"] != "VALID":
                raise ToolError("RECEIPT_INVALID")
        sequence = tail["sequence"] + 1 if tail else 1
        previous = tail["event_hash"] if tail else ZERO
        event = dict(event, sequence=str(sequence), deployment_id=self.store.meta(db, "deployment_id"),
                     group=self.store.meta(db, "group"), policy_fingerprint=self.store.meta(db, "policy_hash"))
        if event.get("schema_version") == 1:
            from .central_contract import validate_central
            validate_central("ActionTrace", event)
        digest = event_hash(previous, event)
        signature = sign_audit(self.store.private("audit.key"), bytes.fromhex(digest[2:])) if event["group"] == "B" else None
        db.execute("INSERT INTO audit VALUES (?,?,?,?,?)", (sequence, previous, digest, canonical(event), signature))
        if event["group"] == "B":
            head = {"deployment_id": event["deployment_id"], "group": "B", "policy_fingerprint": event["policy_fingerprint"],
                    "sequence": str(sequence), "last_hash": digest}
            checkpoint = {"head": head, "signer": self.store.meta(db, "audit_signer"),
                          "signature": sign_audit(self.store.private("audit.key"), checkpoint_bytes(head))}
            db.execute("INSERT INTO meta VALUES ('checkpoint',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (json.dumps(checkpoint),))

    @staticmethod
    def entries(db):
        return [{"sequence": str(row["sequence"]), "previous_hash": row["previous_hash"], "event_hash": row["event_hash"],
                 "event": json.loads(row["event_json"]), "signature": row["signature"]} for row in db.execute("SELECT * FROM audit ORDER BY sequence")]


def verify_log(entries, trusted_signer, *, checkpoint=None, deployment_id=None):
    previous = ZERO
    try:
        for number, entry in enumerate(entries, 1):
            event = entry["event"]
            if (entry["sequence"] != str(number) or event["sequence"] != str(number)
                    or entry["previous_hash"] != previous or event["group"] != "B"
                    or (deployment_id is not None and event["deployment_id"] != deployment_id)):
                raise ValueError()
            digest = event_hash(previous, event)
            if digest != entry["event_hash"] or recover_audit(bytes.fromhex(digest[2:]), entry["signature"]) != trusted_signer:
                raise ValueError()
            previous = digest
        if checkpoint is None:
            return {"status": "PARTIAL", "events_verified": len(entries), "reason": "INDEPENDENT_CHECKPOINT_REQUIRED"}
        head = checkpoint["head"]
        if (checkpoint["signer"] != trusted_signer or recover_audit(checkpoint_bytes(head), checkpoint["signature"]) != trusted_signer
                or head["group"] != "B" or head["sequence"] != str(len(entries)) or head["last_hash"] != previous
                or (deployment_id is not None and head["deployment_id"] != deployment_id)):
            raise ValueError()
        if entries and any(e["event"]["policy_fingerprint"] != head["policy_fingerprint"] for e in entries):
            raise ValueError()
        return {"status": "VALID", "events_verified": len(entries), "head_hash": previous}
    except (ValueError, KeyError, TypeError, ToolError):
        return {"status": "INVALID", "reason": "SIGNATURE_CHAIN_OR_CHECKPOINT_MISMATCH"}
