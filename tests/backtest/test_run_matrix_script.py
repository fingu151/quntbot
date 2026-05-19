from datetime import date
from pathlib import Path

from config import COST
from scripts.run_backtest_matrix import parse_args, run
from src.backtest.models import BacktestResult


def test_parse_args_accepts_matrix_options():
    args = parse_args(
        [
            "--start-date",
            "2026-01-01",
            "--end-date",
            "2026-01-31",
            "--top-ns",
            "10,20",
            "--rebalance-frequencies",
            "daily,weekly",
            "--cost-scenarios",
            "base,zero,slippage20",
            "--include-stops-disabled",
            "--stop-cooldown-days",
            "5",
            "--commission-rate",
            "0.001",
            "--tax-rate-kospi",
            "0.002",
            "--tax-rate-kosdaq",
            "0.003",
            "--slippage-rate",
            "0.004",
            "--initial-capital",
            "5000000",
            "--database-url",
            "sqlite:///:memory:",
        ]
    )

    assert args.start_date == date(2026, 1, 1)
    assert args.end_date == date(2026, 1, 31)
    assert args.top_ns == [10, 20]
    assert args.rebalance_frequencies == ["daily", "weekly"]
    assert args.cost_scenarios == ["base", "zero", "slippage20"]
    assert args.include_stops_disabled is True
    assert args.stop_cooldown_days == 5
    assert args.commission_rate == 0.001
    assert args.tax_rate_kospi == 0.002
    assert args.tax_rate_kosdaq == 0.003
    assert args.slippage_rate == 0.004
    assert args.initial_capital == 5_000_000
    assert args.database_url == "sqlite:///:memory:"


def test_run_prints_one_row_per_matrix_scenario(capsys):
    calls = []

    def fake_run_backtest(engine, **kwargs):
        calls.append(kwargs)
        final_equity = 10_000 + len(calls)
        return BacktestResult(
            initial_capital=10_000,
            final_equity=final_equity,
            total_return=(final_equity / 10_000) - 1.0,
            cagr=0.1,
            max_drawdown=-0.2,
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
            "--top-ns",
            "10,20",
            "--rebalance-frequencies",
            "weekly",
            "--cost-scenarios",
            "base,zero",
            "--include-stops-disabled",
            "--stop-cooldown-days",
            "2",
            "--commission-rate",
            "0.001",
            "--tax-rate-kospi",
            "0.002",
            "--tax-rate-kosdaq",
            "0.003",
            "--slippage-rate",
            "0.004",
            "--initial-capital",
            "10000",
            "--database-url",
            "sqlite:///:memory:",
        ]
    )

    exit_code = run(args, run_backtest_func=fake_run_backtest)

    captured = capsys.readouterr()
    assert exit_code == 0
    assert len(calls) == 8
    assert calls[0]["top_n"] == 10
    assert calls[0]["rebalance_frequency"] == "weekly"
    assert calls[0]["enable_stops"] is True
    assert calls[0]["stop_cooldown_days"] == 2
    assert calls[0]["commission_rate"] == COST.commission_rate
    assert calls[0]["tax_rate_kospi"] == COST.tax_rate_kospi
    assert calls[0]["tax_rate_kosdaq"] == COST.tax_rate_kosdaq
    assert calls[0]["slippage_rate"] == COST.slippage_rate
    assert calls[1]["enable_stops"] is False
    assert calls[2]["commission_rate"] == 0.0
    assert calls[2]["tax_rate_kospi"] == 0.0
    assert calls[2]["tax_rate_kosdaq"] == 0.0
    assert calls[2]["slippage_rate"] == 0.0
    assert "top_n,rebalance_frequency,cost_scenario,stops,final_equity,total_return,cagr,max_drawdown,sharpe_ratio,win_rate,average_holding_days,trade_count" in captured.out
    assert "10,weekly,base,on,10001.00,0.01%,10.00%,-20.00%,1.5000,60.00%,5.00,0" in captured.out


def test_run_writes_csv_output_file(capsys):
    output_path = Path("data/test_backtest_matrix.csv")
    output_path.unlink(missing_ok=True)

    def fake_run_backtest(engine, **kwargs):
        return BacktestResult(
            initial_capital=10_000,
            final_equity=11_000,
            total_return=0.1,
            cagr=0.2,
            max_drawdown=-0.05,
            sharpe_ratio=1.25,
            win_rate=0.55,
            average_holding_days=7.0,
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
            "--output-csv",
            str(output_path),
        ]
    )

    try:
        exit_code = run(args, run_backtest_func=fake_run_backtest)

        captured = capsys.readouterr()
        assert exit_code == 0
        assert f"wrote_csv={output_path}" in captured.out
        assert output_path.read_text(encoding="utf-8").splitlines() == [
            "top_n,rebalance_frequency,cost_scenario,stops,final_equity,total_return,cagr,max_drawdown,sharpe_ratio,win_rate,average_holding_days,trade_count",
            "30,weekly,custom,on,11000.00,10.00%,20.00%,-5.00%,1.2500,55.00%,7.00,0",
        ]
    finally:
        output_path.unlink(missing_ok=True)


def test_run_writes_markdown_report(capsys):
    output_path = Path("data/test_backtest_matrix.md")
    output_path.unlink(missing_ok=True)

    final_equities = iter([10_000, 12_000])

    def fake_run_backtest(engine, **kwargs):
        final_equity = next(final_equities)
        return BacktestResult(
            initial_capital=10_000,
            final_equity=final_equity,
            total_return=(final_equity / 10_000) - 1.0,
            cagr=0.2,
            max_drawdown=-0.05,
            sharpe_ratio=final_equity / 10_000,
            win_rate=0.55,
            average_holding_days=7.0,
            trades=[],
            equity_curve=[],
        )

    args = parse_args(
        [
            "--start-date",
            "2026-01-01",
            "--end-date",
            "2026-01-31",
            "--cost-scenarios",
            "base,zero",
            "--database-url",
            "sqlite:///:memory:",
            "--output-md",
            str(output_path),
        ]
    )

    try:
        exit_code = run(args, run_backtest_func=fake_run_backtest)

        captured = capsys.readouterr()
        report = output_path.read_text(encoding="utf-8")
        assert exit_code == 0
        assert f"wrote_md={output_path}" in captured.out
        assert "# Backtest Matrix Report" in report
        assert "Best by Sharpe: top_n=30, rebalance=weekly, cost=zero, stops=on" in report
        assert "Best by Return: top_n=30, rebalance=weekly, cost=zero, stops=on" in report
        assert "Lowest MDD: top_n=30, rebalance=weekly, cost=base, stops=on" in report
        assert "Lowest Trades: top_n=30, rebalance=weekly, cost=base, stops=on" in report
        assert "| 30 | weekly | zero | on | 12000.00 | 20.00% | 1.2000 |" in report
    finally:
        output_path.unlink(missing_ok=True)
