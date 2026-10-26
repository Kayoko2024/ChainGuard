"""Build from an allowlisted tar context across Windows/WSL without NTFS xattrs."""
import argparse
import hashlib
import io
import json
import subprocess
import tarfile
from pathlib import Path

from check_environment import docker_prefix
from local_env import parse_env

ROOT = Path(__file__).resolve().parents[1]


def create_build_context(root: Path, archive: Path):
    root = root.resolve()
    frozen = json.loads((root / "config/phase0-freeze.json").read_text(encoding="utf-8"))
    names = set(frozen["files"]) | {"config/phase0-freeze.json", "config/toolchain.json", "gateway/Dockerfile", "gateway/requirements.lock", ".dockerignore"}
    names.update(path.relative_to(root).as_posix() for path in (root / "gateway/src").rglob("*.py"))
    archive.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "w", format=tarfile.PAX_FORMAT) as context:
        for name in sorted(names):
            source = (root / name).resolve()
            if not source.is_relative_to(root) or not source.is_file():
                raise ValueError("Unsafe/missing allowlisted build source")
            content = source.read_bytes()
            item = tarfile.TarInfo(name)
            item.size = len(content)
            item.mode = 0o644
            item.mtime = 0
            context.addfile(item, io.BytesIO(content))
    return {"files": len(names), "sha256": hashlib.sha256(archive.read_bytes()).hexdigest()}


def build_image(prefix, log):
    archive = ROOT / ".local/gateway-context.tar"
    manifest = create_build_context(ROOT, archive)
    env_file = ROOT / (".env" if (ROOT / ".env").exists() else ".env.example")
    image = parse_env(env_file)["CHG_PYTHON_IMAGE"]
    if "@sha256:" not in image:
        raise ValueError("Base image must include its reviewed immutable digest")
    with archive.open("rb") as stream:
        completed = subprocess.run(prefix + ["build", "--file", "gateway/Dockerfile", "--tag", "chainguard/gateway:0.1.0", "--build-arg", "PYTHON_IMAGE=" + image, "-"], stdin=stream, stdout=log, stderr=subprocess.STDOUT, timeout=600)
    if completed.returncode:
        raise RuntimeError("Gateway image build failed; inspect the build log")
    destination = ROOT / "results/phase1/build-context.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--wsl-distro")
    parser.add_argument("--wsl-user", default="root")
    args = parser.parse_args()
    prefix = docker_prefix(args.wsl_distro, args.wsl_user)
    if not prefix:
        raise SystemExit("Docker CLI missing")
    log_path = ROOT / ".local/gateway-build.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as log:
        built = build_image(prefix, log)
    print(f"Actual gateway image built from {built['files']} allowlisted files; context sha256={built['sha256']}")


if __name__ == "__main__":
    main()
