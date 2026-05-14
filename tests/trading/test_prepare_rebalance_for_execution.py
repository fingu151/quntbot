from datetime import date
from pathlib import Path
from unittest.mock import MagicMock


def test_parse_args_accepts_prepare_options(tmp_path):
    import scripts.prepare_rebalance_for_execution as prepare

    json_path = tmp_path / "dry_run.json"
    md_path = tmp_path / "dry_run.md"
    args = prepare.parse_args([
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


def test_run_invokes_strict_dry_run_and_preflight(tmp_path, capsys):
    import scripts.prepare_rebalance_for_execution as prepare

    json_path = tmp_path / "dry_run.json"
    md_path = tmp_path / "dry_run.md"
    dry_run_func = MagicMock(return_value=0)
    preflight_func = MagicMock()
    args = prepare.parse_args([
        "--as-of-date",
        "2026-05-08",
        "--output-json",
        str(json_path),
        "--output-md",
        str(md_path),
    ])

    result = prepare.run(
        args,
        dry_run_func=dry_run_func,
        preflight_func=preflight_func,
    )

    dry_run_args = dry_run_func.call_args.args[0]
    assert result == 0
    assert dry_run_args.as_of_date == date(2026, 5, 8)
    assert dry_run_args.output_json == json_path
    assert dry_run_args.output_md == md_path
    assert dry_run_args.price_fallback == "none"
    assert dry_run_args.quote_retries == 4
    assert dry_run_args.quote_delay_sec == 0.5
    preflight_func.assert_called_once_with(
        json_path,
        expected_preflight_date=date(2026, 5, 8),
    )
    assert "prepare_ready=" in capsys.readouterr().out


def test_run_returns_error_when_dry_run_fails(tmp_path, capsys):
    import scripts.prepare_rebalance_for_execution as prepare

    dry_run_func = MagicMock(return_value=1)
    preflight_func = MagicMock()
    args = prepare.parse_args([
        "--as-of-date",
        "2026-05-08",
        "--output-json",
        str(tmp_path / "dry_run.json"),
    ])

    result = prepare.run(
        args,
        dry_run_func=dry_run_func,
        preflight_func=preflight_func,
    )

    assert result == 1
    assert "dry_run_failed=1" in capsys.readouterr().out
    preflight_func.assert_not_called()


def test_run_returns_error_when_preflight_blocks(tmp_path, capsys):
    import scripts.prepare_rebalance_for_execution as prepare

    dry_run_func = MagicMock(return_value=0)
    preflight_func = MagicMock(side_effect=RuntimeError("stale report"))
    args = prepare.parse_args([
        "--as-of-date",
        "2026-05-08",
        "--output-json",
        str(tmp_path / "dry_run.json"),
    ])

    result = prepare.run(
        args,
        dry_run_func=dry_run_func,
        preflight_func=preflight_func,
    )

    assert result == 1
    assert "prepare_blocked=stale report" in capsys.readouterr().out
