param(
    [string]$Source = "",
    [string]$InstallDir = "$env:LOCALAPPDATA\Programs\NyaNya Agent",
    [string]$StateDir = "$env:LOCALAPPDATA\NyaNya Agent",
    [string]$BinDir = "$env:USERPROFILE\.local\bin",
    [string]$RepoUrl = "https://github.com/hcscat/nyanya-agent.git",
    [switch]$Force,
    [switch]$SkipDeps
)

$ErrorActionPreference = "Stop"

function Require-Command($Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Missing required command: $Name"
    }
}

Require-Command python

New-Item -ItemType Directory -Force -Path $BinDir | Out-Null

$tempDir = $null
if ([string]::IsNullOrWhiteSpace($Source)) {
    Require-Command git
    $tempDir = New-Item -ItemType Directory -Path ([System.IO.Path]::Combine([System.IO.Path]::GetTempPath(), "nyanya-" + [System.Guid]::NewGuid().ToString()))
    git clone --depth 1 $RepoUrl (Join-Path $tempDir.FullName "nyanya-agent")
    $Source = Join-Path $tempDir.FullName "nyanya-agent"
}

if (-not (Test-Path (Join-Path $Source "pyproject.toml"))) {
    throw "Source path does not look like a nyanya-agent checkout: $Source"
}

$fullInstall = [System.IO.Path]::GetFullPath($InstallDir).TrimEnd([System.IO.Path]::DirectorySeparatorChar)
$fullSource = [System.IO.Path]::GetFullPath($Source).TrimEnd([System.IO.Path]::DirectorySeparatorChar)
if ($fullInstall -eq $fullSource -or $fullInstall -eq $env:USERPROFILE -or
    $fullInstall -eq [System.IO.Path]::GetPathRoot($fullInstall).TrimEnd([System.IO.Path]::DirectorySeparatorChar) -or
    $fullSource.StartsWith($fullInstall + [System.IO.Path]::DirectorySeparatorChar)) {
    throw "Unsafe install destination"
}

if (Test-Path $InstallDir) {
    $backup = "$InstallDir.backup.$(Get-Date -Format yyyyMMddHHmmss)"
    if ($Force -and (Test-Path $backup)) {
        Remove-Item -Recurse -Force $backup
    }
    Move-Item $InstallDir $backup
    Write-Host "Existing install moved to: $backup"
}

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
python (Join-Path $Source "src/nyanya_agent/distribution_copy.py") $Source $InstallDir
if ($LASTEXITCODE -ne 0) { throw "Public source copy failed" }

$envPath = Join-Path $StateDir ".env"
foreach ($name in @("config", "data", "downloads", "logs", "run", "sessions")) {
    New-Item -ItemType Directory -Force -Path (Join-Path $StateDir $name) | Out-Null
}
if (-not (Test-Path $envPath) -and (Test-Path (Join-Path $InstallDir ".env.example"))) {
    Copy-Item (Join-Path $InstallDir ".env.example") $envPath
}

python -m venv (Join-Path $StateDir ".venv")
$pythonExe = Join-Path $StateDir ".venv\Scripts\python.exe"
if (-not $SkipDeps) {
    & $pythonExe -m pip install --upgrade pip
    & $pythonExe -m pip install --upgrade "$InstallDir[bots,dashboard]"
}

function Write-Launcher($Name, $Module) {
    $path = Join-Path $BinDir "$Name.ps1"
    @"
`$env:NYANYA_PROJECT_ROOT = "$InstallDir"
`$env:NYANYA_HOME = "$StateDir"
`$env:NYANYA_ENV_FILE = "$envPath"
if ("$Name" -eq "nyanya" -and (Get-Command node -ErrorAction SilentlyContinue)) {
    & node "$InstallDir\dist\bin\nyanya.js" @args
    exit `$LASTEXITCODE
}
& "$pythonExe" -m "$Module" @args
exit `$LASTEXITCODE
"@ | Set-Content -Encoding UTF8 $path
}

Write-Launcher "nyanya" "nyanya_agent.core"
Write-Launcher "nyanya-agent" "nyanya_agent.core"
Write-Launcher "nyanyactl" "nyanya_agent.manager"
Write-Launcher "nyanya-discord" "nyanya_agent.discord_bridge"
Write-Launcher "nyanya-telegram" "nyanya_agent.telegram_bridge"
Write-Launcher "nyanya-dashboard" "nyanya_agent.dashboard_api"
Write-Launcher "nyanya-memory-worker" "nyanya_agent.memory_worker"

if ($tempDir) {
    Remove-Item -Recurse -Force $tempDir.FullName
}

Write-Host "NyaNya Agent installed."
Write-Host "Install dir: $InstallDir"
Write-Host "State dir: $StateDir"
Write-Host "Command dir: $BinDir"
Write-Host "Next: nyanya config; nyanya doctor; nyanya"
