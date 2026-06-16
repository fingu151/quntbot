import json
from json import JSONDecodeError
from datetime import date, datetime
from pathlib import Path
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo


KST = ZoneInfo("Asia/Seoul")


def _write_report(path: Path, *, as_of_date: str = "2026-05-08") -> None:
    path.write_text(
        json.dumps({
            "dry_run": True,
            "as_of_date": as_of_date,
            "price_fallback_count": 0,
            "price_lookup_failed_count": 0,
            "price_fallbacks": [],
            "price_lookup_failures": [],
            "orders": [
                {"side": "SELL", "ticker": "OLD", "qty": 3, "reason": "exclude"},
                {"side": "BUY", "ticker": "NEW", "qty": 5, "reason": "include"},
            ],
        }),
        encoding="utf-8",
    )


def test_parse_args_accepts_readiness_options(tmp_path):
    import scripts.check_rebalance_readiness as readiness

    report_path = tmp_path / "dry_run.json"
    args = readiness.parse_args([
        "--dry-run-json",
        str(report_path),
        "--expected-date",
        "2026-05-08",
    ])

    assert args.dry_run_json == report_path
    assert args.expected_date == date(2026, 5, 8)


def test_run_reports_ready_when_market_time_and_preflight_pass(tmp_path, capsys):
    import scripts.check_rebalance_readiness as readiness

    report_path = tmp_path / "dry_run.json"
    _write_report(report_path)
    preflight = MagicMock()
    args = readiness.parse_args([
        "--dry-run-json",
        str(report_path),
        "--expected-date",
        "2026-05-08",
    ])

    result = readiness.run(
        args,
        now=datetime(2026, 5, 8, 10, 0, tzinfo=KST),
        preflight_func=preflight,
    )

    output = capsys.readouterr().out
    assert result == 0
    assert "market_time_status=ready" in output
    assert "preflight_status=clean" in output
    assert "execution_ready=true" in output
    preflight.assert_called_once_with(report_path, expected_preflight_date=date(2026, 5, 8))


def test_run_blocks_outside_market_time_even_when_preflight_passes(tmp_path, capsys):
    import scripts.check_rebalance_readiness as readiness

    report_path = tmp_path / "dry_run.json"
    _write_report(report_path)
    args = readiness.parse_args([
        "--dry-run-json",
        str(report_path),
        "--expected-date",
        "2026-05-08",
    ])

    result = readiness.run(
        args,
        now=datetime(2026, 5, 9, 10, 0, tzinfo=KST),
        preflight_func=MagicMock(),
    )

    output = capsys.readouterr().out
    assert result == 1
    assert "market_time_status=blocked" in output
    assert "execution_ready=false" in output


def test_run_blocks_when_preflight_fails(tmp_path, capsys):
    import scripts.check_rebalance_readiness as readiness

    report_path = tmp_path / "dry_run.json"
    _write_report(report_path, as_of_date="2026-05-07")
    args = readiness.parse_args([
        "--dry-run-json",
        str(report_path),
        "--expected-date",
        "2026-05-08",
    ])

    result = readiness.run(
        args,
        now=datetime(2026, 5, 8, 10, 0, tzinfo=KST),
        preflight_func=MagicMock(side_effect=RuntimeError("stale report")),
    )

    output = capsys.readouterr().out
    assert result == 1
    assert "preflight_status=blocked" in output
    assert "preflight_error=stale report" in output
    assert (
        "next_prepare_command=.\\venv\\Scripts\\python.exe "
        "scripts\\prepare_rebalance_for_execution.py --as-of-date 2026-05-08 --top-n 30"
    ) in output
    assert "execution_ready=false" in output


def test_run_blocks_when_preflight_report_is_missing(tmp_path, capsys):
    import scripts.check_rebalance_readiness as readiness

    report_path = tmp_path / "missing.json"
    args = readiness.parse_args([
        "--dry-run-json",
        str(report_path),
        "--expected-date",
        "2026-05-08",
    ])

    result = readiness.run(
        args,
        now=datetime(2026, 5, 8, 10, 0, tzinfo=KST),
        preflight_func=MagicMock(side_effect=FileNotFoundError("missing report")),
    )

    output = capsys.readouterr().out
    assert result == 1
    assert "preflight_status=blocked" in output
    assert "preflight_error=missing report" in output
    assert "execution_ready=false" in output


def test_run_blocks_when_preflight_report_is_invalid_json(tmp_path, capsys):
    import scripts.check_rebalance_readiness as readiness

    report_path = tmp_path / "dry_run.json"
    report_path.write_text("{not json", encoding="utf-8")
    args = readiness.parse_args([
        "--dry-run-json",
        str(report_path),
        "--expected-date",
        "2026-05-08",
    ])

    result = readiness.run(
        args,
        now=datetime(2026, 5, 8, 10, 0, tzinfo=KST),
        preflight_func=MagicMock(
            side_effect=JSONDecodeError("invalid json", "{not json", 1)
        ),
    )

    output = capsys.readouterr().out
    assert result == 1
    assert "preflight_status=blocked" in output
    assert "preflight_error=invalid json" in output
    assert "execution_ready=false" in output
