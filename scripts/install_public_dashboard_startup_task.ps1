param(
    [string]$TaskName = "QuntbotPublicDashboard",
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
$PowerShellArgs = "-NoProfile -ExecutionPolicy Bypass -File `"$StartScript`" -Port $Port -HostAddress $HostAddress -BrowserAddress $BrowserAddress -RefreshIntervalMinutes $RefreshIntervalMinutes -RunTimeoutMinutes $RunTimeoutMinutes"
if ($SkipSupplementalSources) {
    $PowerShellArgs += " -SkipSupplementalSources"
}
$TaskRun = "powershell.exe $PowerShellArgs"

if ($WhatIf) {
    Write-Output "Would create Windows logon task:"
    Write-Output "task_name=$TaskName"
    Write-Output "trigger=ONLOGON"
    Write-Output "command=$TaskRun"
    exit 0
}

schtasks.exe /Create /TN $TaskName /SC ONLOGON /RL LIMITED /TR $TaskRun /F
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Output "created_startup_task=$TaskName"
Write-Output "trigger=ONLOGON"
Write-Output "port=$Port"
Write-Output "host_address=$HostAddress"
Write-Output "refresh_interval_minutes=$RefreshIntervalMinutes"
