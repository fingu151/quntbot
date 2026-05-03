from datetime import date
import subprocess
import sys

from scripts.run_phase3_backtest import parse_args, run
from src.backtest.models import BacktestResult


def test_parse_args_accepts_backtest_options():
    args = parse_args(
        [
            "--start-date",
            "2026-01-01",
            "--end-date",
            "2026-01-31",
            "--top-n",
            "10",
            "--initial-capital",
            "5000000",
            "--database-url",
            "sqlite:///:memory:",
        ]
    )

    assert args.start_date == date(2026, 1, 1)
    assert args.end_date == date(2026, 1, 31)
    assert args.top_n == 10
    assert args.initial_capital == 5_000_000
    assert args.database_url == "sqlite:///:memory:"


def test_run_prints_backtest_summary(capsys):
    def fake_run_backtest(engine, **kwargs):
        return BacktestResult(
            initial_capital=10_000,
            final_equity=12_000,
            total_return=0.2,
            cagr=0.3,
            max_drawdown=-0.1,
            sharpe_ratio=1.5,
            win_rate=0.6,
            average_holding_days=5.0,
            trades=[],
            equity_curve=[],
        )

    args = parse_args(
        [
            "--start-date",
            "2026-01-01",
            "--end-date",
            "2026-01-31",
            "--database-url",
            "sqlite:///:memory:",
        ]
    )

    exit_code = run(args, run_backtest_func=fake_run_backtest)

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "final_equity=12000.00" in captured.out
    assert "total_return=20.00%" in captured.out
    assert "sharpe_ratio=1.5000" in captured.out


def test_script_can_be_executed_directly_with_help():
    completed = subprocess.run(
        [sys.executable, "scripts/run_phase3_backtest.py", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "Run Phase 3 backtest." in completed.stdout
