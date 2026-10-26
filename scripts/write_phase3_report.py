"""Validate all current evidence and derive an honest stage 3 acceptance report."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "gateway/src"), str(ROOT / "sandbox_tools/src")]
from chainguard_gateway.policy import check_policy_freeze
from chainguard_gateway.integrity import check_frozen_protocol
from run_phase3_container import context_archive

OUT = ROOT / "results/phase3"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def successful_cases(path):
    root = ET.parse(path).getroot()
    cases = root.findall(".//testcase")
    if not cases or any(case.find(tag) is not None for case in cases for tag in ("error", "failure", "skipped")):
        raise SystemExit("Missing, skipped or failed JUnit evidence: " + path.name)
    return len(cases)


def main():
    unchanged = check_frozen_protocol(ROOT)
    policy_hash = check_policy_freeze()
    host_count = successful_cases(OUT / "pytest.xml")
    integration_count = successful_cases(OUT / "integration.xml")
    hardhat = re.search(r"(\d+) passing", (OUT / "hardhat.txt").read_text(encoding="utf-8-sig"))
    if not hardhat or int(hardhat[1]) != 41:
        raise SystemExit("Original contract/golden vector evidence missing")
    integration = json.loads((OUT / "integration.json").read_text())
    actual = json.loads((OUT / "http-side-effects.json").read_text(encoding="utf-8"))
    context = json.loads((OUT / "build-context.json").read_text())
    current, _ = context_archive()
    if (actual["status"] != "PASS" or not actual["test_volume_removed"] or integration["tests"] != integration_count
            or integration["context_sha256"] != context["sha256"] or actual["context_sha256"] != context["sha256"]
            or hashlib.sha256(current).hexdigest() != context["sha256"]):
        raise SystemExit("Real container evidence is failed or stale for current sources")
    for phase in ("prepare", "replay"):
        for group in ("A", "B"):
            data = actual[phase]["groups"][group]
            if data["audit"]["policy_fingerprint"] != policy_hash or not data["startup"]["shutdown"]["lifecycle_complete"]:
                raise SystemExit("Policy or real server lifecycle mismatch")
    regressions = {}
    for suite in ("resources", "tools"):
        source = ROOT / f"results/phase2/{suite}.json"
        result = json.loads(source.read_text())
        if result["exit_code"]:
            raise SystemExit("Sandbox regression failed")
        regressions[suite] = result["tests"]
        (OUT / ("sandbox-" + suite + ".json")).write_bytes(source.read_bytes())
        (OUT / ("sandbox-" + suite + ".txt")).write_bytes((ROOT / f"results/phase2/{suite}.txt").read_bytes())
    from run_phase2_container import context_archive as sandbox_context
    archived, _ = sandbox_context()
    if any(json.loads((OUT / f"sandbox-{suite}.json").read_text())["context_sha256"] != hashlib.sha256(archived).hexdigest() for suite in regressions):
        raise SystemExit("Sandbox regression used stale source context")
    names = {"README.md", "pyproject.toml", "requirements-dev.lock", "gateway/requirements.txt", "gateway/requirements.lock", "gateway/central-test.lock", "gateway/central.Dockerfile", "scripts/run_phase2_container.py"}
    for folder in ("gateway/src", "gateway/tests", "gateway/integration", "sandbox_tools/src"):
        names.update(path.relative_to(ROOT).as_posix() for path in (ROOT / folder).rglob("*.py"))
    for folder, pattern in (("scripts", "*phase3*"), ("docs", "phase3*.md"), ("spec/central", "*.json"), ("config", "phase3*.json")):
        names.update(path.relative_to(ROOT).as_posix() for path in (ROOT / folder).glob(pattern) if path.is_file())
    (OUT / "source-manifest.json").write_text(json.dumps({name: digest(ROOT / name) for name in sorted(names)}, indent=2) + "\n")
    files = [path for path in OUT.iterdir() if path.is_file() and path.name not in {"summary.json"} and not ".failed-" in path.name]
    groups = {}
    for group in ("A", "B"):
        before, after = actual["prepare"]["groups"][group], actual["replay"]["groups"][group]
        groups[group] = {"mailbox_count": after["mailbox_count"], "normal": before["normal_action"]["central_state"],
                         "task_scope_violation": before["unauthorized_action"]["central_state"],
                         "default_delete": before["default_delete_action"]["central_state"],
                         "replay_requests": after["replay_requests"], "new_mail_on_replay": after["mailbox_count"] - before["mailbox_count"]}
    total = host_count + int(hardhat[1]) + integration_count + sum(regressions.values())
    report = {"stage": 3, "recorded_at_utc": datetime.now(timezone.utc).isoformat(), "acceptance": "PHASE3_CENTRAL_AB_PASS",
              "tests": {"host_pytest": host_count, "hardhat": int(hardhat[1]), "central_container": integration_count,
                        "sandbox_regression": regressions, "total_passed": total, "failures": 0, "skipped": 0},
              "original_frozen_files_unchanged": unchanged, "shared_bc_policy_fingerprint": policy_hash,
              "actual_http_groups": groups, "b_audit": actual["independent_b_log_verification"],
              "independent_checkpoint_tail_truncation": actual["independent_tail_truncation_test"],
              "actual_linux_dependencies": integration["packages"], "pip_check": integration["pip_check"],
              "chain_transactions": "NOT_IMPLEMENTED", "execution_receipt": "TODO", "agent_model": "NOT_IMPLEMENTED",
              "evidence_sha256": {path.name: digest(path) for path in sorted(files)},
              "next_stage": "AWAITING_USER_ACCEPTANCE_AND_SCOPE"}
    (OUT / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Phase 3 evidence recorded: {report['acceptance']}; {total} tests passed; policy={policy_hash}")


if __name__ == "__main__":
    main()
