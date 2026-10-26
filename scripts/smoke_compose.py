"""Build/start the real Compose gateway, verify it, and clean up only this test run."""
import argparse
import importlib.metadata
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from check_environment import docker_prefix, project_path, run
from local_env import parse_env
from build_gateway_image import build_image

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--wsl-distro")
    parser.add_argument("--wsl-user", default="root")
    args = parser.parse_args()
    prefix = docker_prefix(args.wsl_distro, args.wsl_user)
    if not prefix:
        raise SystemExit("Docker CLI missing; container startup cannot be claimed")
    compose = prefix + ["compose", "--project-directory", project_path(ROOT, bool(args.wsl_distro)), "-f", project_path(ROOT / "compose.yaml", bool(args.wsl_distro))]
    if (ROOT / ".env").exists():
        compose += ["--env-file", project_path(ROOT / ".env", bool(args.wsl_distro))]
    code, existing, error = run(compose + ["ps", "--all", "--quiet"])
    if code or existing:
        raise SystemExit("Refusing to replace/stop existing Compose containers; run compose down explicitly before this smoke test")
    output = ROOT / "results/phase1"
    output.mkdir(parents=True, exist_ok=True)
    env_path = ROOT / (".env" if (ROOT / ".env").exists() else ".env.example")
    port = int(parse_env(env_path).get("CHG_PORT", "8000"))
    report = {"recorded_at_utc": datetime.now(timezone.utc).isoformat(), "backend": args.wsl_distro or "native", "status": "FAIL", "port": port}
    report["transport"] = "Windows loopback HTTP to WSL-published port" if args.wsl_distro else "host loopback HTTP"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with (output / "compose-startup.log").open("w", encoding="utf-8") as log:
        try:
            if args.wsl_distro:
                report["build_context"] = build_image(prefix, log)
            build_option = "--no-build" if args.wsl_distro else "--build"
            completed = subprocess.run(compose + ["up", build_option, "--wait", "--wait-timeout", "60"], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, timeout=600)
            if completed.returncode:
                raise RuntimeError("Compose startup failed; see compose-startup.log")
            code, container_id, _ = run(compose + ["ps", "--quiet", "gateway"])
            if code or not container_id:
                raise RuntimeError("Compose did not return an actual gateway container")
            code, state_json, _ = run(prefix + ["inspect", container_id, "--format", "{{json .State}}"])
            state = json.loads(state_json)
            if code or not state["Running"] or state["Health"]["Status"] != "healthy":
                raise RuntimeError("Actual container state is not healthy")
            report["container_id"] = container_id
            report["docker_health"] = state["Health"]["Status"]
            for endpoint in ["live", "ready"]:
                deadline = time.monotonic() + 30
                while True:
                    try:
                        with opener.open(f"http://127.0.0.1:{port}/health/{endpoint}", timeout=3) as response:
                            report[endpoint] = json.load(response)
                        break
                    except OSError:
                        if time.monotonic() >= deadline:
                            raise
                        time.sleep(0.2)
            assert report["live"]["status"] == "alive" and report["ready"]["status"] == "ready"
            try:
                opener.open(urllib.request.Request(f"http://127.0.0.1:{port}/v1/tasks", data=b"{}", headers={"Content-Type": "application/json"}), timeout=5)
                raise AssertionError("Unexpected business API in phase 1 image")
            except urllib.error.HTTPError as error:
                assert error.code == 404
                report["business_route_status"] = error.code
            version_script = "import sys,json,importlib.metadata as m; print(json.dumps({'python':sys.version.split()[0],**{name:m.version(name) for name in ['fastapi','starlette','anyio','pydantic','uvicorn']}}))"
            code, versions, _ = run(prefix + ["exec", container_id, "python", "-c", version_script])
            if code:
                raise RuntimeError("Could not inspect actual container dependency versions")
            report["versions"] = json.loads(versions)
            assert report["versions"]["python"] == json.loads((ROOT / "config/toolchain.json").read_text())["tested_python"]
            for name in ["fastapi", "starlette", "anyio", "pydantic", "uvicorn"]:
                assert report["versions"][name] == importlib.metadata.version(name)
            code, pip_check, _ = run(prefix + ["exec", container_id, "python", "-m", "pip", "check"])
            assert code == 0
            report["pip_check"] = pip_check
            report["status"] = "PASS"
        except BaseException as error:
            report["error"] = str(error)
            raise
        finally:
            stopped = subprocess.run(compose + ["down"], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, timeout=60)
            report["compose_down_exit_code"] = stopped.returncode
            if stopped.returncode:
                report["status"] = "FAIL"
            (output / "startup-compose.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if report["status"] != "PASS":
        raise SystemExit("Container cleanup failed")
    print("Real Compose build/start/HTTP health/dependency checks passed; test containers stopped")


if __name__ == "__main__":
    main()
