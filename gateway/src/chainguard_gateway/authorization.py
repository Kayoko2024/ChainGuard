"""Current centralized authorization loaded independently by the tool adapter."""

import time

from .approvals import inspect_approvals
from .crypto import commit, label, recover_intent
from .policy import account_scope, evaluate, require_actor
from chainguard_sandbox.protocol import ToolError


def signatures(store, db, action_id):
    return [store.unseal("approval/" + action_id + "/" + row["signer"], row["signature"])
            for row in db.execute("SELECT * FROM approvals WHERE action_id=? ORDER BY signer", (action_id,))]


def authorize_action(store, db, row, data, resource, params, *, accounted=False):
    task_row, grant = store.task(db, row["task_id"])
    requester = store.actor(db, address=grant["requester"])
    agent = store.actor(db, address=grant["agent"])
    require_actor(requester, "REQUESTER")
    require_actor(agent, "AGENT")
    if store.meta(db, "paused"):
        raise ToolError("POLICY_REVOKED")
    if task_row["revoked"] or int(time.time()) >= int(grant["expires_at"]):
        raise ToolError("POLICY_REVOKED")
    if accounted and row["state"] != "DISPATCHING":
        raise ToolError("STATE_CONFLICT")
    group = store.meta(db, "group")
    decision = account_scope(requester, row["tool_name"], params, resource)
    if group == "A":
        # Irreversible operations keep the same sandbox safety ceiling in both arms.
        if row["tool_name"] == "doc.delete" and not grant["allow_sandbox_delete"]:
            raise ToolError("POLICY_DENY")
        return decision, grant
    decision = evaluate(requester, agent, grant, row["tool_name"], params, resource,
                        now=int(time.time()), used_actions=task_row["used_actions"] - int(accounted), epoch=store.meta(db, "policy_epoch"))
    if decision.risk < 2:
        return decision, grant
    intent = data["intent"]
    if (not intent or intent["task_id"] != row["task_id"] or intent["action_id"] != row["action_id"]
            or intent["tool_id"] != label("tool", row["tool_name"])
            or intent["resource_scope"] != label("scope", decision.scope)
            or intent["policy_id"] != label("policy", decision.policy)
            or intent["requester"] != grant["requester"] or intent["agent"] != grant["agent"]
            or intent["risk"] != decision.risk or int(intent["policy_epoch"]) != decision.epoch):
        raise ToolError("POLICY_REVOKED")
    if commit("params", data["salt"], params) != intent["params_commit"]:
        raise ToolError("PARAMS_MISMATCH")
    issued, expires, stamp = int(intent["issued_at"]), int(intent["expires_at"]), int(time.time())
    if not issued <= stamp < expires or not 0 < expires - issued <= decision.lifetime or expires > int(grant["expires_at"]):
        raise ToolError("RESERVATION_EXPIRED")
    requester_signature = data.get("requester_signature")
    if not requester_signature:
        raise ToolError("APPROVAL_MISSING")
    domain = store.meta(db, "domain")
    if recover_intent(intent, domain, requester_signature) != grant["requester"]:
        raise ToolError("APPROVAL_INVALID")
    inspect_approvals(intent, domain, signatures(store, db, row["action_id"]),
                      lambda address: store.actor(db, address=address), excluded=[store.meta(db, "audit_signer")])
    return decision, grant
