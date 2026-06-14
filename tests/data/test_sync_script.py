from datetime import date
import subprocess
import sys

from scripts.sync_phase1_data import parse_args, run


def test_parse_args_accepts_date_range_and_database_url():
    args = parse_args(
        [
            "--start-date",
            "2026-05-01",
            "--end-date",
            "2026-05-03",
            "--database-url",
            "sqlite:///:memory:",
        ]
    )

    assert args.start_date == date(2026, 5, 1)
    assert args.end_date == date(2026, 5, 3)
    assert args.database_url == "sqlite:///:memory:"


def test_parse_args_accepts_historical_universe_and_no_deactivation():
    args = parse_args(
        [
            "--start-date",
            "2009-01-01",
            "--end-date",
            "2010-12-31",
            "--universe-date",
            "2010-01-04",
            "--no-deactivate-missing",
        ]
    )

    assert args.universe_date == date(2010, 1, 4)
    assert args.deactivate_missing is False


def test_run_prints_sync_counts_with_injected_sync_function(capsys):
    def fake_sync(
        *,
        engine,
        provider,
        start_date,
        end_date,
        max_workers=5,
        universe_date=None,
        deactivate_missing=True,
    ):
        assert provider == "fake-provider"
        assert start_date == date(2026, 5, 1)
        assert end_date == date(2026, 5, 3)
        assert max_workers == 5
        assert universe_date is None
        assert deactivate_missing is True
        return {"universe_count": 2, "price_count": 4, "fundamental_count": 4}

    args = parse_args(
        [
            "--start-date",
            "2026-05-01",
            "--end-date",
            "2026-05-03",
            "--database-url",
            "sqlite:///:memory:",
        ]
    )

    exit_code = run(args, provider="fake-provider", sync_func=fake_sync)

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "universe_count=2" in captured.out
    assert "price_count=4" in captured.out
    assert "fundamental_count=4" in captured.out


def test_run_passes_historical_backfill_options_to_sync_function(capsys):
    def fake_sync(
        *,
        engine,
        provider,
        start_date,
        end_date,
        max_workers=5,
        universe_date=None,
        deactivate_missing=True,
    ):
        del engine
        assert provider == "fake-provider"
        assert start_date == date(2009, 1, 1)
        assert end_date == date(2010, 12, 31)
        assert universe_date == date(2010, 1, 4)
        assert deactivate_missing is False
        assert max_workers == 2
        return {"universe_count": 2, "price_count": 4, "fundamental_count": 4}

    args = parse_args(
        [
            "--start-date",
            "2009-01-01",
            "--end-date",
            "2010-12-31",
            "--universe-date",
            "2010-01-04",
            "--no-deactivate-missing",
            "--workers",
            "2",
            "--database-url",
            "sqlite:///:memory:",
        ]
    )

    exit_code = run(args, provider="fake-provider", sync_func=fake_sync)

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "universe_count=2" in captured.out


def test_script_can_be_executed_directly_with_help():
    completed = subprocess.run(
        [sys.executable, "scripts/sync_phase1_data.py", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "Sync Phase 1 market data into SQLite." in completed.stdout
