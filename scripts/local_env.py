"""Load the deliberately small phase 1 env template; never evaluate shell syntax."""
import os
from pathlib import Path

ALLOWED_KEYS = {
    "COMPOSE_PROJECT_NAME", "CHG_APP_ENV", "CHG_HOST", "CHG_PORT", "CHG_LOG_LEVEL",
    "CHG_SHUTDOWN_TIMEOUT", "CHG_PYTHON_IMAGE",
}


def parse_env(path: Path) -> dict[str, str]:
    values = {}
    for number, raw in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator or key not in ALLOWED_KEYS or key in values or not value:
            raise ValueError(f"Invalid/duplicate phase 1 env entry at line {number}")
        if any(character in value for character in ["'", '"', "`", "$", "\x00"]):
            raise ValueError(f"Unsupported env interpolation/quoting at line {number}")
        values[key] = value
    return values


def load_env(path: Path):
    if path.exists():
        for key, value in parse_env(path).items():
            os.environ.setdefault(key, value)
