"""Flat, operator-created disposable resources; never accept a caller path."""

import os
import secrets
import stat

from .protocol import ToolError, document_id
from .storage import sha256

MAX_DOCUMENT = 1024 * 1024


class Resources:
    def __init__(self, store):
        self.store = store

    def create_document(self, operator_key, doc_id, content, *, scope="PUBLIC_DOCS", organization="OrgA_Business", disposable=False):
        self.store.authorize_operator(operator_key)
        document_id(doc_id)
        if scope not in {"PUBLIC_DOCS", "ORG_A_DOCS", "ORG_A_DISPOSABLE_DOCS"} or type(content) is not bytes or len(content) > MAX_DOCUMENT:
            raise ToolError("SCHEMA_INVALID")
        if type(disposable) is not bool or disposable != (scope == "ORG_A_DISPOSABLE_DOCS"):
            raise ToolError("POLICY_DENY")
        if scope != "PUBLIC_DOCS" and organization != "OrgA_Business":
            raise ToolError("UNAUTHORIZED_SCOPE")
        name = secrets.token_hex(24) + ".test"
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.store.docs_fd)
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
            info = os.fstat(stream.fileno())
        os.fsync(self.store.docs_fd)
        with self.store.transaction() as db:
            db.execute("INSERT INTO documents VALUES (?,?,?,?,?,?,?,?,?)",
                       (doc_id, name, scope, organization, int(disposable), info.st_dev, info.st_ino, sha256(content), len(content)))

    def lookup(self, db, doc_id):
        document_id(doc_id)
        row = db.execute("SELECT * FROM documents WHERE doc_id=?", (doc_id,)).fetchone()
        if row is None:
            raise ToolError("NOT_FOUND")
        # Defend even against a corrupt mapping; never turn a DB value into a path.
        name = row["filename"]
        if len(name) != 53 or not name.endswith(".test") or any(c not in "0123456789abcdef" for c in name[:-5]):
            raise ToolError("UNAUTHORIZED_SCOPE")
        return dict(row)

    def read_verified(self, document):
        try:
            fd = os.open(document["filename"], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.store.docs_fd)
            with os.fdopen(fd, "rb") as stream:
                info = os.fstat(stream.fileno())
                if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.geteuid()
                        or info.st_dev != document["device"] or info.st_ino != document["inode"]
                        or info.st_size > MAX_DOCUMENT):
                    raise ToolError("UNAUTHORIZED_SCOPE")
                data = stream.read(MAX_DOCUMENT + 1)
                if len(data) != document["size"] or sha256(data) != document["sha256"]:
                    raise ToolError("UNAUTHORIZED_SCOPE")
                return data
        except FileNotFoundError:
            raise ToolError("NOT_FOUND") from None
        except OSError:
            raise ToolError("UNAUTHORIZED_SCOPE") from None

    def delete_verified(self, document):
        if document["scope"] != "ORG_A_DISPOSABLE_DOCS" or not document["disposable"]:
            raise ToolError("POLICY_DENY")
        data = self.read_verified(document)
        info = os.stat(document["filename"], dir_fd=self.store.docs_fd, follow_symlinks=False)
        if info.st_ino != document["inode"] or info.st_dev != document["device"] or info.st_nlink != 1:
            raise ToolError("UNAUTHORIZED_SCOPE")
        # The private directory is not writable by Agent or another OS identity.
        # Same-UID malicious administrators are outside the trusted tool boundary.
        os.unlink(document["filename"], dir_fd=self.store.docs_fd)
        os.fsync(self.store.docs_fd)
        return {"doc_id": document["doc_id"], "deleted": True,
                "sha256_before": sha256(data), "size_before": len(data), "inode_before": str(info.st_ino)}
