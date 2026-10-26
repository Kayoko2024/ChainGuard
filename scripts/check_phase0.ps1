$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonExecutable = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExecutable)) {
    throw 'Create .venv and install requirements-dev.lock first; see README.md.'
}
Push-Location $projectRoot
try {
    New-Item -ItemType Directory -Path 'results\phase0' -Force | Out-Null
    & $pythonExecutable scripts/build_specs.py --check
    if ($LASTEXITCODE -ne 0) { throw 'Generated interface files are out of date.' }
    & $pythonExecutable -m pytest tests/python -q --junitxml results/phase0/pytest.xml 2>&1 | Tee-Object -FilePath results/phase0/pytest.txt
    if ($LASTEXITCODE -ne 0) { throw 'Python protocol checks failed.' }
    & npm.cmd test 2>&1 | Tee-Object -FilePath results/phase0/hardhat.txt
    if ($LASTEXITCODE -ne 0) { throw 'Solidity protocol checks failed.' }
    & $pythonExecutable -m pip check
    if ($LASTEXITCODE -ne 0) { throw 'Python dependency check failed.' }
    & $pythonExecutable scripts/write_acceptance_report.py
    if ($LASTEXITCODE -ne 0) { throw 'Acceptance report generation failed.' }
}
finally {
    Pop-Location
}
