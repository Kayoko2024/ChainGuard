from concurrent.futures import ThreadPoolExecutor
import copy
import json
import time

from eth_account import Account
from eth_account.messages import encode_typed_data
import pytest
from unittest.mock import patch

from chainguard_gateway.audit import verify_log
from chainguard_gateway.canonical import validate
from chainguard_gateway.crypto import random_id
from support import ALICE, BOB, MAIL, Lab


@pytest.fixture
def lab():
    fixture = Lab()
    try:
        yield fixture
    finally:
        fixture.close()


def test_b_real_normal_mail_and_signed_trace(lab):
    task = lab.new_task()
    validate("TaskGrant", task)
    action = lab.propose(task)
    validate("ActionIntent", action["intent"])
    assert action["central_state"] == "AWAITING_APPROVAL"
    assert action["typed_data"]["domain"]["chainId"] == "0"
    lab.approvals(action)
    response = lab.execute(action)
    assert response.status_code == 200, response.text
    record = response.json()
    assert record["central_state"] == "CENTRAL_OK" and lab.mailbox_count() == 1
    assert record["chain_state"] == "NONE" and record["execution_receipt"] is None
    with lab.tools.connect() as db:
        assert MAIL["body"].encode() in db.execute("SELECT mime FROM mailbox").fetchone()[0]
    export = lab.client.get("/central/v1/audit/entries", headers=lab.headers("auditor")).json()
    assert verify_log(export["entries"], export["signer"], checkpoint=export["checkpoint"], deployment_id=export["deployment_id"])["status"] == "VALID"
    serialized = json.dumps(export)
    assert MAIL["body"] not in serialized and ALICE not in serialized and "salt" not in serialized


def test_b_task_recipient_escalation_is_denied(lab):
    action = lab.propose(lab.new_task(), params=dict(MAIL, to=[BOB]))
    assert action["central_state"] == "DENIED" and action["policy_error_code"] == "UNAUTHORIZED_SCOPE"
    assert lab.execute(action).json()["central_state"] == "DENIED"
    assert lab.mailbox_count() == 0


def test_a_same_task_and_account_can_expose_task_scope_gap():
    lab = Lab("A")
    try:
        task = lab.new_task()
        action = lab.propose(task, params=dict(MAIL, to=[BOB]))
        assert action["policy_verdict"] == "DENY" and action["policy_enforced"] is False
        assert action["central_state"] == "READY" and action["typed_data"] is None
        assert lab.execute(action).json()["central_state"] == "CENTRAL_OK"
        assert lab.mailbox_count() == 1
        export = lab.service.audit_export("auditor")
        assert export["checkpoint"] is None and all(entry["signature"] is None for entry in export["entries"])
    finally:
        lab.close()


@pytest.mark.parametrize("group", ["A", "B"])
def test_default_delete_denied_and_test_file_preserved(group):
    lab = Lab(group)
    try:
        action = lab.propose(lab.new_task(), "doc.delete", {"doc_id": "doc-trash"})
        assert action["central_state"] == "DENIED"
        assert lab.execute(action).json()["central_state"] == "DENIED"
        with lab.tools.connect() as db:
            document = lab.adapter._tools.resources.lookup(db, "doc-trash")
        assert (lab.tools.root / "documents" / document["filename"]).exists()
    finally:
        lab.close()


def test_missing_approvals_or_requester_signature_produces_no_mail(lab):
    action = lab.propose(lab.new_task())
    assert lab.execute(action).json()["error"]["code"] == "APPROVAL_MISSING"
    lab.approvals(action, ("business",))
    assert lab.execute(action).json()["error"]["code"] == "APPROVAL_MISSING"
    lab.approvals(action, ("security",))
    assert lab.execute(action, body={}).json()["error"]["code"] == "APPROVAL_MISSING"
    assert lab.mailbox_count() == 0


def test_same_org_and_duplicate_approvals_do_not_satisfy_threshold(lab):
    lab.actors["security"]["organization"] = "OrgA_Business"
    lab.register(lab.actors["security"])
    action = lab.propose(lab.new_task())
    lab.approvals(action)
    lab.approvals(action, ("business",))
    assert lab.service.get_action("requester", action["action_id"])["approval_count"] == 2
    assert lab.execute(action).json()["error"]["code"] == "APPROVAL_INVALID"
    assert lab.mailbox_count() == 0


def test_approval_cannot_spoof_identity_or_include_unknown_fields(lab):
    action = lab.propose(lab.new_task())
    path = f"/actions/{action['action_id']}/approve"
    response = lab.post(path, {"signature": lab.signature(action, "business")}, "agent")
    assert response.json()["error"]["code"] == "APPROVAL_INVALID"
    response = lab.post(path, {"signature": lab.signature(action, "business"), "role": "SECURITY_APPROVER"}, "business")
    assert response.status_code == 422
    assert lab.mailbox_count() == 0


def test_wrong_signature_domain_rejected(lab):
    action = lab.propose(lab.new_task())
    wrong = copy.deepcopy(action["typed_data"])
    wrong["domain"]["chainId"] = "31337"
    signature = "0x" + Account.sign_message(encode_typed_data(full_message=wrong), lab.accounts["business"].key).signature.hex()
    response = lab.post(f"/actions/{action['action_id']}/approve", {"signature": signature}, "business")
    assert response.json()["error"]["code"] == "APPROVAL_INVALID"


def test_revoked_approver_and_policy_epoch_checked_at_execution(lab):
    action = lab.propose(lab.new_task())
    lab.approvals(action)
    lab.actors["security"]["active"] = False
    lab.register(lab.actors["security"])
    assert lab.execute(action).json()["error"]["code"] == "APPROVAL_INVALID"
    lab.actors["security"]["active"] = True
    lab.register(lab.actors["security"])
    with lab.store.transaction() as db:
        db.execute("UPDATE meta SET value='2' WHERE key='policy_epoch'")
    assert lab.execute(action).json()["error"]["code"] == "POLICY_REVOKED"
    assert lab.mailbox_count() == 0


def test_tool_independently_rechecks_revocation_after_gateway_claim(lab):
    action = lab.propose(lab.new_task())
    lab.approvals(action)
    execute = lab.adapter.execute
    def revoke_then_execute(action_id, params):
        with lab.store.transaction() as db:
            db.execute("UPDATE tasks SET revoked=1 WHERE task_id=?", (action["task_id"],))
        return execute(action_id, params)
    lab.adapter.execute = revoke_then_execute
    result = lab.execute(action).json()
    assert result["central_state"] == "CENTRAL_REJECTED" and lab.mailbox_count() == 0


def test_gateway_cannot_swap_approved_mail_parameters(lab):
    action = lab.propose(lab.new_task())
    lab.approvals(action)
    execute = lab.adapter.execute
    lab.adapter.execute = lambda action_id, params: execute(action_id, dict(params, body="tampered"))
    assert lab.execute(action).json()["central_state"] == "CENTRAL_REJECTED"
    assert lab.mailbox_count() == 0


def test_20_concurrent_http_replays_consume_one_quota(lab):
    task = lab.new_task(max_actions=1)
    action = lab.propose(task)
    lab.approvals(action)
    signature = lab.signature(action, "requester")
    with ThreadPoolExecutor(max_workers=6) as pool:
        responses = list(pool.map(lambda _: lab.execute(action, body={"requester_signature": signature}), range(20)))
    assert all(response.status_code == 200 for response in responses)
    assert lab.mailbox_count() == 1
    with lab.store.connect() as db:
        assert db.execute("SELECT used_actions FROM tasks WHERE task_id=?", (task["task_id"],)).fetchone()[0] == 1


def test_two_actions_cannot_exceed_atomic_task_quota(lab):
    task = lab.new_task(max_actions=1)
    first, second = lab.propose(task), lab.propose(task)
    lab.approvals(first)
    lab.approvals(second)
    assert lab.execute(first).json()["central_state"] == "CENTRAL_OK"
    assert lab.execute(second).json()["error"]["code"] == "POLICY_DENY"
    assert lab.mailbox_count() == 1


def test_agent_and_unrelated_requester_cannot_dispatch_or_read(lab):
    action = lab.propose(lab.new_task())
    assert lab.execute(action, subject="agent").status_code == 403
    assert lab.execute(action, subject="other").status_code == 404
    response = lab.client.get(f"/central/v1/actions/{action['action_id']}", headers=lab.headers("other"))
    assert response.status_code == 404 and lab.mailbox_count() == 0


def test_http_json_duplicate_keys_authentication_and_whitelist(lab):
    no_auth = lab.client.post("/central/v1/tasks", json=lab.task_body())
    assert no_auth.status_code == 401
    duplicate = lab.client.post("/central/v1/tasks", content=b'{"task_text":"a","task_text":"b"}',
                                headers=dict(lab.headers(), **{"Content-Type": "application/json"}))
    assert duplicate.status_code == 422
    response = lab.post("/actions/propose", {"task_id": random_id(), "tool_name": "shell.exec", "params": {}}, "agent")
    assert response.json()["error"]["code"] == "UNKNOWN_TOOL"
    response = lab.post("/tasks", dict(lab.task_body(), roles=["REQUESTER"]))
    assert response.status_code == 422


def test_jcs_idempotency_and_conflict(lab):
    body, key = lab.task_body(), random_id()
    first = lab.post("/tasks", body, key=key)
    second = lab.post("/tasks", dict(reversed(list(body.items()))), key=key)
    assert first.json() == second.json()
    conflict = lab.post("/tasks", dict(body, task_text="changed"), key=key)
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"


def test_read_real_document_and_explicit_r3_three_party_delete(lab):
    read = lab.propose(lab.new_task(), "doc.read", {"doc_id": "doc-public"})
    assert read["intent"] is None and lab.execute(read).json()["central_state"] == "CENTRAL_OK"
    delete = lab.propose(lab.new_task(allow_sandbox_delete=True), "doc.delete", {"doc_id": "doc-trash"})
    lab.approvals(delete)
    assert lab.execute(delete).json()["error"]["code"] == "APPROVAL_MISSING"
    lab.approvals(delete, ("human",))
    assert lab.execute(delete).json()["central_state"] == "CENTRAL_OK"
    with lab.tools.connect() as db:
        document = lab.adapter._tools.resources.lookup(db, "doc-trash")
    assert not (lab.tools.root / "documents" / document["filename"]).exists()


def test_log_write_failure_before_dispatch_prevents_tool_execution(lab):
    action = lab.propose(lab.new_task())
    lab.approvals(action)
    original = lab.service.audit.append
    def fail_dispatch(db, event):
        if event["event"] == "DISPATCH":
            raise RuntimeError("test crash before dispatch")
        return original(db, event)
    lab.service.audit.append = fail_dispatch
    assert lab.execute(action).json()["error"]["code"] == "EXECUTION_UNKNOWN"
    assert lab.mailbox_count() == 0


def test_lost_tool_response_is_unknown_and_never_resends(lab):
    action = lab.propose(lab.new_task())
    lab.approvals(action)
    execute = lab.adapter.execute
    def lose_response(action_id, params):
        execute(action_id, params)
        raise TimeoutError()
    lab.adapter.execute = lose_response
    assert lab.execute(action).json()["central_state"] == "UNKNOWN"
    assert lab.execute(action).json()["central_state"] == "UNKNOWN"
    assert lab.mailbox_count() == 1
    tail = lab.service.audit_export("auditor")["entries"][-1]["event"]
    assert tail["tool_state"] == "UNKNOWN" and tail["tool_executed"] is None


def test_database_group_downgrade_cannot_bypass_the_b_gateway(lab):
    action = lab.propose(lab.new_task())
    with lab.store.transaction() as db:
        db.execute("UPDATE meta SET value='\"A\"' WHERE key='group'")
    response = lab.execute(action)
    assert response.status_code == 409 and lab.mailbox_count() == 0


def test_corrupt_existing_log_blocks_new_dispatch(lab):
    action = lab.propose(lab.new_task())
    lab.approvals(action)
    with lab.store.transaction() as db:
        db.execute("DROP TRIGGER audit_no_update")
        db.execute("UPDATE audit SET signature=? WHERE sequence=1", ("0x" + "00" * 65,))
    response = lab.execute(action)
    assert response.status_code == 409 and lab.mailbox_count() == 0


def test_tool_primitive_cannot_extend_original_intent_expiry(lab):
    action = lab.propose(lab.new_task())
    lab.approvals(action)
    execute = lab.adapter._tools.execute
    def expire_before_atomic_tool_claim(*args, **kwargs):
        with patch("chainguard_sandbox.tools.now", return_value=int(action["intent"]["expires_at"])):
            return execute(*args, **kwargs)
    lab.adapter._tools.execute = expire_before_atomic_tool_claim
    response = lab.execute(action)
    assert response.json()["central_state"] == "CENTRAL_REJECTED" and lab.mailbox_count() == 0


@pytest.mark.parametrize("group", ["A", "B"])
def test_idempotency_key_is_scoped_to_subject_and_operation_across_actions(group):
    lab = Lab(group)
    try:
        task = lab.new_task()
        first, second = lab.propose(task), lab.propose(task)
        if group == "B":
            lab.approvals(first)
            lab.approvals(second)
        key = random_id()
        assert lab.execute(first, key=key).json()["central_state"] == "CENTRAL_OK"
        assert lab.execute(second, key=key).json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
        assert lab.mailbox_count() == 1
    finally:
        lab.close()
