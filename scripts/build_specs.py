"""Build declarative JSON Schema/OpenAPI files; no business service is implemented."""
import argparse
import json
from pathlib import Path

from eth_utils import keccak

ROOT = Path(__file__).resolve().parents[1]


def bounded_decimal(bits):
    """A standard JSON Schema regex enforces the full unsigned range, even in JS."""
    maximum = str(2**bits - 1)
    terms = ["0", rf"[1-9][0-9]{{0,{len(maximum)-2}}}", maximum]
    for index, digit in enumerate(maximum):
        low = 1 if index == 0 else 0
        high = int(digit) - 1
        if high < low:
            continue
        char = str(low) if low == high else f"[{low}-{high}]"
        terms.append(maximum[:index] + char + rf"[0-9]{{{len(maximum)-index-1}}}")
    return "^(?:" + "|".join(terms) + ")$"


def ref(name):
    return {"$ref": f"#/$defs/{name}"}


def obj(properties, required=None, **extra):
    return {"type": "object", "properties": properties, "required": list(properties) if required is None else required, "additionalProperties": False, **extra}


def array(items, **extra):
    return {"type": "array", "items": items, **extra}


def nullable(name):
    return {"oneOf": [ref(name), {"type": "null"}]}


def absolute_patterns(value):
    # JS and Python '$' both accept a position before a trailing newline.
    # A negative all-character lookahead requires the actual end of the string.
    if isinstance(value, dict):
        return {key: val[:-1] + r"(?![\s\S])" if key == "pattern" and val.endswith("$") else absolute_patterns(val) for key, val in value.items()}
    if isinstance(value, list):
        return [absolute_patterns(item) for item in value]
    return value


def create_schemas():
    machines = json.loads((ROOT / "spec/state-machines.json").read_text())
    errors = json.loads((ROOT / "spec/errors.json").read_text())
    rules = json.loads((ROOT / "spec/risk-rules.json").read_text())["rules"]
    d = {}
    d["Bytes32"] = {"type": "string", "pattern": "^0x(?!0{64}$)[0-9a-f]{64}$"}
    d["Address"] = {"type": "string", "pattern": "^0x(?!0{40}$)[0-9a-f]{40}$"}
    d["UInt64"] = {"type": "string", "pattern": bounded_decimal(64)}
    d["UInt256"] = {"type": "string", "pattern": bounded_decimal(256)}
    d["Signature"] = {"type": "string", "pattern": "^0x[0-9a-f]{128}(?:1b|1c)$"}
    d["Risk"] = {"type": "integer", "enum": [0, 1, 2, 3]}
    d["Outcome"] = {"type": "integer", "enum": [0, 1, 2, 3]}
    d["ActionState"] = {"type": "string", "enum": list(dict.fromkeys(machines["action"]["states"] + machines["read"]["states"]))}
    d["ChainState"] = {"type": "string", "enum": machines["chain"]["states"]}
    d["ToolName"] = {"type": "string", "enum": ["doc.read", "mail.send", "doc.delete"]}
    d["ScopeName"] = {"type": "string", "enum": ["PUBLIC_DOCS", "ORG_A_DOCS", "ORG_A_INTERNAL_MAIL", "ORG_A_DISPOSABLE_DOCS"]}
    d["ActionIntent"] = obj({
        "schema_version": {"const": 1, "type": "integer"},
        "action_id": ref("Bytes32"), "task_id": ref("Bytes32"), "requester": ref("Address"), "agent": ref("Address"),
        "tool_id": ref("Bytes32"), "resource_scope": ref("Bytes32"), "params_commit": ref("Bytes32"), "policy_id": ref("Bytes32"),
        "policy_epoch": ref("UInt64"), "nonce": ref("UInt64"), "issued_at": ref("UInt64"), "expires_at": ref("UInt64"),
        "risk": {"type": "integer", "enum": [2, 3]},
    })
    label_hash = lambda namespace, value: "0x" + keccak(text=f"ChainGuard/{namespace}/{value}").hex()
    d["ActionIntent"]["oneOf"] = [{"properties": {
        "risk": {"const": rule["risk"]}, "tool_id": {"const": label_hash("tool", rule["tool"])},
        "resource_scope": {"const": label_hash("scope", rule["scope"])}, "policy_id": {"const": label_hash("policy", rule["policy"])},
        "policy_epoch": {"not": {"const": "0"}},
    }} for rule in rules if rule["reservation_required"]]
    d["ExecutionReceipt"] = obj({
        "schema_version": {"const": 1, "type": "integer"}, "action_id": ref("Bytes32"), "params_commit": ref("Bytes32"),
        "result_commit": ref("Bytes32"), "evidence_index_commit": ref("Bytes32"), "executed_at": ref("UInt64"), "outcome": ref("Outcome"),
    })
    d["DocumentId"] = {"type": "string", "pattern": "^[a-z][a-z0-9_-]{0,63}$"}
    d["ReadParams"] = obj({"doc_id": ref("DocumentId")})
    d["DeleteParams"] = obj({"doc_id": ref("DocumentId")})
    d["MailParams"] = obj({
        "to": array({"type": "string", "pattern": "^[a-zA-Z0-9._+-]+@inbox\\.chainguard\\.invalid$"}, minItems=1, maxItems=10, uniqueItems=True),
        "subject": {"type": "string", "minLength": 1, "maxLength": 200, "pattern": "^[^\\r\\n]*$"},
        "body": {"type": "string", "maxLength": 20000},
    })
    d["CreateTaskRequest"] = obj({
        "task_text": {"type": "string", "minLength": 1, "maxLength": 20000},
        "agent": ref("Address"),
        "allowed_tools": array(ref("ToolName"), minItems=1, uniqueItems=True),
        "resource_scopes": array(ref("ScopeName"), minItems=1, uniqueItems=True),
        "allowed_document_ids": array(ref("DocumentId"), maxItems=100, uniqueItems=True),
        "allowed_recipients": array(d["MailParams"]["properties"]["to"]["items"], maxItems=10, uniqueItems=True),
        "expires_at": ref("UInt64"), "max_risk": ref("Risk"), "allow_sandbox_delete": {"type": "boolean"},
        "max_actions": {"type": "integer", "minimum": 1, "maximum": 1000},
    })
    d["TaskGrant"] = obj({**d["CreateTaskRequest"]["properties"], "schema_version": {"type": "integer", "const": 1}, "task_id": ref("Bytes32"), "requester": ref("Address")})
    d["ProposeRequest"] = {"oneOf": [obj({"task_id": ref("Bytes32"), "tool_name": {"const": tool, "type": "string"}, "params": ref(params)}) for tool, params in [("doc.read", "ReadParams"), ("mail.send", "MailParams"), ("doc.delete", "DeleteParams")]]}
    d["ApproveRequest"] = obj({"signature": ref("Signature")})
    d["ReserveRequest"] = obj({"requester_signature": ref("Signature")})
    d["ChainEvidence"] = obj({"chain_id": ref("UInt256"), "registry": ref("Address"), "tx_hash": ref("Bytes32"), "block_hash": ref("Bytes32"), "block_number": ref("UInt64")})
    d["ErrorDetail"] = obj({"code": {"type": "string", "enum": list(errors)}, "message": {"type": "string", "maxLength": 512}, "retryable": {"type": "boolean"}, "trace_id": ref("Bytes32")})
    d["ErrorResponse"] = obj({"error": ref("ErrorDetail")})
    d["ActionRecord"] = obj({
        "action_id": ref("Bytes32"), "task_id": ref("Bytes32"), "risk": ref("Risk"), "state": ref("ActionState"),
        "chain_state": ref("ChainState"), "anchor_status": {"type": "string", "enum": ["NOT_APPLICABLE", "PENDING", "CONFIRMED"]},
        "intent": nullable("ActionIntent"), "receipt": nullable("ExecutionReceipt"),
        "reservation_evidence": nullable("ChainEvidence"), "finalization_evidence": nullable("ChainEvidence"), "error": nullable("ErrorDetail"),
    })
    d["ActionRecord"]["allOf"] = [{
        "if": {"properties": {"risk": {"enum": [0, 1]}}},
        "then": {"properties": {"state": {"enum": machines["read"]["states"]}, "chain_state": {"const": "NONE"}, "anchor_status": {"const": "NOT_APPLICABLE"}, "intent": {"type": "null"}, "receipt": {"type": "null"}, "reservation_evidence": {"type": "null"}, "finalization_evidence": {"type": "null"}}},
        "else": {"properties": {"state": {"enum": machines["action"]["states"]}, "intent": ref("ActionIntent")}},
    }]
    d["ActionRecord"]["allOf"].extend([
        {"if": {"properties": {"state": {"const": state}}}, "then": {"properties": {"chain_state": {"const": state}, "anchor_status": {"const": "CONFIRMED"}, "receipt": {"allOf": [ref("ExecutionReceipt"), {"properties": {"outcome": {"const": outcome}}}]}, "reservation_evidence": ref("ChainEvidence"), "finalization_evidence": ref("ChainEvidence")}}}
        for state, outcome in [("FINALIZED_OK", 0), ("FINALIZED_ERROR", 1), ("FINALIZED_REJECTED", 2)]
    ])
    d["ActionRecord"]["allOf"].append({"if": {"properties": {"state": {"const": "EXECUTION_RECORDED"}}}, "then": {"properties": {"anchor_status": {"const": "PENDING"}, "chain_state": {"enum": ["RESERVED", "UNKNOWN"]}, "receipt": {"allOf": [ref("ExecutionReceipt"), {"properties": {"outcome": {"enum": [0, 1, 2]}}}]}, "reservation_evidence": ref("ChainEvidence"), "finalization_evidence": {"type": "null"}}}})
    d["ExecuteRequest"] = obj({"intent": ref("ActionIntent"), "params_salt": ref("Bytes32"), "params": {"oneOf": [ref("MailParams"), ref("DeleteParams")]}, "reservation_evidence": ref("ChainEvidence")})
    d["ExecuteRequest"]["oneOf"] = [
        {"properties": {"intent": {"properties": {"tool_id": {"const": "0x" + keccak(text="ChainGuard/tool/" + tool).hex()}, "risk": {"const": risk}}}, "params": ref(params)}}
        for tool, risk, params in [("mail.send", 2, "MailParams"), ("doc.delete", 3, "DeleteParams")]
    ]
    d["ToolExecutionResponse"] = obj({"action_id": ref("Bytes32"), "state": {"type": "string", "enum": ["EXECUTION_RECORDED", "UNKNOWN"]}, "receipt": nullable("ExecutionReceipt"), "tool_signature": nullable("Signature")})
    d["ToolExecutionResponse"]["oneOf"] = [
        {"properties": {"state": {"const": "EXECUTION_RECORDED"}, "receipt": {"allOf": [ref("ExecutionReceipt"), {"properties": {"outcome": {"enum": [0, 1, 2]}}}]}, "tool_signature": ref("Signature")}},
        {"properties": {"state": {"const": "UNKNOWN"}, "receipt": {"type": "null"}, "tool_signature": {"type": "null"}}},
        {"properties": {"state": {"const": "UNKNOWN"}, "receipt": {"allOf": [ref("ExecutionReceipt"), {"properties": {"outcome": {"const": 3}}}]}, "tool_signature": ref("Signature")}},
    ]
    d["ToolStatusResponse"] = obj({
        "action_id": ref("Bytes32"), "checked_at": ref("UInt64"),
        "status": {"type": "string", "enum": ["NOT_STARTED", "CLAIMED", "EXECUTED_OK", "EXECUTED_ERROR", "REJECTED", "UNKNOWN"]},
        "receipt": nullable("ExecutionReceipt"), "tool_signature": nullable("Signature"),
    })
    d["ToolStatusResponse"]["oneOf"] = [
        {"properties": {"status": {"enum": ["NOT_STARTED", "CLAIMED", "UNKNOWN"]}, "receipt": {"type": "null"}, "tool_signature": {"type": "null"}}},
        *[{"properties": {"status": {"const": state}, "receipt": {"allOf": [ref("ExecutionReceipt"), {"properties": {"outcome": {"const": outcome}}}]}, "tool_signature": ref("Signature")}} for state, outcome in [("EXECUTED_OK", 0), ("EXECUTED_ERROR", 1), ("REJECTED", 2), ("UNKNOWN", 3)]],
    ]
    d["ReconcileRequest"] = obj({"receipt": ref("ExecutionReceipt"), "tool_signature": ref("Signature")})
    d["ProofBundle"] = obj({
        "schema_version": {"type": "integer", "const": 1}, "chain_id": ref("UInt256"), "execution_registry": ref("Address"), "audit_registry": ref("Address"),
        "intent": ref("ActionIntent"), "requester_signature": ref("Signature"), "approval_signatures": array(ref("Signature"), minItems=2, maxItems=16, uniqueItems=True),
        "receipt": nullable("ExecutionReceipt"), "tool_signature": nullable("Signature"), "reservation_evidence": ref("ChainEvidence"), "finalization_evidence": nullable("ChainEvidence"),
        "evidence_status": {"type": "string", "enum": ["AVAILABLE", "MISSING", "NO_ACCESS"]},
    })
    d["ProofBundle"]["allOf"] = [
        {"if": {"properties": {"receipt": {"type": "null"}}}, "then": {"properties": {"tool_signature": {"type": "null"}, "finalization_evidence": {"type": "null"}}}, "else": {"properties": {"tool_signature": ref("Signature")}}},
        {"if": {"properties": {"intent": {"properties": {"risk": {"const": 3}}}}}, "then": {"properties": {"approval_signatures": {"minItems": 3}}}},
    ]
    d["VerifyRequest"] = obj({"proof": ref("ProofBundle")})
    d["VerifyResponse"] = obj({"action_id": ref("Bytes32"), "verdict": {"type": "string", "enum": ["VALID", "INVALID", "PARTIAL"]}, "findings": array({"type": "string", "maxLength": 512})})
    d["MetricsSummary"] = obj({"experiment_version": {"type": "string", "minLength": 1}, "sample_count": {"type": "integer", "minimum": 0}, "unauthorized_attempts": {"type": "integer", "minimum": 0}, "unauthorized_executed": {"type": "integer", "minimum": 0}, "reserve_latency_p95_ms": {"type": ["number", "null"], "minimum": 0}})
    return absolute_patterns({"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": "urn:chainguard:protocol:1", "title": "ChainGuard phase 0 protocol", "$defs": d})


def openapi_refs(value):
    if isinstance(value, dict):
        return {key: val.replace("#/$defs/", "#/components/schemas/") if key == "$ref" else openapi_refs(val) for key, val in value.items()}
    if isinstance(value, list):
        return [openapi_refs(item) for item in value]
    return value


def create_openapi(schema):
    errors = json.loads((ROOT / "spec/errors.json").read_text())
    paths = {}
    definitions = [
        ("post", "/v1/tasks", "createTask", "CreateTaskRequest", "TaskGrant", "201", "user", True),
        ("post", "/v1/agent/actions/propose", "proposeAction", "ProposeRequest", "ActionRecord", "202", "agent", True),
        ("post", "/v1/actions/{id}/approve", "approveAction", "ApproveRequest", "ActionRecord", "200", "approver", False),
        ("post", "/v1/actions/{id}/reserve", "reserveAction", "ReserveRequest", "ActionRecord", "202", "executor", True),
        ("post", "/v1/tools/execute", "executeTool", "ExecuteRequest", "ToolExecutionResponse", "200", "internal_gateway", True),
        ("get", "/v1/tools/actions/{id}", "getToolStatus", None, "ToolStatusResponse", "200", "internal_gateway", False),
        ("get", "/v1/actions/{id}", "getAction", None, "ActionRecord", "200", "scoped_user", False),
        ("get", "/v1/actions/{id}/proof", "getProof", None, "ProofBundle", "200", "auditor", False),
        ("post", "/v1/audit/verify", "verifyProof", "VerifyRequest", "VerifyResponse", "200", "auditor", False),
        ("post", "/v1/actions/{id}/reconcile", "reconcileAction", "ReconcileRequest", "ActionRecord", "202", "reconciler", True),
        ("get", "/v1/metrics/summary", "getMetrics", None, "MetricsSummary", "200", "local_evaluator", False),
    ]
    for method, path, op_id, request, response, status, role, idempotent in definitions:
        operation = {"operationId": op_id, "summary": op_id, "x-required-role": role, "security": [{"ServiceBearer": [], "MutualTLS": []}] if role == "internal_gateway" else [{"BearerAuth": []}], "responses": {status: {"description": "Protocol response; phase 0 declares this endpoint only", "content": {"application/json": {"schema": ref(response)}}}}}
        for code in sorted(set(errors.values())):
            operation["responses"][str(code)] = {"description": ", ".join(name for name, value in errors.items() if value == code), "content": {"application/json": {"schema": ref("ErrorResponse")}}}
        params = []
        if "{id}" in path:
            params.append({"in": "path", "name": "id", "required": True, "schema": ref("Bytes32")})
        if idempotent:
            params.append({"in": "header", "name": "Idempotency-Key", "required": True, "schema": ref("Bytes32"), "description": "Scoped to authenticated principal + operation; same key/different canonical body => 409"})
        if params:
            operation["parameters"] = params
        if request:
            operation["requestBody"] = {"required": True, "content": {"application/json": {"schema": ref(request)}}}
        paths.setdefault(path, {})[method] = operation
    return openapi_refs({"openapi": "3.1.0", "info": {"title": "ChainGuard HTTP contract (unimplemented)", "version": "1.0.0"}, "servers": [{"url": "http://127.0.0.1:8000", "description": "Future local sandbox gateway; no service in phase 0"}], "paths": paths, "components": {"schemas": schema["$defs"], "securitySchemes": {"BearerAuth": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}, "ServiceBearer": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}, "MutualTLS": {"type": "mutualTLS"}}}})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    schema = create_schemas()
    outputs = {ROOT / "spec/schemas/protocol.schema.json": schema, ROOT / "spec/openapi.json": create_openapi(schema)}
    for path, content in outputs.items():
        serialized = json.dumps(content, ensure_ascii=False, indent=2) + "\n"
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != serialized:
                raise SystemExit(f"Out of date: {path}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(serialized, encoding="utf-8")
    print("Schema/OpenAPI outputs match source" if args.check else "Schema/OpenAPI outputs generated")


if __name__ == "__main__":
    main()
