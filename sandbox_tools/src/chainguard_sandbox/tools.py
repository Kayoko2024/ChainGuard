"""Real local side effects with tool-owned authorization and persistent dedup."""

import base64
from email.message import EmailMessage
from email.policy import SMTP
from email.utils import formatdate
import json
import re
import secrets
import time

from .protocol import SCOPES, ToolError, identifier, params_for, request_hash
from .resources import Resources
from .storage import sha256


def now():
    return int(time.time())


class LocalTestTools:
    """Trusted operator harness only. Never exposed as the frozen business API."""

    def __init__(self, store):
        self.store = store
        self.resources = Resources(store)

    def issue_permit(self, operator_key, action_id, principal, tool_name, params, *, scope,
                     organization="OrgA_Business", allowed_documents=(), allowed_recipients=(),
                     allow_sandbox_delete=False, lifetime=60):
        self.store.authorize_operator(operator_key)
        fingerprint = request_hash(action_id, principal, tool_name, params)
        maximum = 60 if tool_name == "doc.delete" else 120
        if type(lifetime) is not int or not 0 < lifetime <= maximum or scope not in SCOPES[tool_name]:
            raise ToolError("POLICY_DENY")
        if type(allow_sandbox_delete) is not bool:
            raise ToolError("SCHEMA_INVALID")
        token = secrets.token_hex(32)
        with self.store.transaction() as db:
            db.execute("INSERT INTO permits(token_hash,action_id,request_sha256,principal,scope,organization,documents,recipients,allow_delete,expires_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                       (sha256(token.encode()), action_id, fingerprint, principal, scope, organization,
                        json.dumps(list(allowed_documents)), json.dumps(list(allowed_recipients)),
                        int(allow_sandbox_delete), now() + lifetime))
        return token

    def revoke_permit(self, operator_key, token):
        self.store.authorize_operator(operator_key)
        with self.store.transaction() as db:
            db.execute("UPDATE permits SET revoked=1 WHERE token_hash=?", (sha256(token.encode()),))

    def _permit(self, db, token, action_id, principal):
        if type(token) is not str or re.fullmatch(r"[0-9a-f]{64}", token) is None:
            raise ToolError("AUTH_REQUIRED")
        permit = db.execute("SELECT * FROM permits WHERE token_hash=?", (sha256(token.encode()),)).fetchone()
        if permit is None or permit["principal"] != principal or permit["action_id"] != action_id:
            raise ToolError("FORBIDDEN")
        if permit["revoked"]:
            raise ToolError("FORBIDDEN")
        return permit

    def _scope(self, db, permit, tool_name, params):
        if permit["scope"] not in SCOPES[tool_name]:
            raise ToolError("UNAUTHORIZED_SCOPE")
        if tool_name == "mail.send":
            if not set(params["to"]) <= set(json.loads(permit["recipients"])):
                raise ToolError("UNAUTHORIZED_SCOPE")
            return None
        document = self.resources.lookup(db, params["doc_id"])
        if document["doc_id"] not in json.loads(permit["documents"]) or document["scope"] != permit["scope"]:
            raise ToolError("UNAUTHORIZED_SCOPE")
        if document["scope"] != "PUBLIC_DOCS" and document["organization"] != permit["organization"]:
            raise ToolError("UNAUTHORIZED_SCOPE")
        if tool_name == "doc.delete" and (not permit["allow_delete"] or not document["disposable"]):
            raise ToolError("POLICY_DENY")
        return document

    @staticmethod
    def _record(row):
        record = dict(row)
        result = record.pop("result_json")
        record["result"] = json.loads(result) if result else None
        # A durable file claim never proves completion, including after restart.
        if record["state"] == "CLAIMED":
            record["state"] = "UNKNOWN"
        record["record_type"] = "LocalExecutionRecord"
        record["authorization_kind"] = "LOCAL_TEST_PERMIT"
        return record

    def status(self, action_id, principal, token):
        identifier(action_id)
        with self.store.connect() as db:
            permit = self._permit(db, token, action_id, principal)
            row = db.execute("SELECT * FROM executions WHERE action_id=?", (action_id,)).fetchone()
            if row is None:
                raise ToolError("NOT_FOUND")
            if row["principal"] != principal:
                raise ToolError("FORBIDDEN")
            if row["request_sha256"] != permit["request_sha256"]:
                raise ToolError("PARAMS_MISMATCH")
            return self._record(row)

    def execute(self, action_id, principal, tool_name, params, token):
        params = params_for(tool_name, params)
        fingerprint = request_hash(action_id, principal, tool_name, params)
        with self.store.transaction() as db:
            permit = self._permit(db, token, action_id, principal)
            if permit["request_sha256"] != fingerprint:
                raise ToolError("PARAMS_MISMATCH")
            old = db.execute("SELECT * FROM executions WHERE action_id=?", (action_id,)).fetchone()
            if old is not None:
                if old["principal"] != principal:
                    raise ToolError("FORBIDDEN")
                if old["request_sha256"] != fingerprint:
                    raise ToolError("PARAMS_MISMATCH")
                return self._record(old)
            if now() >= permit["expires_at"]:
                raise ToolError("RESERVATION_EXPIRED")
            if permit["consumed"]:
                # A missing execution with a consumed permit is corruption, not permission to retry.
                raise ToolError("EXECUTION_UNKNOWN")
            document = self._scope(db, permit, tool_name, params)
            db.execute("INSERT INTO executions VALUES (?,?,?,?,?,?,?,?,?)",
                       (action_id, principal, tool_name, fingerprint, "CLAIMED", str(now()), None, None, None))
            db.execute("INSERT INTO events(action_id,state,observed_at) VALUES (?,?,?)", (action_id, "CLAIMED", str(now())))
            db.execute("UPDATE permits SET consumed=1 WHERE token_hash=?", (permit["token_hash"],))
            if tool_name == "mail.send":
                # Mailbox insertion and result/permit consumption commit together.
                result = self._send(db, action_id, params)
                self._finish(db, action_id, "COMPLETED", result)
                return self._record(db.execute("SELECT * FROM executions WHERE action_id=?", (action_id,)).fetchone())
        # For filesystem operations, the committed claim survives any crash below.
        try:
            if tool_name == "doc.read":
                data = self.resources.read_verified(document)
                result = {"doc_id": params["doc_id"], "content_b64": base64.b64encode(data).decode(),
                          "sha256": sha256(data), "size": len(data)}
            else:
                result = self.resources.delete_verified(document)
        except ToolError as error:
            with self.store.transaction() as db:
                self._finish(db, action_id, "REJECTED", None, error.code)
            return self.status(action_id, principal, token)
        except OSError:
            # An fsync/unlink failure can follow a partial side effect.
            with self.store.transaction() as db:
                self._finish(db, action_id, "UNKNOWN", None, "EXECUTION_UNKNOWN")
            return self.status(action_id, principal, token)
        with self.store.transaction() as db:
            self._finish(db, action_id, "COMPLETED", result)
        return self.status(action_id, principal, token)

    def _finish(self, db, action_id, state, result, error_code=None):
        completed = str(now()) if state in {"COMPLETED", "REJECTED"} else None
        db.execute("UPDATE executions SET state=?,completed_at=?,result_json=?,error_code=? WHERE action_id=? AND state='CLAIMED'",
                   (state, completed, json.dumps(result, ensure_ascii=False) if result is not None else None, error_code, action_id))
        db.execute("INSERT INTO events(action_id,state,observed_at) VALUES (?,?,?)", (action_id, state, str(now())))

    def _send(self, db, action_id, params):
        message = EmailMessage(policy=SMTP)
        message["From"] = "sandbox@inbox.chainguard.invalid"
        message["To"] = ", ".join(params["to"])
        message["Subject"] = params["subject"]
        message["Date"] = formatdate(now(), usegmt=True)
        message["Message-ID"] = f"<{action_id[2:]}@inbox.chainguard.invalid>"
        message.set_content(params["body"])
        data = message.as_bytes()
        ids = []
        for recipient in params["to"]:
            cursor = db.execute("INSERT INTO mailbox(action_id,recipient,mime,mime_sha256) VALUES (?,?,?,?)",
                                (action_id, recipient, data, sha256(data)))
            ids.append(str(cursor.lastrowid))
        return {"message_ids": ids, "delivered_recipients": list(params["to"]), "mime_sha256": sha256(data),
                "transport": "LOCAL_SQLITE_MAILBOX"}

    def execute_reserved(self, *args, **kwargs):
        """No offline fallback: real reservation integration belongs to a later stage."""
        raise ToolError("CHAIN_UNAVAILABLE")
