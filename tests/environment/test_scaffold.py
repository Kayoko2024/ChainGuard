import importlib.metadata as metadata
import json
import sys
from pathlib import Path

import pytest
import yaml
from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from local_env import parse_env
from build_gateway_image import create_build_context


def test_compose_binds_only_gateway_to_loopback_without_credentials_or_host_mounts():
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text())
    assert set(compose["services"]) == {"gateway"}
    gateway = compose["services"]["gateway"]
    assert gateway["ports"] == ["127.0.0.1:${CHG_PORT:-8000}:8000"]
    assert gateway["read_only"] is True
    assert gateway["cap_drop"] == ["ALL"]
    assert gateway["security_opt"] == ["no-new-privileges:true"]
    assert not gateway.get("volumes") and not gateway.get("secrets")
    assert compose["networks"]["gateway_local"]["internal"] is False
    assert compose["networks"]["gateway_local"]["driver"] == "bridge"
    assert not any("KEY" in name or "TOKEN" in name for name in gateway["environment"])


def test_monorepo_workspace_and_lockfile_are_consistent():
    package = json.loads((ROOT / "package.json").read_text())
    lock = json.loads((ROOT / "package-lock.json").read_text())
    contracts = json.loads((ROOT / "contracts/package.json").read_text())
    assert package["workspaces"] == ["contracts"]
    assert lock["packages"][""]["workspaces"] == package["workspaces"]
    assert lock["packages"]["contracts"]["name"] == contracts["name"]
    assert "--config ../hardhat.config.cjs" in contracts["scripts"]["test"]


def test_runtime_lock_contains_the_installed_dependency_closure():
    for line in (ROOT / "gateway/requirements.lock").read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        requirement = Requirement(line)
        assert metadata.version(requirement.name) in requirement.specifier
    for line in (ROOT / "gateway/requirements.txt").read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        requirement = Requirement(line)
        assert metadata.version(requirement.name) in requirement.specifier


def test_environment_template_contains_no_secret_and_is_parseable():
    env = parse_env(ROOT / ".env.example")
    assert env["CHG_HOST"] == "127.0.0.1" and env["CHG_PORT"] == "8000"
    assert set(env) == {"COMPOSE_PROJECT_NAME", "CHG_APP_ENV", "CHG_HOST", "CHG_PORT", "CHG_LOG_LEVEL", "CHG_SHUTDOWN_TIMEOUT", "CHG_PYTHON_IMAGE"}


@pytest.mark.parametrize("content", ["CHG_PORT=8000\nCHG_PORT=8001", "UNKNOWN=value", "CHG_PORT=$(bad)", "CHG_PORT=", "export CHG_PORT=8000"])
def test_environment_loader_rejects_ambiguous_or_executable_input(content, tmp_path):
    path = tmp_path / "env"
    path.write_text(content)
    with pytest.raises(ValueError):
        parse_env(path)


def test_docker_build_archive_contains_frozen_inputs_but_no_credentials_or_caches(tmp_path):
    import tarfile
    archive = tmp_path / "context.tar"
    result = create_build_context(ROOT, archive)
    frozen = json.loads((ROOT / "config/phase0-freeze.json").read_text())
    with tarfile.open(archive) as context:
        names = set(context.getnames())
        assert set(frozen["files"]) <= names
        assert "gateway/Dockerfile" in names and "gateway/requirements.lock" in names
        assert not any(name == ".env" or name.startswith((".venv/", ".git/", ".pytest_cache/", "node_modules/", "secrets/", "results/")) for name in names)
        assert len(names) == result["files"]


def test_docker_build_archive_is_byte_reproducible(tmp_path):
    first = create_build_context(ROOT, tmp_path / "first.tar")
    second = create_build_context(ROOT, tmp_path / "second.tar")
    assert first == second
