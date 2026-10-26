"""Derive acceptance from actual logs and startup results, with source fingerprints."""
import argparse
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "results/phase1"
sys.path.insert(0, str(ROOT / "gateway/src"))
from chainguard_gateway.integrity import check_frozen_protocol


def read(name):
    return json.loads((OUTPUT / name).read_text(encoding="utf-8-sig"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--include-compose", action="store_true")
    args = parser.parse_args()
    suites = ET.parse(OUTPUT / "pytest.xml").findall(".//testsuite")
    totals = {name: sum(int(suite.get(name, 0)) for suite in suites) for name in ["tests", "failures", "errors", "skipped"]}
    hardhat = (OUTPUT / "hardhat.txt").read_text(encoding="utf-8-sig")
    matched = re.search(r"\b(\d+) passing", hardhat)
    environment = read("environment.json")
    local = read("startup-local.json")
    compose = read("startup-compose.json") if args.include_compose else {"status": "NOT_RUN_IN_THIS_CHECK"}
    if not suites or not matched or totals["failures"] or totals["errors"] or environment["local_status"] != "PASS" or local["status"] != "PASS":
        raise SystemExit("Cannot report successful acceptance: local evidence failed")
    if args.include_compose and (compose["status"] != "PASS" or environment["container_environment"]["status"] != "PASS"):
        raise SystemExit("Cannot report full acceptance: real container checks failed")
    source_files = [p for p in ROOT.iterdir() if p.is_file() and p.name not in {".env"}]
    for directory in ["gateway", "contracts", "spec", "config", "scripts", "tests", "docs", "agent", "sandbox_tools", "evaluation", "dashboard"]:
        source_files.extend(p for p in (ROOT / directory).rglob("*") if p.is_file() and not any(part in {"__pycache__", "node_modules"} or part.endswith(".egg-info") for part in p.parts))
    manifest = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(source_files)}
    manifest_path = OUTPUT / "source-manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    evidence = ["pytest.xml", "pytest.txt", "hardhat.txt", "environment.json", "startup-local.json", "source-manifest.json"]
    if args.include_compose:
        evidence.extend(["startup-compose.json", "compose-startup.log"])
    report = {
        "stage": 1, "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "Monorepo, locked environments and health endpoints only",
        "acceptance": "FULL_PHASE1_PASS" if args.include_compose else "LOCAL_CHECKS_PASS",
        "frozen_phase0_files_unchanged": check_frozen_protocol(ROOT),
        "python": {**totals, "passed": totals["tests"] - totals["failures"] - totals["errors"] - totals["skipped"]},
        "hardhat": {"passed": int(matched.group(1)), "business_contracts": "TODO"},
        "local_startup": local["status"], "compose_startup": compose["status"],
        "environment": {"local": environment["local_status"], "container": environment["container_environment"]},
        "toolchain": json.loads((ROOT / "config/toolchain.json").read_text()),
        "evidence_sha256": {name: hashlib.sha256((OUTPUT / name).read_bytes()).hexdigest() for name in evidence},
        "business_implementation": "TODO", "agent": "TODO", "besu_qbft": "TODO", "application_metrics": "NOT_MEASURED",
        "next_stage": "AWAITING_USER_ACCEPTANCE_AND_SCOPE",
    }
    (OUTPUT / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Phase 1 evidence recorded: {report['acceptance']}; Python {report['python']['passed']}; Hardhat {report['hardhat']['passed']}")


if __name__ == "__main__":
    main()
