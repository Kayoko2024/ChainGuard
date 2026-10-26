"""Keep actual JUnit and logs in /tmp; export only public test evidence."""

import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET
import importlib.metadata as metadata


result = subprocess.run([sys.executable, "-m", "pytest", "gateway/integration/test_central.py", "-q", "-p", "no:cacheprovider",
                         "--junitxml=/tmp/central.xml"], capture_output=True, timeout=240)
if result.returncode:
    sys.stdout.buffer.write(result.stdout + result.stderr)
    raise SystemExit(result.returncode)
xml = Path("/tmp/central.xml").read_bytes()
root = ET.fromstring(xml)
cases = root.findall(".//testcase")
assert cases and not any(case.find(tag) is not None for case in cases for tag in ("failure", "error", "skipped"))
assert os.geteuid() == 10001 and sorted(os.listdir("/sys/class/net")) == ["lo"]
packages = {}
for line in Path("gateway/central-test.lock").read_text().splitlines():
    if line and not line.startswith("#"):
        name, expected = line.split("==")
        packages[name] = metadata.version(name)
        assert packages[name] == expected
check = subprocess.run([sys.executable, "-m", "pip", "check"], capture_output=True)
assert check.returncode == 0, check.stdout
print(json.dumps({"tests": len(cases), "failures": 0, "uid": os.geteuid(), "interfaces": sorted(os.listdir("/sys/class/net")),
                  "root_read_only": bool(os.statvfs("/").f_flag & os.ST_RDONLY),
                  "python": sys.version.split()[0], "packages": packages, "pip_check": check.stdout.decode().strip(),
                  "junit_b64": base64.b64encode(xml).decode(), "pytest_log": result.stdout.decode()}))
