"""Freeze installed runtime dependency closure, including marker-appropriate extras.

This explicitly revises the lock; normal bootstrap installs the reviewed lock.
"""
import importlib.metadata as metadata
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[1]


def main():
    pending = [Requirement(line) for line in (ROOT / "gateway/requirements.txt").read_text().splitlines() if line and not line.startswith("#")]
    locked = {}
    while pending:
        requirement = pending.pop()
        if requirement.marker and not requirement.marker.evaluate({"extra": ""}):
            continue
        name = canonicalize_name(requirement.name)
        if name in locked:
            continue
        version = metadata.version(name)
        if not requirement.specifier.contains(version):
            raise SystemExit(f"Installed dependency mismatch: {name}")
        locked[name] = version
        pending.extend(Requirement(item) for item in metadata.requires(name) or [])
    output = "# Runtime dependency closure; generated in the tested Python environment.\n" + "\n".join(f"{name}=={locked[name]}" for name in sorted(locked)) + "\n"
    (ROOT / "gateway/requirements.lock").write_text(output, encoding="utf-8")
    development = {canonicalize_name(dist.metadata["Name"]): dist.version for dist in metadata.distributions() if canonicalize_name(dist.metadata["Name"]) not in {"pip", "chainguard-gateway"}}
    (ROOT / "requirements-dev.lock").write_text("# Development dependency lock; local editable project is installed separately.\n" + "\n".join(f"{name}=={development[name]}" for name in sorted(development)) + "\n", encoding="utf-8")
    print(f"Runtime dependency lock: {len(locked)} distributions")


if __name__ == "__main__":
    main()
