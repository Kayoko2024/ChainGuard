import json

import pytest


@pytest.mark.parametrize("name", ["action", "read", "chain"])
def test_state_graph_is_guarded_reachable_and_terminal(root, name):
    machines = json.loads((root / "spec/state-machines.json").read_text())
    machine = machines[name]
    states = set(machine["states"])
    assert machine["initial"] in states and set(machine["terminal"]) <= states
    edges = machine["transitions"]
    assert len({(edge["from"], edge["to"]) for edge in edges}) == len(edges)
    for edge in edges:
        assert edge["from"] in states and edge["to"] in states and edge["guard"]
        assert edge["from"] not in machine["terminal"]
    reached = {machine["initial"]}
    while True:
        next_set = reached | {edge["to"] for edge in edges if edge["from"] in reached}
        if reached == next_set:
            break
        reached = next_set
    assert reached == states


def test_no_timeout_failure_or_unknown_reexecution_or_unanchored_finality(root):
    machines = json.loads((root / "spec/state-machines.json").read_text())
    edges = machines["action"]["transitions"]
    pairs = {(edge["from"], edge["to"]) for edge in edges}
    assert ("EXECUTING", "FINALIZED_OK") not in pairs
    assert ("UNKNOWN", "EXECUTING") not in pairs
    assert ("UNKNOWN", "EXPIRED") not in pairs
    assert ("UNKNOWN", "FINALIZED_ERROR") not in pairs
    assert ("RESERVING", "UNKNOWN") not in pairs
    for edge in edges:
        if edge["to"].startswith("FINALIZED_"):
            assert edge["from"] == "EXECUTION_RECORDED" and "confirmed" in edge["guard"]
    for state in ["RESERVING", "EXECUTION_RECORDED", "UNKNOWN"]:
        assert any(item.startswith(state + ":") for item in machines["action"]["retry_without_transition"])


def test_expiry_and_lifetime_reference_examples(vector):
    # Contract acceptance examples, not a deployed authorizer or clock abstraction.
    intent = vector["intent_json"]
    issued, expires = int(intent["issued_at"]), int(intent["expires_at"])
    assert 0 < expires - issued <= 120
    for now, expected in [(issued - 1, False), (issued, True), (expires - 1, True), (expires, False), (expires + 1, False)]:
        assert (issued <= now < expires) is expected


def test_risk_rules_identifiers_and_golden_tool_scope_are_consistent(root, vector):
    from eth_utils import keccak
    rules = json.loads((root / "spec/risk-rules.json").read_text())
    identifiers = json.loads((root / "spec/identifiers.json").read_text())
    assert [rule["risk"] for rule in rules["rules"]] == [0, 1, 2, 3]
    assert rules["distinct_approver_addresses"] and rules["unknown_must_not_redispatch"]
    for rule in rules["rules"]:
        assert rule["tool"] in identifiers["tools"]
        assert rule["scope"] in identifiers["scopes"]
        assert rule["policy"] in identifiers["policies"]
        assert set(rule["approval_roles"]) <= set(identifiers["roles"])
        assert rule["reservation_required"] == (rule["risk"] >= 2)
    r2, r3 = rules["rules"][2:]
    assert r2["min_approver_organizations"] == r3["min_approver_organizations"] == 2
    assert r3["approval_roles"] == r2["approval_roles"] + ["HUMAN_APPROVER"]
    assert r2["max_lifetime_seconds"] == 120 and r3["max_lifetime_seconds"] == 60
    assert vector["intent_json"]["tool_id"] == "0x" + keccak(text="ChainGuard/tool/" + r2["tool"]).hex()
