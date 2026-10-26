param([switch]$UseWSL, [string]$WSLDistro = 'Ubuntu')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$projectPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
Push-Location $projectRoot
try {
    New-Item -ItemType Directory -Path results/phase2 -Force | Out-Null
    & $projectPython scripts/build_specs.py --check
    if ($LASTEXITCODE -ne 0) { throw 'Frozen specifications drifted.' }
    & $projectPython -m pytest -q --junitxml results/phase2/pytest.xml 2>&1 | Tee-Object -FilePath results/phase2/pytest.txt
    if ($LASTEXITCODE -ne 0) { throw 'Host protocol/gateway/scaffold tests failed.' }
    & npm.cmd test 2>&1 | Tee-Object -FilePath results/phase2/hardhat.txt
    if ($LASTEXITCODE -ne 0) { throw 'Original Hardhat regression failed.' }
    foreach ($suite in @('resources', 'tools', 'evidence')) {
        $containerArguments = @('scripts/run_phase2_container.py', '--suite', $suite)
        if ($UseWSL) { $containerArguments += @('--wsl-distro', $WSLDistro) }
        & $projectPython @containerArguments
        if ($LASTEXITCODE -ne 0) { throw "Actual isolated container suite failed: $suite" }
    }
    & $projectPython scripts/write_phase2_report.py
    if ($LASTEXITCODE -ne 0) { throw 'Phase 2 evidence validation failed.' }
}
finally { Pop-Location }
