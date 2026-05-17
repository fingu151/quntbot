from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SNAPSHOT_PATH = PROJECT_ROOT / "data" / "public_portfolio_snapshot.json"
DEFAULT_TICKER_BRIEF_PATH = PROJECT_ROOT / "data" / "research_report_ticker_briefs.json"


@dataclass(frozen=True)
class DashboardOpsStatus:
    snapshot_status: str
    ticker_brief_status: str
    snapshot_age_minutes: int | None
    ticker_brief_age_minutes: int | None
    overall_status: str
    recommended_action: str
    recommended_command: str


def build_streamlit_command(
    python_path: Path | str,
    *,
    port: int = 8520,
    host: str = "0.0.0.0",
    browser_host: str = "localhost",
) -> list[str]:
    return [
        str(python_path),
        "-m",
        "streamlit",
        "run",
        "scripts/public_portfolio_dashboard.py",
        "--server.port",
        str(port),
        "--server.address",
        host,
        "--browser.serverAddress",
        browser_host,
        "--browser.serverPort",
        str(port),
        "--browser.gatherUsageStats=false",
    ]


def read_dashboard_ops_status(
    *,
    snapshot_path: Path | str = DEFAULT_SNAPSHOT_PATH,
    ticker_brief_path: Path | str = DEFAULT_TICKER_BRIEF_PATH,
    now: datetime | None = None,
    max_age_minutes: int = 30,
) -> DashboardOpsStatus:
    now = _ensure_aware(now or datetime.now(timezone.utc))
    snapshot_status, snapshot_age = _artifact_status(
        Path(snapshot_path), now=now, max_age_minutes=max_age_minutes
    )
    ticker_status, ticker_age = _artifact_status(
        Path(ticker_brief_path), now=now, max_age_minutes=max_age_minutes
    )
    overall = "ok" if snapshot_status == "ok" and ticker_status == "ok" else "needs_attention"
    recommended_action, recommended_command = _recommended_action(
        snapshot_status=snapshot_status,
        ticker_brief_status=ticker_status,
    )
    return DashboardOpsStatus(
        snapshot_status=snapshot_status,
        ticker_brief_status=ticker_status,
        snapshot_age_minutes=snapshot_age,
        ticker_brief_age_minutes=ticker_age,
        overall_status=overall,
        recommended_action=recommended_action,
        recommended_command=recommended_command,
    )


def _artifact_status(
    path: Path,
    *,
    now: datetime,
    max_age_minutes: int,
) -> tuple[str, int | None]:
    if not path.exists():
        return "missing", None

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return "invalid", None

    generated_at = _find_generated_at(payload)
    if not generated_at:
        return "invalid", None

    generated_dt = _parse_datetime(generated_at)
    if generated_dt is None:
        return "invalid", None

    age_minutes = max(0, int((now - generated_dt).total_seconds() // 60))
    status = "ok" if age_minutes <= max_age_minutes else "stale"
    return status, age_minutes


def _find_generated_at(payload: Any) -> str | None:
    if isinstance(payload, dict):
        for key in ("generated_at", "snapshot_at", "snapshot_time", "created_at"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        meta = payload.get("meta")
        if isinstance(meta, dict):
            return _find_generated_at(meta)
    return None


def _recommended_action(*, snapshot_status: str, ticker_brief_status: str) -> tuple[str, str]:
    statuses = {snapshot_status, ticker_brief_status}
    refresh_command = (
        "powershell.exe -ExecutionPolicy Bypass -File "
        ".\\scripts\\refresh_public_portfolio_snapshot.ps1 -RunOnce -RunTimeoutMinutes 10"
    )
    discovery_command = (
        "powershell.exe -ExecutionPolicy Bypass -File "
        ".\\scripts\\refresh_public_portfolio_snapshot.ps1 -RunOnce "
        "-RunTimeoutMinutes 10 -IncludeSupplementalDiscovery"
    )
    if "invalid" in statuses:
        return (
            "Artifact JSON is invalid. Run one refresh, then inspect .tmp\\public_portfolio_snapshot_refresh.log if it stays invalid.",
            refresh_command,
        )
    if "missing" in statuses:
        return (
            "Required dashboard artifacts are missing. Run one refresh to rebuild snapshot, ticker briefs, and quality queues.",
            refresh_command,
        )
    if "stale" in statuses:
        return (
            "Dashboard artifacts are stale. Run one refresh now, or restart the 30-minute refresh loop if this repeats.",
            refresh_command,
        )
    if ticker_brief_status == "ok" and snapshot_status == "ok":
        return (
            "No manual action required. Keep the dashboard refresh loop running; use supplemental discovery only when Needs review remains high.",
            discovery_command,
        )
    return (
        "Review dashboard artifact status and rerun the public dashboard refresh.",
        refresh_command,
    )


def _parse_datetime(value: str) -> datetime | None:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        return _ensure_aware(datetime.fromisoformat(normalized))
    except ValueError:
        return None


def _ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check public dashboard artifact freshness.")
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT_PATH)
    parser.add_argument("--ticker-briefs", type=Path, default=DEFAULT_TICKER_BRIEF_PATH)
    parser.add_argument("--max-age-minutes", type=int, default=30)
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    status = read_dashboard_ops_status(
        snapshot_path=args.snapshot,
        ticker_brief_path=args.ticker_briefs,
        max_age_minutes=args.max_age_minutes,
    )
    payload = asdict(status)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        print(f"overall_status={status.overall_status}")
        print(f"snapshot_status={status.snapshot_status}")
        print(f"snapshot_age_minutes={status.snapshot_age_minutes}")
        print(f"ticker_brief_status={status.ticker_brief_status}")
        print(f"ticker_brief_age_minutes={status.ticker_brief_age_minutes}")
        print(f"recommended_action={status.recommended_action}")
        print(f"recommended_command={status.recommended_command}")
    return 0 if status.overall_status == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
