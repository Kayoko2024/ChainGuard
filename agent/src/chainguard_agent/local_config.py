"""Literal, allowlisted local model env loading; never eval or log credentials."""
import os
from pathlib import Path
import re

ALLOWED = {'CHAINGUARD_LLM_PROVIDER', 'CHAINGUARD_LLM_MODEL', 'CHAINGUARD_LLM_BASE_URL',
           'CHAINGUARD_LLM_API_KEY', 'CHAINGUARD_LLM_TIMEOUT_SECONDS'}


def load_local_env(path, environ=None):
    target = os.environ if environ is None else environ
    path = Path(path)
    if not path.exists():
        return False
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 32768:
        raise ValueError('Invalid local model env file')
    pending = {}
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        name, separator, value = line.partition('=')
        name, value = name.strip(), value.strip()
        if not separator or not re.fullmatch('[A-Z_]+', name) or name not in ALLOWED or name in pending:
            raise ValueError('Invalid/duplicate model env field; values are never evaluated')
        if value.startswith(('"', "'")):
            if len(value) < 2 or value[-1] != value[0]:
                raise ValueError('Unclosed env quote')
            value = value[1:-1]
        if any(x in value for x in ['\x00', '\r', '\n']):
            raise ValueError('Invalid env value')
        pending[name] = value
    for name, value in pending.items():
        target.setdefault(name, value)
    return True


def redact(value, secret):
    if isinstance(value, str):
        return value.replace(secret, '[REDACTED]') if secret else value
    if isinstance(value, list):
        return [redact(v, secret) for v in value]
    if isinstance(value, dict):
        return {k: '[REDACTED]' if k.lower() in {'authorization', 'api_key', 'chainguard_llm_api_key'} else redact(v, secret) for k, v in value.items()}
    return value
