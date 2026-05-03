from datetime import date

import pytest

from src.backtest.engine import run_backtest
from src.data.database import create_tables, get_engine, session_scope
from src.data.repositories import upsert_daily_prices, upsert_stocks
from src.factors.models import FactorScore


def seed_prices(engine):
    with session_scope(engine) as session:
        upsert_stocks(
            session,
            [
                {"ticker": "AAA", "name": "상승", "market": "KOSPI200"},
                {"ticker": "BBB", "name": "하락", "market": "KOSDAQ150"},
            ],
        )
        upsert_daily_prices(
            session,
            [
                {"ticker": "AAA", "date": date(2026, 1, 1), "close": 100},
                {"ticker": "BBB", "date": date(2026, 1, 1), "close": 100},
                {"ticker": "AAA", "date": date(2026, 1, 2), "close": 110},
                {"ticker": "BBB", "date": date(2026, 1, 2), "close": 90},
                {"ticker": "AAA", "date": date(2026, 1, 3), "close": 120},
                {"ticker": "BBB", "date": date(2026, 1, 3), "close": 80},
            ],
        )


def score_prefers_aaa(engine, *, as_of_date, lookback_days=None):
    return [
        FactorScore("AAA", "상승", "KOSPI200", as_of_date, 1, 0, 1, 2, 1),
        FactorScore("BBB", "하락", "KOSDAQ150", as_of_date, -1, 0, -1, -2, 2),
    ]


def score_switches_on_second_day(engine, *, as_of_date, lookback_days=None):
    if as_of_date < date(2026, 1, 2):
        return [
            FactorScore("AAA", "상승", "KOSPI200", as_of_date, 1, 0, 1, 2, 1),
            FactorScore("BBB", "하락", "KOSDAQ150", as_of_date, -1, 0, -1, -2, 2),
        ]
    return [
        FactorScore("BBB", "하락", "KOSDAQ150", as_of_date, 1, 0, 1, 2, 1),
        FactorScore("AAA", "상승", "KOSPI200", as_of_date, -1, 0, -1, -2, 2),
    ]


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
    )

    assert result.final_equity == 12_000
    assert result.total_return == pytest.approx(0.2)
    assert result.trades[0].side == "BUY"
    assert result.trades[0].ticker == "AAA"
    assert len(result.equity_curve) == 3


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
    )

    trade_sides = [(trade.side, trade.ticker) for trade in result.trades]
    assert trade_sides == [("BUY", "AAA"), ("SELL", "AAA"), ("BUY", "BBB")]


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
