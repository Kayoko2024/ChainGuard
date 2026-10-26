"""Verify independently exported artifacts; never execute file tools on the host."""

import base64
from email import policy
from email.parser import BytesParser
import hashlib
import json
import secrets
import sqlite3
import subprocess


def run(prefix, output, restricted_run):
    volume = "chainguard-phase2-test-" + secrets.token_hex(12)
    created = subprocess.run(prefix + ["volume", "create", "--label", "chainguard.purpose=phase2-disposable-test", volume],
                             capture_output=True, timeout=30)
    if created.returncode:
        raise RuntimeError("Could not create the unique test volume")
    try:
        phases = []
        for phase in ("prepare", "replay"):
            result = restricted_run(prefix, ["python", "scripts/phase2_evidence.py", phase], volume=volume)
            (output / f"container-{phase}.stderr.txt").write_bytes(result.stderr)
            if result.returncode:
                raise RuntimeError(f"Real container {phase} failed: {result.stderr.decode(errors='replace')}")
            phases.append(json.loads(result.stdout))
        first, second = phases
        assert first["runtime"]["hostname"] != second["runtime"]["hostname"]
        for evidence in phases:
            runtime = evidence["runtime"]
            assert runtime["uid"] == 10001 and runtime["root_read_only"] is True
            assert int(runtime["cap_eff"], 16) == 0 and runtime["interfaces"] == ["lo"]
        snapshot = base64.b64decode(second.pop("snapshot_b64"))
        assert hashlib.sha256(snapshot).hexdigest() == second["snapshot_sha256"]
        mime = base64.b64decode(second.pop("mime_b64"))
        assert hashlib.sha256(mime).hexdigest() == first["mime_sha256"]
        source = base64.b64decode(first["source_content_b64"])
        assert hashlib.sha256(source).hexdigest() == first["source_sha256"]
        message = BytesParser(policy=policy.default).parsebytes(mime)
        assert message["To"] == "evidence@inbox.chainguard.invalid"
        assert message.get_content().strip() == "Read SHA-256: " + first["source_sha256"]
        (output / "mail.eml").write_bytes(mime)
        (output / "execution-snapshot.sqlite3").write_bytes(snapshot)
        # Independent host SQLite reader verifies durable actual mailbox and journal.
        db = sqlite3.connect((output / "execution-snapshot.sqlite3").as_uri() + "?mode=ro", uri=True)
        try:
            assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            assert db.execute("SELECT count(*) FROM mailbox").fetchone()[0] == 1
            assert db.execute("SELECT count(*) FROM executions WHERE state='COMPLETED'").fetchone()[0] == 3
            assert db.execute("SELECT mime FROM mailbox").fetchone()[0] == mime
            records = {row[0]: json.loads(row[1]) for row in db.execute("SELECT action_id,result_json FROM executions")}
            for record in first["actions"]:
                assert records[record["action_id"]] == record["result"]
        finally:
            db.close()
        report = {"status": "PASS", "authorization": "LOCAL_TEST_PERMIT_ONLY", "prepare": first, "replay": second,
                  "independent_snapshot_verification": "PASS", "no_host_directory_mounts": True,
                  "actual_test_volume": volume,
                  "context_sha256": json.loads((output / "build-context.json").read_text())["sha256"]}
    finally:
        removed = subprocess.run(prefix + ["volume", "rm", volume], capture_output=True, timeout=30)
        if removed.returncode:
            raise RuntimeError("Own disposable test volume cleanup failed")
    report["test_volume_removed"] = True
    (output / "side-effects.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Real side effects PASS: source read verified, 1 MIME message, test file unlinked; new container replayed 30 calls with 0 new effects. SQLite snapshot independently verified; own test volume removed.")
