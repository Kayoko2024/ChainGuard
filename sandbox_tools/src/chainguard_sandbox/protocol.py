"""Validate the frozen primitive schemas without a new runtime dependency."""

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEFS = json.loads((ROOT / "spec/schemas/protocol.schema.json").read_text(encoding="utf-8"))["$defs"]
PARAM_TYPES = {"doc.read": "ReadParams", "mail.send": "MailParams", "doc.delete": "DeleteParams"}
SCOPES = {"doc.read": {"PUBLIC_DOCS", "ORG_A_DOCS"}, "mail.send": {"ORG_A_INTERNAL_MAIL"}, "doc.delete": {"ORG_A_DISPOSABLE_DOCS"}}


class ToolError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)  # Never expose paths, tokens or raw parameters.


def _validate(value, rule):
    if "$ref" in rule:
        return _validate(value, DEFS[rule["$ref"].rsplit("/", 1)[1]])
    kind = rule["type"]
    valid = {"object": type(value) is dict, "array": type(value) is list,
             "string": type(value) is str, "integer": type(value) is int,
             "boolean": type(value) is bool}[kind]
    if not valid:
        raise ToolError("SCHEMA_INVALID")
    if "enum" in rule and value not in rule["enum"]:
        raise ToolError("SCHEMA_INVALID")
    if kind == "object":
        if not set(rule.get("required", ())) <= value.keys() or value.keys() - rule["properties"].keys():
            raise ToolError("SCHEMA_INVALID")
        for key, item in value.items():
            _validate(item, rule["properties"][key])
    elif kind in ("string", "array"):
        low, high = ("minLength", "maxLength") if kind == "string" else ("minItems", "maxItems")
        if len(value) < rule.get(low, 0) or len(value) > rule.get(high, 1 << 30):
            raise ToolError("SCHEMA_INVALID")
        if kind == "string":
            try:
                value.encode("utf-8", errors="strict")
            except UnicodeError:
                raise ToolError("SCHEMA_INVALID") from None
            if "pattern" in rule and re.search(rule["pattern"], value) is None:
                raise ToolError("SCHEMA_INVALID")
        else:
            for item in value:
                _validate(item, rule["items"])
            if rule.get("uniqueItems") and len(set(value)) != len(value):
                raise ToolError("SCHEMA_INVALID")


def identifier(value):
    _validate(value, DEFS["Bytes32"])
    return value


def document_id(value):
    _validate(value, DEFS["DocumentId"])
    return value


def params_for(tool_name, params):
    if type(tool_name) is not str or tool_name not in PARAM_TYPES:
        raise ToolError("UNKNOWN_TOOL")
    _validate(params, DEFS[PARAM_TYPES[tool_name]])
    # Detach from caller-owned mutable objects before checking or executing.
    return json.loads(json.dumps(params, ensure_ascii=False, allow_nan=False))


def request_hash(action_id, principal, tool_name, params):
    identifier(action_id)
    if type(principal) is not str or re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", principal) is None:
        raise ToolError("AUTH_REQUIRED")
    payload = {"action_id": action_id, "principal": principal, "tool_name": tool_name,
               "params": params_for(tool_name, params)}
    # ASCII schema keys and string-only parameter leaves. This is a local hash,
    # deliberately not the salted keccak params_commit from the EIP-712 protocol.
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()
