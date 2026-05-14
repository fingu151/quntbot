import json
from pathlib import Path


def _write_dry_run_report(
    path: Path,
    *,
    fallback_count: int = 0,
    failed_count: int = 0,
) -> None:
    path.write_text(
        json.dumps({
            "dry_run": True,
            "as_of_date": "2026-05-08",
            "cash": 100000,
            "target_count": 2,
            "sell_count": 1,
            "buy_count": 1,
            "price_fallback_count": fallback_count,
            "price_lookup_failed_count": failed_count,
            "price_retry_success_count": 1,
            "price_retry_failed_count": 1,
            "price_retry_attempts": [
                {
                    "ticker": "NEW",
                    "attempt_count": 2,
                    "status": "success",
                    "last_error": "temporary quote failure",
                },
                {
                    "ticker": "MISS",
                    "attempt_count": 2,
                    "status": "failed",
                    "last_error": "quote server still failed",
                },
            ],
            "skipped_buy_count": 1,
            "skipped_buys": [
                {
                    "ticker": "GAP",
                    "reason": "gap_move_too_large",
                    "execution_price": 12100,
                    "previous_close": 10000,
                    "gap_pct": 0.21,
                    "threshold_pct": 0.2,
                }
            ],
            "price_fallbacks": [{"ticker": "FALL", "price": 1000, "source": "latest-db"}]
            if fallback_count
            else [],
            "price_lookup_failures": ["MISS"] if failed_count else [],
            "orders": [
                {"side": "SELL", "ticker": "OLD", "qty": 3, "reason": "exclude"},
                {"side": "BUY", "ticker": "NEW", "qty": 5, "reason": "include"},
            ],
        }),
        encoding="utf-8",
    )


def _write_execution_report(path: Path, *, failed: list[str] | None = None) -> None:
    failed = failed or []
    path.write_text(
        json.dumps({
            "paper_execution": True,
            "dry_run_json": "dry_run.json",
            "expected_date": "2026-05-08",
            "executed_at": "2026-05-08T10:00:00+09:00",
            "sold": ["OLD"],
            "bought": ["NEW"],
            "failed": failed,
            "sold_count": 1,
            "bought_count": 1,
            "failed_count": len(failed),
            "planned_sells": ["OLD"],
            "planned_buys": ["NEW"],
            "planned_sell_count": 1,
            "planned_buy_count": 1,
            "execution_match_status": "mismatched" if failed else "matched",
            "missing_sells": failed,
            "missing_buys": [],
            "unexpected_sells": [],
            "unexpected_buys": [],
        }),
        encoding="utf-8",
    )


def test_parse_args_accepts_review_options(tmp_path):
    import scripts.review_rebalance_reports as review

    dry_run_path = tmp_path / "dry_run.json"
    execution_path = tmp_path / "execution.json"
    args = review.parse_args([
        "--dry-run-json",
        str(dry_run_path),
        "--execution-report-json",
        str(execution_path),
    ])

    assert args.dry_run_json == dry_run_path
    assert args.execution_report_json == execution_path


def test_run_prints_clean_dry_run_summary(tmp_path, capsys):
    import scripts.review_rebalance_reports as review

    dry_run_path = tmp_path / "dry_run.json"
    _write_dry_run_report(dry_run_path)
    args = review.parse_args(["--dry-run-json", str(dry_run_path)])

    result = review.run(args)

    output = capsys.readouterr().out
    assert result == 0
    assert "dry_run_status=clean" in output
    assert "as_of_date=2026-05-08" in output
    assert "orders=2" in output
    assert "skipped_buy_count=1" in output
    assert "skipped_buy,GAP,gap_move_too_large,12100,10000,21.00%,20.00%" in output
    assert "SELL,OLD,3" in output
    assert "BUY,NEW,5" in output


def test_run_returns_error_for_unclean_dry_run(tmp_path, capsys):
    import scripts.review_rebalance_reports as review

    dry_run_path = tmp_path / "dry_run.json"
    _write_dry_run_report(dry_run_path, fallback_count=1, failed_count=1)
    args = review.parse_args(["--dry-run-json", str(dry_run_path)])

    result = review.run(args)

    output = capsys.readouterr().out
    assert result == 1
    assert "dry_run_status=blocked" in output
    assert "price_fallback_count=1" in output
    assert "price_lookup_failed_count=1" in output


def test_run_prints_price_retry_summary(tmp_path, capsys):
    import scripts.review_rebalance_reports as review

    dry_run_path = tmp_path / "dry_run.json"
    _write_dry_run_report(dry_run_path)
    args = review.parse_args(["--dry-run-json", str(dry_run_path)])

    result = review.run(args)

    output = capsys.readouterr().out
    assert result == 0
    assert "price_retry_success_count=1" in output
    assert "price_retry_failed_count=1" in output
    assert "price_retry,NEW,success,2,temporary quote failure" in output
    assert "price_retry,MISS,failed,2,quote server still failed" in output


def test_run_returns_error_when_dry_run_report_is_missing(tmp_path, capsys):
    import scripts.review_rebalance_reports as review

    dry_run_path = tmp_path / "missing.json"
    args = review.parse_args(["--dry-run-json", str(dry_run_path)])

    result = review.run(args)

    output = capsys.readouterr().out
    assert result == 1
    assert "dry_run_status=missing_or_invalid" in output
    assert "report_error=" in output


def test_run_returns_error_when_dry_run_report_is_invalid_json(tmp_path, capsys):
    import scripts.review_rebalance_reports as review

    dry_run_path = tmp_path / "dry_run.json"
    dry_run_path.write_text("{not json", encoding="utf-8")
    args = review.parse_args(["--dry-run-json", str(dry_run_path)])

    result = review.run(args)

    output = capsys.readouterr().out
    assert result == 1
    assert "dry_run_status=missing_or_invalid" in output
    assert "report_error=" in output


def test_run_includes_execution_report_summary(tmp_path, capsys):
    import scripts.review_rebalance_reports as review

    dry_run_path = tmp_path / "dry_run.json"
    execution_path = tmp_path / "execution.json"
    _write_dry_run_report(dry_run_path)
    _write_execution_report(execution_path)
    args = review.parse_args([
        "--dry-run-json",
        str(dry_run_path),
        "--execution-report-json",
        str(execution_path),
    ])

    result = review.run(args)

    output = capsys.readouterr().out
    assert result == 0
    assert "execution_status=clean" in output
    assert "sold_count=1" in output
    assert "bought_count=1" in output
    assert "failed_count=0" in output
    assert "execution_match_status=matched" in output
    assert "planned_sell_count=1" in output
    assert "planned_buy_count=1" in output
    assert "missing_sells=" in output
    assert "missing_buys=" in output


def test_run_returns_error_when_execution_report_has_failures(tmp_path, capsys):
    import scripts.review_rebalance_reports as review

    dry_run_path = tmp_path / "dry_run.json"
    execution_path = tmp_path / "execution.json"
    _write_dry_run_report(dry_run_path)
    _write_execution_report(execution_path, failed=["ERR"])
    args = review.parse_args([
        "--dry-run-json",
        str(dry_run_path),
        "--execution-report-json",
        str(execution_path),
    ])

    result = review.run(args)

    output = capsys.readouterr().out
    assert result == 1
    assert "execution_status=failed" in output
    assert "execution_match_status=mismatched" in output
    assert "missing_sells=ERR" in output
    assert "failed_tickers=ERR" in output


def test_run_returns_error_when_execution_report_is_missing(tmp_path, capsys):
    import scripts.review_rebalance_reports as review

    dry_run_path = tmp_path / "dry_run.json"
    execution_path = tmp_path / "missing_execution.json"
    _write_dry_run_report(dry_run_path)
    args = review.parse_args([
        "--dry-run-json",
        str(dry_run_path),
        "--execution-report-json",
        str(execution_path),
    ])

    result = review.run(args)

    output = capsys.readouterr().out
    assert result == 1
    assert "dry_run_status=clean" in output
    assert "execution_status=missing_or_invalid" in output
    assert "report_error=" in output
