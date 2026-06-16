param(
    [string]$PythonPath = ".\venv\Scripts\python.exe",
    [int]$LookbackDays = 14,
    [string]$StartDate = "",
    [string]$EndDate = "",
    [int]$HankyungPages = 15,
    [int]$MiraePages = 20,
    [int]$CommandTimeoutMinutes = 90,
    [switch]$IncludeSupplementalDiscovery,
    [switch]$SkipResearchSync,
    [switch]$Force
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
$LogPath = Join-Path $LogDir "public_research_dashboard_daily_refresh.log"
$LockPath = Join-Path $LogDir "public_research_dashboard_daily_refresh.lock"
$SuccessMarkerPath = Join-Path $LogDir "public_research_dashboard_daily_refresh_success.txt"

function Get-KstToday {
    $tz = [System.TimeZoneInfo]::FindSystemTimeZoneById("Korea Standard Time")
    return [System.TimeZoneInfo]::ConvertTimeFromUtc([DateTime]::UtcNow, $tz).Date
}

function Write-RefreshLog {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$timestamp $Message" | Tee-Object -FilePath $LogPath -Append
}

function Format-ProcessArguments {
    param([string[]]$Arguments)
    $quoted = @()
    foreach ($arg in $Arguments) {
        if ($arg -match '[\s"]') {
            $quoted += '"' + ($arg -replace '"', '\"') + '"'
        } else {
            $quoted += $arg
        }
    }
    return ($quoted -join " ")
}

function Invoke-LoggedPython {
    param(
        [string]$StepName,
        [string[]]$Arguments
    )

    Write-RefreshLog "step_start=$StepName"
    Write-RefreshLog ("running=" + $PythonPath + " " + ($Arguments -join " "))

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $PythonPath
    $psi.WorkingDirectory = $ProjectRoot
    $psi.Arguments = Format-ProcessArguments $Arguments
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.CreateNoWindow = $true

    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $psi
    [void]$process.Start()
    $stdoutTask = $process.StandardOutput.ReadToEndAsync()
    $stderrTask = $process.StandardError.ReadToEndAsync()

    $completed = $process.WaitForExit($CommandTimeoutMinutes * 60 * 1000)
    if (-not $completed) {
        try {
            $process.Kill()
            $process.WaitForExit()
        } catch {
            Write-RefreshLog "failed_to_stop_timed_out_process step=$StepName error=$($_.Exception.Message)"
        }
    } else {
        $process.WaitForExit()
    }

    $stdoutText = $stdoutTask.Result
    $stderrText = $stderrTask.Result
    if ($stdoutText) {
        $stdoutText -split "`r?`n" | Where-Object { $_ } | Tee-Object -FilePath $LogPath -Append
    }
    if ($stderrText) {
        $stderrText -split "`r?`n" | Where-Object { $_ } | Tee-Object -FilePath $LogPath -Append
    }

    $exitCode = if ($completed) { $process.ExitCode } else { 124 }
    Write-RefreshLog "step_done=$StepName exit_code=$exitCode"
    if ($exitCode -ne 0) {
        throw "step_failed=$StepName exit_code=$exitCode"
    }
}

if ($LookbackDays -lt 1) {
    throw "LookbackDays must be at least 1."
}
if ($CommandTimeoutMinutes -lt 1) {
    throw "CommandTimeoutMinutes must be at least 1."
}

$today = Get-KstToday
if (-not $EndDate) {
    $EndDate = $today.ToString("yyyy-MM-dd")
}
if (-not $StartDate) {
    $StartDate = $today.AddDays(-1 * $LookbackDays).ToString("yyyy-MM-dd")
}

$lockHandle = $null
try {
    try {
        $lockHandle = [System.IO.File]::Open($LockPath, [System.IO.FileMode]::OpenOrCreate, [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::None)
    } catch {
        Write-RefreshLog "daily_research_dashboard_refresh_skipped=already_running"
        exit 0
    }

    if ((-not $Force) -and (Test-Path $SuccessMarkerPath)) {
        $lastSuccessDate = (Get-Content -Path $SuccessMarkerPath -ErrorAction SilentlyContinue | Select-Object -First 1)
        if ($lastSuccessDate -eq $EndDate) {
            Write-RefreshLog "daily_research_dashboard_refresh_skipped=already_completed date=$EndDate"
            exit 0
        }
    }

    Write-RefreshLog "daily_research_dashboard_refresh_start start_date=$StartDate end_date=$EndDate lookback_days=$LookbackDays skip_research_sync=$SkipResearchSync include_supplemental_discovery=$IncludeSupplementalDiscovery"

    if (-not $SkipResearchSync) {
        Invoke-LoggedPython "research_hankyung" @(
            "scripts\run_hankyung_research_readonly_pipeline.py",
            "--start-date", $StartDate,
            "--end-date", $EndDate,
            "--as-of-date", $EndDate,
            "--pages", "$HankyungPages",
            "--limit", "3000",
            "--top-n", "100"
        )

        Invoke-LoggedPython "research_mirae" @(
            "scripts\run_mirae_research_readonly_pipeline.py",
            "--start-date", $StartDate,
            "--end-date", $EndDate,
            "--as-of-date", $EndDate,
            "--pages", "$MiraePages",
            "--limit", "1000",
            "--top-n", "100"
        )
    }

    $dashboardArgs = @(
        "-m", "scripts.refresh_public_dashboard_artifacts",
        "--snapshot-output", "data\public_portfolio_snapshot.json",
        "--refreshed-through", $EndDate,
        "--fallback-existing-snapshot",
        "--skip-supplemental"
    )
    if ($IncludeSupplementalDiscovery) {
        $dashboardArgs += "--include-supplemental-discovery"
    }
    Invoke-LoggedPython "public_dashboard_artifacts" $dashboardArgs

    Invoke-LoggedPython "public_dashboard_ops" @(
        "-m", "scripts.public_dashboard_ops",
        "--max-age-minutes", "1440"
    )

    Set-Content -Path $SuccessMarkerPath -Value $EndDate -Encoding UTF8
    Write-RefreshLog "daily_research_dashboard_refresh_completed=true"
    Write-RefreshLog "orders_submitted=0"
} finally {
    if ($null -ne $lockHandle) {
        $lockHandle.Close()
    }
}
