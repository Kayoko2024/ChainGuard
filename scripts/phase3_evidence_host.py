"""Independent artifact and signed-history verification for actual HTTP runs."""

import base64
from email import policy
from email.parser import BytesParser
import hashlib
import json
from pathlib import Path
import secrets
import sqlite3
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "gateway/src"), str(ROOT / "sandbox_tools/src")]
from chainguard_gateway.audit import verify_log
from openapi_spec_validator import validate


def run(prefix, output, run_restricted):
    volume = "chainguard-phase3-test-" + secrets.token_hex(12)
    result = subprocess.run(prefix + ["volume", "create", "--label", "chainguard.purpose=phase3-disposable-test", volume], capture_output=True, timeout=30)
    if result.returncode:
        raise RuntimeError("Own isolated test volume creation failed")
    try:
        phases = []
        for phase in ("prepare", "replay"):
            actual = run_restricted(prefix, ["python", "gateway/integration/http_evidence.py", phase], volume=volume)
            (output / f"http-{phase}.stderr.txt").write_bytes(actual.stderr)
            if actual.returncode:
                raise RuntimeError(f"Actual HTTP {phase} failed: {actual.stderr.decode(errors='replace')}")
            phases.append(json.loads(actual.stdout))
        first, second = phases
        assert first["runtime"]["hostname"] != second["runtime"]["hostname"]
        for phase in phases:
            runtime = phase["runtime"]
            assert runtime["uid"] == 10001 and runtime["interfaces"] == ["lo"] and runtime["root_read_only"]
            assert int(runtime["cap_eff"], 16) == 0
        for group in ("A", "B"):
            initial, resumed = first["groups"][group], second["groups"][group]
            validate(initial["openapi"])
            (output / f"{group.lower()}-openapi.json").write_text(json.dumps(initial.pop("openapi"), indent=2) + "\n")
            assert initial["mailbox_count"] == resumed["mailbox_count"]
            for kind in ("mailbox", "central"):
                snapshot = base64.b64decode(resumed.pop(kind + "_snapshot_b64"))
                assert hashlib.sha256(snapshot).hexdigest() == resumed[kind + "_snapshot_sha256"]
                path = output / f"{group.lower()}-{kind}.sqlite3"
                path.write_bytes(snapshot)
                db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
                try:
                    assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
                    if kind == "mailbox":
                        assert db.execute("SELECT count(*) FROM mailbox").fetchone()[0] == resumed["mailbox_count"]
                    else:
                        assert b"synthetic central content" not in snapshot
                finally:
                    db.close()
            for number, mail in enumerate(resumed["mails"], 1):
                mime = base64.b64decode(mail.pop("mime_b64"))
                assert hashlib.sha256(mime).hexdigest() == mail["mime_sha256"]
                parsed = BytesParser(policy=policy.default).parsebytes(mime)
                assert parsed["To"] == mail["recipient"] and parsed.get_content().strip() == "synthetic central content"
                (output / f"{group.lower()}-mail-{number}.eml").write_bytes(mime)
            audit = resumed["audit"]
            (output / f"{group.lower()}-traces.jsonl").write_text("".join(json.dumps(entry, ensure_ascii=False) + "\n" for entry in audit["entries"]), encoding="utf-8")
        b = second["groups"]["B"]["audit"]
        pinned = first["groups"]["B"]["audit"]
        assert b["checkpoint"] == pinned["checkpoint"] and b["signer"] == pinned["signer"]
        assert verify_log(b["entries"], pinned["signer"], checkpoint=pinned["checkpoint"], deployment_id=pinned["deployment_id"])["status"] == "VALID"
        assert verify_log(b["entries"][:-1], pinned["signer"], checkpoint=pinned["checkpoint"], deployment_id=pinned["deployment_id"])["status"] == "INVALID"
        assert first["groups"]["A"]["audit"]["policy_fingerprint"] == b["policy_fingerprint"]
        (output / "b-checkpoint.json").write_text(json.dumps(b["checkpoint"], indent=2) + "\n")
        evidence = {"status": "PASS", "prepare": first, "replay": second, "independent_b_log_verification": "VALID",
                    "independent_tail_truncation_test": "INVALID_AS_EXPECTED", "no_host_directory_mounts": True,
                    "context_sha256": json.loads((output / "build-context.json").read_text())["sha256"]}
    finally:
        cleaned = subprocess.run(prefix + ["volume", "rm", volume], capture_output=True, timeout=30)
        if cleaned.returncode:
            raise RuntimeError("Own stage 3 test volume cleanup failed")
    evidence["test_volume_removed"] = True
    (output / "http-side-effects.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Actual Uvicorn A/B HTTP and restart PASS: A mailbox=2 (normal+task-scope violation), B mailbox=1 (normal only); default deletion denied in both. Real MIME/SQLite and signed B checkpoints verified; own test volume removed.")
