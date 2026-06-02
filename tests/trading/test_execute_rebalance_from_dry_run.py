import json
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


def test_parse_args_accepts_execute_options(tmp_path):
    import scripts.execute_rebalance_from_dry_run as execute_script

    report_path = tmp_path / "dry_run.json"
    execution_report_path = tmp_path / "execution.json"
    args = execute_script.parse_args([
        "--dry-run-json",
        str(report_path),
        "--expected-date",
        "2026-05-08",
        "--confirm",
        "EXECUTE_PAPER_REBALANCE",
        "--execution-report-json",
        str(execution_report_path),
        "--force-overwrite-report",
        "--review-before-execute",
    ])

    assert args.dry_run_json == report_path
    assert args.expected_date == date(2026, 5, 8)
    assert args.confirm == "EXECUTE_PAPER_REBALANCE"
    assert args.execution_report_json == execution_report_path
    assert args.force_overwrite_report is True
    assert args.review_before_execute is True


def test_run_blocks_without_confirmation_token(tmp_path):
    import scripts.execute_rebalance_from_dry_run as execute_script

    report_path = tmp_path / "dry_run.json"
    _write_report(report_path)
    execute_func = MagicMock()
    args = execute_script.parse_args([
        "--dry-run-json",
        str(report_path),
        "--expected-date",
        "2026-05-08",
    ])

    result = execute_script.run(
        args,
        engine_factory=MagicMock(),
        execute_func=execute_func,
    )

    assert result == 1
    execute_func.assert_not_called()


def test_run_executes_orders_from_clean_confirmed_dry_run(tmp_path):
    import scripts.execute_rebalance_from_dry_run as execute_script

    report_path = tmp_path / "dry_run.json"
    _write_report(report_path)
    engine = MagicMock()
    execute_func = MagicMock(return_value={"sold": ["OLD"], "bought": ["NEW"], "failed": []})
    args = execute_script.parse_args([
        "--dry-run-json",
        str(report_path),
        "--expected-date",
        "2026-05-08",
        "--confirm",
        "EXECUTE_PAPER_REBALANCE",
    ])

    result = execute_script.run(
        args,
        engine_factory=MagicMock(return_value=engine),
        execute_func=execute_func,
        now=datetime(2026, 5, 4, 10, 0, tzinfo=KST),
    )

    sells = execute_func.call_args.args[1]
    buys = execute_func.call_args.args[2]

    assert result == 0
    assert [order.ticker for order in sells] == ["OLD"]
    assert [order.ticker for order in buys] == ["NEW"]
    assert execute_func.call_args.kwargs["preflight_report_path"] == report_path
    assert execute_func.call_args.kwargs["expected_preflight_date"] == date(2026, 5, 8)


def test_run_skips_requested_tickers_from_dry_run_orders(tmp_path):
    import scripts.execute_rebalance_from_dry_run as execute_script

    report_path = tmp_path / "dry_run.json"
    report_path.write_text(
        json.dumps({
            "dry_run": True,
            "as_of_date": "2026-05-08",
            "price_fallback_count": 0,
            "price_lookup_failed_count": 0,
            "price_fallbacks": [],
            "price_lookup_failures": [],
            "orders": [
                {"side": "SELL", "ticker": "000270", "qty": 3, "reason": "done"},
                {"side": "SELL", "ticker": "012860", "qty": 2, "reason": "done"},
                {"side": "SELL", "ticker": "023160", "qty": 1, "reason": "next"},
                {"side": "BUY", "ticker": "066570", "qty": 1, "reason": "next"},
            ],
        }),
        encoding="utf-8",
    )
    execute_func = MagicMock(return_value={"sold": ["023160"], "bought": ["066570"], "failed": []})
    args = execute_script.parse_args([
        "--dry-run-json",
        str(report_path),
        "--expected-date",
        "2026-05-08",
        "--confirm",
        "EXECUTE_PAPER_REBALANCE",
        "--skip-ticker",
        "000270",
        "--skip-ticker",
        "012860",
    ])

    result = execute_script.run(
        args,
        engine_factory=MagicMock(return_value=MagicMock()),
        execute_func=execute_func,
        now=datetime(2026, 5, 4, 10, 0, tzinfo=KST),
    )

    sells = execute_func.call_args.args[1]
    buys = execute_func.call_args.args[2]

    assert result == 0
    assert [order.ticker for order in sells] == ["023160"]
    assert [order.ticker for order in buys] == ["066570"]


def test_run_writes_execution_report_json(tmp_path):
    import scripts.execute_rebalance_from_dry_run as execute_script

    report_path = tmp_path / "dry_run.json"
    execution_report_path = tmp_path / "execution.json"
    _write_report(report_path)
    execute_func = MagicMock(return_value={"sold": ["OLD"], "bought": ["NEW"], "failed": []})
    args = execute_script.parse_args([
        "--dry-run-json",
        str(report_path),
        "--expected-date",
        "2026-05-08",
        "--confirm",
        "EXECUTE_PAPER_REBALANCE",
        "--execution-report-json",
        str(execution_report_path),
    ])

    result = execute_script.run(
        args,
        engine_factory=MagicMock(return_value=MagicMock()),
        execute_func=execute_func,
        now=datetime(2026, 5, 4, 10, 0, tzinfo=KST),
    )

    payload = json.loads(execution_report_path.read_text(encoding="utf-8"))

    assert result == 0
    assert payload["paper_execution"] is True
    assert payload["dry_run_json"] == str(report_path)
    assert payload["expected_date"] == "2026-05-08"
    assert payload["executed_at"].startswith("2026-05-04T10:00:00")
    assert payload["sold"] == ["OLD"]
    assert payload["bought"] == ["NEW"]
    assert payload["failed"] == []
    assert payload["sold_count"] == 1
    assert payload["bought_count"] == 1
    assert payload["failed_count"] == 0
    assert payload["planned_sells"] == ["OLD"]
    assert payload["planned_buys"] == ["NEW"]
    assert payload["planned_sell_count"] == 1
    assert payload["planned_buy_count"] == 1
    assert payload["execution_match_status"] == "matched"
    assert payload["missing_sells"] == []
    assert payload["missing_buys"] == []
    assert payload["unexpected_sells"] == []
    assert payload["unexpected_buys"] == []


def test_run_execution_report_detects_plan_mismatch(tmp_path):
    import scripts.execute_rebalance_from_dry_run as execute_script

    report_path = tmp_path / "dry_run.json"
    execution_report_path = tmp_path / "execution.json"
    _write_report(report_path)
    execute_func = MagicMock(return_value={"sold": [], "bought": ["NEW", "EXTRA"], "failed": ["OLD"]})
    args = execute_script.parse_args([
        "--dry-run-json",
        str(report_path),
        "--expected-date",
        "2026-05-08",
        "--confirm",
        "EXECUTE_PAPER_REBALANCE",
        "--execution-report-json",
        str(execution_report_path),
    ])

    result = execute_script.run(
        args,
        engine_factory=MagicMock(return_value=MagicMock()),
        execute_func=execute_func,
        now=datetime(2026, 5, 4, 10, 0, tzinfo=KST),
    )

    payload = json.loads(execution_report_path.read_text(encoding="utf-8"))

    assert result == 1
    assert payload["execution_match_status"] == "mismatched"
    assert payload["missing_sells"] == ["OLD"]
    assert payload["missing_buys"] == []
    assert payload["unexpected_sells"] == []
    assert payload["unexpected_buys"] == ["EXTRA"]


def test_run_blocks_when_execution_report_exists_without_force(tmp_path, capsys):
    import scripts.execute_rebalance_from_dry_run as execute_script

    report_path = tmp_path / "dry_run.json"
    execution_report_path = tmp_path / "execution.json"
    _write_report(report_path)
    execution_report_path.write_text('{"existing": true}', encoding="utf-8")
    execute_func = MagicMock()
    args = execute_script.parse_args([
        "--dry-run-json",
        str(report_path),
        "--expected-date",
        "2026-05-08",
        "--confirm",
        "EXECUTE_PAPER_REBALANCE",
        "--execution-report-json",
        str(execution_report_path),
    ])

    result = execute_script.run(
        args,
        engine_factory=MagicMock(return_value=MagicMock()),
        execute_func=execute_func,
        now=datetime(2026, 5, 4, 10, 0, tzinfo=KST),
    )

    assert result == 1
    assert "execution_report_exists=" in capsys.readouterr().out
    assert json.loads(execution_report_path.read_text(encoding="utf-8")) == {"existing": True}
    execute_func.assert_not_called()


def test_run_overwrites_existing_execution_report_when_forced(tmp_path):
    import scripts.execute_rebalance_from_dry_run as execute_script

    report_path = tmp_path / "dry_run.json"
    execution_report_path = tmp_path / "execution.json"
    _write_report(report_path)
    execution_report_path.write_text('{"existing": true}', encoding="utf-8")
    execute_func = MagicMock(return_value={"sold": ["OLD"], "bought": ["NEW"], "failed": []})
    args = execute_script.parse_args([
        "--dry-run-json",
        str(report_path),
        "--expected-date",
        "2026-05-08",
        "--confirm",
        "EXECUTE_PAPER_REBALANCE",
        "--execution-report-json",
        str(execution_report_path),
        "--force-overwrite-report",
    ])

    result = execute_script.run(
        args,
        engine_factory=MagicMock(return_value=MagicMock()),
        execute_func=execute_func,
        now=datetime(2026, 5, 4, 10, 0, tzinfo=KST),
    )

    payload = json.loads(execution_report_path.read_text(encoding="utf-8"))
    assert result == 0
    assert payload["paper_execution"] is True
    assert payload["sold"] == ["OLD"]


def test_run_reviews_dry_run_before_execute_when_requested(tmp_path):
    import scripts.execute_rebalance_from_dry_run as execute_script

    report_path = tmp_path / "dry_run.json"
    _write_report(report_path)
    execute_func = MagicMock(return_value={"sold": ["OLD"], "bought": ["NEW"], "failed": []})
    review_func = MagicMock(return_value=0)
    args = execute_script.parse_args([
        "--dry-run-json",
        str(report_path),
        "--expected-date",
        "2026-05-08",
        "--confirm",
        "EXECUTE_PAPER_REBALANCE",
        "--review-before-execute",
    ])

    result = execute_script.run(
        args,
        engine_factory=MagicMock(return_value=MagicMock()),
        execute_func=execute_func,
        review_func=review_func,
        now=datetime(2026, 5, 4, 10, 0, tzinfo=KST),
    )

    review_args = review_func.call_args.args[0]
    assert result == 0
    assert review_args.dry_run_json == report_path
    assert review_args.execution_report_json is None
    execute_func.assert_called_once()


def test_run_blocks_when_pre_execution_review_fails(tmp_path, capsys):
    import scripts.execute_rebalance_from_dry_run as execute_script

    report_path = tmp_path / "dry_run.json"
    _write_report(report_path)
    execute_func = MagicMock()
    review_func = MagicMock(return_value=1)
    args = execute_script.parse_args([
        "--dry-run-json",
        str(report_path),
        "--expected-date",
        "2026-05-08",
        "--confirm",
        "EXECUTE_PAPER_REBALANCE",
        "--review-before-execute",
    ])

    result = execute_script.run(
        args,
        engine_factory=MagicMock(return_value=MagicMock()),
        execute_func=execute_func,
        review_func=review_func,
        now=datetime(2026, 5, 4, 10, 0, tzinfo=KST),
    )

    assert result == 1
    assert "pre_execution_review_blocked=1" in capsys.readouterr().out
    execute_func.assert_not_called()


def test_run_returns_error_when_dry_run_report_is_missing(tmp_path, capsys):
    import scripts.execute_rebalance_from_dry_run as execute_script

    report_path = tmp_path / "missing.json"
    execute_func = MagicMock()
    args = execute_script.parse_args([
        "--dry-run-json",
        str(report_path),
        "--expected-date",
        "2026-05-08",
        "--confirm",
        "EXECUTE_PAPER_REBALANCE",
    ])

    result = execute_script.run(
        args,
        engine_factory=MagicMock(return_value=MagicMock()),
        execute_func=execute_func,
        now=datetime(2026, 5, 4, 10, 0, tzinfo=KST),
    )

    output = capsys.readouterr().out
    assert result == 1
    assert "dry_run_status=missing_or_invalid" in output
    assert "report_error=" in output
    execute_func.assert_not_called()


def test_run_returns_error_when_dry_run_report_is_invalid_json(tmp_path, capsys):
    import scripts.execute_rebalance_from_dry_run as execute_script

    report_path = tmp_path / "dry_run.json"
    report_path.write_text("{not json", encoding="utf-8")
    execute_func = MagicMock()
    args = execute_script.parse_args([
        "--dry-run-json",
        str(report_path),
        "--expected-date",
        "2026-05-08",
        "--confirm",
        "EXECUTE_PAPER_REBALANCE",
    ])

    result = execute_script.run(
        args,
        engine_factory=MagicMock(return_value=MagicMock()),
        execute_func=execute_func,
        now=datetime(2026, 5, 4, 10, 0, tzinfo=KST),
    )

    output = capsys.readouterr().out
    assert result == 1
    assert "dry_run_status=missing_or_invalid" in output
    assert "report_error=" in output
    execute_func.assert_not_called()


def test_run_returns_error_when_preflight_blocks(tmp_path, capsys):
    import scripts.execute_rebalance_from_dry_run as execute_script

    report_path = tmp_path / "dry_run.json"
    _write_report(report_path)
    execute_func = MagicMock(side_effect=RuntimeError("dry-run preflight blocked: stale report"))
    args = execute_script.parse_args([
        "--dry-run-json",
        str(report_path),
        "--expected-date",
        "2026-05-09",
        "--confirm",
        "EXECUTE_PAPER_REBALANCE",
    ])

    result = execute_script.run(
        args,
        engine_factory=MagicMock(return_value=MagicMock()),
        execute_func=execute_func,
        now=datetime(2026, 5, 4, 10, 0, tzinfo=KST),
    )

    assert result == 1
    assert "execution_blocked=dry-run preflight blocked" in capsys.readouterr().out


def test_run_blocks_outside_regular_market_hours_even_with_confirmation(tmp_path, capsys):
    import scripts.execute_rebalance_from_dry_run as execute_script

    report_path = tmp_path / "dry_run.json"
    _write_report(report_path)
    execute_func = MagicMock()
    args = execute_script.parse_args([
        "--dry-run-json",
        str(report_path),
        "--expected-date",
        "2026-05-08",
        "--confirm",
        "EXECUTE_PAPER_REBALANCE",
    ])

    result = execute_script.run(
        args,
        engine_factory=MagicMock(return_value=MagicMock()),
        execute_func=execute_func,
        now=datetime(2026, 5, 9, 10, 0, tzinfo=KST),
    )

    assert result == 1
    assert "market_time_required" in capsys.readouterr().out
    execute_func.assert_not_called()
