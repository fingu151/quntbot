from datetime import date
import subprocess
import sys

from scripts.rank_phase2_factors import parse_args, run
from src.factors.models import FactorScore


def test_parse_args_accepts_as_of_date_top_n_and_database_url():
    args = parse_args(
        [
            "--as-of-date",
            "2026-05-01",
            "--top-n",
            "5",
            "--database-url",
            "sqlite:///:memory:",
        ]
    )

    assert args.as_of_date == date(2026, 5, 1)
    assert args.top_n == 5
    assert args.database_url == "sqlite:///:memory:"


def test_run_prints_top_ranked_factor_scores(capsys):
    def fake_calculate(engine, *, as_of_date, lookback_days=None):
        return [
            FactorScore("AAA", "좋은종목", "KOSPI200", as_of_date, 1.1, 0.0, 0.9, 2.0, 1),
            FactorScore("BBB", "나쁜종목", "KOSDAQ150", as_of_date, -1.1, 0.0, -0.9, -2.0, 2),
        ]

    args = parse_args(
        [
            "--as-of-date",
            "2026-05-01",
            "--top-n",
            "1",
            "--database-url",
            "sqlite:///:memory:",
        ]
    )

    exit_code = run(args, calculate_func=fake_calculate)

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "rank=1 ticker=AAA name=좋은종목 total=2.0000" in captured.out
    assert "BBB" not in captured.out


def test_script_can_be_executed_directly_with_help():
    completed = subprocess.run(
        [sys.executable, "scripts/rank_phase2_factors.py", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "Rank Phase 2 factor scores." in completed.stdout
