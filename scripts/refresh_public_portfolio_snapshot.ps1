param(
    [int]$IntervalMinutes = 30,
    [int]$RunTimeoutMinutes = 5,
    [string]$PythonPath = ".\venv\Scripts\python.exe",
    [string]$OutputPath = "data\public_portfolio_snapshot.json",
    [string]$RefreshedThrough = "",
    [switch]$IncludeSupplementalDiscovery,
    [switch]$SkipSupplementalSources,
    [switch]$RunOnce
)

$ErrorActionPreference = "Continue"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $ProjectRoot
$Utf8NoBom = New-Object System.Text.UTF8Encoding $false
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$env:PYTHONIOENCODING = "utf-8"

$LogDir = Join-Path $ProjectRoot ".tmp"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogPath = Join-Path $LogDir "public_portfolio_snapshot_refresh.log"

function Write-RefreshLog {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$timestamp $Message" | Tee-Object -FilePath $LogPath -Append
}

function Get-KstTodayString {
    $tz = [System.TimeZoneInfo]::FindSystemTimeZoneById("Korea Standard Time")
    $kstToday = [System.TimeZoneInfo]::ConvertTimeFromUtc([DateTime]::UtcNow, $tz).Date
    return $kstToday.ToString("yyyy-MM-dd")
}

function Invoke-LoggedProcess {
    param(
        [string]$FileName,
        [string]$Arguments,
        [int]$TimeoutMinutes
    )

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $FileName
    $psi.WorkingDirectory = $ProjectRoot
    $psi.Arguments = $Arguments
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.CreateNoWindow = $true

    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $psi
    [void]$process.Start()
    $stdoutTask = $process.StandardOutput.ReadToEndAsync()
    $stderrTask = $process.StandardError.ReadToEndAsync()

    $completed = $process.WaitForExit($TimeoutMinutes * 60 * 1000)
    if (-not $completed) {
        try {
            $process.Kill()
            $process.WaitForExit()
        } catch {
            Write-RefreshLog "Failed to stop timed-out process. error=$($_.Exception.Message)"
        }
    } else {
        $process.WaitForExit()
    }

    $exitCode = if ($completed) { $process.ExitCode } else { 124 }
    $stdoutText = $stdoutTask.Result
    $stderrText = $stderrTask.Result
    [pscustomobject]@{
        Completed = $completed
        ExitCode = $exitCode
        Stdout = $stdoutText
        Stderr = $stderrText
    }
}

if ($IntervalMinutes -lt 1) {
    Write-RefreshLog "IntervalMinutes must be at least 1."
    exit 2
}

if ($RunTimeoutMinutes -lt 1) {
    Write-RefreshLog "RunTimeoutMinutes must be at least 1."
    exit 2
}

if (-not $RefreshedThrough) {
    $RefreshedThrough = Get-KstTodayString
}

Write-RefreshLog "Starting public snapshot refresh loop. interval_minutes=$IntervalMinutes run_timeout_minutes=$RunTimeoutMinutes output=$OutputPath refreshed_through=$RefreshedThrough include_supplemental_discovery=$IncludeSupplementalDiscovery skip_supplemental_sources=$SkipSupplementalSources"

while ($true) {
    Write-RefreshLog "Running public dashboard artifact refresh..."
    $arguments = '-m scripts.refresh_public_dashboard_artifacts --snapshot-output "' + $OutputPath + '"'
    if ($RefreshedThrough) {
        $arguments += ' --refreshed-through "' + $RefreshedThrough + '"'
    }
    if ($IncludeSupplementalDiscovery) {
        $arguments += ' --include-supplemental-discovery'
    }
    if ($SkipSupplementalSources) {
        $arguments += ' --skip-supplemental-sources'
    }
    $arguments += ' --fallback-existing-snapshot'

    $result = Invoke-LoggedProcess -FileName $PythonPath -Arguments $arguments -TimeoutMinutes $RunTimeoutMinutes
    if (-not $result.Completed) {
        Write-RefreshLog "Snapshot refresh timed out after $RunTimeoutMinutes minutes."
    }
    $stdoutText = $result.Stdout
    $stderrText = $result.Stderr
    $exitCode = $result.ExitCode

    if ($stdoutText) {
        $stdoutText -split "`r?`n" | Where-Object { $_ } | Tee-Object -FilePath $LogPath -Append
    }
    if ($stderrText) {
        $stderrText -split "`r?`n" | Where-Object { $_ } | Tee-Object -FilePath $LogPath -Append
    }

    if ($result.Completed -and $exitCode -eq 0) {
        Write-RefreshLog "Public dashboard artifact refresh completed."
        Write-RefreshLog "Checking public dashboard artifact freshness..."
        $opsResult = Invoke-LoggedProcess -FileName $PythonPath -Arguments "-m scripts.public_dashboard_ops --max-age-minutes $IntervalMinutes" -TimeoutMinutes 1
        $opsStdout = $opsResult.Stdout
        $opsStderr = $opsResult.Stderr
        if ($opsStdout) {
            $opsStdout -split "`r?`n" | Where-Object { $_ } | Tee-Object -FilePath $LogPath -Append
        }
        if ($opsStderr) {
            $opsStderr -split "`r?`n" | Where-Object { $_ } | Tee-Object -FilePath $LogPath -Append
        }
        if ($opsResult.ExitCode -ne 0) {
            Write-RefreshLog "Public dashboard freshness check needs attention. exit_code=$($opsResult.ExitCode)"
        }
    } else {
        Write-RefreshLog "Public dashboard artifact refresh failed. exit_code=$exitCode"
    }

    Write-RefreshLog "Sleeping for $IntervalMinutes minutes."
    if ($RunOnce) {
        Write-RefreshLog "RunOnce requested; exiting refresh loop."
        break
    }
    Start-Sleep -Seconds ($IntervalMinutes * 60)
    Write-RefreshLog "Woke up for next refresh."
}
