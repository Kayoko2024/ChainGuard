"""Download only pinned Linux wheels; normal runs never revise dependency locks."""

import argparse
import hashlib
import importlib.metadata as metadata
import json
from pathlib import Path
import subprocess
import sys

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "gateway/central-test.lock"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-lock", action="store_true")
    args = parser.parse_args()
    if args.write_lock:
        if LOCK.exists():
            raise SystemExit("Test lock already exists; explicit review required to change")
        pending = [Requirement(line) for line in (ROOT / "gateway/requirements.lock").read_text().splitlines()
                   if line and not line.startswith("#")] + [Requirement("pytest==8.4.2"), Requirement("httpx==0.28.1")]
        locked = {}
        while pending:
            requirement = pending.pop()
            if requirement.marker and not requirement.marker.evaluate({"extra": "", "sys_platform": "linux", "platform_system": "Linux", "os_name": "posix"}):
                continue
            name = canonicalize_name(requirement.name)
            if name in locked:
                continue
            version = metadata.version(name)
            if not requirement.specifier.contains(version):
                raise SystemExit(f"Installed lock source mismatch: {name}")
            locked[name] = version
            pending.extend(Requirement(value) for value in metadata.requires(name) or [])
        LOCK.write_text("# Exact Linux central lab/test dependency closure.\n" + "\n".join(f"{k}=={v}" for k, v in sorted(locked.items())) + "\n")
    destination = ROOT / ".local/phase3-wheels"
    destination.mkdir(parents=True, exist_ok=True)
    output = ROOT / "results/phase3"
    output.mkdir(parents=True, exist_ok=True)
    with (output / "wheel-download.log").open("wb") as log:
        completed = subprocess.run([sys.executable, "-m", "pip", "download", "--no-deps", "--only-binary=:all:",
            "--platform", "manylinux2014_x86_64", "--python-version", "314", "--implementation", "cp", "--abi", "cp314",
            "--dest", str(destination), "-r", str(LOCK)], stdout=log, stderr=subprocess.STDOUT, timeout=300)
    if completed.returncode:
        raise SystemExit("Pinned Linux wheel download failed; see results/phase3/wheel-download.log")
    manifest = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(destination.glob("*.whl"))}
    (output / "wheels.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Pinned Linux wheels ready: {len(manifest)}; source lock {LOCK.name}")


if __name__ == "__main__":
    main()
