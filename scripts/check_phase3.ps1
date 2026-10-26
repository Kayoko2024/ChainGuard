param([switch]$UseWSL, [string]$WSLDistro = 'Ubuntu')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$projectPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
Push-Location $projectRoot
try {
    New-Item -ItemType Directory -Path results/phase3 -Force | Out-Null
    & $projectPython scripts/build_specs.py --check
    if ($LASTEXITCODE -ne 0) { throw 'Original frozen specifications drifted.' }
    & $projectPython scripts/freeze_phase3_policy.py --check
    if ($LASTEXITCODE -ne 0) { throw 'Shared B/C policy drifted.' }
    & $projectPython -m pytest -q --junitxml results/phase3/pytest.xml 2>&1 | Tee-Object -FilePath results/phase3/pytest.txt
    if ($LASTEXITCODE -ne 0) { throw 'Host gateway/protocol/policy/audit tests failed.' }
    & npm.cmd test 2>&1 | Tee-Object -FilePath results/phase3/hardhat.txt
    if ($LASTEXITCODE -ne 0) { throw 'Hardhat regression failed.' }
    $backend = @()
    if ($UseWSL) { $backend += @('--wsl-distro', $WSLDistro) }
    if (-not (Test-Path -LiteralPath results/phase3/wheels.json)) {
        & $projectPython scripts/prepare_phase3_wheels.py
        if ($LASTEXITCODE -ne 0) { throw 'Exact Linux wheel preparation failed.' }
    }
    & $projectPython scripts/run_phase3_container.py @backend
    if ($LASTEXITCODE -ne 0) { throw 'Actual A/B HTTP/tool integration tests failed.' }
    & $projectPython scripts/run_phase3_container.py @backend --evidence
    if ($LASTEXITCODE -ne 0) { throw 'Actual Uvicorn/side-effect/restart acceptance failed.' }
    foreach ($suite in @('resources', 'tools')) {
        & $projectPython scripts/run_phase2_container.py @backend --suite $suite
        if ($LASTEXITCODE -ne 0) { throw "Original sandbox regression failed: $suite" }
    }
    & $projectPython scripts/write_phase3_report.py
    if ($LASTEXITCODE -ne 0) { throw 'Phase 3 evidence validation failed.' }
}
finally { Pop-Location }
