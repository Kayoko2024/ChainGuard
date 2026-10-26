import copy
import json
import re
import subprocess
import sys

import pytest
from jsonschema import Draft202012Validator, ValidationError
from openapi_spec_validator import validate as validate_openapi


def test_schema_and_openapi_are_valid_and_generated(root, schemas):
    Draft202012Validator.check_schema(schemas)
    api = json.loads((root / "spec/openapi.json").read_text(encoding="utf-8"))
    validate_openapi(api)
    assert api["components"]["schemas"] == json.loads(json.dumps(schemas["$defs"]).replace("#/$defs/", "#/components/schemas/"))
    subprocess.run([sys.executable, str(root / "scripts/build_specs.py"), "--check"], check=True)


@pytest.mark.parametrize("kind,key", [("ActionIntent", "intent_json"), ("ExecutionReceipt", "receipt_json")])
def test_golden_payload_obeys_schema_and_mapping(kind, key, vector, protocol, schemas, validate):
    payload = vector[key]
    validate(kind, payload)
    mapping = protocol["json_to_typed"][kind]
    assert set(mapping) == set(schemas["$defs"][kind]["properties"]) == set(payload)
    assert list(mapping.values()) == [field["name"] for field in protocol["types"][kind]]
    assert {typed: payload[wire] for wire, typed in mapping.items()} == vector["vectors"][kind]["typed_data"]["message"]
    for field in payload:
        missing = copy.deepcopy(payload)
        del missing[field]
        with pytest.raises(ValidationError):
            validate(kind, missing)
    with pytest.raises(ValidationError):
        validate(kind, {**payload, "unexpected": True})


@pytest.mark.parametrize("bits", [64, 256])
def test_unsigned_decimal_boundaries(bits, validate):
    for value in [0, 1, 2**53 + 1, 2**bits - 1]:
        validate(f"UInt{bits}", str(value))
    for value in [str(2**bits), "-1", "01", "1.0", "1e3", "", 1, True, "0x01", "1\n"]:
        with pytest.raises(ValidationError):
            validate(f"UInt{bits}", value)


@pytest.mark.parametrize("updates", [{"risk": 4}, {"risk": "R2"}, {"schema_version": 2}, {"nonce": "18446744073709551616"}, {"requester": "0x" + "00" * 20}, {"params_commit": "0x1234"}])
def test_invalid_intent_shape_rejected(updates, vector, validate):
    with pytest.raises(ValidationError):
        validate("ActionIntent", {**vector["intent_json"], **updates})


def test_tool_parameter_contracts_are_closed_and_sandbox_only(vector, validate):
    valid = {"task_id": vector["intent_json"]["task_id"], "tool_name": "mail.send", "params": vector["commitments"]["params"]["value"]}
    validate("ProposeRequest", valid)
    cases = [
        {**valid, "tool_name": "shell.exec"},
        {**valid, "params": {**valid["params"], "to": ["real@example.com"]}},
        {**valid, "params": {**valid["params"], "subject": "hello\r\nBcc:bad"}},
        {**valid, "params": {**valid["params"], "subject": "hello\n"}},
        {**valid, "params": {**valid["params"], "to": ["report@inbox.chainguard.invalid\n"]}},
        {**valid, "params": {**valid["params"], "api_key": "forbidden"}},
        {**valid, "tool_name": "doc.delete", "params": {"doc_id": "../real-file"}},
        {**valid, "tool_name": "doc.read", "params": {"doc_id": "C:\\private.txt"}},
    ]
    for case in cases:
        with pytest.raises(ValidationError):
            validate("ProposeRequest", case)
    for tool in ["doc.read", "doc.delete"]:
        validate("ProposeRequest", {**valid, "tool_name": tool, "params": {"doc_id": "sandbox_doc_1"}})


def test_api_auth_roles_paths_errors_and_internal_and_security(root, schemas):
    api = json.loads((root / "spec/openapi.json").read_text(encoding="utf-8"))
    errors = json.loads((root / "spec/errors.json").read_text())
    operations = [op for path in api["paths"].values() for op in path.values()]
    assert len(operations) == 11
    assert len({op["operationId"] for op in operations}) == len(operations)
    for path, methods in api["paths"].items():
        for method, op in methods.items():
            assert op["security"] and op["x-required-role"]
            assert {str(code) for code in errors.values()} <= set(op["responses"])
            if "{id}" in path:
                assert any(p["name"] == "id" and p["required"] for p in op["parameters"])
            if method == "get":
                assert "requestBody" not in op
    internal = api["paths"]["/v1/tools/execute"]["post"]
    assert internal["security"] == [{"ServiceBearer": [], "MutualTLS": []}]
    assert api["paths"]["/v1/tools/actions/{id}"]["get"]["security"] == internal["security"]
    assert set(schemas["$defs"]["ErrorDetail"]["properties"]["code"]["enum"]) == set(errors)
    # All references are local and resolvable; no schema fetch/network is needed.
    for name in re.findall(r'"\$ref": "#/components/schemas/([^"/]+)"', json.dumps(api)):
        assert name in api["components"]["schemas"]


def test_finalized_and_unanchored_action_shapes(vector, validate):
    evidence = {"chain_id": "31337", "registry": "0x1111111111111111111111111111111111111111", "tx_hash": "0x" + "aa" * 32, "block_hash": "0x" + "bb" * 32, "block_number": "10"}
    record = {"action_id": vector["intent_json"]["action_id"], "task_id": vector["intent_json"]["task_id"], "risk": 2, "state": "EXECUTION_RECORDED", "chain_state": "RESERVED", "anchor_status": "PENDING", "intent": vector["intent_json"], "receipt": vector["receipt_json"], "reservation_evidence": evidence, "finalization_evidence": None, "error": None}
    validate("ActionRecord", record)
    for updates in [{"anchor_status": "CONFIRMED"}, {"receipt": None}, {"state": "FINALIZED_OK"}]:
        with pytest.raises(ValidationError):
            validate("ActionRecord", {**record, **updates})
    final = {**record, "state": "FINALIZED_OK", "chain_state": "FINALIZED_OK", "anchor_status": "CONFIRMED", "finalization_evidence": {**evidence, "registry": "0x2222222222222222222222222222222222222222"}}
    validate("ActionRecord", final)
    with pytest.raises(ValidationError):
        validate("ActionRecord", {**final, "receipt": {**vector["receipt_json"], "outcome": 3}})
    read = {**record, "risk": 0, "state": "READ_OK", "chain_state": "NONE", "anchor_status": "NOT_APPLICABLE", "intent": None, "receipt": None, "reservation_evidence": None}
    validate("ActionRecord", read)
    with pytest.raises(ValidationError):
        validate("ActionRecord", {**read, "chain_state": "RESERVED"})


def test_tool_response_cannot_claim_an_unsigned_or_unknown_result_as_recorded(vector, validate):
    signature = vector["vectors"]["ExecutionReceipt"]["signatures"][0]["signature"]
    response = {"action_id": vector["intent_json"]["action_id"], "state": "EXECUTION_RECORDED", "receipt": vector["receipt_json"], "tool_signature": signature}
    validate("ToolExecutionResponse", response)
    for updates in [{"receipt": None}, {"tool_signature": None}, {"receipt": {**vector["receipt_json"], "outcome": 3}}]:
        with pytest.raises(ValidationError):
            validate("ToolExecutionResponse", {**response, **updates})
    validate("ToolExecutionResponse", {**response, "state": "UNKNOWN", "receipt": None, "tool_signature": None})


def test_execute_tool_and_params_must_agree(vector, validate):
    request = {"intent": vector["intent_json"], "params_salt": vector["commitments"]["params"]["salt"], "params": vector["commitments"]["params"]["value"], "reservation_evidence": {"chain_id": "31337", "registry": "0x1111111111111111111111111111111111111111", "tx_hash": "0x" + "aa" * 32, "block_hash": "0x" + "bb" * 32, "block_number": "10"}}
    validate("ExecuteRequest", request)
    with pytest.raises(ValidationError):
        validate("ExecuteRequest", {**request, "params": {"doc_id": "sandbox_doc_1"}})


def test_task_authorization_is_an_explicit_closed_contract(vector, validate):
    task = {"task_text": "读取指定文档并给本地邮箱发摘要", "agent": vector["intent_json"]["agent"], "allowed_tools": ["doc.read", "mail.send"], "resource_scopes": ["ORG_A_DOCS", "ORG_A_INTERNAL_MAIL"], "allowed_document_ids": ["sandbox_doc_1"], "allowed_recipients": ["report@inbox.chainguard.invalid"], "expires_at": vector["intent_json"]["expires_at"], "max_risk": 2, "allow_sandbox_delete": False, "max_actions": 5}
    validate("CreateTaskRequest", task)
    grant = {**task, "schema_version": 1, "task_id": vector["intent_json"]["task_id"], "requester": vector["intent_json"]["requester"]}
    validate("TaskGrant", grant)
    with pytest.raises(ValidationError):
        validate("CreateTaskRequest", {**task, "requester": grant["requester"]})
    with pytest.raises(ValidationError):
        validate("CreateTaskRequest", {**task, "allowed_recipients": ["someone@example.com"]})


def test_spec_strings_reject_trailing_newline_and_public_vector_has_no_private_keys(vector, validate):
    for name, value in [("Bytes32", vector["intent_json"]["action_id"]), ("Address", vector["intent_json"]["requester"]), ("DocumentId", "sandbox_doc_1"), ("Signature", vector["vectors"]["ExecutionReceipt"]["signatures"][0]["signature"])]:
        validate(name, value)
        with pytest.raises(ValidationError):
            validate(name, value + "\n")
    def visit(value):
        if isinstance(value, dict):
            assert not {"private_key", "privateKey", "secret_key", "mnemonic", "api_key"} & set(value)
            for item in value.values():
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)
    visit(vector)
