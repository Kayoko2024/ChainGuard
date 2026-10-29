param([Parameter(Mandatory=$true)][string]$Config)
$ErrorActionPreference='Stop'
$phase10ConfigPath=(Resolve-Path -LiteralPath $Config).Path
$phase10Root=Split-Path -Parent $PSScriptRoot
$phase10PrivateRoot=[IO.Path]::GetFullPath((Join-Path $phase10Root '.local\phase10'))+[IO.Path]::DirectorySeparatorChar
if(-not $phase10ConfigPath.StartsWith($phase10PrivateRoot,[StringComparison]::OrdinalIgnoreCase)){throw 'Only a local phase10 config is supported'}
$phase10Runtime=Get-Content -LiteralPath $phase10ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
foreach($phase10TargetConfig in @($phase10ConfigPath,$phase10Runtime.audit_config)) {
  $phase10Targets=Get-CimInstance Win32_Process | Where-Object {$_.Name -eq 'python.exe' -and $_.CommandLine -like "*$phase10TargetConfig*" -and $_.CommandLine -match 'chainguard_gateway.phase10_(api|audit)'}
  foreach($phase10Target in $phase10Targets){Stop-Process -Id $phase10Target.ProcessId -Force -ErrorAction SilentlyContinue}
}
& (Join-Path $PSScriptRoot 'start_phase10.ps1') -Config $phase10ConfigPath
