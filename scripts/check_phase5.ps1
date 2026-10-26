param(
    [switch]$DeployBesu,
    [string]$VerifyRun,
    [string]$EvidenceDirectory
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$projectPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
if ($DeployBesu -and $VerifyRun) { throw 'Use DeployBesu or VerifyRun separately.' }
if (-not $EvidenceDirectory) {
    $stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')
    $EvidenceDirectory = Join-Path $projectRoot "results\phase5\checks\$stamp"
}
$resolvedEvidence = [IO.Path]::GetFullPath($EvidenceDirectory)
$allowedEvidence = [IO.Path]::GetFullPath((Join-Path $projectRoot 'results\phase5')) + [IO.Path]::DirectorySeparatorChar
if (-not $resolvedEvidence.StartsWith($allowedEvidence, [StringComparison]::OrdinalIgnoreCase)) { throw 'Evidence directory must be under results/phase5.' }
if (Test-Path -LiteralPath $resolvedEvidence) { throw 'Evidence directory exists; use a new directory.' }
New-Item -ItemType Directory -Path $resolvedEvidence | Out-Null
function Invoke-Check([string]$Name, [scriptblock]$Operation) {
    $logFile = Join-Path $resolvedEvidence "$Name.txt"
    & $Operation *> $logFile
    $commandCode = $LASTEXITCODE
    Get-Content -LiteralPath $logFile
    if ($commandCode -ne 0) { throw "$Name failed ($commandCode); retained $logFile" }
}
Push-Location $projectRoot
try {
    Invoke-Check 'spec' { & $projectPython scripts/build_specs.py --check }
    Invoke-Check 'shared-policy' { & $projectPython scripts/freeze_phase3_policy.py --check }
    Invoke-Check 'pytest' { & $projectPython -m pytest -q --junitxml (Join-Path $resolvedEvidence 'pytest.xml') }
    Invoke-Check 'hardhat' { & npm.cmd test }
    if ($DeployBesu) {
        $VerifyRun = Join-Path $resolvedEvidence 'besu'
        Invoke-Check 'besu-deploy' { & node.exe scripts/deploy_phase5.cjs --out $VerifyRun }
    }
    if ($VerifyRun) {
        Invoke-Check 'besu-python-verification' { & $projectPython scripts/verify_phase5.py $VerifyRun }
    }
    Write-Host "Phase 5 checks PASS; evidence: $resolvedEvidence"
}
finally { Pop-Location }
