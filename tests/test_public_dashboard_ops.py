from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.public_dashboard_ops import (
    DashboardOpsStatus,
    build_streamlit_command,
    read_dashboard_ops_status,
)


def test_build_streamlit_command_uses_public_dashboard_script_and_port():
    command = build_streamlit_command(
        python_path=Path(".venv/Scripts/python.exe"),
        port=8520,
        host="0.0.0.0",
    )

    assert command == [
        ".venv\\Scripts\\python.exe",
        "-m",
        "streamlit",
        "run",
        "scripts/public_portfolio_dashboard.py",
        "--server.port",
        "8520",
        "--server.address",
        "0.0.0.0",
        "--browser.serverAddress",
        "localhost",
        "--browser.serverPort",
        "8520",
        "--browser.gatherUsageStats=false",
    ]


def test_read_dashboard_ops_status_flags_fresh_artifacts(tmp_path: Path):
    now = datetime(2026, 5, 15, 9, 0, tzinfo=timezone.utc)
    snapshot_path = tmp_path / "snapshot.json"
    ticker_path = tmp_path / "ticker.json"
    snapshot_path.write_text(
        json.dumps({"generated_at": (now - timedelta(minutes=10)).isoformat(), "positions": []}),
        encoding="utf-8",
    )
    ticker_path.write_text(
        json.dumps({"generated_at": (now - timedelta(minutes=5)).isoformat(), "tickers": []}),
        encoding="utf-8",
    )

    status = read_dashboard_ops_status(
        snapshot_path=snapshot_path,
        ticker_brief_path=ticker_path,
        now=now,
        max_age_minutes=30,
    )

    assert status == DashboardOpsStatus(
        snapshot_status="ok",
        ticker_brief_status="ok",
        snapshot_age_minutes=10,
        ticker_brief_age_minutes=5,
        overall_status="ok",
        recommended_action=(
            "No manual action required. Keep the dashboard refresh loop running; "
            "use supplemental discovery only when Needs review remains high."
        ),
        recommended_command=(
            "powershell.exe -ExecutionPolicy Bypass -File "
            ".\\scripts\\refresh_public_portfolio_snapshot.ps1 -RunOnce "
            "-RunTimeoutMinutes 10 -IncludeSupplementalDiscovery"
        ),
    )


def test_read_dashboard_ops_status_flags_missing_and_stale_artifacts(tmp_path: Path):
    now = datetime(2026, 5, 15, 9, 0, tzinfo=timezone.utc)
    ticker_path = tmp_path / "ticker.json"
    ticker_path.write_text(
        json.dumps({"generated_at": (now - timedelta(minutes=90)).isoformat()}),
        encoding="utf-8",
    )

    status = read_dashboard_ops_status(
        snapshot_path=tmp_path / "missing.json",
        ticker_brief_path=ticker_path,
        now=now,
        max_age_minutes=30,
    )

    assert status.snapshot_status == "missing"
    assert status.ticker_brief_status == "stale"
    assert status.overall_status == "needs_attention"
    assert status.recommended_action.startswith("Required dashboard artifacts are missing")
    assert "-RunOnce" in status.recommended_command


def test_dashboard_start_script_exposes_host_and_hidden_refresh_loop():
    script = Path("scripts/start_public_dashboard_with_refresh.ps1").read_text(encoding="utf-8")

    assert "[string]$HostAddress" in script
    assert "--server.address $HostAddress" in script
    assert "[string]$BrowserAddress" in script
    assert "--browser.serverAddress $BrowserAddress" in script
    assert "-WindowStyle Hidden" in script
    assert "PYTHONIOENCODING" in script
    assert "public_dashboard_streamlit.log" in script


def test_refresh_script_logs_dashboard_ops_status_after_successful_refresh():
    script = Path("scripts/refresh_public_portfolio_snapshot.ps1").read_text(encoding="utf-8")

    assert "-m scripts.public_dashboard_ops --max-age-minutes $IntervalMinutes" in script
    assert "[switch]$SkipSupplementalSources" in script
    assert "--skip-supplemental-sources" in script
    assert "--fallback-existing-snapshot" in script
    assert "function Invoke-LoggedProcess" in script
    assert "RedirectStandardOutput" in script
    assert "PYTHONIOENCODING" in script
    assert "Public dashboard freshness check needs attention" in script
    assert "recommended_action" in Path("scripts/public_dashboard_ops.py").read_text(encoding="utf-8")


def test_startup_task_script_registers_logon_task():
    script = Path("scripts/install_public_dashboard_startup_task.ps1").read_text(encoding="utf-8")

    assert "QuntbotPublicDashboard" in script
    assert "/SC ONLOGON" in script
    assert "/RL LIMITED" in script
    assert "start_public_dashboard_with_refresh.ps1" in script
    assert "[switch]$WhatIf" in script
    assert "-SkipSupplementalSources" in script


def test_startup_shortcut_script_targets_current_user_startup_folder():
    script = Path("scripts/install_public_dashboard_startup_shortcut.ps1").read_text(encoding="utf-8")

    assert 'GetFolderPath("Startup")' in script
    assert "CreateShortcut" in script
    assert "-BrowserAddress $BrowserAddress" in script
    assert "-SkipSupplementalSources" in script
    assert "start_public_dashboard_with_refresh.ps1" in script
    assert "[switch]$WhatIf" in script
