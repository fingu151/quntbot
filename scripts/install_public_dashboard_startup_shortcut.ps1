param(
    [string]$ShortcutName = "Quntbot Public Dashboard.lnk",
    [int]$Port = 8520,
    [string]$HostAddress = "0.0.0.0",
    [string]$BrowserAddress = "localhost",
    [int]$RefreshIntervalMinutes = 30,
    [int]$RunTimeoutMinutes = 10,
    [switch]$SkipSupplementalSources,
    [switch]$WhatIf
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$StartScript = Join-Path $ProjectRoot "scripts\start_public_dashboard_with_refresh.ps1"
$StartupDir = [Environment]::GetFolderPath("Startup")
$ShortcutPath = Join-Path $StartupDir $ShortcutName
$PowerShellArgs = "-NoProfile -ExecutionPolicy Bypass -File `"$StartScript`" -Port $Port -HostAddress $HostAddress -BrowserAddress $BrowserAddress -RefreshIntervalMinutes $RefreshIntervalMinutes -RunTimeoutMinutes $RunTimeoutMinutes"
if ($SkipSupplementalSources) {
    $PowerShellArgs += " -SkipSupplementalSources"
}

if ($WhatIf) {
    Write-Output "Would create startup shortcut:"
    Write-Output "shortcut_path=$ShortcutPath"
    Write-Output "target=powershell.exe"
    Write-Output "arguments=$PowerShellArgs"
    exit 0
}

$Shell = New-Object -ComObject WScript.Shell
$Shortcut = $Shell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = "powershell.exe"
$Shortcut.Arguments = $PowerShellArgs
$Shortcut.WorkingDirectory = $ProjectRoot.Path
$Shortcut.WindowStyle = 7
$Shortcut.Description = "Start Quntbot public dashboard and refresh loop."
$Shortcut.Save()

Write-Output "created_startup_shortcut=$ShortcutPath"
Write-Output "port=$Port"
Write-Output "host_address=$HostAddress"
Write-Output "refresh_interval_minutes=$RefreshIntervalMinutes"
