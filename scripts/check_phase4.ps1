param([switch]$UseWSL, [string]$WSLDistro = 'Ubuntu')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$projectPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
$backend = @()
if ($UseWSL) { $backend += @('--wsl-distro', $WSLDistro) }
Push-Location $projectRoot
try {
    New-Item -ItemType Directory -Path results/phase4 -Force | Out-Null
    & $projectPython scripts/build_specs.py --check
    if ($LASTEXITCODE -ne 0) { throw 'Frozen protocol drifted.' }
    & $projectPython scripts/freeze_phase3_policy.py --check
    if ($LASTEXITCODE -ne 0) { throw 'Frozen B/C policy drifted.' }
    & $projectPython -m pytest -q --junitxml results/phase4/pytest.xml 2>&1 | Tee-Object -FilePath results/phase4/pytest.txt
    if ($LASTEXITCODE -ne 0) { throw 'Host regression/config tests failed.' }
    foreach ($action in @('preflight','init','validate','up','acceptance')) {
        & $projectPython scripts/chain.py $action @backend
        if ($LASTEXITCODE -ne 0) { throw "Real Besu $action failed; see phase4 evidence and private diagnostic logs." }
    }
    & $projectPython scripts/check_phase4_lifecycle.py @backend
    if ($LASTEXITCODE -ne 0) { throw 'Real full down/up persistence or WSL session cleanup failed.' }
    & npm.cmd test 2>&1 | Tee-Object -FilePath results/phase4/hardhat.txt
    if ($LASTEXITCODE -ne 0) { throw 'Original Hardhat regression failed.' }
    & $projectPython scripts/write_phase4_report.py
    if ($LASTEXITCODE -ne 0) { throw 'Network evidence verification failed.' }
}
finally { Pop-Location }
