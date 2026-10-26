"""B/C shared deterministic ABAC/RBAC. No transport, chain or model dependency."""

from dataclasses import dataclass
import hashlib
import json

from .canonical import ROOT
from chainguard_sandbox.protocol import ToolError, params_for

RULES = json.loads((ROOT / "spec/risk-rules.json").read_text())["rules"]
TOOLS = frozenset(rule["tool"] for rule in RULES)


def check_policy_freeze():
    manifest_path = ROOT / "config/phase3-policy-freeze.json"
    try:
        manifest = json.loads(manifest_path.read_text())
        for name, expected in manifest["files"].items():
            source = (ROOT / name).resolve()
            if not source.is_relative_to(ROOT) or hashlib.sha256(source.read_bytes()).hexdigest() != expected:
                raise ValueError()
        from .canonical import canonical
        return "0x" + hashlib.sha256(canonical(manifest)).hexdigest()
    except (OSError, ValueError, KeyError):
        raise ToolError("POLICY_REVOKED") from None


@dataclass(frozen=True)
class Decision:
    verdict: str
    risk: int
    scope: str
    policy: str
    roles: tuple
    lifetime: int | None
    epoch: int


def require_actor(actor, role):
    if not actor or not actor.get("active") or role not in actor["roles"]:
        raise ToolError("FORBIDDEN")


def rule_for(tool, resource=None, epoch=1):
    if tool not in TOOLS:
        raise ToolError("UNKNOWN_TOOL")
    scope = resource["scope"] if tool == "doc.read" and resource else {
        "mail.send": "ORG_A_INTERNAL_MAIL", "doc.delete": "ORG_A_DISPOSABLE_DOCS"}.get(tool)
    rule = next((entry for entry in RULES if entry["tool"] == tool and entry["scope"] == scope), None)
    if rule is None:
        raise ToolError("UNAUTHORIZED_SCOPE")
    return Decision("REQUIRE_APPROVAL" if rule["reservation_required"] else "ALLOW", rule["risk"], scope,
                    rule["policy"], tuple(rule["approval_roles"]), rule["max_lifetime_seconds"], epoch)


def account_scope(requester, tool, params, resource):
    """Conventional account authorization also enforced by the A baseline."""
    require_actor(requester, "REQUESTER")
    params_for(tool, params)
    if tool not in requester["allowed_tools"]:
        raise ToolError("POLICY_DENY")
    decision = rule_for(tool, resource)
    if decision.scope not in requester["resource_scopes"] or decision.risk > requester["max_risk"]:
        raise ToolError("UNAUTHORIZED_SCOPE")
    if tool == "mail.send":
        if not set(params["to"]) <= set(requester["allowed_recipients"]):
            raise ToolError("UNAUTHORIZED_SCOPE")
    else:
        if not resource or params["doc_id"] not in requester["allowed_document_ids"]:
            raise ToolError("UNAUTHORIZED_SCOPE")
        if decision.scope != "PUBLIC_DOCS" and resource["organization"] != requester["organization"]:
            raise ToolError("UNAUTHORIZED_SCOPE")
    return decision


def evaluate(requester, agent, task, tool, params, resource, *, now, used_actions, epoch=1):
    decision = account_scope(requester, tool, params, resource)
    require_actor(agent, "AGENT")
    if task["requester"] != requester["address"] or task["agent"] != agent["address"]:
        raise ToolError("FORBIDDEN")
    if task.get("revoked") or now >= int(task["expires_at"]):
        raise ToolError("POLICY_REVOKED")
    if used_actions >= task["max_actions"]:
        raise ToolError("POLICY_DENY")
    if tool not in task["allowed_tools"] or decision.scope not in task["resource_scopes"] or decision.risk > task["max_risk"]:
        raise ToolError("POLICY_DENY")
    if tool == "mail.send" and not set(params["to"]) <= set(task["allowed_recipients"]):
        raise ToolError("UNAUTHORIZED_SCOPE")
    if tool != "mail.send" and params["doc_id"] not in task["allowed_document_ids"]:
        raise ToolError("UNAUTHORIZED_SCOPE")
    if tool == "doc.delete" and (not task["allow_sandbox_delete"] or not resource["disposable"]):
        raise ToolError("POLICY_DENY")
    return rule_for(tool, resource, epoch)


def validate_new_grant(requester, agent, grant, *, now):
    require_actor(requester, "REQUESTER")
    require_actor(agent, "AGENT")
    if grant["agent"] != agent["address"] or agent["organization"] != requester["organization"]:
        raise ToolError("FORBIDDEN")
    for key in ("allowed_tools", "resource_scopes", "allowed_document_ids", "allowed_recipients"):
        if not set(grant[key]) <= set(requester[key]):
            raise ToolError("UNAUTHORIZED_SCOPE")
    if not now < int(grant["expires_at"]) <= now + 86400 or grant["max_risk"] > requester["max_risk"]:
        raise ToolError("POLICY_DENY")
    if grant["allow_sandbox_delete"] and (grant["max_risk"] != 3 or "doc.delete" not in grant["allowed_tools"]):
        raise ToolError("POLICY_DENY")
