param(
    [ValidateSet('validate','up','down','status','logs')][string]$Action = 'validate',
    [switch]$UseWSL,
    [string]$WSLDistro = 'Ubuntu',
    [string]$WSLUser = 'root'
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$composeArguments = @('compose','--project-directory',$projectRoot,'-f',(Join-Path $projectRoot 'compose.yaml'))
if (Test-Path -LiteralPath (Join-Path $projectRoot '.env')) { $composeArguments += @('--env-file',(Join-Path $projectRoot '.env')) }
if ($UseWSL) {
    $drive = [System.IO.Path]::GetPathRoot($projectRoot).Substring(0,1).ToLowerInvariant()
    $linuxRoot = '/mnt/' + $drive + '/' + $projectRoot.Substring(3).Replace([char]92,[char]47)
    $composeArguments = @('compose','--project-directory',$linuxRoot,'-f',($linuxRoot + '/compose.yaml'))
    if (Test-Path -LiteralPath (Join-Path $projectRoot '.env')) { $composeArguments += @('--env-file',($linuxRoot + '/.env')) }
}
$composeArguments += switch ($Action) {
    'validate' { @('config','--quiet') }
    'up' { @('up','--build','--wait','--wait-timeout','60') }
    'down' { @('down') }
    'status' { @('ps','--format','json') }
    'logs' { @('logs','--no-color','--tail','100') }
}
Push-Location $projectRoot
try {
    if ($UseWSL -and $Action -eq 'up') {
        $projectPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
        if (-not (Test-Path -LiteralPath $projectPython)) { throw 'Run bootstrap.ps1 before the Windows/WSL build wrapper.' }
        & $projectPython scripts/build_gateway_image.py --wsl-distro $WSLDistro --wsl-user $WSLUser
        if ($LASTEXITCODE -ne 0) { throw 'Allowlisted WSL build failed; see .local/gateway-build.log.' }
        $composeArguments = $composeArguments | ForEach-Object { if ($_ -eq '--build') { '--no-build' } else { $_ } }
    }
    if ($UseWSL) { & wsl.exe -d $WSLDistro -u $WSLUser -- docker @composeArguments }
    else {
        if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Docker CLI missing. Install an Engine/Compose or use -UseWSL with an existing WSL Engine.' }
        & docker @composeArguments
    }
    if ($LASTEXITCODE -ne 0) { throw "Docker Compose $Action failed with exit code $LASTEXITCODE" }
}
finally { Pop-Location }
