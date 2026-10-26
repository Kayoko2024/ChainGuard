param([string]$PythonExecutable = 'python')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
        & $PythonExecutable -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Python virtual environment creation failed.' }
    }
    $projectPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
    & $projectPython -m pip install --disable-pip-version-check -r requirements-dev.lock
    if ($LASTEXITCODE -ne 0) { throw 'Locked Python dependency installation failed.' }
    & $projectPython -m pip install --disable-pip-version-check --no-deps --no-build-isolation -e .
    if ($LASTEXITCODE -ne 0) { throw 'Editable gateway installation failed.' }
    & npm.cmd ci --ignore-scripts --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { throw 'Locked npm workspace installation failed.' }
    if (-not (Test-Path -LiteralPath '.env')) { Copy-Item -LiteralPath '.env.example' -Destination '.env' }
    & $projectPython scripts/check_environment.py
    if ($LASTEXITCODE -ne 0) { throw 'Local development environment check failed.' }
}
finally { Pop-Location }
