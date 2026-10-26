import copy
import json
from pathlib import Path
import time
import base64
import hmac

from eth_account.messages import encode_typed_data
from eth_utils import keccak
import pytest

from chainguard_gateway.canonical import ROOT, canonical, parse_json
from chainguard_gateway.crypto import commit, recover_intent, typed_intent
from chainguard_gateway.identity import authenticate, issue_token
from chainguard_gateway.policy import evaluate, validate_new_grant
from chainguard_sandbox.protocol import ToolError


@pytest.mark.parametrize("raw", [b'{"a":1,"a":2}', b'{"x":{"a":1,"a":2}}', b'{"x":1.0}',
    b'{"x":NaN}', b'{"x":Infinity}', b'{"x":9007199254740992}', b'{"x":"\\ud800"}',
    b'\xff', b'', b'{} trailing', b'[' * 1500, b' ' * 65537], ids=[f"invalid-{n}" for n in range(12)])
def test_json_rejects_lossy_or_ambiguous_input(raw):
    with pytest.raises(ToolError, match="SCHEMA_INVALID"):
        parse_json(raw)


def test_jcs_runtime_and_commitments_match_frozen_golden_vector():
    vector = json.loads((ROOT / "spec/vectors/eip712-v1.json").read_text(encoding="utf-8"))
    for kind, item in vector["commitments"].items():
        assert commit(kind, item["salt"], item["value"]) == item["commitment"]
    entry = vector["vectors"]["ActionIntent"]
    encoded = encode_typed_data(full_message=typed_intent(vector["intent_json"], entry["typed_data"]["domain"]))
    assert "0x" + keccak(b"\x19" + encoded.version + encoded.header + encoded.body).hex() == entry["expected"]["digest"]
    for sig in entry["signatures"]:
        assert recover_intent(vector["intent_json"], entry["typed_data"]["domain"], sig["signature"]) == sig["signer"]
    edge = vector["jcs_edge_case"]
    assert "0x" + canonical(edge["input"]).hex() == edge["canonical_utf8_hex"]
    assert canonical({"b": "Cafe\u0301", "a": 1}) != canonical({"b": "Café", "a": 1})


def actors_and_task():
    requester = {"active": True, "roles": ["REQUESTER"], "address": "0x" + "11" * 20,
                 "organization": "OrgA_Business", "allowed_tools": ["doc.read", "mail.send", "doc.delete"],
                 "resource_scopes": ["PUBLIC_DOCS", "ORG_A_DOCS", "ORG_A_INTERNAL_MAIL", "ORG_A_DISPOSABLE_DOCS"],
                 "allowed_document_ids": ["doc-public", "doc-private", "doc-trash"],
                 "allowed_recipients": ["alice@inbox.chainguard.invalid", "bob@inbox.chainguard.invalid"], "max_risk": 3}
    agent = {"active": True, "roles": ["AGENT"], "address": "0x" + "22" * 20, "organization": "OrgA_Business"}
    task = {"requester": requester["address"], "agent": agent["address"], "allowed_tools": ["doc.read", "mail.send", "doc.delete"],
            "resource_scopes": requester["resource_scopes"], "allowed_document_ids": requester["allowed_document_ids"],
            "allowed_recipients": ["alice@inbox.chainguard.invalid"], "max_risk": 3, "allow_sandbox_delete": False,
            "max_actions": 2, "expires_at": str(int(time.time()) + 500)}
    return requester, agent, task


def test_shared_policy_mail_requires_exact_recipient_and_two_roles():
    requester, agent, task = actors_and_task()
    params = {"to": ["alice@inbox.chainguard.invalid"], "subject": "x", "body": "y"}
    decision = evaluate(requester, agent, task, "mail.send", params, None, now=int(time.time()), used_actions=0)
    assert decision.risk == 2 and decision.verdict == "REQUIRE_APPROVAL"
    assert decision.roles == ("BUSINESS_APPROVER", "SECURITY_APPROVER") and decision.lifetime == 120
    params["to"] = ["bob@inbox.chainguard.invalid"]
    with pytest.raises(ToolError, match="UNAUTHORIZED_SCOPE"):
        evaluate(requester, agent, task, "mail.send", params, None, now=int(time.time()), used_actions=0)


@pytest.mark.parametrize("mutation,expected", [
    ({"revoked": True}, "POLICY_REVOKED"), ({"expires_at": "0"}, "POLICY_REVOKED"),
    ({"max_actions": 0}, "POLICY_DENY"), ({"allowed_tools": ["doc.read"]}, "POLICY_DENY"),
    ({"max_risk": 1}, "POLICY_DENY"), ({"agent": "0x" + "33" * 20}, "FORBIDDEN"),
])
def test_abac_denies_expiry_revocation_quota_and_privilege_changes(mutation, expected):
    requester, agent, task = actors_and_task()
    task.update(mutation)
    with pytest.raises(ToolError, match=expected):
        evaluate(requester, agent, task, "mail.send", {"to": task["allowed_recipients"], "subject": "x", "body": "y"}, None,
                 now=int(time.time()), used_actions=0)


def test_default_delete_denied_and_explicit_delete_requires_human():
    requester, agent, task = actors_and_task()
    resource = {"scope": "ORG_A_DISPOSABLE_DOCS", "organization": "OrgA_Business", "disposable": True}
    with pytest.raises(ToolError, match="POLICY_DENY"):
        evaluate(requester, agent, task, "doc.delete", {"doc_id": "doc-trash"}, resource, now=int(time.time()), used_actions=0)
    task["allow_sandbox_delete"] = True
    rule = evaluate(requester, agent, task, "doc.delete", {"doc_id": "doc-trash"}, resource, now=int(time.time()), used_actions=0)
    assert rule.risk == 3 and rule.lifetime == 60 and "HUMAN_APPROVER" in rule.roles


def test_r1_other_org_cannot_be_downgraded_to_r0():
    requester, agent, task = actors_and_task()
    with pytest.raises(ToolError, match="UNAUTHORIZED_SCOPE"):
        evaluate(requester, agent, task, "doc.read", {"doc_id": "doc-private"},
                 {"scope": "ORG_A_DOCS", "organization": "OrgB_Security"}, now=int(time.time()), used_actions=0)


def test_grant_creation_intersects_current_account_rights():
    requester, agent, task = actors_and_task()
    validate_new_grant(requester, agent, task, now=int(time.time()))
    task["allowed_recipients"].append("unknown@inbox.chainguard.invalid")
    with pytest.raises(ToolError, match="UNAUTHORIZED_SCOPE"):
        validate_new_grant(requester, agent, task, now=int(time.time()))


def test_jwt_real_mac_and_claims_are_enforced():
    key = b"k" * 32
    token = issue_token(key, "requester")
    assert authenticate(key, "Bearer " + token) == "requester"
    for bad in [None, "Bearer " + token + "x", "Basic " + token, "Bearer a.b.c"]:
        with pytest.raises(ToolError, match="AUTH_REQUIRED"):
            authenticate(key, bad)
    with pytest.raises(ToolError, match="AUTH_REQUIRED"):
        authenticate(b"q" * 32, "Bearer " + token)


def test_signature_sdk_rejects_invalid_curve_point_without_internal_error():
    vector = json.loads((ROOT / "spec/vectors/eip712-v1.json").read_text(encoding="utf-8"))
    malformed = "0x" + "00" * 32 + "00" * 31 + "01" + "1b"
    with pytest.raises(ToolError, match="APPROVAL_INVALID"):
        recover_intent(vector["intent_json"], vector["vectors"]["ActionIntent"]["typed_data"]["domain"], malformed)


@pytest.mark.parametrize("patch", [{"iss": "other"}, {"aud": "other"}, {"exp": 0}, {"nbf": 9999999999},
                                  {"iat": True}, {"roles": ["REQUESTER"]}, {"sub": "../requester"}, {"exp": 9999999999}])
def test_genuine_mac_cannot_override_required_jwt_claims(patch):
    from chainguard_gateway.identity import ISSUER, AUDIENCE
    key, stamp = b"j" * 32, int(time.time())
    claims = {"iss": ISSUER, "aud": AUDIENCE, "sub": "requester", "iat": stamp, "nbf": stamp, "exp": stamp + 60, "jti": "test-id"}
    claims.update(patch)
    b64 = lambda data: base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()
    unsigned = b64({"alg": "HS256", "typ": "JWT"}) + "." + b64(claims)
    signature = base64.urlsafe_b64encode(hmac.digest(key, unsigned.encode(), "sha256")).rstrip(b"=").decode()
    with pytest.raises(ToolError, match="AUTH_REQUIRED"):
        authenticate(key, "Bearer " + unsigned + "." + signature)
