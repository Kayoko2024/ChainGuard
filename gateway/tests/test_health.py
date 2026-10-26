import json
import os
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from openapi_spec_validator import validate
from pydantic import ValidationError

from chainguard_gateway.config import PROJECT_ROOT, Settings, load_settings
from chainguard_gateway.integrity import ProtocolIntegrityError, check_frozen_protocol
from chainguard_gateway.main import create_app


@pytest.fixture
def project_copy(tmp_path):
    root = tmp_path / "project"
    manifest = json.loads((PROJECT_ROOT / "config/phase0-freeze.json").read_text(encoding="utf-8"))
    for name in ["config/phase0-freeze.json", *manifest["files"]]:
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PROJECT_ROOT / name, target)
    return root


def test_live_and_ready_reflect_running_process_and_protocol():
    with TestClient(create_app(Settings(app_env="test"))) as client:
        live = client.get("/health/live")
        ready = client.get("/health/ready")
        assert live.status_code == ready.status_code == 200
        assert live.json()["pid"] == ready.json()["pid"] == os.getpid()
        assert live.json()["uptime_seconds"] >= 0
        assert live.json()["status"] == "alive"
        assert ready.json()["status"] == "ready"
        assert ready.json()["protocol_version"] == "1.0.0"
        assert ready.json()["checks"] == {"startup": True, "frozen_protocol": True}


def test_health_openapi_is_separate_and_business_routes_are_absent():
    with TestClient(create_app(Settings(app_env="test"))) as client:
        operations = client.get("/operations/openapi.json").json()
        validate(operations)
        assert set(operations["paths"]) == {"/health/live", "/health/ready"}
        for path in ["/v1/tasks", "/v1/agent/actions/propose", "/v1/tools/execute"]:
            assert client.post(path, json={}).status_code == 404
        assert client.get("/docs").status_code == 404


def test_ready_requires_actual_lifespan_startup():
    application = create_app(Settings(app_env="test"))
    with TestClient(application) as client:
        assert client.get("/health/ready").status_code == 200
    assert application.state.startup_complete is False
    response = TestClient(application).get("/health/ready")
    assert response.status_code == 503 and response.json()["checks"]["startup"] is False


def test_startup_rejects_changed_frozen_protocol(project_copy):
    path = project_copy / "spec/eip712.json"
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ProtocolIntegrityError):
        with TestClient(create_app(Settings(app_env="test"), project_copy)):
            pytest.fail("Application must not start with changed frozen protocol")


def test_readiness_detects_changes_after_start_without_claiming_chain_health(project_copy):
    with TestClient(create_app(Settings(app_env="test"), project_copy)) as client:
        assert client.get("/health/ready").status_code == 200
        path = project_copy / "spec/eip712.json"
        path.write_bytes(path.read_bytes() + b" ")
        response = client.get("/health/ready")
        assert response.status_code == 503
        assert response.json()["status"] == "not_ready"
        assert response.json()["checks"]["frozen_protocol"] is False
        assert "chain" not in response.json()["checks"]
        assert client.get("/health/live").status_code == 200


def test_protocol_manifest_cannot_escape_project_root(project_copy):
    manifest_path = project_copy / "config/phase0-freeze.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["files"]["../outside"] = "00" * 32
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ProtocolIntegrityError, match="Unsafe"):
        check_frozen_protocol(project_copy)


@pytest.mark.parametrize("settings", [{"CHG_PORT": "80"}, {"CHG_PORT": "65536"}, {"CHG_HOST": "example.com"}, {"CHG_APP_ENV": "production"}, {"CHG_LOG_LEVEL": "verbose"}, {"CHG_SHUTDOWN_TIMEOUT": "0"}])
def test_bad_environment_fails_validation(settings):
    with pytest.raises(ValidationError):
        load_settings(settings)


def test_environment_types_and_defaults_are_validated():
    assert load_settings({}).host == "127.0.0.1"
    assert load_settings({"CHG_PORT": "8123", "CHG_APP_ENV": "test"}).port == 8123
