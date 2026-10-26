"""Strict JSON ingestion and RFC8785 serialization for all gateway requests."""

import json
from pathlib import Path

from jsonschema import Draft202012Validator
import rfc8785

from chainguard_sandbox.protocol import ToolError

ROOT = Path(__file__).resolve().parents[3]
DEFS = json.loads((ROOT / "spec/schemas/protocol.schema.json").read_text(encoding="utf-8"))["$defs"]
ERRORS = json.loads((ROOT / "spec/errors.json").read_text())


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ToolError("SCHEMA_INVALID")
        result[key] = value
    return result


def _reject(*args):
    raise ToolError("SCHEMA_INVALID")


def _integer(value):
    parsed = int(value)
    if abs(parsed) > 9007199254740991:
        raise ToolError("SCHEMA_INVALID")
    return parsed


def canonical(value):
    # Never permit floats, even 1.0, or booleans as integer alternatives.
    if isinstance(value, float):
        raise ToolError("SCHEMA_INVALID")
    if isinstance(value, dict):
        for item in value.values():
            canonical(item)
    elif isinstance(value, list):
        for item in value:
            canonical(item)
    try:
        return rfc8785.dumps(value)
    except (ValueError, TypeError, UnicodeError):
        raise ToolError("SCHEMA_INVALID") from None


def parse_json(data):
    if not data or len(data) > 65536:
        raise ToolError("SCHEMA_INVALID")
    try:
        value = json.loads(data.decode("utf-8", errors="strict"), object_pairs_hook=_object,
                           parse_int=_integer, parse_float=_reject, parse_constant=_reject)
        canonical(value)
        return value
    except (ValueError, UnicodeError, RecursionError):
        raise ToolError("SCHEMA_INVALID") from None


def validate(name, value):
    canonical(value)
    validator = Draft202012Validator({"$ref": f"#/$defs/{name}", "$defs": DEFS})
    if not validator.is_valid(value):
        raise ToolError("SCHEMA_INVALID")
    return value
