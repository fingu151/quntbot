param(
    [int]$Port = 8520,
    [string]$HostAddress = "0.0.0.0",
    [string]$BrowserAddress = "localhost",
    [string]$PythonPath = ".\venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $ProjectRoot
$Utf8NoBom = New-Object System.Text.UTF8Encoding $false
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$env:PYTHONIOENCODING = "utf-8"

$LogDir = Join-Path $ProjectRoot ".tmp"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$StreamlitLogPath = Join-Path $LogDir "public_dashboard_streamlit.log"

& $PythonPath -m streamlit run scripts\public_portfolio_dashboard.py `
    --server.port $Port `
    --server.address $HostAddress `
    --browser.serverAddress $BrowserAddress `
    --browser.serverPort $Port `
    --browser.gatherUsageStats=false 2>&1 | Tee-Object -FilePath $StreamlitLogPath -Append
