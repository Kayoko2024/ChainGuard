param([switch]$UseWSL, [switch]$RequireDocker, [string]$WSLDistro = 'Ubuntu')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$projectPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
Push-Location $projectRoot
try {
    New-Item -ItemType Directory -Path results/phase1 -Force | Out-Null
    & $projectPython scripts/build_specs.py --check
    if ($LASTEXITCODE -ne 0) { throw 'Frozen generated specifications drifted.' }
    & $projectPython -m pytest -q --junitxml results/phase1/pytest.xml 2>&1 | Tee-Object -FilePath results/phase1/pytest.txt
    if ($LASTEXITCODE -ne 0) { throw 'Python tests failed.' }
    & npm.cmd test 2>&1 | Tee-Object -FilePath results/phase1/hardhat.txt
    if ($LASTEXITCODE -ne 0) { throw 'Hardhat tests failed.' }
    & $projectPython scripts/smoke_gateway.py
    if ($LASTEXITCODE -ne 0) { throw 'Real local gateway startup failed.' }
    $environmentArguments = @('scripts/check_environment.py')
    if ($UseWSL) { $environmentArguments += @('--require-docker','--wsl-distro',$WSLDistro) }
    elseif ($RequireDocker) { $environmentArguments += '--require-docker' }
    & $projectPython @environmentArguments
    if ($LASTEXITCODE -ne 0) { throw 'Environment compatibility check failed.' }
    if ($UseWSL -or $RequireDocker) {
        $smokeArguments = @('scripts/smoke_compose.py')
        if ($UseWSL) { $smokeArguments += @('--wsl-distro',$WSLDistro) }
        & $projectPython @smokeArguments
        if ($LASTEXITCODE -ne 0) { throw 'Real Compose gateway startup failed.' }
    }
    $reportArguments = @('scripts/write_phase1_report.py')
    if ($UseWSL -or $RequireDocker) { $reportArguments += '--include-compose' }
    & $projectPython @reportArguments
    if ($LASTEXITCODE -ne 0) { throw 'Acceptance evidence generation failed.' }
}
finally { Pop-Location }
