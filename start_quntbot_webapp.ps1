# ============================================================
#  quntbot webapp — keep the dashboard live.
#    1) serve the static webapp on $Port (repo root)
#    2) regenerate data/public_portfolio_snapshot.json every
#       $RefreshMinutes (best-effort; --fallback-existing-snapshot
#       reuses the previous snapshot if KIS is unreachable)
#  The web page (snapshot.js) auto-polls every 60s, so a new
#  rebalance shows up without a manual reload.
#  Registered as an ONLOGON task by install_quntbot_webapp_task.ps1.
# ============================================================
param(
    [int]$Port = 5500,
    [int]$RefreshMinutes = 30
)
$ErrorActionPreference = 'Continue'
$Root = $PSScriptRoot
Set-Location $Root

$Py = Join-Path $Root 'venv\Scripts\python.exe'
if (-not (Test-Path $Py)) { $Py = 'python' }

$LogDir = Join-Path $Root '.tmp'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Log = Join-Path $LogDir 'quntbot_webapp.log'
function Write-WebLog([string]$m) {
    "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $m" | Tee-Object -FilePath $Log -Append
}

# 1) static server (only if nothing is already listening on $Port)
$listening = $false
try { $listening = [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) } catch {}
if (-not $listening) {
    Start-Process -WindowStyle Hidden -FilePath $Py -ArgumentList @('-m', 'http.server', "$Port") -WorkingDirectory $Root
    Write-WebLog "started static server on port $Port"
} else {
    Write-WebLog "static server already listening on port $Port"
}
Write-WebLog "open http://localhost:$Port/webapp/ui_kits/toss-invest/index.html"

# 2) snapshot refresh loop
while ($true) {
    try {
        & $Py -m scripts.generate_public_portfolio_snapshot --fallback-existing-snapshot 2>&1 | Out-Null
        Write-WebLog "snapshot refreshed"
    } catch {
        Write-WebLog "snapshot refresh failed: $($_.Exception.Message)"
    }
    Start-Sleep -Seconds ($RefreshMinutes * 60)
}
