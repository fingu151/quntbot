from datetime import date
from pathlib import Path

from scripts import run_strategy_optimization
from src.backtest.models import BacktestResult, BacktestTrade


def _result(final_equity: float, *, reason: str = "rebalance") -> BacktestResult:
    return BacktestResult(
        initial_capital=100_000_000,
        final_equity=final_equity,
        total_return=(final_equity / 100_000_000) - 1.0,
        cagr=0.10,
        max_drawdown=-0.12,
        sharpe_ratio=final_equity / 100_000_000,
        win_rate=0.55,
        average_holding_days=20.0,
        trades=[
            BacktestTrade(
                date=date(2026, 1, 2),
                ticker="AAA",
                side="SELL",
                quantity=1,
                price=10_000,
                gross_amount=10_000,
                cost=15,
                reason=reason,
            )
        ],
        equity_curve=[],
    )


def test_parse_args_defaults_to_plan_windows_and_candidates():
    args = run_strategy_optimization.parse_args([])

    assert args.recent_start == date(2024, 5, 16)
    assert args.recent_end == date(2026, 5, 19)
    assert args.bear_start == date(2021, 7, 1)
    assert args.bear_end == date(2023, 1, 31)
    assert args.long_start == date(2020, 7, 1)
    assert args.long_end == date(2026, 5, 18)
    assert args.candidates == [
        "current_top30",
        "top15",
        "top20",
        "adaptive_alpha_tuned",
        "adaptive_alpha_v2",
        "inverse_hedge_conservative",
        "crash_guard_top30",
        "crash_guard_inverse_top30",
        "crash_guard_v2_reentry",
        "dynamic_topn_crash_guard",
        "dynamic_topn_deep_defense",
        "dynamic_topn_deep_reentry10",
        "dynamic_topn_deep_reentry10_cash10",
        "dynamic_topn_deep_reentry10_cash10_vol20",
    ]


def test_run_writes_strategy_optimization_report(tmp_path, capsys):
    calls = []

    def fake_base_backtest(engine, **kwargs):
        calls.append(("base", kwargs))
        return _result(110_000_000, reason="rebalance")

    def fake_adaptive_backtest(engine, **kwargs):
        calls.append(("adaptive", kwargs))
        return _result(120_000_000, reason="profit_take_20")

    output_csv = tmp_path / "strategy.csv"
    output_md = tmp_path / "strategy.md"
    args = run_strategy_optimization.parse_args(
        [
            "--windows",
            "recent",
            "--database-url",
            f"sqlite:///{tmp_path / 'strategy.db'}",
            "--output-csv",
            str(output_csv),
            "--output-md",
            str(output_md),
        ]
    )

    exit_code = run_strategy_optimization.run(
        args,
        base_backtest_func=fake_base_backtest,
        adaptive_backtest_func=fake_adaptive_backtest,
    )

    out = capsys.readouterr().out
    rows = output_csv.read_text(encoding="utf-8").splitlines()
    report = output_md.read_text(encoding="utf-8")

    assert exit_code == 0
    assert rows[0].startswith("window,candidate,start_date,end_date")
    assert len(rows) == 15
    assert any("recent,current_top30" in row for row in rows)
    assert any("recent,adaptive_alpha_v2" in row for row in rows)
    assert "profit_take_20:1" in report
    assert "Best by Sharpe" in report
    assert "wrote_csv=" in out
    assert calls[0][0] == "base"
    assert calls[0][1]["top_n"] == 30
    assert calls[3][0] == "adaptive"
    assert calls[4][1]["config"].top_n == 30
    assert calls[5][1]["enable_inverse_etf_hedge"] is True
    assert calls[5][1]["inverse_etf_require_market_confirmation"] is True
    assert calls[6][0] == "base"
    assert calls[6][1]["enable_crash_guard"] is True
    assert calls[6][1]["crash_guard_severe_cash_target"] == 0.55
    assert calls[7][1]["enable_crash_guard"] is True
    assert calls[7][1]["enable_inverse_etf_hedge"] is True
    assert calls[7][1]["inverse_etf_require_market_confirmation"] is True
    assert calls[8][1]["enable_crash_guard_reentry"] is True
    assert calls[8][1]["crash_guard_reentry_cash_target"] == 0.15
    assert calls[9][1]["enable_dynamic_top_n"] is True
    assert calls[9][1]["defensive_top_n"] == 20
    assert calls[9][1]["severe_defensive_top_n"] == 15
    assert calls[10][1]["enable_dynamic_top_n"] is True
    assert calls[10][1]["crash_guard_moderate_cash_target"] == 0.40
    assert calls[10][1]["crash_guard_severe_cash_target"] == 0.60
    assert calls[10][1]["defensive_top_n"] == 18
    assert calls[10][1]["severe_defensive_top_n"] == 12
    assert calls[11][1]["enable_dynamic_top_n"] is True
    assert calls[11][1]["crash_guard_moderate_cash_target"] == 0.40
    assert calls[11][1]["crash_guard_severe_cash_target"] == 0.60
    assert calls[11][1]["crash_guard_reentry_cash_target"] == 0.10
    assert calls[11][1]["defensive_top_n"] == 18
    assert calls[11][1]["severe_defensive_top_n"] == 12
    assert calls[12][1]["baseline_cash_target"] == 0.10
    assert calls[12][1]["crash_guard_reentry_cash_target"] == 0.10
    assert calls[12][1]["defensive_top_n"] == 18
    assert calls[12][1]["severe_defensive_top_n"] == 12
    assert calls[13][1]["baseline_cash_target"] == 0.10
    assert calls[13][1]["enable_volatility_cash_overlay"] is True
    assert calls[13][1]["volatility_moderate_annualized"] == 0.20
    assert calls[13][1]["volatility_severe_annualized"] == 0.30


def test_run_reuses_base_scoring_func_per_window(tmp_path):
    calls = []
    factory_calls = []

    def fake_score_func(engine, *, as_of_date):
        del engine, as_of_date
        return []

    def fake_score_func_factory(engine, *, start_date, end_date):
        factory_calls.append((start_date, end_date))
        return fake_score_func

    def fake_base_backtest(engine, **kwargs):
        calls.append(kwargs)
        return _result(110_000_000, reason="rebalance")

    args = run_strategy_optimization.parse_args(
        [
            "--windows",
            "long",
            "--candidates",
            "current_top30,crash_guard_top30,crash_guard_inverse_top30",
            "--database-url",
            f"sqlite:///{tmp_path / 'strategy.db'}",
            "--output-csv",
            str(tmp_path / "strategy.csv"),
            "--output-md",
            str(tmp_path / "strategy.md"),
        ]
    )

    run_strategy_optimization.run(
        args,
        base_backtest_func=fake_base_backtest,
        score_func_factory=fake_score_func_factory,
    )

    assert factory_calls == [(date(2020, 7, 1), date(2026, 5, 18))]
    assert [call["scoring_func"] for call in calls] == [
        fake_score_func,
        fake_score_func,
        fake_score_func,
    ]


def test_parse_args_accepts_experimental_dynamic_topn_candidates():
    args = run_strategy_optimization.parse_args(
        [
            "--candidates",
            (
                "dynamic_topn_loose_guard,dynamic_topn_fast_reentry,"
                "dynamic_topn_deep_reentry10_cash5,dynamic_topn_deep_reentry10_cash10,"
                "dynamic_topn_deep_reentry10_cash10_vol20,"
                "dynamic_topn_deep_reentry10_cash10_vol25,"
                "dynamic_topn_deep_reentry10_cash10_vol20_flow45,"
                "dynamic_topn_deep_reentry10_cash10_vol20_flow40,"
                "dynamic_topn_deep_reentry10_cash10_vol20_breadth45,"
                "dynamic_topn_deep_reentry10_cash10_vol20_breadth40,"
                "dynamic_topn_deep_reentry15_cash15_crash45,"
                "dynamic_topn_deep_reentry10_cash10_vol20_winner_room"
            ),
        ]
    )

    assert args.candidates == [
        "dynamic_topn_loose_guard",
        "dynamic_topn_fast_reentry",
        "dynamic_topn_deep_reentry10_cash5",
        "dynamic_topn_deep_reentry10_cash10",
        "dynamic_topn_deep_reentry10_cash10_vol20",
        "dynamic_topn_deep_reentry10_cash10_vol25",
        "dynamic_topn_deep_reentry10_cash10_vol20_flow45",
        "dynamic_topn_deep_reentry10_cash10_vol20_flow40",
        "dynamic_topn_deep_reentry10_cash10_vol20_breadth45",
        "dynamic_topn_deep_reentry10_cash10_vol20_breadth40",
        "dynamic_topn_deep_reentry15_cash15_crash45",
        "dynamic_topn_deep_reentry10_cash10_vol20_winner_room",
    ]


def test_run_dispatches_experimental_dynamic_topn_parameters_and_cash_reserve(tmp_path):
    calls = []

    def fake_base_backtest(engine, **kwargs):
        calls.append(kwargs)
        return _result(110_000_000, reason="rebalance")

    args = run_strategy_optimization.parse_args(
        [
            "--windows",
            "recent",
            "--candidates",
            (
                "dynamic_topn_loose_guard,dynamic_topn_fast_reentry,"
                "dynamic_topn_deep_reentry10_cash5,dynamic_topn_deep_reentry10_cash10,"
                "dynamic_topn_deep_reentry10_cash10_vol20,"
                "dynamic_topn_deep_reentry10_cash10_vol25,"
                "dynamic_topn_deep_reentry10_cash10_vol20_flow45,"
                "dynamic_topn_deep_reentry10_cash10_vol20_flow40,"
                "dynamic_topn_deep_reentry10_cash10_vol20_breadth45,"
                "dynamic_topn_deep_reentry10_cash10_vol20_breadth40,"
                "dynamic_topn_deep_reentry15_cash15_crash45,"
                "dynamic_topn_deep_reentry10_cash10_vol20_winner_room"
            ),
            "--database-url",
            f"sqlite:///{tmp_path / 'strategy.db'}",
            "--output-csv",
            str(tmp_path / "strategy.csv"),
            "--output-md",
            str(tmp_path / "strategy.md"),
        ]
    )

    run_strategy_optimization.run(args, base_backtest_func=fake_base_backtest)

    assert calls[0]["crash_guard_moderate_cash_target"] == 0.30
    assert calls[0]["crash_guard_severe_cash_target"] == 0.45
    assert calls[0]["defensive_top_n"] == 22
    assert calls[0]["severe_defensive_top_n"] == 18
    assert calls[1]["crash_guard_reentry_cash_target"] == 0.05
    assert calls[1]["crash_guard_reentry_rsi_threshold"] == 40.0
    assert calls[1]["crash_guard_reentry_positive_days"] == 2
    assert calls[2]["baseline_cash_target"] == 0.05
    assert calls[2]["crash_guard_reentry_cash_target"] == 0.10
    assert calls[2]["defensive_top_n"] == 18
    assert calls[2]["severe_defensive_top_n"] == 12
    assert calls[3]["baseline_cash_target"] == 0.10
    assert calls[3]["crash_guard_reentry_cash_target"] == 0.10
    assert calls[3]["defensive_top_n"] == 18
    assert calls[3]["severe_defensive_top_n"] == 12
    assert calls[4]["baseline_cash_target"] == 0.10
    assert calls[4]["enable_volatility_cash_overlay"] is True
    assert calls[4]["volatility_moderate_annualized"] == 0.20
    assert calls[4]["volatility_severe_annualized"] == 0.30
    assert calls[5]["baseline_cash_target"] == 0.10
    assert calls[5]["enable_volatility_cash_overlay"] is True
    assert calls[5]["volatility_moderate_annualized"] == 0.25
    assert calls[5]["volatility_severe_annualized"] == 0.35
    assert calls[6]["enable_flow_breadth_cash_overlay"] is True
    assert calls[6]["flow_breadth_moderate_threshold"] == 0.45
    assert calls[6]["flow_breadth_severe_threshold"] == 0.40
    assert calls[7]["enable_flow_breadth_cash_overlay"] is True
    assert calls[7]["flow_breadth_moderate_threshold"] == 0.40
    assert calls[7]["flow_breadth_severe_threshold"] == 0.35
    assert calls[8]["enable_price_breadth_cash_overlay"] is True
    assert calls[8]["price_breadth_moderate_threshold"] == 0.45
    assert calls[8]["price_breadth_severe_threshold"] == 0.35
    assert calls[9]["enable_price_breadth_cash_overlay"] is True
    assert calls[9]["price_breadth_moderate_threshold"] == 0.40
    assert calls[9]["price_breadth_severe_threshold"] == 0.30
    assert calls[10]["baseline_cash_target"] == 0.15
    assert calls[10]["crash_guard_moderate_cash_target"] == 0.45
    assert calls[10]["crash_guard_severe_cash_target"] == 0.65
    assert calls[10]["crash_guard_reentry_cash_target"] == 0.15
    assert calls[11]["baseline_cash_target"] == 0.10
    assert calls[11]["profit_take_sell_fraction"] == 0.45
    assert calls[11]["post_profit_trailing_stop_pct"] == -0.10
    assert calls[11]["breakeven_stop_pct"] == -0.03
