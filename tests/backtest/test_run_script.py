from datetime import date
import subprocess
import sys

import pytest

from scripts import run_backtest_matrix as matrix_script
from scripts.run_phase3_backtest import parse_args, run
from src.backtest.models import BacktestResult, BacktestTrade


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
    assert args.enable_stops is True
    assert args.rebalance_frequency == "weekly"


def test_parse_args_accepts_disable_stops():
    args = parse_args(["--disable-stops"])

    assert args.enable_stops is False


def test_parse_args_accepts_trade_summary():
    args = parse_args(["--trade-summary"])

    assert args.trade_summary is True


def test_parse_args_accepts_rebalance_frequency():
    args = parse_args(["--rebalance-frequency", "weekly"])

    assert args.rebalance_frequency == "weekly"


def test_parse_args_accepts_stop_thresholds():
    args = parse_args(
        ["--stop-loss-pct", "-0.05", "--trailing-stop-pct", "-0.07", "--stop-cooldown-days", "3"]
    )

    assert args.stop_loss_pct == -0.05
    assert args.trailing_stop_pct == -0.07
    assert args.stop_cooldown_days == 3


def test_parse_args_accepts_staged_exit_rebalance_and_weighting_options():
    args = parse_args(
        [
            "--profit-take-pct",
            "0.25",
            "--profit-take-sell-fraction",
            "0.40",
            "--breakeven-stop-pct",
            "-0.01",
            "--sell-rank-buffer",
            "25",
            "--min-holding-trading-days",
            "4",
            "--weighting",
            "equal",
            "--min-position-weight",
            "0.05",
            "--max-position-weight",
            "0.20",
        ]
    )

    assert args.profit_take_pct == 0.25
    assert args.profit_take_sell_fraction == 0.40
    assert args.breakeven_stop_pct == -0.01
    assert args.sell_rank_buffer == 25
    assert args.min_holding_trading_days == 4
    assert args.weighting == "equal"
    assert args.min_position_weight == 0.05
    assert args.max_position_weight == 0.20


@pytest.mark.parametrize(
    ("argv", "expected_message"),
    [
        (["--min-position-weight", "0"], "--min-position-weight must be greater than 0"),
        (["--max-position-weight", "1.1"], "--max-position-weight must be at most 1"),
        (
            ["--min-position-weight", "0.30", "--max-position-weight", "0.20"],
            "--min-position-weight must be less than or equal to --max-position-weight",
        ),
    ],
)
def test_parse_args_validates_position_weight_caps(argv, expected_message, capsys):
    with pytest.raises(SystemExit):
        parse_args(argv)

    captured = capsys.readouterr()
    assert expected_message in captured.err


def test_parse_args_accepts_cost_overrides():
    args = parse_args(
        [
            "--commission-rate",
            "0.001",
            "--tax-rate-kospi",
            "0.002",
            "--tax-rate-kosdaq",
            "0.003",
            "--slippage-rate",
            "0.004",
        ]
    )

    assert args.commission_rate == 0.001
    assert args.tax_rate_kospi == 0.002
    assert args.tax_rate_kosdaq == 0.003
    assert args.slippage_rate == 0.004


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


def test_run_prints_trade_summary_when_requested(capsys):
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
            trades=[
                BacktestTrade(date(2026, 1, 1), "AAA", "BUY", 1, 100, 100, 1, "rebalance"),
                BacktestTrade(date(2026, 1, 2), "AAA", "SELL", 1, 110, 110, 1, "rebalance"),
                BacktestTrade(date(2026, 1, 3), "BBB", "SELL", 1, 90, 90, 1, "stop_loss"),
            ],
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
            "--trade-summary",
        ]
    )

    run(args, run_backtest_func=fake_run_backtest)

    captured = capsys.readouterr()
    assert "buy_count=1" in captured.out
    assert "sell_count=2" in captured.out
    assert "trade_reasons=rebalance:2, stop_loss:1" in captured.out


def test_run_passes_stop_toggle_to_backtest():
    captured_kwargs = {}

    def fake_run_backtest(engine, **kwargs):
        captured_kwargs.update(kwargs)
        return BacktestResult(
            initial_capital=10_000,
            final_equity=10_000,
            total_return=0.0,
            cagr=0.0,
            max_drawdown=0.0,
            sharpe_ratio=0.0,
            win_rate=0.0,
            average_holding_days=0.0,
            trades=[],
            equity_curve=[],
        )

    args = parse_args(["--database-url", "sqlite:///:memory:", "--disable-stops"])

    run(args, run_backtest_func=fake_run_backtest)

    assert captured_kwargs["enable_stops"] is False


def test_run_passes_rebalance_frequency_to_backtest():
    captured_kwargs = {}

    def fake_run_backtest(engine, **kwargs):
        captured_kwargs.update(kwargs)
        return BacktestResult(
            initial_capital=10_000,
            final_equity=10_000,
            total_return=0.0,
            cagr=0.0,
            max_drawdown=0.0,
            sharpe_ratio=0.0,
            win_rate=0.0,
            average_holding_days=0.0,
            trades=[],
            equity_curve=[],
        )

    args = parse_args(["--database-url", "sqlite:///:memory:", "--rebalance-frequency", "monthly"])

    run(args, run_backtest_func=fake_run_backtest)

    assert captured_kwargs["rebalance_frequency"] == "monthly"


def test_run_passes_stop_thresholds_to_backtest():
    captured_kwargs = {}

    def fake_run_backtest(engine, **kwargs):
        captured_kwargs.update(kwargs)
        return BacktestResult(
            initial_capital=10_000,
            final_equity=10_000,
            total_return=0.0,
            cagr=0.0,
            max_drawdown=0.0,
            sharpe_ratio=0.0,
            win_rate=0.0,
            average_holding_days=0.0,
            trades=[],
            equity_curve=[],
        )

    args = parse_args(
        [
            "--database-url",
            "sqlite:///:memory:",
            "--stop-loss-pct",
            "-0.05",
            "--trailing-stop-pct",
            "-0.07",
            "--stop-cooldown-days",
            "3",
        ]
    )

    run(args, run_backtest_func=fake_run_backtest)

    assert captured_kwargs["stop_loss_pct"] == -0.05
    assert captured_kwargs["trailing_stop_pct"] == -0.07
    assert captured_kwargs["stop_cooldown_days"] == 3


def test_run_passes_staged_exit_rebalance_and_weighting_options_to_backtest():
    captured_kwargs = {}

    def fake_run_backtest(engine, **kwargs):
        captured_kwargs.update(kwargs)
        return BacktestResult(
            initial_capital=10_000,
            final_equity=10_000,
            total_return=0.0,
            cagr=0.0,
            max_drawdown=0.0,
            sharpe_ratio=0.0,
            win_rate=0.0,
            average_holding_days=0.0,
            trades=[],
            equity_curve=[],
        )

    args = parse_args(
        [
            "--database-url",
            "sqlite:///:memory:",
            "--profit-take-pct",
            "0.25",
            "--profit-take-sell-fraction",
            "0.40",
            "--breakeven-stop-pct",
            "-0.01",
            "--sell-rank-buffer",
            "25",
            "--min-holding-trading-days",
            "4",
            "--weighting",
            "equal",
            "--min-position-weight",
            "0.05",
            "--max-position-weight",
            "0.20",
        ]
    )

    run(args, run_backtest_func=fake_run_backtest)

    assert captured_kwargs["profit_take_pct"] == 0.25
    assert captured_kwargs["profit_take_sell_fraction"] == 0.40
    assert captured_kwargs["breakeven_stop_pct"] == -0.01
    assert captured_kwargs["sell_rank_buffer"] == 25
    assert captured_kwargs["min_holding_trading_days"] == 4
    assert captured_kwargs["weighting"] == "equal"
    assert captured_kwargs["min_position_weight"] == 0.05
    assert captured_kwargs["max_position_weight"] == 0.20


def test_run_passes_cost_overrides_to_backtest():
    captured_kwargs = {}

    def fake_run_backtest(engine, **kwargs):
        captured_kwargs.update(kwargs)
        return BacktestResult(
            initial_capital=10_000,
            final_equity=10_000,
            total_return=0.0,
            cagr=0.0,
            max_drawdown=0.0,
            sharpe_ratio=0.0,
            win_rate=0.0,
            average_holding_days=0.0,
            trades=[],
            equity_curve=[],
        )

    args = parse_args(
        [
            "--database-url",
            "sqlite:///:memory:",
            "--commission-rate",
            "0.001",
            "--tax-rate-kospi",
            "0.002",
            "--tax-rate-kosdaq",
            "0.003",
            "--slippage-rate",
            "0.004",
        ]
    )

    run(args, run_backtest_func=fake_run_backtest)

    assert captured_kwargs["commission_rate"] == 0.001
    assert captured_kwargs["tax_rate_kospi"] == 0.002
    assert captured_kwargs["tax_rate_kosdaq"] == 0.003
    assert captured_kwargs["slippage_rate"] == 0.004


def test_matrix_parse_args_accepts_staged_exit_rebalance_and_weighting_options():
    args = matrix_script.parse_args(
        [
            "--profit-take-pct",
            "0.25",
            "--profit-take-sell-fraction",
            "0.40",
            "--breakeven-stop-pct",
            "-0.01",
            "--sell-rank-buffer",
            "25",
            "--min-holding-trading-days",
            "4",
            "--weighting",
            "equal",
            "--min-position-weight",
            "0.05",
            "--max-position-weight",
            "0.20",
        ]
    )

    assert args.profit_take_pct == 0.25
    assert args.profit_take_sell_fraction == 0.40
    assert args.breakeven_stop_pct == -0.01
    assert args.sell_rank_buffer == 25
    assert args.min_holding_trading_days == 4
    assert args.weighting == "equal"
    assert args.min_position_weight == 0.05
    assert args.max_position_weight == 0.20


@pytest.mark.parametrize(
    ("argv", "expected_message"),
    [
        (["--min-position-weight", "0"], "--min-position-weight must be greater than 0"),
        (["--max-position-weight", "1.1"], "--max-position-weight must be at most 1"),
        (
            ["--min-position-weight", "0.30", "--max-position-weight", "0.20"],
            "--min-position-weight must be less than or equal to --max-position-weight",
        ),
    ],
)
def test_matrix_parse_args_validates_position_weight_caps(argv, expected_message, capsys):
    with pytest.raises(SystemExit):
        matrix_script.parse_args(argv)

    captured = capsys.readouterr()
    assert expected_message in captured.err


def test_matrix_run_passes_staged_exit_rebalance_and_weighting_options_to_backtest(capsys):
    captured_kwargs = {}

    def fake_run_backtest(engine, **kwargs):
        captured_kwargs.update(kwargs)
        return BacktestResult(
            initial_capital=10_000,
            final_equity=10_000,
            total_return=0.0,
            cagr=0.0,
            max_drawdown=0.0,
            sharpe_ratio=0.0,
            win_rate=0.0,
            average_holding_days=0.0,
            trades=[],
            equity_curve=[],
        )

    args = matrix_script.parse_args(
        [
            "--database-url",
            "sqlite:///:memory:",
            "--profit-take-pct",
            "0.25",
            "--profit-take-sell-fraction",
            "0.40",
            "--breakeven-stop-pct",
            "-0.01",
            "--sell-rank-buffer",
            "25",
            "--min-holding-trading-days",
            "4",
            "--weighting",
            "equal",
            "--min-position-weight",
            "0.05",
            "--max-position-weight",
            "0.20",
        ]
    )

    matrix_script.run(args, run_backtest_func=fake_run_backtest)
    capsys.readouterr()

    assert captured_kwargs["profit_take_pct"] == 0.25
    assert captured_kwargs["profit_take_sell_fraction"] == 0.40
    assert captured_kwargs["breakeven_stop_pct"] == -0.01
    assert captured_kwargs["sell_rank_buffer"] == 25
    assert captured_kwargs["min_holding_trading_days"] == 4
    assert captured_kwargs["weighting"] == "equal"
    assert captured_kwargs["min_position_weight"] == 0.05
    assert captured_kwargs["max_position_weight"] == 0.20


def test_script_can_be_executed_directly_with_help():
    completed = subprocess.run(
        [sys.executable, "scripts/run_phase3_backtest.py", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "Run Phase 3 backtest." in completed.stdout
    assert "--disable-stops" in completed.stdout
    assert "--rebalance-frequency" in completed.stdout
    assert "--stop-loss-pct" in completed.stdout
    assert "--trailing-stop-pct" in completed.stdout
    assert "--stop-cooldown-days" in completed.stdout
    assert "--profit-take-pct" in completed.stdout
    assert "--profit-take-sell-fraction" in completed.stdout
    assert "--breakeven-stop-pct" in completed.stdout
    assert "--sell-rank-buffer" in completed.stdout
    assert "--min-holding-trading-days" in completed.stdout
    assert "--weighting" in completed.stdout
    assert "--min-position-weight" in completed.stdout
    assert "--max-position-weight" in completed.stdout
    assert "--commission-rate" in completed.stdout
    assert "--slippage-rate" in completed.stdout
