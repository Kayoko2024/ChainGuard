"""Executable validation for the additive central record and ActionTrace DTOs."""

import json
from jsonschema import Draft202012Validator

from .canonical import DEFS, ROOT
from chainguard_sandbox.protocol import ToolError

SCHEMAS = json.loads(json.dumps(DEFS).replace("#/$defs/", "#/components/schemas/"))
SCHEMAS.update(json.loads((ROOT / "spec/central/schemas.json").read_text()))


def validate_central(name, value):
    if not Draft202012Validator({"components": {"schemas": SCHEMAS}, "$ref": "#/components/schemas/" + name}).is_valid(value):
        raise ToolError("SCHEMA_INVALID")
    return value
