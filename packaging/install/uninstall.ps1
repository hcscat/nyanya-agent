param(
    [string]$InstallDir = "$env:LOCALAPPDATA\nyanya-agent",
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

if ($PurgeData) {
    if (Test-Path $InstallDir) {
        Remove-Item -Recurse -Force $InstallDir
    }
    Write-Host "Removed install directory: $InstallDir"
} else {
    Write-Host "Commands removed. Install directory kept: $InstallDir"
    Write-Host "Run with -PurgeData to remove local config/data as well."
}
