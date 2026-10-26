import copy
import json
import sqlite3

import pytest
from eth_account import Account

from chainguard_gateway.audit import AuditLog, verify_log
from chainguard_gateway.central_store import CentralStore
from chainguard_sandbox.protocol import ToolError


@pytest.fixture
def store(tmp_path):
    return CentralStore.create(tmp_path / "central", "B", "0x" + "ab" * 32, "/sandbox/test-placeholder")


def events(store):
    with store.transaction() as db:
        for number in range(3):
            AuditLog(store).append(db, {"event": "TEST_OBSERVATION", "test_number": number})
    with store.connect() as db:
        return AuditLog.entries(db), store.meta(db, "checkpoint"), store.meta(db, "audit_signer"), store.meta(db, "deployment_id")


def test_signed_append_log_and_checkpoint_are_real_and_survive_reopen(store):
    entries, checkpoint, signer, deployment = events(store)
    assert verify_log(entries, signer, checkpoint=checkpoint, deployment_id=deployment)["status"] == "VALID"
    assert verify_log(entries, signer)["status"] == "PARTIAL"
    reopened = CentralStore(store.root)
    with reopened.connect() as db:
        assert AuditLog.entries(db) == entries
        assert reopened.meta(db, "checkpoint") == checkpoint


@pytest.mark.parametrize("attack", ["edit", "delete-middle", "reorder", "signature", "truncate", "empty", "wrong-key", "wrong-deployment"])
def test_signed_log_detects_tampering_and_checkpoint_truncation(store, attack):
    entries, checkpoint, signer, deployment = events(store)
    if attack == "edit":
        entries[1]["event"]["test_number"] = 99
    elif attack == "delete-middle":
        entries.pop(1)
    elif attack == "reorder":
        entries.reverse()
    elif attack == "signature":
        entries[1]["signature"] = entries[0]["signature"]
    elif attack == "truncate":
        entries.pop()
    elif attack == "empty":
        entries.clear()
    elif attack == "wrong-key":
        signer = Account.create().address.lower()
    else:
        deployment = "0x" + "cd" * 32
    assert verify_log(entries, signer, checkpoint=checkpoint, deployment_id=deployment)["status"] == "INVALID"


def test_sqlite_rejects_normal_log_update_and_delete(store):
    events(store)
    with store.connect() as db:
        for sql in ["UPDATE audit SET signature='forged'", "DELETE FROM audit"]:
            with pytest.raises(sqlite3.IntegrityError, match="append only"):
                db.execute(sql)


def test_sensitive_json_is_encrypted_and_aad_bound(store):
    secret = {"body": "sensitive synthetic content", "salt": "0x" + "12" * 32}
    encrypted = store.seal("action/one", secret)
    assert secret["body"].encode() not in encrypted
    assert store.unseal("action/one", encrypted) == secret
    for context, data in [("action/two", encrypted), ("action/one", encrypted[:-1] + bytes([encrypted[-1] ^ 1]))]:
        with pytest.raises(ToolError, match="STATE_CONFLICT"):
            store.unseal(context, data)


def test_a_plain_baseline_does_not_claim_signature_security(tmp_path):
    store = CentralStore.create(tmp_path / "plain", "A", "0x" + "ab" * 32, "/sandbox/test-placeholder")
    with store.transaction() as db:
        AuditLog(store).append(db, {"event": "A_OBSERVATION"})
    with store.connect() as db:
        entries = AuditLog.entries(db)
    assert entries[0]["signature"] is None
    assert verify_log(entries, "0x" + "12" * 20)["status"] == "INVALID"
