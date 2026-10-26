"""B/C common signature, current-role and independent-organization checks."""

import itertools

from .crypto import recover_intent
from .policy import rule_for
from chainguard_sandbox.protocol import ToolError


def inspect_approvals(intent, domain, signatures, lookup_address, *, excluded=(), require_complete=True):
    roles = ("BUSINESS_APPROVER", "SECURITY_APPROVER") + (("HUMAN_APPROVER",) if intent["risk"] == 3 else ())
    excluded = {intent["requester"], intent["agent"], *excluded}
    seen, actors = set(), []
    for signature in signatures:
        address = recover_intent(intent, domain, signature)
        actor = lookup_address(address)
        if (address in seen or address in excluded or not actor or not actor["active"]
                or not set(roles).intersection(actor["roles"]) or "TOOL_SIGNER" in actor["roles"]):
            raise ToolError("APPROVAL_INVALID")
        # Scope labels are recovered from the same frozen rule the intent must bind.
        from .crypto import label
        scopes = ["ORG_A_INTERNAL_MAIL"] if intent["risk"] == 2 else ["ORG_A_DISPOSABLE_DOCS"]
        if not any(label("scope", scope) == intent["resource_scope"] and scope in actor["resource_scopes"] for scope in scopes):
            raise ToolError("APPROVAL_INVALID")
        seen.add(address)
        actors.append(actor)
    candidates = [[actor for actor in actors if role in actor["roles"]] for role in roles]
    complete = False
    for assignment in itertools.product(*candidates):
        if (len({actor["address"] for actor in assignment}) == len(roles)
                and assignment[0]["organization"] != assignment[1]["organization"]
                and len({actor["organization"] for actor in assignment}) >= 2):
            complete = True
            break
    if require_complete and not complete:
        if len(actors) >= len(roles):
            raise ToolError("APPROVAL_INVALID")
        raise ToolError("APPROVAL_MISSING")
    return {"complete": complete, "approval_count": len(actors),
            "independent_org_count": len({actor["organization"] for actor in actors})}
