param(
    [string]$PythonPath = ".\venv\Scripts\python.exe",
    [int]$Port = 8520,
    [string]$HostAddress = "0.0.0.0",
    [string]$BrowserAddress = "localhost",
    [int]$LookbackDays = 14,
    [int]$Workers = 1,
    [int]$TopN = 30,
    [int]$CommandTimeoutMinutes = 120,
    [switch]$OpenBrowser,
    [switch]$Force,
    [switch]$SkipDashboard,
    [switch]$SkipResearchSync,
    [switch]$SkipDataSync,
    [switch]$SkipRebalanceReview
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
$LogPath = Join-Path $LogDir "quntbot_login_workflow.log"
$StreamlitLogPath = Join-Path $LogDir "public_dashboard_streamlit.log"
$LockPath = Join-Path $LogDir "quntbot_login_workflow.lock"
$SuccessMarkerPath = Join-Path $LogDir "quntbot_login_workflow_success.txt"

function Get-KstToday {
    $tz = [System.TimeZoneInfo]::FindSystemTimeZoneById("Korea Standard Time")
    return [System.TimeZoneInfo]::ConvertTimeFromUtc([DateTime]::UtcNow, $tz).Date
}

function Write-WorkflowLog {
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
        [string[]]$Arguments,
        [switch]$AllowFailure
    )

    Write-WorkflowLog "step_start=$StepName"
    Write-WorkflowLog ("running=" + $PythonPath + " " + ($Arguments -join " "))

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
            Write-WorkflowLog "failed_to_stop_timed_out_process step=$StepName error=$($_.Exception.Message)"
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
    Write-WorkflowLog "step_done=$StepName exit_code=$exitCode"
    if ($exitCode -ne 0 -and -not $AllowFailure) {
        throw "step_failed=$StepName exit_code=$exitCode"
    }
    return $exitCode
}

function Test-TcpPort {
    param(
        [string]$HostName,
        [int]$Port
    )
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $connect = $client.BeginConnect($HostName, $Port, $null, $null)
        if (-not $connect.AsyncWaitHandle.WaitOne(1000, $false)) {
            return $false
        }
        $client.EndConnect($connect)
        return $true
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

function Start-PublicDashboard {
    if (Test-TcpPort -HostName "127.0.0.1" -Port $Port) {
        Write-WorkflowLog "dashboard_status=already_running port=$Port"
        return
    }

    $dashboardServerScript = Join-Path $ProjectRoot "scripts\start_public_dashboard_server.ps1"
    Start-Process powershell.exe -ArgumentList @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", "`"$dashboardServerScript`"",
        "-Port", "$Port",
        "-HostAddress", $HostAddress,
        "-BrowserAddress", $BrowserAddress,
        "-PythonPath", $PythonPath
    ) -WindowStyle Hidden

    Start-Sleep -Seconds 8
    if (Test-TcpPort -HostName "127.0.0.1" -Port $Port) {
        Write-WorkflowLog "dashboard_status=started url=http://localhost:$Port/"
    } else {
        Write-WorkflowLog "dashboard_status=start_requested port=$Port"
    }
}

if ($LookbackDays -lt 1) {
    throw "LookbackDays must be at least 1."
}
if ($Workers -lt 1) {
    throw "Workers must be at least 1."
}
if ($TopN -lt 1) {
    throw "TopN must be at least 1."
}
if ($CommandTimeoutMinutes -lt 1) {
    throw "CommandTimeoutMinutes must be at least 1."
}

$today = Get-KstToday
$EndDate = $today.ToString("yyyy-MM-dd")
$StartDate = $today.AddDays(-1 * $LookbackDays).ToString("yyyy-MM-dd")
$DryRunJson = "data\dry_run_rebalance_latest.json"
$DryRunMd = "data\dry_run_rebalance_latest.md"

$lockHandle = $null
try {
    try {
        $lockHandle = [System.IO.File]::Open($LockPath, [System.IO.FileMode]::OpenOrCreate, [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::None)
    } catch {
        Write-WorkflowLog "login_workflow_skipped=already_running"
        exit 0
    }

    if (-not $SkipDashboard) {
        Start-PublicDashboard
    }
    if ($OpenBrowser) {
        Start-Process "http://localhost:$Port/"
    }

    if ((-not $Force) -and (Test-Path $SuccessMarkerPath)) {
        $lastSuccessDate = (Get-Content -Path $SuccessMarkerPath -ErrorAction SilentlyContinue | Select-Object -First 1)
        if ($lastSuccessDate -eq $EndDate) {
            Write-WorkflowLog "login_workflow_skipped=already_completed date=$EndDate"
            exit 0
        }
    }

    Write-WorkflowLog "login_workflow_start start_date=$StartDate end_date=$EndDate lookback_days=$LookbackDays top_n=$TopN"

    $researchArgs = @(
        "-File", "scripts\refresh_public_research_dashboard_daily.ps1",
        "-PythonPath", $PythonPath,
        "-LookbackDays", "$LookbackDays",
        "-EndDate", $EndDate,
        "-CommandTimeoutMinutes", "$CommandTimeoutMinutes"
    )
    if ($Force) {
        $researchArgs += "-Force"
    }
    if ($SkipResearchSync) {
        $researchArgs += "-SkipResearchSync"
    }
    Write-WorkflowLog ("step_start=research_dashboard_refresh")
    $researchProcessArgs = @("-NoProfile", "-ExecutionPolicy", "Bypass") + $researchArgs
    & powershell.exe @researchProcessArgs
    $researchExitCode = $LASTEXITCODE
    Write-WorkflowLog "step_done=research_dashboard_refresh exit_code=$researchExitCode"
    if ($researchExitCode -ne 0) {
        throw "step_failed=research_dashboard_refresh exit_code=$researchExitCode"
    }

    if (-not $SkipDataSync) {
        Invoke-LoggedPython "phase1_data_sync" @(
            "scripts\sync_phase1_data.py",
            "--start-date", $StartDate,
            "--end-date", $EndDate,
            "--workers", "$Workers"
        )
    }

    if (-not $SkipRebalanceReview) {
        Invoke-LoggedPython "rebalance_prepare_review" @(
            "scripts\prepare_and_review_rebalance.py",
            "--as-of-date", $EndDate,
            "--top-n", "$TopN",
            "--output-json", $DryRunJson,
            "--output-md", $DryRunMd
        )
        Invoke-LoggedPython "rebalance_readiness_check" @(
            "scripts\check_rebalance_readiness.py",
            "--dry-run-json", $DryRunJson,
            "--expected-date", $EndDate
        ) -AllowFailure
    }

    Set-Content -Path $SuccessMarkerPath -Value $EndDate -Encoding UTF8
    Write-WorkflowLog "login_workflow_completed=true"
    Write-WorkflowLog "orders_submitted=0"
} finally {
    if ($null -ne $lockHandle) {
        $lockHandle.Close()
    }
}
