"""Explicit centralized HTTP contract, separate from the future chain API."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .canonical import DEFS, ERRORS, parse_json, validate
from .crypto import random_id
from .identity import authenticate
from chainguard_sandbox.protocol import ToolError


def install_central_api(application, service):
    router = APIRouter(prefix="/central/v1", tags=["centralized A/B"])

    @application.middleware("http")
    async def secure_requests(request: Request, call_next):
        if not request.url.path.startswith("/central/"):
            return await call_next(request)
        trace_id = random_id()
        request.state.trace_id = trace_id
        request.state.subject = None
        try:
            request.state.subject = authenticate(service.store.private("jwt.key"), request.headers.get("authorization"))
            service.current_actor(request.state.subject)
            response = await call_next(request)
            if response.status_code in (404, 405):
                return error_response(request, ToolError("NOT_FOUND"))
            response.headers["X-Trace-Id"] = trace_id
            return response
        except ToolError as error:
            return error_response(request, error)
        except Exception:
            return error_response(request, ToolError("EXECUTION_UNKNOWN"))

    def error_response(request, error):
        trace_id = request.state.trace_id
        try:
            service.rejected_request(request.state.subject, trace_id, error.code)
        except Exception:
            # No unlogged new execution is allowed by service's dispatch transaction.
            error = ToolError("EXECUTION_UNKNOWN")
        return JSONResponse(status_code=ERRORS[error.code], headers={"X-Trace-Id": trace_id}, content={"error": {
            "code": error.code, "message": error.code, "retryable": False, "trace_id": trace_id}})

    @application.exception_handler(ToolError)
    async def on_tool_error(request, error):
        return error_response(request, error)

    async def body(request):
        if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
            raise ToolError("SCHEMA_INVALID")
        pieces, length = [], 0
        async for piece in request.stream():
            length += len(piece)
            if length > 65536:
                raise ToolError("SCHEMA_INVALID")
            pieces.append(piece)
        return parse_json(b"".join(pieces))

    def key(request):
        return validate("Bytes32", request.headers.get("idempotency-key"))

    def request_schema(name):
        return {"requestBody": {"required": True, "content": {"application/json": {"schema": {"$ref": f"#/components/schemas/{name}"}}}}}

    @router.post("/tasks", status_code=201, openapi_extra=request_schema("CreateTaskRequest"))
    async def create_task(request: Request):
        return service.create_task(request.state.subject, await body(request), key(request), request.state.trace_id)

    @router.post("/actions/propose", status_code=202, openapi_extra=request_schema("ProposeRequest"))
    async def propose(request: Request):
        return service.propose(request.state.subject, await body(request), key(request), request.state.trace_id)

    @router.post("/actions/{action_id}/approve", openapi_extra=request_schema("ApproveRequest"))
    async def approve(action_id: str, request: Request):
        validate("Bytes32", action_id)
        return service.approve(request.state.subject, action_id, await body(request), request.state.trace_id)

    @router.post("/actions/{action_id}/execute")
    async def execute(action_id: str, request: Request):
        validate("Bytes32", action_id)
        return service.execute(request.state.subject, action_id, await body(request), key(request), request.state.trace_id)

    @router.get("/actions/{action_id}")
    def get_action(action_id: str, request: Request):
        return service.get_action(request.state.subject, action_id)

    @router.get("/audit/entries")
    def audit(request: Request):
        return service.audit_export(request.state.subject)

    @router.get("/audit/checkpoint")
    def checkpoint(request: Request):
        export = service.audit_export(request.state.subject)
        return {"group": export["group"], "checkpoint": export["checkpoint"], "signer": export["signer"]}

    application.include_router(router)
    previous_openapi = application.openapi

    def openapi():
        spec = previous_openapi()
        # Reuse exact frozen DTO schemas while relocating local $refs.
        import json
        schemas = json.loads(json.dumps(DEFS).replace("#/$defs/", "#/components/schemas/"))
        spec.setdefault("components", {}).setdefault("schemas", {}).update(schemas)
        from pathlib import Path
        import json
        from .canonical import ROOT
        central = json.loads((ROOT / "spec/central/schemas.json").read_text())
        spec["components"]["schemas"].update(central)
        spec["components"].setdefault("securitySchemes", {})["CentralJWT"] = {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}
        for path, operations in spec["paths"].items():
            if path.startswith("/central/"):
                for operation in operations.values():
                    operation["security"] = [{"CentralJWT": []}]
                    for status in (401, 403, 404, 409, 422, 503):
                        operation.setdefault("responses", {})[str(status)] = {"description": "Frozen error envelope", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ErrorResponse"}}}}
                    if operation.get("operationId", "").startswith(("create_task", "propose", "execute")):
                        parameters = operation.setdefault("parameters", [])
                        if not any(value["name"] == "Idempotency-Key" for value in parameters):
                            parameters.append({"name": "Idempotency-Key", "in": "header", "required": True, "schema": schemas["Bytes32"]})
                    if path.endswith("/execute"):
                        operation["requestBody"] = {"required": True, "content": {"application/json": {"schema": {"$ref": "#/components/schemas/CentralExecuteRequest"}}}}
                    result_name = "TaskGrant" if path == "/central/v1/tasks" else ("CentralActionRecord" if "/actions" in path else None)
                    if result_name:
                        status = "201" if path.endswith("/tasks") else ("202" if path.endswith("/propose") else "200")
                        operation["responses"][status] = {"description": "Actual current local state", "content": {"application/json": {"schema": {"$ref": f"#/components/schemas/{result_name}"}}}}
        return spec

    application.openapi = openapi
