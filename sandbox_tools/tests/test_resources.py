"""Run with unittest inside the restricted Linux container, never on the host."""

import os
import unittest

from chainguard_sandbox.protocol import ToolError
from chainguard_sandbox.resources import Resources
from chainguard_sandbox.storage import Store


class ResourceTests(unittest.TestCase):
    def setUp(self):
        self.store = Store.create()
        self.key = self.store.private_read("operator.key").decode()
        self.resources = Resources(self.store)
        self.resources.create_document(self.key, "doc-public", b"actual test bytes")

    def tearDown(self):
        self.store.close()

    def document(self):
        with self.store.connect() as db:
            return self.resources.lookup(db, "doc-public")

    def test_actual_read_and_persistence_after_reopen(self):
        root = self.store.root
        self.assertEqual(self.resources.read_verified(self.document()), b"actual test bytes")
        self.store.close()
        self.store = Store(root)
        self.resources = Resources(self.store)
        self.assertEqual(self.resources.read_verified(self.document()), b"actual test bytes")

    def test_external_root_and_operator_rejected(self):
        with self.assertRaisesRegex(ToolError, "POLICY_DENY"):
            Store("/etc")
        with self.assertRaisesRegex(ToolError, "FORBIDDEN"):
            self.resources.create_document("fake", "doc-forged", b"forged")

    def test_corrupt_mapping_cannot_escape(self):
        with self.store.transaction() as db:
            db.execute("UPDATE documents SET filename='../operator.key'")
        with self.assertRaisesRegex(ToolError, "UNAUTHORIZED_SCOPE"):
            self.document()

    def test_symlink_rejected_and_target_unchanged(self):
        doc = self.document()
        os.unlink(doc["filename"], dir_fd=self.store.docs_fd)
        os.symlink("../marker", doc["filename"], dir_fd=self.store.docs_fd)
        with self.assertRaisesRegex(ToolError, "UNAUTHORIZED_SCOPE"):
            self.resources.read_verified(doc)
        self.assertEqual(self.store.private_read("marker"), b"ChainGuard/disposable-test-data/v1")

    def test_hardlink_rejected(self):
        doc = self.document()
        os.link(doc["filename"], "second.test", src_dir_fd=self.store.docs_fd, dst_dir_fd=self.store.docs_fd)
        with self.assertRaisesRegex(ToolError, "UNAUTHORIZED_SCOPE"):
            self.resources.read_verified(doc)

    def test_fifo_rejected_without_blocking(self):
        doc = self.document()
        os.unlink(doc["filename"], dir_fd=self.store.docs_fd)
        os.mkfifo(doc["filename"], dir_fd=self.store.docs_fd)
        with self.assertRaisesRegex(ToolError, "UNAUTHORIZED_SCOPE"):
            self.resources.read_verified(doc)

    def test_replaced_or_modified_file_rejected(self):
        doc = self.document()
        fd = os.open(doc["filename"], os.O_WRONLY | os.O_TRUNC, dir_fd=self.store.docs_fd)
        os.write(fd, b"changed")
        os.close(fd)
        with self.assertRaisesRegex(ToolError, "UNAUTHORIZED_SCOPE"):
            self.resources.read_verified(doc)

    def test_only_explicit_disposable_test_document_deleted(self):
        with self.assertRaisesRegex(ToolError, "POLICY_DENY"):
            self.resources.delete_verified(self.document())
        self.resources.create_document(self.key, "doc-trash", b"disposable bytes", scope="ORG_A_DISPOSABLE_DOCS", disposable=True)
        with self.store.connect() as db:
            doc = self.resources.lookup(db, "doc-trash")
        result = self.resources.delete_verified(doc)
        self.assertTrue(result["deleted"])
        self.assertFalse(os.path.exists(self.store.root / "documents" / doc["filename"]))
        self.assertEqual(self.resources.read_verified(self.document()), b"actual test bytes")


if __name__ == "__main__":
    unittest.main()
