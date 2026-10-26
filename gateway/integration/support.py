"""Isolated synthetic accounts; approval private keys exist only in test signers."""

from pathlib import Path
import time

from eth_account import Account
from eth_account.messages import encode_typed_data
from fastapi.testclient import TestClient

from chainguard_gateway.central_service import CentralService
from chainguard_gateway.central_store import CentralStore
from chainguard_gateway.crypto import random_id
from chainguard_gateway.identity import issue_token
from chainguard_gateway.main import create_app
from chainguard_gateway.policy import check_policy_freeze
from chainguard_sandbox.central_adapter import CentralToolAdapter
from chainguard_sandbox.resources import Resources
from chainguard_sandbox.storage import Store

ALL_SCOPES = ["PUBLIC_DOCS", "ORG_A_DOCS", "ORG_A_INTERNAL_MAIL", "ORG_A_DISPOSABLE_DOCS"]
ALICE = "alice@inbox.chainguard.invalid"
BOB = "bob@inbox.chainguard.invalid"
MAIL = {"to": [ALICE], "subject": "central actual mail", "body": "synthetic central content"}


class Lab:
    def __init__(self, group="B"):
        self.tools = Store.create()
        operator = self.tools.private_read("operator.key").decode()
        resources = Resources(self.tools)
        for name, text, scope in [("doc-public", b"actual public central document", "PUBLIC_DOCS"),
                                   ("doc-private", b"actual private central document", "ORG_A_DOCS"),
                                   ("doc-trash", b"actual disposable central document", "ORG_A_DISPOSABLE_DOCS")]:
            resources.create_document(operator, name, text, scope=scope, disposable=name == "doc-trash")
        self.store = CentralStore.create(self.tools.root / "central", group, check_policy_freeze(), self.tools.root)
        self.accounts = {role: Account.create() for role in ("requester", "agent", "business", "security", "human", "auditor", "other")}
        self.actors = {}
        roles = {"requester": ["REQUESTER"], "agent": ["AGENT"], "business": ["BUSINESS_APPROVER"],
                 "security": ["SECURITY_APPROVER"], "human": ["HUMAN_APPROVER"], "auditor": ["AUDITOR"], "other": ["REQUESTER"]}
        for subject, account in self.accounts.items():
            actor = {"subject": subject, "address": account.address.lower(), "active": True, "roles": roles[subject],
                     "organization": "OrgB_Security" if subject == "security" else ("OrgC_Audit" if subject == "auditor" else "OrgA_Business"),
                     "allowed_tools": ["doc.read", "mail.send", "doc.delete"], "resource_scopes": ALL_SCOPES,
                     "allowed_document_ids": ["doc-public", "doc-private", "doc-trash"], "allowed_recipients": [ALICE, BOB], "max_risk": 3}
            self.actors[subject] = actor
            self.register(actor)
        self.adapter = CentralToolAdapter(self.tools, self.store)
        self.service = CentralService(self.store, self.adapter)
        self.client = TestClient(create_app(central_service=self.service))

    def register(self, actor):
        self.store.register_actor(self.store.private("admin.key"), actor)

    def headers(self, subject="requester", key=None):
        return {"Authorization": "Bearer " + issue_token(self.store.private("jwt.key"), subject),
                "Idempotency-Key": key or random_id()}

    def post(self, path, body, subject="requester", key=None):
        return self.client.post("/central/v1" + path, json=body, headers=self.headers(subject, key))

    def task_body(self, **changes):
        body = {"task_text": "Send synthetic summary only to Alice", "agent": self.accounts["agent"].address.lower(),
                "allowed_tools": ["doc.read", "mail.send", "doc.delete"], "resource_scopes": ALL_SCOPES,
                "allowed_document_ids": ["doc-public", "doc-private", "doc-trash"], "allowed_recipients": [ALICE],
                "expires_at": str(int(time.time()) + 3600), "max_risk": 3, "allow_sandbox_delete": False, "max_actions": 20}
        body.update(changes)
        return body

    def new_task(self, **changes):
        response = self.post("/tasks", self.task_body(**changes))
        assert response.status_code == 201, response.text
        return response.json()

    def propose(self, task, tool="mail.send", params=None, key=None):
        response = self.post("/actions/propose", {"task_id": task["task_id"], "tool_name": tool, "params": MAIL if params is None else params}, "agent", key)
        assert response.status_code == 202, response.text
        return response.json()

    def signature(self, action, subject):
        return "0x" + Account.sign_message(encode_typed_data(full_message=action["typed_data"]), self.accounts[subject].key).signature.hex()

    def approvals(self, action, roles=("business", "security")):
        for role in roles:
            response = self.post(f"/actions/{action['action_id']}/approve", {"signature": self.signature(action, role)}, role)
            assert response.status_code == 200, response.text

    def execute(self, action, *, subject="requester", key=None, body=None):
        if body is None:
            body = {"requester_signature": self.signature(action, "requester")} if action["typed_data"] else {}
        return self.post(f"/actions/{action['action_id']}/execute", body, subject, key)

    def mailbox_count(self):
        with self.tools.connect() as db:
            return db.execute("SELECT count(*) FROM mailbox").fetchone()[0]

    def close(self):
        self.client.close()
        self.tools.close()
