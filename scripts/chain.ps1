param(
    [ValidateSet('preflight','init','validate','up','down','status','logs','health','acceptance')][string]$Action = 'health',
    [switch]$UseWSL,
    [string]$WSLDistro = 'Ubuntu'
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$projectPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
$backend = @()
if ($UseWSL) { $backend += @('--wsl-distro', $WSLDistro) }
Push-Location $projectRoot
try {
    & $projectPython scripts/chain.py $Action @backend
    if ($LASTEXITCODE -ne 0) { throw "Chain $Action failed ($LASTEXITCODE)" }
}
finally { Pop-Location }
