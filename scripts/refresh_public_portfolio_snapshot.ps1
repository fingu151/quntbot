param(
    [int]$IntervalMinutes = 30,
    [string]$PythonPath = ".\venv\Scripts\python.exe",
    [string]$OutputPath = "data\public_portfolio_snapshot.json"
)

$ErrorActionPreference = "Continue"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $ProjectRoot

$LogDir = Join-Path $ProjectRoot ".tmp"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogPath = Join-Path $LogDir "public_portfolio_snapshot_refresh.log"

function Write-RefreshLog {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$timestamp $Message" | Tee-Object -FilePath $LogPath -Append
}

if ($IntervalMinutes -lt 1) {
    Write-RefreshLog "IntervalMinutes must be at least 1."
    exit 2
}

Write-RefreshLog "Starting public snapshot refresh loop. interval_minutes=$IntervalMinutes output=$OutputPath"

while ($true) {
    Write-RefreshLog "Running snapshot refresh..."
    & $PythonPath scripts\generate_public_portfolio_snapshot.py --output $OutputPath 2>&1 |
        Tee-Object -FilePath $LogPath -Append

    if ($LASTEXITCODE -eq 0) {
        Write-RefreshLog "Snapshot refresh completed."
    } else {
        Write-RefreshLog "Snapshot refresh failed. exit_code=$LASTEXITCODE"
    }

    Write-RefreshLog "Sleeping for $IntervalMinutes minutes."
    Start-Sleep -Seconds ($IntervalMinutes * 60)
}
