import base64
from concurrent.futures import ThreadPoolExecutor
from email import policy
from email.parser import BytesParser
import json
import os
import secrets
import subprocess
import sys
import unittest
from unittest.mock import patch

from chainguard_sandbox.protocol import ToolError
from chainguard_sandbox.storage import Store, sha256
from chainguard_sandbox.tools import LocalTestTools, now

MAIL = {"to": ["alice@inbox.chainguard.invalid"], "subject": "真实本地测试", "body": "邮件副作用\nChainGuard"}


class ToolTests(unittest.TestCase):
    def setUp(self):
        self.store = Store.create()
        self.key = self.store.private_read("operator.key").decode()
        self.tools = LocalTestTools(self.store)
        self.tools.resources.create_document(self.key, "doc-public", b"public actual bytes")
        self.tools.resources.create_document(self.key, "doc-private", b"private actual bytes", scope="ORG_A_DOCS")
        self.tools.resources.create_document(self.key, "doc-trash", b"only disposable bytes", scope="ORG_A_DISPOSABLE_DOCS", disposable=True)

    def tearDown(self):
        self.store.close()

    def permit(self, tool="mail.send", params=None, **changes):
        params = MAIL if params is None else params
        action = "0x" + secrets.token_hex(32)
        options = {"scope": {"mail.send": "ORG_A_INTERNAL_MAIL", "doc.read": "PUBLIC_DOCS", "doc.delete": "ORG_A_DISPOSABLE_DOCS"}[tool],
                   "allowed_documents": [params["doc_id"]] if "doc_id" in params else [],
                   "allowed_recipients": params.get("to", []), "allow_sandbox_delete": tool == "doc.delete"}
        options.update(changes)
        token = self.tools.issue_permit(self.key, action, "gateway", tool, params, **options)
        return action, token

    def execute(self, action, token, tool="mail.send", params=None):
        return self.tools.execute(action, "gateway", tool, MAIL if params is None else params, token)

    def count(self, table):
        assert table in {"mailbox", "executions", "events"}
        with self.store.connect() as db:
            return db.execute("SELECT count(*) FROM " + table).fetchone()[0]

    def doc(self, name="doc-trash"):
        with self.store.connect() as db:
            return self.tools.resources.lookup(db, name)

    def crash_child(self, action, token, tool, params, point="finish"):
        code = """
import json, os, sys
from chainguard_sandbox.storage import Store
from chainguard_sandbox.tools import LocalTestTools
s=Store(sys.argv[1]); t=LocalTestTools(s)
def crash(*a, **kw): os._exit(73)
if sys.argv[6]=='finish': t._finish=crash
else: t.resources.delete_verified=crash
t.execute(sys.argv[2], 'gateway', sys.argv[3], json.loads(sys.argv[4]), sys.argv[5])
"""
        result = subprocess.run([sys.executable, "-c", code, str(self.store.root), action, tool, json.dumps(params), token, point], capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 73, result.stderr.decode())

    def test_read_returns_real_bytes_and_hash(self):
        params = {"doc_id": "doc-public"}
        action, token = self.permit("doc.read", params)
        result = self.execute(action, token, "doc.read", params)
        self.assertEqual(result["state"], "COMPLETED")
        self.assertEqual(base64.b64decode(result["result"]["content_b64"]), b"public actual bytes")
        self.assertEqual(result["result"]["sha256"], sha256(b"public actual bytes"))
        self.assertEqual(self.count("executions"), 1)

    def test_mail_mime_is_really_in_local_mailbox(self):
        action, token = self.permit()
        record = self.execute(action, token)
        with self.store.connect() as db:
            mail = db.execute("SELECT * FROM mailbox").fetchone()
        message = BytesParser(policy=policy.default).parsebytes(mail["mime"])
        self.assertEqual(message["Subject"], MAIL["subject"])
        self.assertEqual(message["To"], MAIL["to"][0])
        self.assertEqual(message.get_content().replace("\r\n", "\n"), MAIL["body"] + "\n")
        self.assertEqual(sha256(mail["mime"]), record["result"]["mime_sha256"])
        self.assertEqual(record["record_type"], "LocalExecutionRecord")
        self.assertNotIn("receipt", record)

    def test_multiple_local_recipients_are_individually_delivered(self):
        params = dict(MAIL, to=["alice@inbox.chainguard.invalid", "bob@inbox.chainguard.invalid"])
        action, token = self.permit(params=params)
        self.execute(action, token, params=params)
        self.assertEqual(self.count("mailbox"), 2)
        self.execute(action, token, params=params)
        self.assertEqual(self.count("mailbox"), 2)

    def test_100_concurrent_replays_have_one_mail_side_effect(self):
        action, token = self.permit()
        with ThreadPoolExecutor(max_workers=12) as pool:
            records = list(pool.map(lambda _: self.execute(action, token), range(100)))
        self.assertTrue(all(record == records[0] for record in records))
        self.assertEqual(self.count("mailbox"), 1)
        self.assertEqual(self.count("executions"), 1)
        self.assertEqual(self.count("events"), 2)

    def test_new_permit_cannot_reexecute_same_action(self):
        action, token = self.permit()
        original = self.execute(action, token)
        another = self.tools.issue_permit(self.key, action, "gateway", "mail.send", MAIL, scope="ORG_A_INTERNAL_MAIL", allowed_recipients=MAIL["to"])
        self.assertEqual(self.execute(action, another), original)
        self.assertEqual(self.count("mailbox"), 1)

    def test_same_action_changed_body_or_tool_rejected(self):
        action, token = self.permit()
        self.execute(action, token)
        for changed in [dict(MAIL, body="different"), dict(MAIL, to=["bob@inbox.chainguard.invalid"])]:
            with self.assertRaisesRegex(ToolError, "PARAMS_MISMATCH"):
                self.execute(action, token, params=changed)
        with self.assertRaisesRegex(ToolError, "PARAMS_MISMATCH"):
            self.execute(action, token, "doc.delete", {"doc_id": "doc-trash"})
        self.assertEqual(self.count("mailbox"), 1)

    def test_new_action_cannot_reuse_old_permit(self):
        action, token = self.permit()
        with self.assertRaisesRegex(ToolError, "FORBIDDEN"):
            self.execute("0x" + secrets.token_hex(32), token)
        self.assertEqual(self.count("mailbox"), 0)

    def test_missing_forged_token_and_wrong_principal_rejected(self):
        action, token = self.permit()
        for bad in [None, "approved", "0" * 64]:
            with self.assertRaises(ToolError):
                self.execute(action, bad)
        with self.assertRaisesRegex(ToolError, "FORBIDDEN"):
            self.tools.execute(action, "agent", "mail.send", MAIL, token)
        self.assertEqual(self.count("mailbox"), 0)

    def test_expired_unstarted_permit_rejected(self):
        action, token = self.permit()
        with patch("chainguard_sandbox.tools.now", return_value=now() + 121):
            with self.assertRaisesRegex(ToolError, "RESERVATION_EXPIRED"):
                self.execute(action, token)
        self.assertEqual(self.count("executions"), 0)

    def test_revoked_permit_rejected(self):
        action, token = self.permit()
        self.tools.revoke_permit(self.key, token)
        with self.assertRaisesRegex(ToolError, "FORBIDDEN"):
            self.execute(action, token)
        self.assertEqual(self.count("mailbox"), 0)

    def test_completed_result_survives_expiry_and_reopen(self):
        action, token = self.permit()
        original = self.execute(action, token)
        root = self.store.root
        self.store.close()
        self.store = Store(root)
        self.tools = LocalTestTools(self.store)
        with patch("chainguard_sandbox.tools.now", return_value=now() + 121):
            self.assertEqual(self.execute(action, token), original)
        self.assertEqual(self.count("mailbox"), 1)

    def test_exact_recipient_allowlist_is_enforced(self):
        action, token = self.permit(allowed_recipients=["different@inbox.chainguard.invalid"])
        with self.assertRaisesRegex(ToolError, "UNAUTHORIZED_SCOPE"):
            self.execute(action, token)
        self.assertEqual(self.count("mailbox"), 0)

    def test_external_email_cannot_be_granted(self):
        with self.assertRaisesRegex(ToolError, "SCHEMA_INVALID"):
            self.permit(params=dict(MAIL, to=["real@example.com"]))
        self.assertEqual(self.count("mailbox"), 0)

    def test_wrong_document_set_scope_or_organization_rejected(self):
        params = {"doc_id": "doc-private"}
        for options in [{"scope": "PUBLIC_DOCS"}, {"scope": "ORG_A_DOCS", "allowed_documents": []},
                        {"scope": "ORG_A_DOCS", "organization": "OrgB_Security"}]:
            action, token = self.permit("doc.read", params, **options)
            with self.assertRaisesRegex(ToolError, "UNAUTHORIZED_SCOPE"):
                self.execute(action, token, "doc.read", params)
        self.assertEqual(self.count("executions"), 0)

    def test_r1_document_read_for_matching_scope_and_organization(self):
        params = {"doc_id": "doc-private"}
        action, token = self.permit("doc.read", params, scope="ORG_A_DOCS")
        record = self.execute(action, token, "doc.read", params)
        self.assertEqual(base64.b64decode(record["result"]["content_b64"]), b"private actual bytes")

    def test_delete_requires_explicit_permission(self):
        params = {"doc_id": "doc-trash"}
        action, token = self.permit("doc.delete", params, allow_sandbox_delete=False)
        with self.assertRaisesRegex(ToolError, "POLICY_DENY"):
            self.execute(action, token, "doc.delete", params)
        self.assertTrue((self.store.root / "documents" / self.doc()["filename"]).exists())

    def test_real_delete_and_25_retries_only_one_record(self):
        params = {"doc_id": "doc-trash"}
        action, token = self.permit("doc.delete", params)
        document = self.doc()
        record = self.execute(action, token, "doc.delete", params)
        self.assertFalse((self.store.root / "documents" / document["filename"]).exists())
        self.assertEqual(record["result"]["sha256_before"], document["sha256"])
        for _ in range(25):
            self.assertEqual(self.execute(action, token, "doc.delete", params), record)
        self.assertEqual(self.count("events"), 2)
        self.assertEqual(self.count("executions"), 1)
        self.assertTrue((self.store.root / "documents" / self.doc("doc-public")["filename"]).exists())

    def test_50_concurrent_delete_requests_cannot_repeat_unlink(self):
        params = {"doc_id": "doc-trash"}
        action, token = self.permit("doc.delete", params)
        with ThreadPoolExecutor(max_workers=12) as pool:
            records = list(pool.map(lambda _: self.execute(action, token, "doc.delete", params), range(50)))
        self.assertTrue(all(record["state"] in {"UNKNOWN", "COMPLETED"} for record in records))
        self.assertEqual(self.tools.status(action, "gateway", token)["state"], "COMPLETED")
        self.assertEqual(self.count("executions"), 1)
        self.assertEqual(self.count("events"), 2)

    def test_delete_symlink_cannot_remove_out_of_scope_target(self):
        params = {"doc_id": "doc-trash"}
        action, token = self.permit("doc.delete", params)
        path = self.store.root / "documents" / self.doc()["filename"]
        path.unlink()
        path.symlink_to("../marker")
        result = self.execute(action, token, "doc.delete", params)
        self.assertEqual(result["state"], "REJECTED")
        self.assertEqual(self.store.private_read("marker"), b"ChainGuard/disposable-test-data/v1")
        self.assertTrue(path.is_symlink())

    def test_another_principal_cannot_take_over_action_id(self):
        action, token = self.permit()
        self.execute(action, token)
        other = self.tools.issue_permit(self.key, action, "other-gateway", "mail.send", MAIL,
                                        scope="ORG_A_INTERNAL_MAIL", allowed_recipients=MAIL["to"])
        with self.assertRaisesRegex(ToolError, "FORBIDDEN"):
            self.tools.execute(action, "other-gateway", "mail.send", MAIL, other)
        self.assertEqual(self.count("mailbox"), 1)

    def test_tampered_delete_target_is_rejected_and_preserved(self):
        params = {"doc_id": "doc-trash"}
        action, token = self.permit("doc.delete", params)
        path = self.store.root / "documents" / self.doc()["filename"]
        path.write_bytes(b"changed test bytes")
        result = self.execute(action, token, "doc.delete", params)
        self.assertEqual(result["state"], "REJECTED")
        self.assertEqual(result["error_code"], "UNAUTHORIZED_SCOPE")
        self.assertTrue(path.exists())

    def test_crash_after_unlink_is_unknown_and_never_reexecuted(self):
        params = {"doc_id": "doc-trash"}
        action, token = self.permit("doc.delete", params)
        path = self.store.root / "documents" / self.doc()["filename"]
        self.crash_child(action, token, "doc.delete", params)
        self.assertFalse(path.exists())
        self.assertEqual(self.tools.status(action, "gateway", token)["state"], "UNKNOWN")
        path.write_bytes(b"replacement test sentinel")
        result = self.execute(action, token, "doc.delete", params)
        self.assertEqual(result["state"], "UNKNOWN")
        self.assertIsNone(result["result"])
        self.assertEqual(path.read_bytes(), b"replacement test sentinel")

    def test_crash_before_unlink_does_not_blindly_retry(self):
        params = {"doc_id": "doc-trash"}
        action, token = self.permit("doc.delete", params)
        self.crash_child(action, token, "doc.delete", params, "before")
        self.assertEqual(self.execute(action, token, "doc.delete", params)["state"], "UNKNOWN")
        self.assertTrue((self.store.root / "documents" / self.doc()["filename"]).exists())

    def test_mail_crash_before_commit_rolls_back_mailbox_and_claim(self):
        action, token = self.permit()
        self.crash_child(action, token, "mail.send", MAIL)
        self.assertEqual(self.count("mailbox"), 0)
        self.assertEqual(self.count("executions"), 0)
        self.assertEqual(self.execute(action, token)["state"], "COMPLETED")
        self.assertEqual(self.count("mailbox"), 1)

    def test_status_is_observation_and_cannot_send(self):
        action, token = self.permit()
        with self.assertRaisesRegex(ToolError, "NOT_FOUND"):
            self.tools.status(action, "gateway", token)
        self.assertEqual(self.count("mailbox"), 0)
        record = self.execute(action, token)
        self.assertEqual(self.tools.status(action, "gateway", token), record)
        self.assertEqual(self.count("mailbox"), 1)

    def test_chain_entry_never_accepts_a_local_permit(self):
        action, token = self.permit()
        with self.assertRaisesRegex(ToolError, "CHAIN_UNAVAILABLE"):
            self.tools.execute_reserved(action_id=action, token=token, approved=True)
        self.assertEqual(self.count("mailbox"), 0)


if __name__ == "__main__":
    unittest.main()
