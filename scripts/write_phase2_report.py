"""Derive the acceptance result from actual logs, artifacts and frozen hashes."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "results/phase2"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    frozen = json.loads((ROOT / "config/phase0-freeze.json").read_text())
    for name, expected in frozen["files"].items():
        if digest(ROOT / name) != expected:
            raise SystemExit(f"Frozen file changed: {name}")
    xml = ET.parse(OUTPUT / "pytest.xml").getroot()
    cases = xml.findall(".//testcase")
    if not cases or any(case.find(tag) is not None for case in cases for tag in ("failure", "error", "skipped")):
        raise SystemExit("Host pytest evidence is missing or failed")
    hardhat = re.search(r"(\d+) passing", (OUTPUT / "hardhat.txt").read_text(encoding="utf-8-sig"))
    if not hardhat or int(hardhat[1]) != 41:
        raise SystemExit("Original Hardhat evidence is missing or changed")
    suites = [json.loads((OUTPUT / f"{name}.json").read_text()) for name in ("resources", "tools")]
    effects = json.loads((OUTPUT / "side-effects.json").read_text(encoding="utf-8"))
    context = json.loads((OUTPUT / "build-context.json").read_text())
    if any(suite["exit_code"] or suite["context_sha256"] != context["sha256"] for suite in suites):
        raise SystemExit("Container suite failed or used a different source context")
    if effects["status"] != "PASS" or not effects["test_volume_removed"] or effects["context_sha256"] != context["sha256"]:
        raise SystemExit("Real side effects or cleanup were not verified")
    if digest(OUTPUT / "execution-snapshot.sqlite3") != effects["replay"]["snapshot_sha256"]:
        raise SystemExit("SQLite snapshot differs from actual container export")
    if digest(OUTPUT / "mail.eml") != effects["prepare"]["mime_sha256"]:
        raise SystemExit("MIME message differs from actual mailbox")
    sources = set(frozen["files"]) | {"pyproject.toml", "README.md", "sandbox_tools/README.md", "sandbox_tools/Dockerfile"}
    for directory in ("sandbox_tools/src", "sandbox_tools/tests"):
        sources.update(path.relative_to(ROOT).as_posix() for path in (ROOT / directory).rglob("*.py"))
    sources.update(path.relative_to(ROOT).as_posix() for path in (ROOT / "scripts").glob("*phase2*"))
    sources.update(path.relative_to(ROOT).as_posix() for path in (ROOT / "docs").glob("phase2*.md"))
    manifest = {name: digest(ROOT / name) for name in sorted(sources)}
    (OUTPUT / "source-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    evidence = ["pytest.xml", "pytest.txt", "hardhat.txt", "resources.txt", "resources.json", "tools.txt", "tools.json",
                "side-effects.json", "execution-snapshot.sqlite3", "mail.eml", "build-context.json", "source-manifest.json"]
    report = {"stage": 2, "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
              "acceptance": "PHASE2_LOCAL_TOOLS_PASS", "frozen_files_unchanged": len(frozen["files"]),
              "host_pytest": {"passed": len(cases), "failures": 0, "skipped": 0},
              "hardhat": {"passed": int(hardhat[1])},
              "container_tests": {entry["suite"]: entry["tests"] for entry in suites},
              "actual_side_effects": {"mailbox_messages": effects["replay"]["mailbox_after"],
                                      "persistent_execution_records": effects["replay"]["execution_records"],
                                      "replay_after_container_restart": effects["replay"]["replay_requests"],
                                      "new_effects_on_replay": 0, "test_file_deleted": effects["replay"]["delete_still_absent"]},
              "authorization": "LOCAL_TEST_PERMIT_ONLY", "production_chain_execution": "BLOCKED_CHAIN_UNAVAILABLE",
              "eip712_execution_receipts": "TODO", "evidence_sha256": {name: digest(OUTPUT / name) for name in evidence},
              "next_stage": "AWAITING_USER_ACCEPTANCE_AND_SCOPE"}
    (OUTPUT / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Phase 2 evidence recorded: {report['acceptance']}; host {len(cases)}, Hardhat {hardhat[1]}, container {sum(s['tests'] for s in suites)}")


if __name__ == "__main__":
    main()
