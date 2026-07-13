param(
    [string]$InstallDir = "$env:LOCALAPPDATA\Programs\NyaNya Agent",
    [string]$StateDir = "$env:LOCALAPPDATA\NyaNya Agent",
    [string]$BinDir = "$env:USERPROFILE\.local\bin",
    [switch]$PurgeData
)

$ErrorActionPreference = "Stop"

foreach ($command in @("nyanya", "nyanya-agent", "nyanyactl", "nyanya-discord", "nyanya-telegram", "nyanya-dashboard", "nyanya-memory-worker")) {
    $path = Join-Path $BinDir "$command.ps1"
    if (Test-Path $path) {
        Remove-Item -Force $path
    }
}

if (Test-Path $InstallDir) {
    Remove-Item -Recurse -Force $InstallDir
}
Write-Host "Removed code directory: $InstallDir"

if ($PurgeData) {
    if (Test-Path $StateDir) {
        Remove-Item -Recurse -Force $StateDir
    }
    Write-Host "Removed state directory: $StateDir"
} else {
    Write-Host "User state kept: $StateDir"
    Write-Host "Run with -PurgeData to remove local config/data as well."
}
