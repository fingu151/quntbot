from datetime import date
from pathlib import Path
from unittest.mock import MagicMock


def test_parse_args_accepts_prepare_and_review_options(tmp_path):
    import scripts.prepare_and_review_rebalance as script

    json_path = tmp_path / "dry_run.json"
    md_path = tmp_path / "dry_run.md"
    args = script.parse_args([
        "--as-of-date",
        "2026-05-08",
        "--top-n",
        "20",
        "--output-json",
        str(json_path),
        "--output-md",
        str(md_path),
        "--quote-retries",
        "4",
        "--quote-delay-sec",
        "0.5",
    ])

    assert args.as_of_date == date(2026, 5, 8)
    assert args.top_n == 20
    assert args.output_json == json_path
    assert args.output_md == md_path
    assert args.quote_retries == 4
    assert args.quote_delay_sec == 0.5


def test_run_calls_prepare_then_review_when_prepare_succeeds(tmp_path):
    import scripts.prepare_and_review_rebalance as script

    json_path = tmp_path / "dry_run.json"
    md_path = tmp_path / "dry_run.md"
    prepare_run = MagicMock(return_value=0)
    review_run = MagicMock(return_value=0)
    args = script.parse_args([
        "--as-of-date",
        "2026-05-08",
        "--output-json",
        str(json_path),
        "--output-md",
        str(md_path),
    ])

    result = script.run(args, prepare_run=prepare_run, review_run=review_run)

    prepare_args = prepare_run.call_args.args[0]
    review_args = review_run.call_args.args[0]
    assert result == 0
    assert prepare_args.as_of_date == date(2026, 5, 8)
    assert prepare_args.output_json == json_path
    assert prepare_args.output_md == md_path
    assert review_args.dry_run_json == json_path
    assert review_args.execution_report_json is None


def test_run_stops_before_review_when_prepare_fails(tmp_path):
    import scripts.prepare_and_review_rebalance as script

    prepare_run = MagicMock(return_value=1)
    review_run = MagicMock()
    args = script.parse_args([
        "--as-of-date",
        "2026-05-08",
        "--output-json",
        str(tmp_path / "dry_run.json"),
    ])

    result = script.run(args, prepare_run=prepare_run, review_run=review_run)

    assert result == 1
    review_run.assert_not_called()


def test_run_returns_review_failure_when_prepare_passes_but_review_blocks(tmp_path):
    import scripts.prepare_and_review_rebalance as script

    prepare_run = MagicMock(return_value=0)
    review_run = MagicMock(return_value=1)
    args = script.parse_args([
        "--as-of-date",
        "2026-05-08",
        "--output-json",
        str(tmp_path / "dry_run.json"),
    ])

    result = script.run(args, prepare_run=prepare_run, review_run=review_run)

    assert result == 1
