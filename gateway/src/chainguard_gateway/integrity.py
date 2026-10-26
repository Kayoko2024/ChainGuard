"""Accidental protocol drift detection, not an authorization/security trust root."""
import hashlib
import json
from pathlib import Path


class ProtocolIntegrityError(RuntimeError):
    """The local frozen protocol files are missing, unsafe or changed."""


def check_frozen_protocol(project_root: Path) -> int:
    root = project_root.resolve()
    manifest = json.loads((root / "config/phase0-freeze.json").read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or manifest.get("protocol_version") != "1.0.0" or not isinstance(manifest.get("files"), dict) or not manifest["files"]:
        raise ProtocolIntegrityError("Invalid protocol freeze manifest")
    for relative, expected in manifest["files"].items():
        if not isinstance(relative, str) or not isinstance(expected, str) or len(expected) != 64:
            raise ProtocolIntegrityError("Invalid protocol freeze entry")
        source = (root / relative).resolve()
        if not source.is_relative_to(root):
            raise ProtocolIntegrityError("Unsafe protocol manifest path")
        if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != expected:
            raise ProtocolIntegrityError("Frozen protocol file missing or changed")
    protocol = json.loads((root / "spec/eip712.json").read_text(encoding="utf-8"))
    if protocol.get("protocol_version") != "1.0.0" or protocol.get("schema_version") != 1:
        raise ProtocolIntegrityError("Unsupported protocol version")
    return len(manifest["files"])
