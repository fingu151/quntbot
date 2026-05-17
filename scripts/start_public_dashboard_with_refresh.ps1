param(
    [int]$Port = 8520,
    [string]$HostAddress = "0.0.0.0",
    [string]$BrowserAddress = "localhost",
    [int]$RefreshIntervalMinutes = 30,
    [int]$RunTimeoutMinutes = 10,
    [string]$PythonPath = ".\venv\Scripts\python.exe",
    [string]$RefreshedThrough = "2026-05-15",
    [switch]$IncludeSupplementalDiscovery,
    [switch]$SkipSupplementalSources
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $ProjectRoot
$Utf8NoBom = New-Object System.Text.UTF8Encoding $false
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$env:PYTHONIOENCODING = "utf-8"

$RefreshScript = Join-Path $ProjectRoot "scripts\refresh_public_portfolio_snapshot.ps1"
$LogDir = Join-Path $ProjectRoot ".tmp"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$StreamlitLogPath = Join-Path $LogDir "public_dashboard_streamlit.log"

Write-Host "Starting public dashboard..."
Write-Host "Same PC URL: http://localhost:$Port/"
Write-Host "LAN URL: use http://<THIS_PC_LOCAL_IP>:$Port/ from another device."
Write-Host "Binding address: $HostAddress"

$RefreshArgs = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", "`"$RefreshScript`"",
    "-IntervalMinutes", "$RefreshIntervalMinutes",
    "-RunTimeoutMinutes", "$RunTimeoutMinutes",
    "-PythonPath", "`"$PythonPath`"",
    "-RefreshedThrough", "$RefreshedThrough"
)
if ($IncludeSupplementalDiscovery) {
    $RefreshArgs += "-IncludeSupplementalDiscovery"
}
if ($SkipSupplementalSources) {
    $RefreshArgs += "-SkipSupplementalSources"
}

Start-Process powershell.exe -ArgumentList $RefreshArgs -WindowStyle Hidden

& $PythonPath -m streamlit run scripts\public_portfolio_dashboard.py `
    --server.port $Port `
    --server.address $HostAddress `
    --browser.serverAddress $BrowserAddress `
    --browser.serverPort $Port `
    --browser.gatherUsageStats=false 2>&1 | Tee-Object -FilePath $StreamlitLogPath -Append

$StreamlitExitCode = $LASTEXITCODE
$ExitMessage = "Streamlit exited. exit_code=$StreamlitExitCode"
Write-Host $ExitMessage
Add-Content -Path $StreamlitLogPath -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $ExitMessage" -Encoding UTF8
