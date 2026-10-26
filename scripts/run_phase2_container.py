"""Run real sandbox operations only in restricted, networkless containers."""

import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import secrets
import subprocess
import tarfile

from check_environment import docker_prefix

ROOT = Path(__file__).resolve().parents[1]
IMAGE = "chainguard/sandbox-tools:0.2.0"


def context_archive():
    names = {"sandbox_tools/Dockerfile", "spec/schemas/protocol.schema.json"}
    for directory in ("sandbox_tools/src", "sandbox_tools/tests"):
        names.update(path.relative_to(ROOT).as_posix() for path in (ROOT / directory).rglob("*.py"))
    evidence = ROOT / "scripts/phase2_evidence.py"
    if evidence.exists():
        names.add("scripts/phase2_evidence.py")
    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode="w") as archive:
        for name in sorted(names):
            path = ROOT / name
            if path.is_symlink() or not path.resolve().is_relative_to(ROOT):
                raise ValueError("Unsafe build source")
            content = path.read_bytes()
            entry = tarfile.TarInfo(name)
            entry.size, entry.mode, entry.mtime = len(content), 0o644, 0
            archive.addfile(entry, io.BytesIO(content))
    return data.getvalue(), sorted(names)


def restricted_run(prefix, command, *, volume=None):
    name = "chainguard-phase2-" + secrets.token_hex(12)
    args = prefix + ["run", "--rm", "--name", name, "--read-only", "--network", "none",
                     "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true",
                     "--pids-limit", "128", "--memory", "256m", "--cpus", "1",
                     "--tmpfs", "/tmp:rw,noexec,nosuid,size=16m"]
    if volume:
        args += ["--mount", f"type=volume,src={volume},dst=/sandbox"]
    else:
        args += ["--tmpfs", "/sandbox:rw,noexec,nosuid,size=32m,mode=0700,uid=10001,gid=10001"]
    try:
        return subprocess.run(args + [IMAGE] + command, capture_output=True, timeout=180)
    finally:
        # Only this invocation's unguessable container name; never host files.
        subprocess.run(prefix + ["rm", "--force", name], capture_output=True, timeout=30)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--wsl-distro")
    parser.add_argument("--suite", choices=["resources", "tools", "evidence"], default="resources")
    args = parser.parse_args()
    prefix = docker_prefix(args.wsl_distro, "root")
    if not prefix:
        raise SystemExit("A working Docker backend is required; no host-side deletion fallback")
    output = ROOT / "results/phase2"
    output.mkdir(parents=True, exist_ok=True)
    archive, names = context_archive()
    build = subprocess.run(prefix + ["build", "--network", "none", "--file", "sandbox_tools/Dockerfile", "--tag", IMAGE, "-"],
                           input=archive, capture_output=True, timeout=180)
    (output / "build.log").write_bytes(build.stdout + build.stderr)
    if build.returncode:
        raise SystemExit("Sandbox image build failed; see results/phase2/build.log")
    (output / "build-context.json").write_text(json.dumps({"sha256": hashlib.sha256(archive).hexdigest(), "files": names}, indent=2) + "\n")
    if args.suite == "evidence":
        evidence_run(prefix, output)
        return
    result = restricted_run(prefix, ["python", "-m", "unittest", "discover", "-s", "sandbox_tools/tests",
                                     "-p", f"test_{args.suite}.py", "-v"])
    log = result.stdout + result.stderr
    (output / f"{args.suite}.txt").write_bytes(log)
    match = re.search(rb"Ran (\d+) tests? in", log)
    if result.returncode or not match or b"\nOK\n" not in log:
        import sys
        sys.stdout.buffer.write(log[-8000:])
        raise SystemExit(f"Actual container {args.suite} tests failed")
    print(f"Actual restricted sandbox {args.suite}: {int(match[1])} tests PASS; complete raw log saved.")
    report = {"suite": args.suite, "tests": int(match[1]), "exit_code": result.returncode,
              "network": "none", "root_read_only": True, "user": "10001:10001", "host_mounts": [],
              "context_sha256": hashlib.sha256(archive).hexdigest()}
    (output / f"{args.suite}.json").write_text(json.dumps(report, indent=2) + "\n")


def evidence_run(prefix, output):
    from phase2_evidence_host import run
    run(prefix, output, restricted_run)


if __name__ == "__main__":
    main()
