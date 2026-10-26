"""Container-side actual side effects and cross-container replay evidence."""

import argparse
import base64
import json
import os
from pathlib import Path
import secrets
import socket

from chainguard_sandbox.storage import Store, sha256
from chainguard_sandbox.tools import LocalTestTools


def runtime():
    status = Path("/proc/self/status").read_text()
    effective = next(line.split()[1] for line in status.splitlines() if line.startswith("CapEff:"))
    return {"uid": os.geteuid(), "hostname": socket.gethostname(), "cap_eff": effective,
            "interfaces": sorted(os.listdir("/sys/class/net")),
            "root_read_only": bool(os.statvfs("/").f_flag & os.ST_RDONLY)}


def create_private(path, content):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def prepare():
    store = Store.create()
    tools = LocalTestTools(store)
    operator = store.private_read("operator.key").decode()
    source = ("Synthetic ChainGuard fixture " + secrets.token_hex(24)).encode()
    trash = ("Disposable test fixture " + secrets.token_hex(24)).encode()
    tools.resources.create_document(operator, "doc-public", source)
    tools.resources.create_document(operator, "doc-trash", trash, scope="ORG_A_DISPOSABLE_DOCS", disposable=True)
    # A separate, unregistered sandbox is the out-of-scope sentinel, not a host file.
    outside = Store.create()
    sentinel = ("Unrelated container-only sentinel " + secrets.token_hex(24)).encode()
    create_private(outside.root / "sentinel.test", sentinel)
    actions = []
    read = {"doc_id": "doc-public"}
    mail = {"to": ["evidence@inbox.chainguard.invalid"], "subject": "ChainGuard actual side effect",
            "body": "Read SHA-256: " + sha256(source)}
    delete = {"doc_id": "doc-trash"}
    for tool, params, scope in [("doc.read", read, "PUBLIC_DOCS"), ("mail.send", mail, "ORG_A_INTERNAL_MAIL"),
                                 ("doc.delete", delete, "ORG_A_DISPOSABLE_DOCS")]:
        action = "0x" + secrets.token_hex(32)
        permit = tools.issue_permit(operator, action, "gateway", tool, params, scope=scope,
                                    allowed_documents=[params["doc_id"]] if "doc_id" in params else [],
                                    allowed_recipients=params.get("to", []), allow_sandbox_delete=tool == "doc.delete")
        record = tools.execute(action, "gateway", tool, params, permit)
        assert record["state"] == "COMPLETED"
        actions.append({"action_id": action, "token": permit, "tool_name": tool, "params": params, "record": record})
    with store.connect() as db:
        deleted = tools.resources.lookup(db, "doc-trash")
        messages = db.execute("SELECT * FROM mailbox").fetchall()
    assert len(messages) == 1
    actual = base64.b64decode(actions[0]["record"]["result"]["content_b64"])
    assert actual == source
    assert not (store.root / "documents" / deleted["filename"]).exists()
    assert (outside.root / "sentinel.test").read_bytes() == sentinel
    private = {"root": str(store.root), "outside": str(outside.root), "sentinel_sha256": sha256(sentinel),
               "deleted_filename": deleted["filename"], "actions": actions}
    create_private(store.root / "acceptance-private.json", json.dumps(private).encode())
    create_private(Path("/sandbox/evidence-root.txt"), str(store.root).encode())
    public = {"phase": "prepare", "runtime": runtime(), "source_sha256": sha256(actual),
              "source_content_b64": base64.b64encode(actual).decode(), "delete_sha256_before": sha256(trash),
              "delete_exists_after": False, "outside_sentinel_sha256": sha256(sentinel),
              "mailbox_count": len(messages), "mime_sha256": messages[0]["mime_sha256"],
              "actions": [entry["record"] for entry in actions]}
    store.close()
    outside.close()
    return public


def replay():
    root = Path("/sandbox/evidence-root.txt").read_text()
    store = Store(root)
    private = json.loads(store.private_read("acceptance-private.json"))
    tools = LocalTestTools(store)
    with store.connect() as db:
        before = db.execute("SELECT count(*) FROM mailbox").fetchone()[0]
    for _ in range(10):
        for entry in private["actions"]:
            observed = tools.execute(entry["action_id"], "gateway", entry["tool_name"], entry["params"], entry["token"])
            assert observed == entry["record"]
    with store.connect() as db:
        rows = db.execute("SELECT * FROM mailbox").fetchall()
        executions = db.execute("SELECT count(*) FROM executions").fetchone()[0]
        events = db.execute("SELECT count(*) FROM events").fetchone()[0]
        snapshot = db.serialize()
    assert before == len(rows) == 1 and executions == 3 and events == 6
    assert not (store.root / "documents" / private["deleted_filename"]).exists()
    outside = Store(private["outside"])
    assert sha256(outside.private_read("sentinel.test")) == private["sentinel_sha256"]
    # The snapshot contains hashes of bearer tokens, never raw tokens or the operator key.
    assert store.private_read("operator.key") not in snapshot
    assert all(entry["token"].encode() not in snapshot for entry in private["actions"])
    result = {"phase": "replay", "runtime": runtime(), "replay_requests": 30,
              "mailbox_before": before, "mailbox_after": len(rows), "execution_records": executions,
              "journal_events": events, "delete_still_absent": True, "outside_sentinel_unchanged": True,
              "mime_b64": base64.b64encode(rows[0]["mime"]).decode(),
              "snapshot_b64": base64.b64encode(snapshot).decode(), "snapshot_sha256": sha256(snapshot)}
    store.close()
    outside.close()
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["prepare", "replay"])
    args = parser.parse_args()
    print(json.dumps(prepare() if args.phase == "prepare" else replay(), ensure_ascii=False))
