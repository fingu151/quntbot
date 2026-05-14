param(
    [int]$Port = 8520,
    [int]$RefreshIntervalMinutes = 30
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $ProjectRoot

$PythonPath = ".\venv\Scripts\python.exe"
$RefreshScript = Join-Path $ProjectRoot "scripts\refresh_public_portfolio_snapshot.ps1"

Start-Process powershell.exe -ArgumentList @(
    "-NoExit",
    "-ExecutionPolicy", "Bypass",
    "-File", "`"$RefreshScript`"",
    "-IntervalMinutes", "$RefreshIntervalMinutes"
) -WindowStyle Minimized

& $PythonPath -m streamlit run scripts\public_portfolio_dashboard.py --server.port $Port --browser.gatherUsageStats=false
