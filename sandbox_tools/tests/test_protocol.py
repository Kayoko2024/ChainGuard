import copy
import os

import pytest
from jsonschema import Draft202012Validator

from chainguard_sandbox.protocol import DEFS, ToolError, params_for, request_hash


@pytest.mark.parametrize("tool,schema,params", [
    ("doc.read", "ReadParams", {"doc_id": "doc-public"}),
    ("doc.delete", "DeleteParams", {"doc_id": "doc-trash"}),
    ("mail.send", "MailParams", {"to": ["test@inbox.chainguard.invalid"], "subject": "测试", "body": "正文\n🌱"}),
])
def test_params_match_frozen_schema_and_are_detached(tool, schema, params):
    Draft202012Validator({"$ref": f"#/$defs/{schema}", "$defs": DEFS}).validate(params)
    result = params_for(tool, params)
    assert result == params and result is not params


@pytest.mark.parametrize("params", [
    {"doc_id": "../outside"}, {"doc_id": "/etc/passwd"}, {"doc_id": "C:\\real.txt"},
    {"doc_id": "doc-ok", "path": "/etc/passwd"}, {"doc_id": "doc-ok\n"},
    {"doc_id": "文档"}, {"doc_id": None}, {"doc_id": "doc-ok", "risk": 0},
])
def test_invalid_document_inputs(params):
    with pytest.raises(ToolError, match="SCHEMA_INVALID"):
        params_for("doc.read", params)


@pytest.mark.parametrize("patch", [
    {"to": ["real@example.com"]}, {"to": ["a@inbox.chainguard.invalid.evil"]},
    {"to": ["a@inbox.chainguard.invalid\nBcc:evil@example.com"]},
    {"to": ["a@inbox.chainguard.invalid"] * 2}, {"to": []}, {"subject": "x\r\ny"},
    {"body": "\ud800"}, {"body": "x" * 20001}, {"attachment": "/etc/passwd"},
    {"to": ["a@INBOX.CHAINGUARD.INVALID"]}, {"to": [1]}, {"to": [{}]},
])
def test_mail_rejects_external_or_malformed_input(patch):
    params = {"to": ["a@inbox.chainguard.invalid"], "subject": "x", "body": "y"}
    params.update(patch)
    with pytest.raises(ToolError, match="SCHEMA_INVALID"):
        params_for("mail.send", params)


def test_request_hash_binds_principal_tool_and_every_parameter():
    action = "0x" + "12" * 32
    original = {"to": ["a@inbox.chainguard.invalid"], "subject": "x", "body": "y"}
    digest = request_hash(action, "gateway", "mail.send", original)
    assert digest == request_hash(action, "gateway", "mail.send", dict(reversed(list(original.items()))))
    for key in original:
        changed = copy.deepcopy(original)
        changed[key] = ["b@inbox.chainguard.invalid"] if key == "to" else "z"
        assert request_hash(action, "gateway", "mail.send", changed) != digest
    assert request_hash(action, "other", "mail.send", original) != digest
    with pytest.raises(ToolError, match="UNKNOWN_TOOL"):
        params_for("shell.exec", {})


def test_host_cannot_create_a_file_tool_sandbox():
    from chainguard_sandbox.storage import Store
    # Host test suite intentionally never opens a destructive sandbox.
    if os.name == "nt":
        with pytest.raises(ToolError, match="POLICY_DENY"):
            Store.create()


def test_build_context_excludes_private_data_and_credentials():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    from run_phase2_container import context_archive
    import io
    import tarfile
    archive, names = context_archive()
    with tarfile.open(fileobj=io.BytesIO(archive)) as context:
        assert context.getnames() == names
    assert all(name.endswith(".py") or name in {"sandbox_tools/Dockerfile", "spec/schemas/protocol.schema.json"} for name in names)
    assert not any(".local" in name or "results" in name or "operator.key" in name or ".env" in name for name in names)
