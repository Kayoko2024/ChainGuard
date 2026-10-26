"""Start a real local Uvicorn child, call HTTP health endpoints, then stop only it."""
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    output = ROOT / "results/phase1"
    output.mkdir(parents=True, exist_ok=True)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    env = {**os.environ, "CHG_APP_ENV": "test", "CHG_HOST": "127.0.0.1", "CHG_PORT": str(port)}
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    report = {"started_at_utc": datetime.now(timezone.utc).isoformat(), "transport": "real loopback HTTP", "port": port}
    with (output / "gateway-local.log").open("w", encoding="utf-8") as log:
        child = subprocess.Popen([sys.executable, str(ROOT / "scripts/run_gateway.py")], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, creationflags=flags)
        report["launcher_pid"] = child.pid
        try:
            deadline = time.monotonic() + 30
            while True:
                if child.poll() is not None:
                    raise RuntimeError(f"Gateway exited during startup: {child.returncode}; see gateway-local.log")
                try:
                    with opener.open(f"http://127.0.0.1:{port}/health/ready", timeout=1) as response:
                        report["ready"] = json.load(response)
                    break
                except (OSError, urllib.error.URLError):
                    if time.monotonic() >= deadline:
                        raise RuntimeError("Gateway startup timed out")
                    time.sleep(0.1)
            with opener.open(f"http://127.0.0.1:{port}/health/live", timeout=2) as response:
                report["live"] = json.load(response)
            assert report["ready"]["status"] == "ready" and report["live"]["status"] == "alive"
            assert report["ready"]["pid"] == report["live"]["pid"]
            report["server_pid"] = report["ready"]["pid"]
            log.flush()
            startup_log = (output / "gateway-local.log").read_text(encoding="utf-8")
            logged_pid = re.search(r"Started server process \[(\d+)\]", startup_log)
            assert logged_pid and int(logged_pid.group(1)) == report["server_pid"]
            try:
                opener.open(urllib.request.Request(f"http://127.0.0.1:{port}/v1/tasks", data=b"{}", headers={"Content-Type": "application/json"}), timeout=2)
                raise AssertionError("Business API must not be implemented in phase 1")
            except urllib.error.HTTPError as error:
                assert error.code == 404
                report["business_route_status"] = error.code
            report["status"] = "PASS"
        finally:
            if child.poll() is None:
                if os.name == "nt":
                    # Windows venv python.exe can be a launcher with a real Python child.
                    # Kill only the exact process tree created by this Popen, before its
                    # launcher exits; terminating the launcher alone is insufficient.
                    stopped = subprocess.run(["taskkill.exe", "/PID", str(child.pid), "/T", "/F"], capture_output=True, timeout=10)
                    if stopped.returncode and child.poll() is None:
                        raise RuntimeError("Could not stop the owned gateway process tree")
                else:
                    child.terminate()
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=5)
            report["child_exit_code"] = child.returncode
    with socket.socket() as probe:
        report["port_released"] = probe.connect_ex(("127.0.0.1", port)) != 0
    assert report["port_released"]
    (output / "startup-local.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Real gateway HTTP startup passed; port={port}; child stopped and port released")


if __name__ == "__main__":
    main()
