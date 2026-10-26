"""Record actual test outputs; no application/benchmark metrics are invented."""
import hashlib
import importlib.metadata
import json
import platform
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "results/phase0"


def main():
    suites = ET.parse(OUTPUT / "pytest.xml").findall(".//testsuite")
    totals = {name: sum(int(suite.get(name, 0)) for suite in suites) for name in ["tests", "failures", "errors", "skipped"]}
    hardhat = (OUTPUT / "hardhat.txt").read_text(encoding="utf-8-sig")
    match = re.search(r"\b(\d+) passing", hardhat)
    if not suites or totals["failures"] or totals["errors"] or not match or re.search(r"\b[1-9][0-9]* failing", hardhat):
        raise SystemExit("Refusing to report successful acceptance without successful test outputs")
    baseline = json.loads((ROOT / "spec/baseline.json").read_text(encoding="utf-8"))
    report = {
        "stage": 0,
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": baseline["scope"],
        "design_sha256": baseline["design_sha256"],
        "environment": {"python": sys.version.split()[0], "node": subprocess.check_output(["node", "--version"], text=True).strip(), "platform": platform.platform(), "python_packages": {name: importlib.metadata.version(name) for name in ["pytest", "eth-account", "eth-abi", "jsonschema", "rfc8785", "openapi-spec-validator"]}, "hardhat": json.loads((ROOT / "node_modules/hardhat/package.json").read_text())["version"], "solc": json.loads((ROOT / "node_modules/solc/package.json").read_text())["version"]},
        "python": {**totals, "passed": totals["tests"] - totals["failures"] - totals["errors"] - totals["skipped"]},
        "hardhat": {"passed": int(match.group(1)), "network": "local Hardhat EVM", "business_contracts": "NOT_IMPLEMENTED", "besu": "NOT_DEPLOYED"},
        "commands": [".venv/Scripts/python.exe scripts/build_specs.py --check", ".venv/Scripts/python.exe -m pytest tests/python -q --junitxml results/phase0/pytest.xml", "npm.cmd test", ".venv/Scripts/python.exe -m pip check"],
        "evidence_sha256": {name: hashlib.sha256((OUTPUT / name).read_bytes()).hexdigest() for name in ["pytest.xml", "pytest.txt", "hardhat.txt"]},
        "golden_vector_sha256": hashlib.sha256((ROOT / "spec/vectors/eip712-v1.json").read_bytes()).hexdigest(),
        "application_metrics": "NOT_MEASURED",
        "next_stage": "AWAITING_USER_ACCEPTANCE_AND_SCOPE",
    }
    (OUTPUT / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Actual acceptance results: Python {report['python']['passed']} passed; Solidity {report['hardhat']['passed']} passed")


if __name__ == "__main__":
    main()
