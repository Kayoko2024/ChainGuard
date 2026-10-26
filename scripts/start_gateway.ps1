$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonExecutable = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExecutable)) { throw 'Run scripts/bootstrap.ps1 first.' }
Push-Location $projectRoot
try {
    & $pythonExecutable scripts/run_gateway.py
    if ($LASTEXITCODE -ne 0) { throw "Gateway exited with code $LASTEXITCODE" }
}
finally { Pop-Location }
