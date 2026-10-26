"""Private SQLite state in a container-only, newly created test sandbox."""

import contextlib
import hashlib
import os
from pathlib import Path
import secrets
import sqlite3
import stat
import re

from .protocol import ToolError

BOUNDARY = Path("/sandbox")
DDL = """
CREATE TABLE IF NOT EXISTS documents (
 doc_id TEXT PRIMARY KEY, filename TEXT NOT NULL UNIQUE, scope TEXT NOT NULL,
 organization TEXT NOT NULL, disposable INTEGER NOT NULL,
 device INTEGER NOT NULL, inode INTEGER NOT NULL, sha256 TEXT NOT NULL, size INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS permits (
 token_hash TEXT PRIMARY KEY, action_id TEXT NOT NULL, request_sha256 TEXT NOT NULL,
 principal TEXT NOT NULL, scope TEXT NOT NULL, organization TEXT NOT NULL,
 documents TEXT NOT NULL, recipients TEXT NOT NULL, allow_delete INTEGER NOT NULL,
 expires_at INTEGER NOT NULL, revoked INTEGER NOT NULL DEFAULT 0, consumed INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS executions (
 action_id TEXT PRIMARY KEY, principal TEXT NOT NULL, tool_name TEXT NOT NULL,
 request_sha256 TEXT NOT NULL, state TEXT NOT NULL,
 started_at TEXT NOT NULL, completed_at TEXT, result_json TEXT, error_code TEXT);
CREATE TABLE IF NOT EXISTS mailbox (
 message_id INTEGER PRIMARY KEY, action_id TEXT NOT NULL REFERENCES executions(action_id),
 recipient TEXT NOT NULL, mime BLOB NOT NULL, mime_sha256 TEXT NOT NULL,
 UNIQUE(action_id, recipient));
CREATE TABLE IF NOT EXISTS events (
 sequence INTEGER PRIMARY KEY, action_id TEXT NOT NULL,
 state TEXT NOT NULL, observed_at TEXT NOT NULL);
"""


def require_container():
    if os.name != "posix" or not Path("/.dockerenv").is_file() or os.geteuid() == 0:
        raise ToolError("POLICY_DENY")


def _directory(path, *, dir_fd=None):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=dir_fd)
    info = os.fstat(fd)
    if info.st_uid != os.geteuid() or info.st_mode & 0o022:
        os.close(fd)
        raise ToolError("POLICY_DENY")
    return fd


class Store:
    @classmethod
    def create(cls):
        require_container()
        boundary_fd = _directory(BOUNDARY)
        name = "test-" + secrets.token_hex(16)
        try:
            os.mkdir(name, mode=0o700, dir_fd=boundary_fd)
        finally:
            os.close(boundary_fd)
        root = BOUNDARY / name
        os.mkdir(root / "documents", mode=0o700)
        for name, data in (("operator.key", secrets.token_hex(32).encode("ascii")),
                           ("marker", b"ChainGuard/disposable-test-data/v1"),
                           ("state.sqlite3", b"")):
            fd = os.open(root / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        store = cls(root)
        with store.connect() as db:
            db.executescript(DDL)
        return store

    def __init__(self, root):
        require_container()
        self.root = Path(root)
        if self.root.parent != BOUNDARY or not self.root.name.startswith("test-"):
            raise ToolError("POLICY_DENY")
        self.root_fd = _directory(self.root)
        try:
            self.docs_fd = _directory("documents", dir_fd=self.root_fd)
            if self.private_read("marker") != b"ChainGuard/disposable-test-data/v1":
                raise ToolError("POLICY_DENY")
            self.private_read("operator.key")
            self._check_private_file("state.sqlite3")
        except BaseException:
            self.close()
            raise

    def _check_private_file(self, name):
        info = os.stat(name, dir_fd=self.root_fd, follow_symlinks=False)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise ToolError("POLICY_DENY")

    def private_read(self, name):
        self._check_private_file(name)
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=self.root_fd)
        with os.fdopen(fd, "rb") as stream:
            return stream.read()

    def authorize_operator(self, key):
        if type(key) is not str or re.fullmatch(r"[0-9a-f]{64}", key) is None or not secrets.compare_digest(key.encode("ascii"), self.private_read("operator.key")):
            raise ToolError("FORBIDDEN")

    @contextlib.contextmanager
    def connect(self):
        self._check_private_file("state.sqlite3")
        db = sqlite3.connect(f"/proc/self/fd/{self.root_fd}/state.sqlite3", timeout=30, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA synchronous=FULL")
        try:
            yield db
        finally:
            db.close()

    @contextlib.contextmanager
    def transaction(self):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise

    def close(self):
        for name in ("docs_fd", "root_fd"):
            fd = getattr(self, name, None)
            if fd is not None:
                os.close(fd)
                setattr(self, name, None)


def sha256(data):
    return hashlib.sha256(data).hexdigest()
