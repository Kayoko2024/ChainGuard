"""Read actual tool/package/Engine versions and emit a stage 1 preflight report."""
import argparse
import importlib.metadata as metadata
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.version import Version

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "gateway/src"))
from chainguard_gateway.integrity import check_frozen_protocol


def run(command, timeout=30):
    try:
        completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
        return completed.returncode, completed.stdout.strip(), completed.stderr.strip()
    except (OSError, subprocess.TimeoutExpired) as error:
        return 127, "", type(error).__name__


def docker_prefix(distro=None, user="root"):
    if distro:
        return ["wsl.exe", "-d", distro, "-u", user, "--", "docker"]
    return ["docker"] if shutil.which("docker") else None


def project_path(path, wsl=False):
    value = str(path.resolve())
    if wsl and os.name == "nt":
        return "/mnt/" + value[0].lower() + "/" + value[3:].replace("\\", "/")
    return value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-docker", action="store_true")
    parser.add_argument("--wsl-distro")
    parser.add_argument("--wsl-user", default="root")
    args = parser.parse_args()
    toolchain = json.loads((ROOT / "config/toolchain.json").read_text())
    report = {"recorded_at_utc": datetime.now(timezone.utc).isoformat(), "platform": platform.platform(), "python": platform.python_version(), "tools": {}, "packages": {}, "checks": {}}
    report["checks"]["python_version"] = report["python"] == toolchain["tested_python"]
    for name, command, expected in [("node", ["node", "--version"], "v" + toolchain["tested_node"]), ("npm", ["npm.cmd" if os.name == "nt" else "npm", "--version"], toolchain["tested_npm"]), ("git", ["git", "rev-parse", "--is-inside-work-tree"], "true")]:
        code, stdout, stderr = run(command)
        report["tools"][name] = {"exit_code": code, "value": stdout if code == 0 else stderr}
        report["checks"][name] = code == 0 and stdout == expected
    for line in (ROOT / "requirements-dev.lock").read_text(encoding="utf-8-sig").splitlines():
        if not line or line.startswith("#"):
            continue
        requirement = Requirement(line)
        try:
            installed = metadata.distribution(requirement.name)
            python_requirement = installed.metadata.get("Requires-Python", "")
            valid = requirement.specifier.contains(installed.version) and (not python_requirement or SpecifierSet(python_requirement).contains(report["python"]))
            report["packages"][requirement.name] = {"version": installed.version, "lock_match": valid, "requires_python": python_requirement}
        except metadata.PackageNotFoundError:
            valid = False
            report["packages"][requirement.name] = {"status": "MISSING"}
        report["checks"]["package:" + requirement.name] = valid
    for name, expected in json.loads((ROOT / "package.json").read_text())["devDependencies"].items():
        path = ROOT / "node_modules" / name / "package.json"
        installed = json.loads(path.read_text())["version"] if path.is_file() else None
        report["tools"][name] = installed
        report["checks"]["npm:" + name] = installed == expected
    report["frozen_files_checked"] = check_frozen_protocol(ROOT)
    code, stdout, stderr = run([sys.executable, "-m", "pip", "check"])
    report["pip_check"] = stdout or stderr
    report["checks"]["pip_check"] = code == 0
    prefix = docker_prefix(args.wsl_distro, args.wsl_user)
    container = {"status": "BLOCKED", "reason": "Docker CLI unavailable; local checks do not imply container startup", "backend": args.wsl_distro or "native"}
    if prefix:
        code, stdout, stderr = run(prefix + ["version", "--format", "{{json .}}"])
        if code == 0:
            versions = json.loads(stdout)
            engine = versions["Server"]["Version"]
            compose_code, compose, _ = run(prefix + ["compose", "version", "--short"])
            buildx_code, buildx, _ = run(prefix + ["buildx", "version"])
            config_code, config_stdout, config_error = run(prefix + ["compose", "--project-directory", project_path(ROOT, bool(args.wsl_distro)), "-f", project_path(ROOT / "compose.yaml", bool(args.wsl_distro)), "config", "--quiet"])
            compose_match = re.match(r"v?(\d+\.\d+\.\d+)", compose)
            valid = Version(engine) >= Version(toolchain["docker_engine_minimum"]) and compose_code == 0 and bool(compose_match) and Version(compose_match.group(1)) >= Version(toolchain["docker_compose_minimum"]) and buildx_code == 0 and config_code == 0
            container = {"status": "PASS" if valid else "FAIL", "backend": args.wsl_distro or "native", "engine": engine, "compose": compose, "buildx": buildx, "compose_config_exit_code": config_code}
            if config_code:
                container["compose_config_error"] = config_error or config_stdout
        else:
            container["reason"] = "Docker Engine query failed"
            container["exit_code"] = code
    report["local_status"] = "PASS" if all(report["checks"].values()) else "FAIL"
    report["container_environment"] = container
    output = ROOT / "results/phase1/environment.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Local environment: {report['local_status']}; Docker/Compose environment: {container['status']}")
    raise SystemExit(0 if report["local_status"] == "PASS" and (not args.require_docker or container["status"] == "PASS") else 1)


if __name__ == "__main__":
    main()
