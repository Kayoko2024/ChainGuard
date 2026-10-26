"""Central A/B action lifecycle; intentionally no chain reservation or receipt."""

import hashlib
import hmac
import json
import time

from .approvals import inspect_approvals
from .audit import AuditLog
from .authorization import authorize_action, signatures
from .canonical import canonical, validate
from .crypto import commit, label, random_id, recover_intent, typed_intent
from .policy import TOOLS, account_scope, check_policy_freeze, evaluate, require_actor, rule_for, validate_new_grant
from chainguard_sandbox.protocol import ToolError

TERMINAL = {"CENTRAL_OK", "CENTRAL_REJECTED", "UNKNOWN", "DENIED"}


class CentralService:
    def __init__(self, store, adapter):
        self.store, self.adapter = store, adapter
        self.audit = AuditLog(store)
        with store.connect() as db:
            self.group = store.meta(db, "group")
            if store.meta(db, "policy_hash") != check_policy_freeze():
                raise ToolError("POLICY_REVOKED")

    def current_actor(self, subject):
        with self.store.connect() as db:
            actor = self.store.actor(db, subject=subject)
            if not actor or not actor["active"]:
                raise ToolError("FORBIDDEN")
            return actor

    def trace(self, db, subject, event, trace_id, *, action_id=None, task_id=None, tool_name=None,
              verdict="ALLOW", code=None, risk=None, params_commit=None, tool_state=None,
              elapsed_ms=0, approval_count=0, org_count=0):
        self.audit.append(db, {"schema_version": 1, "trace_id": trace_id, "action_id": action_id, "task_id": task_id,
            "subject_hash": "0x" + hashlib.sha256((subject or "unauthenticated").encode()).hexdigest(),
            "event": event, "tool_name": tool_name, "policy_verdict": verdict, "error_code": code,
            "risk": risk, "params_commit": params_commit, "policy_epoch": str(self.store.meta(db, "policy_epoch")),
            "tool_state": tool_state, "tool_executed": (None if event == "TOOL_RESULT" and tool_state in {None, "UNKNOWN"} else tool_state == "COMPLETED"), "observed_at": str(int(time.time())),
            "elapsed_ms": elapsed_ms, "approval_count": approval_count, "independent_org_count": org_count})

    def rejected_request(self, subject, trace_id, code):
        with self.store.transaction() as db:
            self.trace(db, subject, "REQUEST_DENIED", trace_id, verdict="DENY", code=code)

    def _idempotency(self, db, subject, operation, key, body):
        validate("Bytes32", key)
        digest = hmac.digest(self.store.private("data.key"), operation.encode() + b"\0" + canonical(body), "sha256").hex()
        row = db.execute("SELECT * FROM idempotency WHERE subject=? AND operation=? AND key=?", (subject, operation, key)).fetchone()
        if row and row["request_mac"] != digest:
            raise ToolError("IDEMPOTENCY_CONFLICT")
        return row["entity_id"] if row else None, digest

    @staticmethod
    def _save_idempotency(db, subject, operation, key, digest, entity):
        db.execute("INSERT OR IGNORE INTO idempotency VALUES (?,?,?,?,?)", (subject, operation, key, digest, entity))

    def create_task(self, subject, body, key, trace_id):
        validate("CreateTaskRequest", body)
        with self.store.transaction() as db:
            requester = self.store.actor(db, subject=subject)
            require_actor(requester, "REQUESTER")
            old, digest = self._idempotency(db, subject, "create_task", key, body)
            if old:
                return self.store.task(db, old)[1]
            agent = self.store.actor(db, address=body["agent"])
            validate_new_grant(requester, agent, body, now=int(time.time()))
            grant = dict(body, schema_version=1, task_id=random_id(), requester=requester["address"])
            validate("TaskGrant", grant)
            db.execute("INSERT INTO tasks(task_id,requester,agent,data) VALUES (?,?,?,?)",
                       (grant["task_id"], grant["requester"], grant["agent"], self.store.seal("task/" + grant["task_id"], grant)))
            self._save_idempotency(db, subject, "create_task", key, digest, grant["task_id"])
            self.trace(db, subject, "TASK_CREATED", trace_id, task_id=grant["task_id"])
            return grant

    def _visible(self, db, subject, row):
        actor = self.store.actor(db, subject=subject)
        if not actor or not actor["active"]:
            raise ToolError("FORBIDDEN")
        _, grant = self.store.task(db, row["task_id"])
        owns = actor["address"] in {grant["requester"], grant["agent"]}
        can_review = bool(set(actor["roles"]) & {"BUSINESS_APPROVER", "SECURITY_APPROVER", "HUMAN_APPROVER", "AUDITOR"})
        if not owns and not can_review:
            raise ToolError("NOT_FOUND")
        if not owns:
            _, data = self.store.action(db, row["action_id"])
            if data["scope"] not in actor["resource_scopes"]:
                raise ToolError("NOT_FOUND")
        return actor, owns

    def _view(self, db, subject, row, data):
        actor, owns = self._visible(db, subject, row)
        state = "UNKNOWN" if row["state"] == "DISPATCHING" else row["state"]
        from .central_contract import validate_central
        return validate_central("CentralActionRecord", {"record_type": "CentralActionRecord", "group": self.group, "action_id": row["action_id"],
                "task_id": row["task_id"], "tool_name": row["tool_name"], "risk": data["risk"], "central_state": state,
                "policy_verdict": data["shadow_verdict"], "policy_error_code": data["policy_error"],
                "policy_enforced": self.group == "B", "intent": data["intent"],
                "typed_data": typed_intent(data["intent"], self.store.meta(db, "domain")) if data["intent"] else None,
                "approval_count": db.execute("SELECT count(*) FROM approvals WHERE action_id=?", (row["action_id"],)).fetchone()[0],
                "result": self.store.unseal("result/" + row["action_id"], row["result"]) if row["result"] and owns else None,
                "chain_state": "NONE", "chain_evidence": None, "execution_receipt": None})

    def get_action(self, subject, action_id):
        validate("Bytes32", action_id)
        with self.store.connect() as db:
            row, data = self.store.action(db, action_id)
            return self._view(db, subject, row, data)

    def propose(self, subject, body, key, trace_id):
        if type(body) is not dict or type(body.get("tool_name")) is not str or body.get("tool_name") not in TOOLS:
            raise ToolError("UNKNOWN_TOOL")
        validate("ProposeRequest", body)
        with self.store.transaction() as db:
            actor = self.store.actor(db, subject=subject)
            require_actor(actor, "AGENT")
            task_row, grant = self.store.task(db, body["task_id"])
            if actor["address"] != grant["agent"]:
                raise ToolError("NOT_FOUND")
            old, digest = self._idempotency(db, subject, "propose", key, body)
            if old:
                row, data = self.store.action(db, old)
                return self._view(db, subject, row, data)
            requester = self.store.actor(db, address=grant["requester"])
            resource = self.adapter.attributes(body["tool_name"], body["params"])
            rule = rule_for(body["tool_name"], resource, self.store.meta(db, "policy_epoch"))
            shadow_error, basic_error = None, None
            try:
                account_scope(requester, body["tool_name"], body["params"], resource)
                if body["tool_name"] == "doc.delete" and not grant["allow_sandbox_delete"]:
                    raise ToolError("POLICY_DENY")
                if task_row["revoked"] or int(time.time()) >= int(grant["expires_at"]) or self.store.meta(db, "paused"):
                    raise ToolError("POLICY_REVOKED")
            except ToolError as error:
                basic_error = error.code
            try:
                evaluate(requester, actor, dict(grant, revoked=bool(task_row["revoked"])), body["tool_name"], body["params"], resource,
                         now=int(time.time()), used_actions=task_row["used_actions"], epoch=rule.epoch)
                if self.store.meta(db, "paused"):
                    raise ToolError("POLICY_REVOKED")
            except ToolError as error:
                shadow_error = error.code
            denied = basic_error or (shadow_error if self.group == "B" else None)
            action_id, salt = random_id(), random_id()
            intent = None
            if self.group == "B" and rule.risk >= 2 and not denied:
                nonce_row = db.execute("SELECT next_nonce FROM nonces WHERE requester=?", (grant["requester"],)).fetchone()
                nonce = int(nonce_row[0]) if nonce_row else 0
                if nonce >= (1 << 64) - 1:
                    raise ToolError("NONCE_REUSED")
                db.execute("INSERT INTO nonces VALUES (?,?) ON CONFLICT(requester) DO UPDATE SET next_nonce=excluded.next_nonce", (grant["requester"], str(nonce + 1)))
                issued = int(time.time())
                intent = {"schema_version": 1, "action_id": action_id, "task_id": grant["task_id"], "requester": grant["requester"],
                          "agent": grant["agent"], "tool_id": label("tool", body["tool_name"]), "resource_scope": label("scope", rule.scope),
                          "params_commit": commit("params", salt, body["params"]), "policy_id": label("policy", rule.policy),
                          "policy_epoch": str(rule.epoch), "nonce": str(nonce), "issued_at": str(issued),
                          "expires_at": str(min(issued + rule.lifetime, int(grant["expires_at"]))), "risk": rule.risk}
                validate("ActionIntent", intent)
            data = {"params": body["params"], "salt": salt, "intent": intent, "risk": rule.risk, "scope": rule.scope,
                    "shadow_verdict": "DENY" if shadow_error else rule.verdict, "policy_error": denied or shadow_error, "requester_signature": None}
            state = "DENIED" if denied else ("AWAITING_APPROVAL" if intent else "READY")
            db.execute("INSERT INTO actions(action_id,task_id,tool_name,state,data) VALUES (?,?,?,?,?)",
                       (action_id, grant["task_id"], body["tool_name"], state, self.store.seal("action/" + action_id, data)))
            self._save_idempotency(db, subject, "propose", key, digest, action_id)
            self.trace(db, subject, "DENIED" if denied else "PROPOSED", trace_id, action_id=action_id, task_id=grant["task_id"],
                       tool_name=body["tool_name"], verdict=data["shadow_verdict"], code=data["policy_error"], risk=rule.risk,
                       params_commit=intent["params_commit"] if intent else None)
            row, stored = self.store.action(db, action_id)
            return self._view(db, subject, row, stored)

    def approve(self, subject, action_id, body, trace_id):
        validate("ApproveRequest", body)
        with self.store.transaction() as db:
            row, data = self.store.action(db, action_id)
            actor, _ = self._visible(db, subject, row)
            if self.group != "B" or not data["intent"] or row["state"] != "AWAITING_APPROVAL":
                raise ToolError("STATE_CONFLICT")
            if int(time.time()) >= int(data["intent"]["expires_at"]):
                raise ToolError("RESERVATION_EXPIRED")
            task_row, grant = self.store.task(db, row["task_id"])
            if (task_row["revoked"] or self.store.meta(db, "paused")
                    or int(data["intent"]["policy_epoch"]) != self.store.meta(db, "policy_epoch")):
                raise ToolError("POLICY_REVOKED")
            evaluate(self.store.actor(db, address=grant["requester"]), self.store.actor(db, address=grant["agent"]),
                     grant, row["tool_name"], data["params"], self.adapter.attributes(row["tool_name"], data["params"]),
                     now=int(time.time()), used_actions=task_row["used_actions"], epoch=self.store.meta(db, "policy_epoch"))
            domain = self.store.meta(db, "domain")
            signer = recover_intent(data["intent"], domain, body["signature"])
            if signer != actor["address"]:
                raise ToolError("APPROVAL_INVALID")
            old = db.execute("SELECT signature FROM approvals WHERE action_id=? AND signer=?", (action_id, signer)).fetchone()
            if old:
                if self.store.unseal("approval/" + action_id + "/" + signer, old[0]) != body["signature"]:
                    raise ToolError("IDEMPOTENCY_CONFLICT")
                return self._view(db, subject, row, data)
            counts = inspect_approvals(data["intent"], domain, signatures(self.store, db, action_id) + [body["signature"]],
                                      lambda address: self.store.actor(db, address=address),
                                      excluded=[self.store.meta(db, "audit_signer")], require_complete=False)
            db.execute("INSERT INTO approvals VALUES (?,?,?)", (action_id, signer, self.store.seal("approval/" + action_id + "/" + signer, body["signature"])))
            self.trace(db, subject, "APPROVED", trace_id, action_id=action_id, task_id=row["task_id"], tool_name=row["tool_name"],
                       verdict="REQUIRE_APPROVAL", risk=data["risk"], params_commit=data["intent"]["params_commit"],
                       approval_count=counts["approval_count"], org_count=counts["independent_org_count"])
            return self._view(db, subject, row, data)

    def execute(self, subject, action_id, body, key, trace_id):
        if type(body) is not dict or set(body) - {"requester_signature"}:
            raise ToolError("SCHEMA_INVALID")
        if "requester_signature" in body:
            validate("ReserveRequest", body)
        check_policy_freeze()
        with self.store.transaction() as db:
            row, data = self.store.action(db, action_id)
            actor, _ = self._visible(db, subject, row)
            require_actor(actor, "REQUESTER")
            _, grant = self.store.task(db, row["task_id"])
            if actor["address"] != grant["requester"]:
                raise ToolError("NOT_FOUND")
            operation = "execute"
            _, digest = self._idempotency(db, subject, operation, key, {"action_id": action_id, "request": body})
            if row["state"] in TERMINAL or row["state"] == "DISPATCHING":
                self._save_idempotency(db, subject, operation, key, digest, action_id)
                return self._view(db, subject, row, data)
            data["requester_signature"] = body.get("requester_signature")
            resource = self.adapter.attributes(row["tool_name"], data["params"])
            decision, grant = authorize_action(self.store, db, row, data, resource, data["params"])
            if self.store.meta(db, "policy_hash") != check_policy_freeze():
                raise ToolError("POLICY_REVOKED")
            db.execute("UPDATE tasks SET used_actions=used_actions+1 WHERE task_id=?", (row["task_id"],))
            db.execute("UPDATE actions SET state='DISPATCHING',data=? WHERE action_id=?", (self.store.seal("action/" + action_id, data), action_id))
            self._save_idempotency(db, subject, operation, key, digest, action_id)
            self.trace(db, subject, "DISPATCH", trace_id, action_id=action_id, task_id=row["task_id"], tool_name=row["tool_name"],
                       risk=data["risk"], verdict=decision.verdict, params_commit=data["intent"]["params_commit"] if data["intent"] else None)
        start = time.monotonic()
        try:
            tool_record = self.adapter.execute(action_id, data["params"])
            state = {"COMPLETED": "CENTRAL_OK", "REJECTED": "CENTRAL_REJECTED", "UNKNOWN": "UNKNOWN"}[tool_record["state"]]
            code = tool_record["error_code"]
        except ToolError as error:
            state, code, tool_record = "CENTRAL_REJECTED", error.code, None
        except Exception:
            state, code, tool_record = "UNKNOWN", "EXECUTION_UNKNOWN", None
        try:
            with self.store.transaction() as db:
                db.execute("UPDATE actions SET state=?,result=? WHERE action_id=?",
                           (state, self.store.seal("result/" + action_id, tool_record) if tool_record else None, action_id))
                self.trace(db, subject, "TOOL_RESULT", trace_id, action_id=action_id, task_id=row["task_id"], tool_name=row["tool_name"],
                           risk=data["risk"], code=code, tool_state=tool_record["state"] if tool_record else ("REJECTED" if state == "CENTRAL_REJECTED" else "UNKNOWN"),
                           params_commit=data["intent"]["params_commit"] if data["intent"] else None,
                           elapsed_ms=int((time.monotonic() - start) * 1000))
        except Exception:
            # Durable DISPATCHING is reported UNKNOWN; never call the tool again.
            raise ToolError("EXECUTION_UNKNOWN") from None
        return self.get_action(subject, action_id)

    def audit_export(self, subject):
        with self.store.connect() as db:
            actor = self.store.actor(db, subject=subject)
            require_actor(actor, "AUDITOR")
            if not {"PUBLIC_DOCS", "ORG_A_DOCS", "ORG_A_INTERNAL_MAIL", "ORG_A_DISPOSABLE_DOCS"} <= set(actor["resource_scopes"]):
                raise ToolError("FORBIDDEN")
            return {"group": self.group, "entries": AuditLog.entries(db), "checkpoint": self.store.meta(db, "checkpoint") if self.group == "B" else None,
                    "signer": self.store.meta(db, "audit_signer") if self.group == "B" else None,
                    "deployment_id": self.store.meta(db, "deployment_id"), "policy_fingerprint": self.store.meta(db, "policy_hash")}
