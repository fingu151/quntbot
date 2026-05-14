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


def test_run_prints_sync_counts_with_injected_sync_function(capsys):
    def fake_sync(*, engine, provider, start_date, end_date, max_workers=5):
        assert provider == "fake-provider"
        assert start_date == date(2026, 5, 1)
        assert end_date == date(2026, 5, 3)
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


def test_script_can_be_executed_directly_with_help():
    completed = subprocess.run(
        [sys.executable, "scripts/sync_phase1_data.py", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "Sync Phase 1 market data into SQLite." in completed.stdout
