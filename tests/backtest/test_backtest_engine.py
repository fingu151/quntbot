from datetime import date, timedelta

import pytest

from src.backtest import engine as backtest_engine
from src.backtest.engine import _group_prices_by_date, _is_kosdaq_market, run_backtest
from src.data.database import create_tables, get_engine, session_scope
from src.data.repositories import (
    upsert_daily_prices,
    upsert_fundamentals,
    upsert_quality_metrics,
    upsert_stocks,
)
from src.factors.models import FactorScore


def seed_prices(engine):
    with session_scope(engine) as session:
        upsert_stocks(
            session,
            [
                {"ticker": "AAA", "name": "상승", "market": "KOSPI"},
                {"ticker": "BBB", "name": "하락", "market": "KOSDAQ"},
            ],
        )
        upsert_daily_prices(
            session,
            [
                {"ticker": "AAA", "date": date(2026, 1, 1), "open": 100, "close": 100},
                {"ticker": "BBB", "date": date(2026, 1, 1), "open": 100, "close": 100},
                {"ticker": "AAA", "date": date(2026, 1, 2), "open": 110, "close": 110},
                {"ticker": "BBB", "date": date(2026, 1, 2), "open": 90, "close": 90},
                {"ticker": "AAA", "date": date(2026, 1, 3), "open": 120, "close": 120},
                {"ticker": "BBB", "date": date(2026, 1, 3), "open": 80, "close": 80},
            ],
        )


def score_prefers_aaa(engine, *, as_of_date, lookback_days=None):
    return [
        FactorScore("AAA", "상승", "KOSPI", as_of_date, 1, 0, 1, 0, 0, 2, 1),
        FactorScore("BBB", "하락", "KOSDAQ", as_of_date, -1, 0, -1, 0, 0, -2, 2),
    ]


def score_switches_on_second_day(engine, *, as_of_date, lookback_days=None):
    if as_of_date < date(2026, 1, 2):
        return [
            FactorScore("AAA", "상승", "KOSPI", as_of_date, 1, 0, 1, 0, 0, 2, 1),
            FactorScore("BBB", "하락", "KOSDAQ", as_of_date, -1, 0, -1, 0, 0, -2, 2),
        ]
    return [
        FactorScore("BBB", "하락", "KOSDAQ", as_of_date, 1, 0, 1, 0, 0, 2, 1),
        FactorScore("AAA", "상승", "KOSPI", as_of_date, -1, 0, -1, 0, 0, -2, 2),
    ]


def score_prefers_bbb_then_aaa(engine, *, as_of_date, lookback_days=None):
    if as_of_date < date(2026, 1, 2):
        return [
            FactorScore("BBB", "?섎씫", "KOSDAQ", as_of_date, 1, 0, 1, 0, 0, 2, 1),
            FactorScore("AAA", "?곸듅", "KOSPI", as_of_date, -1, 0, -1, 0, 0, -2, 2),
        ]
    return [
        FactorScore("AAA", "?곸듅", "KOSPI", as_of_date, 1, 0, 1, 0, 0, 2, 1),
        FactorScore("BBB", "?섎씫", "KOSDAQ", as_of_date, -1, 0, -1, 0, 0, -2, 2),
    ]


def score_always_aaa(engine, *, as_of_date, lookback_days=None):
    return [FactorScore("AAA", "AAA", "KOSPI", as_of_date, 1, 0, 1, 0, 0, 2, 1)]


def score_always_aaa_bbb(engine, *, as_of_date, lookback_days=None):
    return [
        FactorScore("AAA", "AAA", "KOSPI", as_of_date, 1, 0, 1, 0, 0, 2, 1),
        FactorScore("BBB", "BBB", "KOSPI", as_of_date, 0, 0, 0, 0, 0, 0, 2),
    ]


def seed_single_stock_prices(engine, rows):
    with session_scope(engine) as session:
        upsert_stocks(session, [{"ticker": "AAA", "name": "AAA", "market": "KOSPI"}])
        upsert_daily_prices(
            session,
            [{"ticker": "AAA", "date": price_date, "open": open_, "close": close} for price_date, open_, close in rows],
        )


def seed_prices_for_tickers(engine, tickers, *, start: date, days: int, price: int) -> None:
    with session_scope(engine) as session:
        upsert_stocks(
            session,
            [{"ticker": ticker, "name": ticker, "market": "KOSPI"} for ticker in tickers],
        )
        rows = []
        for offset in range(days):
            price_date = start + timedelta(days=offset)
            for ticker in tickers:
                rows.append({"ticker": ticker, "date": price_date, "open": price, "close": price})
        upsert_daily_prices(session, rows)


def test_run_backtest_buys_top_ranked_stock_and_tracks_equity():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    seed_prices(engine)

    result = run_backtest(
        engine,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 3),
        scoring_func=score_prefers_aaa,
        initial_capital=10_000,
        top_n=1,
        commission_rate=0.0,
        tax_rate_kospi=0.0,
        tax_rate_kosdaq=0.0,
        slippage_rate=0.0,
        enable_stops=False,
        rebalance_frequency="daily",
        weighting="equal",
    )

    assert result.final_equity == pytest.approx(10_909.0909090909)
    assert result.total_return == pytest.approx(0.0909090909090909)
    assert result.trades[0].side == "BUY"
    assert result.trades[0].ticker == "AAA"
    assert result.trades[0].date == date(2026, 1, 2)
    assert len(result.equity_curve) == 3


def test_run_backtest_scores_previous_trading_day_and_executes_rebalance_at_open():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    seed_prices(engine)
    signal_dates = []

    def score_records_signal_date(engine, *, as_of_date, lookback_days=None):
        signal_dates.append(as_of_date)
        return [FactorScore("AAA", "AAA", "KOSPI", as_of_date, 1, 0, 1, 0, 0, 2, 1)]

    result = run_backtest(
        engine,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 3),
        scoring_func=score_records_signal_date,
        initial_capital=10_000,
        top_n=1,
        commission_rate=0.0,
        tax_rate_kospi=0.0,
        tax_rate_kosdaq=0.0,
        slippage_rate=0.0,
        enable_stops=False,
        rebalance_frequency="daily",
        sell_rank_buffer=1,
        min_holding_trading_days=0,
        weighting="equal",
    )

    first_buy = next(trade for trade in result.trades if trade.side == "BUY")
    assert signal_dates[0] == date(2026, 1, 1)
    assert first_buy.date == date(2026, 1, 2)
    assert first_buy.price == 110


def test_run_backtest_skips_new_buy_when_execution_open_gap_is_too_large():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    seed_single_stock_prices(
        engine,
        [
            (date(2026, 1, 1), 100, 100),
            (date(2026, 1, 2), 121, 121),
        ],
    )

    result = run_backtest(
        engine,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 2),
        scoring_func=score_always_aaa,
        initial_capital=10_000,
        top_n=1,
        commission_rate=0.0,
        tax_rate_kospi=0.0,
        tax_rate_kosdaq=0.0,
        slippage_rate=0.0,
        enable_stops=False,
        rebalance_frequency="daily",
        sell_rank_buffer=1,
        min_holding_trading_days=0,
        weighting="equal",
    )

    assert result.trades == []


def test_run_backtest_rebalances_when_top_rank_changes():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    seed_prices(engine)

    result = run_backtest(
        engine,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 3),
        scoring_func=score_switches_on_second_day,
        initial_capital=10_000,
        top_n=1,
        commission_rate=0.0,
        tax_rate_kospi=0.0,
        tax_rate_kosdaq=0.0,
        slippage_rate=0.0,
        enable_stops=False,
        rebalance_frequency="daily",
        sell_rank_buffer=1,
        min_holding_trading_days=0,
        weighting="equal",
    )

    trade_sides = [(trade.side, trade.ticker) for trade in result.trades]
    assert trade_sides == [("BUY", "AAA"), ("SELL", "AAA"), ("BUY", "BBB")]


def test_run_backtest_weekly_rebalance_waits_until_next_week():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    with session_scope(engine) as session:
        upsert_stocks(
            session,
            [
                {"ticker": "AAA", "name": "AAA", "market": "KOSPI"},
                {"ticker": "BBB", "name": "BBB", "market": "KOSPI"},
            ],
        )
        upsert_daily_prices(
            session,
            [
                {"ticker": "AAA", "date": date(2026, 1, 1), "open": 100, "close": 100},
                {"ticker": "BBB", "date": date(2026, 1, 1), "open": 100, "close": 100},
                {"ticker": "AAA", "date": date(2026, 1, 2), "open": 100, "close": 100},
                {"ticker": "BBB", "date": date(2026, 1, 2), "open": 100, "close": 100},
                {"ticker": "AAA", "date": date(2026, 1, 5), "open": 100, "close": 100},
                {"ticker": "BBB", "date": date(2026, 1, 5), "open": 100, "close": 100},
            ],
        )

    result = run_backtest(
        engine,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 5),
        scoring_func=score_switches_on_second_day,
        initial_capital=10_000,
        top_n=1,
        commission_rate=0.0,
        tax_rate_kospi=0.0,
        tax_rate_kosdaq=0.0,
        slippage_rate=0.0,
        enable_stops=False,
        rebalance_frequency="weekly",
        sell_rank_buffer=1,
        min_holding_trading_days=0,
        weighting="equal",
    )

    trade_sides = [(trade.date, trade.side, trade.ticker) for trade in result.trades]
    assert trade_sides == [
        (date(2026, 1, 2), "BUY", "AAA"),
        (date(2026, 1, 5), "SELL", "AAA"),
        (date(2026, 1, 5), "BUY", "BBB"),
    ]


def test_run_backtest_costs_reduce_final_equity():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    seed_prices(engine)

    no_cost = run_backtest(
        engine,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 3),
        scoring_func=score_prefers_aaa,
        initial_capital=10_000,
        top_n=1,
        commission_rate=0.0,
        tax_rate_kospi=0.0,
        tax_rate_kosdaq=0.0,
        slippage_rate=0.0,
    )
    with_cost = run_backtest(
        engine,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 3),
        scoring_func=score_prefers_aaa,
        initial_capital=10_000,
        top_n=1,
        commission_rate=0.01,
        tax_rate_kospi=0.02,
        tax_rate_kosdaq=0.02,
        slippage_rate=0.0,
    )

    assert with_cost.final_equity < no_cost.final_equity


def test_sell_uses_kospi_tax_rate():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    seed_prices(engine)

    result = run_backtest(
        engine,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 3),
        scoring_func=score_switches_on_second_day,
        initial_capital=10_000,
        top_n=1,
        commission_rate=0.0,
        tax_rate_kospi=0.0020,
        tax_rate_kosdaq=0.0,
        slippage_rate=0.0,
        rebalance_frequency="daily",
        sell_rank_buffer=1,
        min_holding_trading_days=0,
        weighting="equal",
    )

    sell = next(trade for trade in result.trades if trade.side == "SELL" and trade.ticker == "AAA")
    assert sell.cost == pytest.approx(sell.gross_amount * 0.0020)


def test_sell_uses_kosdaq_tax_rate():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    seed_prices(engine)

    result = run_backtest(
        engine,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 3),
        scoring_func=score_prefers_bbb_then_aaa,
        initial_capital=10_000,
        top_n=1,
        commission_rate=0.0,
        tax_rate_kospi=0.0,
        tax_rate_kosdaq=0.0020,
        slippage_rate=0.0,
        sell_rank_buffer=1,
        min_holding_trading_days=0,
        weighting="equal",
    )

    sell = next(trade for trade in result.trades if trade.side == "SELL" and trade.ticker == "BBB")
    assert sell.cost == pytest.approx(sell.gross_amount * 0.0020)


def test_run_backtest_triggers_stop_loss_and_executes_next_open():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    seed_single_stock_prices(
        engine,
        [
            (date(2026, 1, 1), 100, 100),
            (date(2026, 1, 2), 100, 100),
            (date(2026, 1, 3), 95, 95),
            (date(2026, 1, 4), 89, 88),
            (date(2026, 1, 5), 86, 90),
        ],
    )

    result = run_backtest(
        engine,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 5),
        scoring_func=score_always_aaa,
        initial_capital=10_000,
        top_n=1,
        commission_rate=0.0,
        tax_rate_kospi=0.0,
        tax_rate_kosdaq=0.0,
        slippage_rate=0.0,
        stop_loss_pct=-0.10,
    )

    sells = [trade for trade in result.trades if trade.side == "SELL"]
    assert len(sells) == 1
    assert sells[0].date == date(2026, 1, 5)
    assert sells[0].price == 86
    assert sells[0].reason == "stop_loss"
    assert [trade.side for trade in result.trades] == ["BUY", "SELL"]


def test_run_backtest_triggers_trailing_stop_after_peak_drop():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    seed_single_stock_prices(
        engine,
        [
            (date(2026, 1, 1), 100, 100),
            (date(2026, 1, 2), 110, 110),
            (date(2026, 1, 3), 120, 120),
            (date(2026, 1, 4), 106, 105),
            (date(2026, 1, 5), 104, 108),
        ],
    )

    result = run_backtest(
        engine,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 5),
        scoring_func=score_always_aaa,
        initial_capital=10_000,
        top_n=1,
        commission_rate=0.0,
        tax_rate_kospi=0.0,
        tax_rate_kosdaq=0.0,
        slippage_rate=0.0,
        stop_loss_pct=-0.50,
        profit_take_pct=0.05,
        trailing_stop_pct=-0.10,
        breakeven_stop_pct=-0.20,
        weighting="equal",
    )

    sells = [trade for trade in result.trades if trade.side == "SELL"]
    assert [trade.reason for trade in sells] == ["profit_take_20", "post_profit_trailing_stop"]
    assert sells[-1].date == date(2026, 1, 5)
    assert sells[-1].price == 104


def test_run_backtest_prefers_stop_loss_when_both_stops_trigger():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    seed_single_stock_prices(
        engine,
        [
            (date(2026, 1, 1), 100, 100),
            (date(2026, 1, 2), 130, 130),
            (date(2026, 1, 3), 120, 120),
            (date(2026, 1, 4), 89, 88),
            (date(2026, 1, 5), 87, 90),
        ],
    )

    result = run_backtest(
        engine,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 5),
        scoring_func=score_always_aaa,
        initial_capital=10_000,
        top_n=1,
        commission_rate=0.0,
        tax_rate_kospi=0.0,
        tax_rate_kosdaq=0.0,
        slippage_rate=0.0,
        stop_loss_pct=-0.10,
        trailing_stop_pct=-0.10,
        weighting="equal",
    )

    sell = next(trade for trade in result.trades if trade.side == "SELL")
    assert sell.reason == "stop_loss"


def test_run_backtest_triggers_stop_on_last_day_uses_close_fallback():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    seed_single_stock_prices(
        engine,
        [
            (date(2026, 1, 1), 100, 100),
            (date(2026, 1, 2), 100, 100),
            (date(2026, 1, 3), 95, 95),
            (date(2026, 1, 4), 89, 88),
        ],
    )

    result = run_backtest(
        engine,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 4),
        scoring_func=score_always_aaa,
        initial_capital=10_000,
        top_n=1,
        commission_rate=0.0,
        tax_rate_kospi=0.0,
        tax_rate_kosdaq=0.0,
        slippage_rate=0.0,
        stop_loss_pct=-0.10,
        weighting="equal",
    )

    sell = next(trade for trade in result.trades if trade.side == "SELL")
    assert sell.date == date(2026, 1, 4)
    assert sell.price == 88
    assert sell.reason == "stop_loss_close_fallback"


def test_run_backtest_disable_stops_keeps_old_behavior():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    seed_single_stock_prices(
        engine,
        [
            (date(2026, 1, 1), 100, 100),
            (date(2026, 1, 2), 96, 96),
            (date(2026, 1, 3), 95, 95),
            (date(2026, 1, 4), 89, 88),
            (date(2026, 1, 5), 86, 90),
        ],
    )

    result = run_backtest(
        engine,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 5),
        scoring_func=score_always_aaa,
        initial_capital=10_000,
        top_n=1,
        commission_rate=0.0,
        tax_rate_kospi=0.0,
        tax_rate_kosdaq=0.0,
        slippage_rate=0.0,
        enable_stops=False,
        stop_loss_pct=-0.10,
        weighting="equal",
    )

    assert [trade.side for trade in result.trades] == ["BUY"]


def test_run_backtest_takes_half_profit_at_twenty_percent_next_open():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    seed_single_stock_prices(
        engine,
        [
            (date(2026, 1, 1), 100, 100),
            (date(2026, 1, 2), 100, 121),
            (date(2026, 1, 3), 122, 122),
        ],
    )

    result = run_backtest(
        engine,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 3),
        scoring_func=score_always_aaa,
        initial_capital=10_000,
        top_n=1,
        commission_rate=0.0,
        tax_rate_kospi=0.0,
        tax_rate_kosdaq=0.0,
        slippage_rate=0.0,
        stop_loss_pct=-0.05,
        profit_take_pct=0.20,
        profit_take_sell_fraction=0.50,
        weighting="equal",
    )

    sells = [trade for trade in result.trades if trade.side == "SELL"]
    assert len(sells) == 1
    assert sells[0].reason == "profit_take_20"
    assert sells[0].date == date(2026, 1, 3)
    assert sells[0].quantity == pytest.approx(50.0)


def test_run_backtest_post_profit_trailing_bucket_sells_independently():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    seed_single_stock_prices(
        engine,
        [
            (date(2026, 1, 1), 100, 100),
            (date(2026, 1, 2), 100, 121),
            (date(2026, 1, 3), 122, 130),
            (date(2026, 1, 4), 116, 116),
            (date(2026, 1, 5), 115, 118),
        ],
    )

    result = run_backtest(
        engine,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 5),
        scoring_func=score_always_aaa,
        initial_capital=10_000,
        top_n=1,
        commission_rate=0.0,
        tax_rate_kospi=0.0,
        tax_rate_kosdaq=0.0,
        slippage_rate=0.0,
        stop_loss_pct=-0.05,
        profit_take_pct=0.20,
        trailing_stop_pct=-0.10,
        weighting="equal",
    )

    reasons = [trade.reason for trade in result.trades if trade.side == "SELL"]
    assert reasons == ["profit_take_20", "post_profit_trailing_stop"]


def test_run_backtest_post_profit_breakeven_bucket_sells_independently():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    seed_single_stock_prices(
        engine,
        [
            (date(2026, 1, 1), 100, 100),
            (date(2026, 1, 2), 100, 121),
            (date(2026, 1, 3), 122, 130),
            (date(2026, 1, 4), 101, 100),
            (date(2026, 1, 5), 99, 100),
        ],
    )

    result = run_backtest(
        engine,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 5),
        scoring_func=score_always_aaa,
        initial_capital=10_000,
        top_n=1,
        commission_rate=0.0,
        tax_rate_kospi=0.0,
        tax_rate_kosdaq=0.0,
        slippage_rate=0.0,
        stop_loss_pct=-0.05,
        profit_take_pct=0.20,
        trailing_stop_pct=-0.50,
        weighting="equal",
    )

    reasons = [trade.reason for trade in result.trades if trade.side == "SELL"]
    assert reasons == ["profit_take_20", "post_profit_breakeven_stop"]


def test_rebalance_buffer_keeps_rank_just_outside_top_n():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    seed_prices_for_tickers(engine, ["AAA", "BBB"], start=date(2026, 1, 1), days=5, price=100)

    def score_func(_engine, *, as_of_date):
        if as_of_date <= date(2026, 1, 2):
            return [
                FactorScore("AAA", "AAA", "KOSPI", as_of_date, 1, 0, 1, 0, 0, 10.0, 1),
                FactorScore("BBB", "BBB", "KOSPI", as_of_date, 1, 0, 1, 0, 0, 9.0, 2),
            ]
        return [
            FactorScore("BBB", "BBB", "KOSPI", as_of_date, 1, 0, 1, 0, 0, 10.0, 1),
            FactorScore("AAA", "AAA", "KOSPI", as_of_date, 1, 0, 1, 0, 0, 9.0, 2),
        ]

    result = run_backtest(
        engine,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 5),
        scoring_func=score_func,
        initial_capital=10_000,
        top_n=1,
        sell_rank_buffer=2,
        rebalance_frequency="daily",
        commission_rate=0.0,
        tax_rate_kospi=0.0,
        tax_rate_kosdaq=0.0,
        slippage_rate=0.0,
        enable_stops=False,
    )

    assert [trade.reason for trade in result.trades if trade.side == "SELL"] == []


def test_rebalance_min_holding_blocks_early_rebalance_sell():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    seed_prices_for_tickers(engine, ["AAA", "BBB"], start=date(2026, 1, 1), days=6, price=100)

    def score_func(_engine, *, as_of_date):
        if as_of_date <= date(2026, 1, 2):
            return [FactorScore("AAA", "AAA", "KOSPI", as_of_date, 1, 0, 1, 0, 0, 10.0, 1)]
        return [FactorScore("BBB", "BBB", "KOSPI", as_of_date, 1, 0, 1, 0, 0, 10.0, 1)]

    result = run_backtest(
        engine,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 6),
        scoring_func=score_func,
        initial_capital=10_000,
        top_n=1,
        sell_rank_buffer=1,
        min_holding_trading_days=2,
        rebalance_frequency="daily",
        commission_rate=0.0,
        tax_rate_kospi=0.0,
        tax_rate_kosdaq=0.0,
        slippage_rate=0.0,
        enable_stops=False,
    )

    sells = [trade for trade in result.trades if trade.side == "SELL" and trade.reason == "rebalance"]
    assert sells[0].date == date(2026, 1, 4)


def test_run_backtest_score_weighted_allocation_uses_target_scores():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    seed_prices_for_tickers(engine, ["AAA", "BBB"], start=date(2026, 1, 1), days=3, price=100)

    def score_func(_engine, *, as_of_date):
        return [
            FactorScore("AAA", "AAA", "KOSPI", as_of_date, 1, 0, 1, 0, 0, 3.0, 1),
            FactorScore("BBB", "BBB", "KOSPI", as_of_date, 1, 0, 1, 0, 0, 1.0, 2),
        ]

    result = run_backtest(
        engine,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 3),
        scoring_func=score_func,
        initial_capital=10_000,
        top_n=2,
        weighting="score_weighted",
        min_position_weight=0.01,
        max_position_weight=0.80,
        commission_rate=0.0,
        tax_rate_kospi=0.0,
        tax_rate_kosdaq=0.0,
        slippage_rate=0.0,
        enable_stops=False,
    )

    buys = [trade for trade in result.trades if trade.side == "BUY"]
    assert [(trade.ticker, trade.quantity) for trade in buys] == [
        ("AAA", pytest.approx(75.0)),
        ("BBB", pytest.approx(25.0)),
    ]


def test_stops_with_costs_change_trade_count_and_equity():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    with session_scope(engine) as session:
        upsert_stocks(
            session,
            [
                {"ticker": "AAA", "name": "AAA", "market": "KOSPI"},
                {"ticker": "BBB", "name": "BBB", "market": "KOSPI"},
            ],
        )
        upsert_daily_prices(
            session,
            [
                {"ticker": "AAA", "date": date(2026, 1, 1), "open": 100, "close": 100},
                {"ticker": "AAA", "date": date(2026, 1, 2), "open": 100, "close": 100},
                {"ticker": "AAA", "date": date(2026, 1, 3), "open": 95, "close": 95},
                {"ticker": "AAA", "date": date(2026, 1, 4), "open": 89, "close": 88},
                {"ticker": "AAA", "date": date(2026, 1, 5), "open": 86, "close": 90},
                {"ticker": "BBB", "date": date(2026, 1, 1), "open": 100, "close": 100},
                {"ticker": "BBB", "date": date(2026, 1, 2), "open": 100, "close": 100},
                {"ticker": "BBB", "date": date(2026, 1, 3), "open": 100, "close": 100},
                {"ticker": "BBB", "date": date(2026, 1, 4), "open": 100, "close": 100},
                {"ticker": "BBB", "date": date(2026, 1, 5), "open": 100, "close": 100},
            ],
        )

    stop_result = run_backtest(
        engine,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 5),
        scoring_func=score_always_aaa_bbb,
        initial_capital=10_000,
        top_n=2,
        commission_rate=0.001,
        tax_rate_kospi=0.002,
        tax_rate_kosdaq=0.002,
        slippage_rate=0.001,
        stop_loss_pct=-0.10,
        rebalance_frequency="daily",
    )
    no_stop_result = run_backtest(
        engine,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 5),
        scoring_func=score_always_aaa_bbb,
        initial_capital=10_000,
        top_n=2,
        commission_rate=0.001,
        tax_rate_kospi=0.002,
        tax_rate_kosdaq=0.002,
        slippage_rate=0.001,
        enable_stops=False,
        stop_loss_pct=-0.10,
        rebalance_frequency="daily",
    )

    assert len(stop_result.trades) > len(no_stop_result.trades)
    assert stop_result.final_equity != no_stop_result.final_equity


def test_stop_cooldown_blocks_rebuy_until_calendar_days_pass():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    with session_scope(engine) as session:
        upsert_stocks(session, [{"ticker": "AAA", "name": "AAA", "market": "KOSPI"}])
        upsert_daily_prices(
            session,
            [
                {"ticker": "AAA", "date": date(2026, 1, 1), "open": 100, "close": 100},
                {"ticker": "AAA", "date": date(2026, 1, 2), "open": 100, "close": 80},
                {"ticker": "AAA", "date": date(2026, 1, 3), "open": 80, "close": 80},
                {"ticker": "AAA", "date": date(2026, 1, 4), "open": 80, "close": 80},
                {"ticker": "AAA", "date": date(2026, 1, 5), "open": 80, "close": 80},
                {"ticker": "AAA", "date": date(2026, 1, 6), "open": 80, "close": 80},
            ],
        )

    result = run_backtest(
        engine,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 6),
        scoring_func=score_prefers_aaa,
        initial_capital=10_000,
        top_n=1,
        commission_rate=0.0,
        tax_rate_kospi=0.0,
        tax_rate_kosdaq=0.0,
        slippage_rate=0.0,
        stop_loss_pct=-0.10,
        stop_cooldown_days=1,
        rebalance_frequency="daily",
        weighting="equal",
    )

    buys = [trade.date for trade in result.trades if trade.side == "BUY"]
    sells = [trade.date for trade in result.trades if trade.side == "SELL"]
    assert sells == [date(2026, 1, 3)]
    assert buys == [date(2026, 1, 2), date(2026, 1, 5)]


def test_is_kosdaq_market_accepts_new_and_legacy_market_names():
    assert _is_kosdaq_market("KOSDAQ") is True
    assert _is_kosdaq_market("KOSDAQ150") is True
    assert _is_kosdaq_market("KOSPI") is False


def test_group_prices_by_date_groups_tickers_under_each_trading_date():
    grouped = _group_prices_by_date({
        ("AAA", date(2026, 1, 1)): 100.0,
        ("BBB", date(2026, 1, 1)): 90.0,
        ("AAA", date(2026, 1, 2)): 110.0,
    })

    assert grouped == {
        date(2026, 1, 1): {"AAA": 100.0, "BBB": 90.0},
        date(2026, 1, 2): {"AAA": 110.0},
    }


def test_load_prices_includes_open_and_close():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    with session_scope(engine) as session:
        upsert_stocks(session, [{"ticker": "AAA", "name": "AAA", "market": "KOSPI"}])
        upsert_daily_prices(
            session,
            [{"ticker": "AAA", "date": date(2026, 1, 1), "open": 95, "close": 100}],
        )

    prices = backtest_engine._load_prices(
        engine,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 1),
    )

    assert prices[("AAA", date(2026, 1, 1))] == {"open": 95.0, "close": 100.0}


def test_default_fast_scorer_uses_quality_metrics_for_ranking():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    start_date = date(2026, 5, 15)
    end_date = date(2026, 5, 16)
    price_rows = []
    for offset in range(130, -1, -1):
        price_date = start_date.fromordinal(start_date.toordinal() - offset)
        close = 100 + ((130 - offset) * 0.1)
        for ticker in ["AAA", "BBB"]:
            price_rows.append(
                {"ticker": ticker, "date": price_date, "open": close, "close": close}
            )
    for ticker in ["AAA", "BBB"]:
        price_rows.append({"ticker": ticker, "date": end_date, "open": 114, "close": 114})

    with session_scope(engine) as session:
        upsert_stocks(
            session,
            [
                {"ticker": "AAA", "name": "Low Quality", "market": "KOSPI"},
                {"ticker": "BBB", "name": "High Quality", "market": "KOSPI"},
            ],
        )
        upsert_daily_prices(session, price_rows)
        upsert_fundamentals(
            session,
            [
                {"ticker": "AAA", "date": start_date, "per": 10, "pbr": 1, "eps": 1, "bps": 10, "div": 1},
                {"ticker": "BBB", "date": start_date, "per": 10, "pbr": 1, "eps": 1, "bps": 10, "div": 1},
            ],
        )
        upsert_quality_metrics(
            session,
            [
                {
                    "ticker": "AAA",
                    "fiscal_year": 2025,
                    "fiscal_quarter": 4,
                    "roe": -0.05,
                    "operating_margin": 0.01,
                    "debt_ratio": 3.0,
                    "published_at": date(2026, 3, 31),
                },
                {
                    "ticker": "BBB",
                    "fiscal_year": 2025,
                    "fiscal_quarter": 4,
                    "roe": 0.20,
                    "operating_margin": 0.15,
                    "debt_ratio": 0.4,
                    "published_at": date(2026, 3, 31),
                },
            ],
        )

    result = run_backtest(
        engine,
        start_date=start_date,
        end_date=end_date,
        initial_capital=10_000,
        top_n=1,
        commission_rate=0.0,
        tax_rate_kospi=0.0,
        tax_rate_kosdaq=0.0,
        slippage_rate=0.0,
        enable_stops=False,
    )

    first_buy = next(trade for trade in result.trades if trade.side == "BUY")
    assert first_buy.ticker == "BBB"
