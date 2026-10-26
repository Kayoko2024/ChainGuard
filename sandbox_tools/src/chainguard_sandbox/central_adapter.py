"""Tool-owned centralized authorization; the caller cannot mint a tool permit."""

from .protocol import ToolError, params_for
from .tools import LocalTestTools
from .storage import sha256


class CentralToolAdapter:
    def __init__(self, tool_store, central_store):
        self.tool_store = tool_store
        self.central_store = central_store
        self._tools = LocalTestTools(tool_store)

    def attributes(self, tool_name, params):
        params = params_for(tool_name, params)
        if tool_name == "mail.send":
            return None
        with self.tool_store.connect() as db:
            return self._tools.resources.lookup(db, params["doc_id"])

    def execute(self, action_id, params):
        from chainguard_gateway.authorization import authorize_action
        from chainguard_gateway.policy import check_policy_freeze
        check_policy_freeze()
        # Read from the adapter's configured central store, never caller claims.
        with self.central_store.connect() as db:
            row, data = self.central_store.action(db, action_id)
            resource = self.attributes(row["tool_name"], params)
            decision, grant = authorize_action(self.central_store, db, row, data, resource, params, accounted=True)
            if self.central_store.meta(db, "policy_hash") != check_policy_freeze():
                raise ToolError("POLICY_REVOKED")
            # A read still binds to the persisted original parameters, not a wider account.
            from chainguard_gateway.canonical import canonical
            if canonical(data["params"]) != canonical(params):
                raise ToolError("PARAMS_MISMATCH")
            deadline = int(grant["expires_at"])
            if data["intent"]:
                deadline = min(deadline, int(data["intent"]["expires_at"]))
        operator = self.tool_store.private_read("operator.key").decode("ascii")
        permit = self._tools.issue_permit(operator, action_id, "central-gateway", row["tool_name"], params,
                                         scope=decision.scope, organization="OrgA_Business",
                                         allowed_documents=[params["doc_id"]] if "doc_id" in params else [],
                                         allowed_recipients=params.get("to", []),
                                         allow_sandbox_delete=row["tool_name"] == "doc.delete",
                                         lifetime=decision.lifetime or 120)
        # Preserve the original absolute deadline in the primitive's atomic claim.
        with self.tool_store.transaction() as db:
            db.execute("UPDATE permits SET expires_at=min(expires_at,?) WHERE token_hash=?", (deadline, sha256(permit.encode())))
        return self._tools.execute(action_id, "central-gateway", row["tool_name"], params, permit)
