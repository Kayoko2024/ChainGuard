"""Real Uvicorn HTTP A/B runs, followed by a different container's replay."""

import base64
from contextlib import contextmanager
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from chainguard_gateway.audit import verify_log
from chainguard_gateway.central_store import CentralStore
from chainguard_gateway.crypto import random_id
from chainguard_gateway.identity import issue_token
from chainguard_sandbox.storage import Store, sha256
from support import BOB, MAIL, Lab


def runtime():
    effective = next(line.split()[1] for line in Path("/proc/self/status").read_text().splitlines() if line.startswith("CapEff:"))
    return {"uid": os.geteuid(), "hostname": socket.gethostname(), "cap_eff": effective,
            "interfaces": sorted(os.listdir("/sys/class/net")), "root_read_only": bool(os.statvfs("/").f_flag & os.ST_RDONLY)}


@contextmanager
def server(store, group):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    log = Path("/tmp/server-" + group + ".log").open("wb")
    process = subprocess.Popen([sys.executable, "-m", "chainguard_gateway.central_server", "--root", str(store.root), "--port", str(port)], stdout=log, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}"
    started = {"pid": process.pid, "port": port}
    try:
        for _ in range(150):
            if process.poll() is not None:
                raise RuntimeError("Actual gateway exited during startup")
            try:
                with urlopen(base + "/health/ready", timeout=1) as response:
                    health = json.load(response)
                if health["status"] == "ready":
                    assert health["pid"] == process.pid and health["stage"] == 3
                    break
            except OSError:
                time.sleep(0.1)
        else:
            raise RuntimeError("Actual gateway readiness timeout")
        started["health"] = health
        yield base, started
    finally:
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        log.close()
        lifecycle = Path("/tmp/server-" + group + ".log").read_text()
        with socket.socket() as probe:
            probe.settimeout(1)
            released = probe.connect_ex(("127.0.0.1", port)) != 0
        complete = "Application shutdown complete" in lifecycle and "Finished server process" in lifecycle
        started["shutdown"] = {"exit_code": process.returncode, "lifecycle_complete": complete, "port_released": released}
        # Uvicorn 0.38 re-raises the handled SIGTERM after completing shutdown.
        assert process.returncode in (0, -15) and complete and released, lifecycle[-2000:]


def request(store, base, path, subject="requester", body=None):
    headers = {"Authorization": "Bearer " + issue_token(store.private("jwt.key"), subject), "Idempotency-Key": random_id()}
    data = None if body is None else json.dumps(body).encode()
    if data is not None:
        headers["Content-Type"] = "application/json"
    query = Request(base + path, data=data, headers=headers)
    try:
        with urlopen(query, timeout=30) as response:
            return response.status, json.load(response)
    except HTTPError as error:
        return error.code, json.load(error)


def prepare():
    public, private = {}, {}
    for group in ("A", "B"):
        lab = Lab(group)
        try:
            with server(lab.store, group) as (base, started):
                status, task = request(lab.store, base, "/central/v1/tasks", body=lab.task_body())
                assert status == 201
                status, normal = request(lab.store, base, "/central/v1/actions/propose", "agent",
                                         {"task_id": task["task_id"], "tool_name": "mail.send", "params": MAIL})
                assert status == 202
                if group == "B":
                    for role in ("business", "security"):
                        status, _ = request(lab.store, base, f"/central/v1/actions/{normal['action_id']}/approve", role,
                                            {"signature": lab.signature(normal, role)})
                        assert status == 200
                execute_body = {"requester_signature": lab.signature(normal, "requester")} if group == "B" else {}
                status, sent = request(lab.store, base, f"/central/v1/actions/{normal['action_id']}/execute", body=execute_body)
                assert status == 200 and sent["central_state"] == "CENTRAL_OK"
                status, unauthorized = request(lab.store, base, "/central/v1/actions/propose", "agent",
                    {"task_id": task["task_id"], "tool_name": "mail.send", "params": dict(MAIL, to=[BOB])})
                assert status == 202 and unauthorized["policy_verdict"] == "DENY"
                status, attempted = request(lab.store, base, f"/central/v1/actions/{unauthorized['action_id']}/execute", body={})
                assert status == 200
                assert attempted["central_state"] == ("CENTRAL_OK" if group == "A" else "DENIED")
                status, delete = request(lab.store, base, "/central/v1/actions/propose", "agent",
                    {"task_id": task["task_id"], "tool_name": "doc.delete", "params": {"doc_id": "doc-trash"}})
                assert status == 202 and delete["central_state"] == "DENIED"
                status, audit = request(lab.store, base, "/central/v1/audit/entries", "auditor")
                assert status == 200
                status, openapi = request(lab.store, base, "/operations/openapi.json")
                assert status == 200
                if group == "B":
                    assert verify_log(audit["entries"], audit["signer"], checkpoint=audit["checkpoint"], deployment_id=audit["deployment_id"])["status"] == "VALID"
                with lab.tools.connect() as db:
                    count = db.execute("SELECT count(*) FROM mailbox").fetchone()[0]
                    document = lab.adapter._tools.resources.lookup(db, "doc-trash")
                assert count == (2 if group == "A" else 1)
                assert (lab.tools.root / "documents" / document["filename"]).exists()
                public[group] = {"startup": started, "normal_action": sent, "unauthorized_action": attempted,
                                 "default_delete_action": delete, "mailbox_count": count, "audit": audit, "openapi": openapi,
                                 "default_delete_file_preserved": True}
                private[group] = {"central_root": str(lab.store.root), "tool_root": str(lab.tools.root),
                                  "action_id": normal["action_id"], "execute_body": execute_body, "original": sent,
                                  "mailbox_count": count, "delete_filename": document["filename"]}
        finally:
            lab.close()
    descriptor = os.open("/sandbox/phase3-private.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        json.dump(private, stream)
    return {"phase": "prepare", "runtime": runtime(), "groups": public}


def replay():
    private = json.loads(Path("/sandbox/phase3-private.json").read_text())
    public = {}
    for group, saved in private.items():
        store, tools = CentralStore(saved["central_root"]), Store(saved["tool_root"])
        try:
            with server(store, group) as (base, started):
                for _ in range(10):
                    status, observed = request(store, base, f"/central/v1/actions/{saved['action_id']}/execute", body=saved["execute_body"])
                    assert status == 200 and observed == saved["original"]
                status, export = request(store, base, "/central/v1/audit/entries", "auditor")
                assert status == 200
                with tools.connect() as db:
                    mails = [dict(row) for row in db.execute("SELECT recipient,mime,mime_sha256 FROM mailbox ORDER BY message_id")]
                    snapshot = db.serialize()
                assert len(mails) == saved["mailbox_count"]
                assert (tools.root / "documents" / saved["delete_filename"]).exists()
                with store.connect() as db:
                    central_snapshot = db.serialize()
                for name in ("data.key", "jwt.key", "audit.key", "admin.key"):
                    assert store.private(name) not in central_snapshot
                public[group] = {"startup": started, "mailbox_count": len(mails), "replay_requests": 10,
                    "default_delete_file_preserved": True, "audit": export,
                    "mailbox_snapshot_b64": base64.b64encode(snapshot).decode(), "mailbox_snapshot_sha256": sha256(snapshot),
                    "central_snapshot_b64": base64.b64encode(central_snapshot).decode(), "central_snapshot_sha256": sha256(central_snapshot),
                    "mails": [{"recipient": mail["recipient"], "mime_b64": base64.b64encode(mail["mime"]).decode(), "mime_sha256": mail["mime_sha256"]} for mail in mails]}
        finally:
            tools.close()
    return {"phase": "replay", "runtime": runtime(), "groups": public}


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in {"prepare", "replay"}:
        raise SystemExit("Choose prepare or replay")
    print(json.dumps(prepare() if sys.argv[1] == "prepare" else replay()))
