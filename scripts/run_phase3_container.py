"""Offline build and real, restricted A/B gateway integration tests."""

import argparse
import hashlib
import io
import json
from pathlib import Path
import secrets
import subprocess
import tarfile

from check_environment import docker_prefix

ROOT = Path(__file__).resolve().parents[1]
IMAGE = "chainguard/central-lab:0.3.0"


def context_archive():
    frozen = json.loads((ROOT / "config/phase0-freeze.json").read_text())
    names = set(frozen["files"]) | {"gateway/central.Dockerfile", "gateway/central-test.lock", "config/phase0-freeze.json", "config/phase3-policy-freeze.json"}
    for directory in ("gateway/src", "gateway/integration", "sandbox_tools/src", "sandbox_tools/tests"):
        names.update(path.relative_to(ROOT).as_posix() for path in (ROOT / directory).rglob("*.py"))
    names.add("spec/central/schemas.json")
    files = {name: ROOT / name for name in names}
    wheels = json.loads((ROOT / "results/phase3/wheels.json").read_text())
    for name, expected in wheels.items():
        source = ROOT / ".local/phase3-wheels" / name
        if not name.endswith(".whl") or "/" in name or "\\" in name or hashlib.sha256(source.read_bytes()).hexdigest() != expected:
            raise ValueError("Wheel cache integrity mismatch")
        files["wheelhouse/" + name] = source
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w") as tar:
        for name, source in sorted(files.items()):
            if source.is_symlink() or not source.resolve().is_relative_to(ROOT):
                raise ValueError("Unsafe build source")
            content = source.read_bytes()
            item = tarfile.TarInfo(name)
            item.mode, item.mtime, item.size = 0o644, 0, len(content)
            tar.addfile(item, io.BytesIO(content))
    return archive.getvalue(), sorted(files)


def run_restricted(prefix, command, *, volume=None):
    name = "chainguard-phase3-" + secrets.token_hex(12)
    args = prefix + ["run", "--rm", "--name", name, "--read-only", "--network", "none", "--cap-drop", "ALL",
                     "--security-opt", "no-new-privileges:true", "--pids-limit", "128", "--memory", "512m", "--cpus", "2",
                     "--tmpfs", "/tmp:rw,noexec,nosuid,size=32m"]
    args += ["--mount", f"type=volume,src={volume},dst=/sandbox"] if volume else ["--tmpfs", "/sandbox:rw,noexec,nosuid,size=64m,mode=0700,uid=10001,gid=10001"]
    try:
        return subprocess.run(args + [IMAGE] + command, capture_output=True, timeout=300)
    finally:
        subprocess.run(prefix + ["rm", "--force", name], capture_output=True, timeout=30)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--wsl-distro")
    parser.add_argument("--evidence", action="store_true")
    args = parser.parse_args()
    prefix = docker_prefix(args.wsl_distro, "root")
    if not prefix:
        raise SystemExit("Working Docker required; no host tool fallback")
    output = ROOT / "results/phase3"
    output.mkdir(parents=True, exist_ok=True)
    archive, names = context_archive()
    with (output / "build.log").open("wb") as log:
        build = subprocess.run(prefix + ["build", "--network", "none", "--file", "gateway/central.Dockerfile", "--tag", IMAGE, "-"],
                               input=archive, stdout=log, stderr=subprocess.STDOUT, timeout=300)
    if build.returncode:
        raise SystemExit("Offline image build failed; see results/phase3/build.log")
    manifest = {"sha256": hashlib.sha256(archive).hexdigest(), "files": names}
    (output / "build-context.json").write_text(json.dumps(manifest, indent=2) + "\n")
    if args.evidence:
        from phase3_evidence_host import run
        run(prefix, output, run_restricted)
        return
    result = run_restricted(prefix, ["python", "gateway/integration/run_tests.py"])
    (output / "integration.txt").write_bytes(result.stdout + result.stderr)
    if result.returncode:
        # Preserve complete test output without printing bearer or private fixture files.
        import sys
        sys.stdout.buffer.write((result.stdout + result.stderr)[-8000:])
        raise SystemExit("Actual gateway/tool integration tests failed")
    data = json.loads(result.stdout)
    import base64
    (output / "integration.xml").write_bytes(base64.b64decode(data.pop("junit_b64")))
    data["context_sha256"] = manifest["sha256"]
    (output / "integration.json").write_text(json.dumps(data, indent=2) + "\n")
    print(f"Restricted real central API/tool integration PASS: {data['tests']} tests; uid={data['uid']}, network={data['interfaces']}")


if __name__ == "__main__":
    main()
