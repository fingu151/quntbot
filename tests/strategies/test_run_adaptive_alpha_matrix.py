from datetime import date

from scripts import run_adaptive_alpha_matrix
from src.backtest.models import BacktestResult


def test_parse_args_accepts_small_matrix():
    args = run_adaptive_alpha_matrix.parse_args(
        [
            "--start-date",
            "2026-01-01",
            "--end-date",
            "2026-01-31",
            "--sell-rank-buffers",
            "40,45",
            "--atr-multipliers",
            "2.0,2.2",
            "--profit-take-pcts",
            "0.18",
        ]
    )

    assert args.start_date == date(2026, 1, 1)
    assert args.sell_rank_buffers == [40, 45]
    assert args.atr_multipliers == [2.0, 2.2]
    assert args.profit_take_pcts == [0.18]


def test_run_writes_matrix_outputs(tmp_path, capsys):
    calls = []

    def fake_backtest(engine, **kwargs):
        calls.append(kwargs["config"])
        return BacktestResult(
            initial_capital=100,
            final_equity=110 + len(calls),
            total_return=0.10 + len(calls) / 100,
            cagr=0.10,
            max_drawdown=-0.05,
            sharpe_ratio=1.2 + len(calls) / 10,
            win_rate=0.5,
            average_holding_days=5,
            trades=[],
            equity_curve=[],
        )

    output_csv = tmp_path / "matrix.csv"
    output_md = tmp_path / "matrix.md"
    args = run_adaptive_alpha_matrix.parse_args(
        [
            "--start-date",
            "2026-01-01",
            "--end-date",
            "2026-01-31",
            "--database-url",
            f"sqlite:///{tmp_path / 'matrix.db'}",
            "--sell-rank-buffers",
            "40,45",
            "--atr-multipliers",
            "2.2",
            "--profit-take-pcts",
            "0.18",
            "--output-csv",
            str(output_csv),
            "--output-md",
            str(output_md),
        ]
    )

    exit_code = run_adaptive_alpha_matrix.run(args, backtest_func=fake_backtest)

    assert exit_code == 0
    assert [config.sell_rank_buffer for config in calls] == [40, 45]
    assert output_csv.read_text(encoding="utf-8").splitlines()[0].startswith("sell_rank_buffer,")
    assert "Best by Sharpe" in output_md.read_text(encoding="utf-8")
    assert "wrote_csv=" in capsys.readouterr().out
