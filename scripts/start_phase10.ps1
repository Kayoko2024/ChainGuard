param([Parameter(Mandatory=$true)][string]$Config)
$ErrorActionPreference='Stop'
$phase10ConfigPath=(Resolve-Path -LiteralPath $Config).Path
$phase10Runtime=Get-Content -LiteralPath $phase10ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
$phase10Root=Split-Path -Parent $PSScriptRoot
$phase10Python=Join-Path $phase10Root '.venv\Scripts\python.exe'
$env:PYTHONPATH="$phase10Root\gateway\src;$phase10Root\sandbox_tools\src;$phase10Root\agent\src"
$env:PYTHONUTF8='1'
$phase10Processes=@()
foreach($phase10Service in @(@{module='chainguard_gateway.phase10_api'; config=$phase10ConfigPath; name='business'},@{module='chainguard_gateway.phase10_audit'; config=$phase10Runtime.audit_config; name='audit'})) {
  $phase10Log=Join-Path (Split-Path -Parent $phase10ConfigPath) $phase10Service.name
  $phase10Process=Start-Process -FilePath $phase10Python -ArgumentList @('-m',$phase10Service.module,'--config',('"'+$phase10Service.config+'"')) -WorkingDirectory $phase10Root -WindowStyle Hidden -PassThru -RedirectStandardOutput ($phase10Log+'.stdout.log') -RedirectStandardError ($phase10Log+'.stderr.log')
  $phase10Processes+=@{name=$phase10Service.name; pid=$phase10Process.Id}
}
$phase10Processes | ConvertTo-Json | Set-Content -LiteralPath (Join-Path (Split-Path -Parent $phase10ConfigPath) 'processes.json') -Encoding UTF8
$phase10AuditRuntime=Get-Content -LiteralPath $phase10Runtime.audit_config -Raw -Encoding UTF8 | ConvertFrom-Json
foreach($phase10Port in @($phase10Runtime.port,$phase10AuditRuntime.port)) {
  $phase10Ready=$false
  for($phase10Attempt=0;$phase10Attempt -lt 40;$phase10Attempt++) {
    try { $phase10Health=Invoke-RestMethod -Uri "http://127.0.0.1:$phase10Port/health/live" -TimeoutSec 1; if($phase10Health.status -eq 'alive'){$phase10Ready=$true;break} } catch {}
    Start-Sleep -Milliseconds 250
  }
  if(-not $phase10Ready){throw "Phase10 localhost readiness failed on port $phase10Port"}
}
Write-Output 'Started localhost business and read-only audit processes; credentials remain in the local ignored directory.'
