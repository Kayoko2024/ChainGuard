import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def root():
    return ROOT


@pytest.fixture(scope="session")
def protocol():
    return json.loads((ROOT / "spec/eip712.json").read_text())


@pytest.fixture(scope="session")
def vector():
    return json.loads((ROOT / "spec/vectors/eip712-v1.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def schemas():
    return json.loads((ROOT / "spec/schemas/protocol.schema.json").read_text(encoding="utf-8"))


@pytest.fixture
def validate(schemas):
    def check(name, value):
        Draft202012Validator({"$ref": f"#/$defs/{name}", "$defs": schemas["$defs"]}).validate(value)
    return check
