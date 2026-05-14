from datetime import date, timedelta

import pandas as pd
import pytest

from src.factors import engine as factor_engine
from src.data.database import create_tables, get_engine, session_scope
from src.data.repositories import (
    upsert_daily_prices,
    upsert_fundamentals,
    upsert_quality_metrics,
    upsert_stocks,
)
from src.factors.engine import calculate_factor_scores


def seed_factor_data(engine):
    as_of_date = date(2026, 5, 1)
    lookback_date = as_of_date - timedelta(days=2)
    with session_scope(engine) as session:
        upsert_stocks(
            session,
            [
                {"ticker": "AAA", "name": "Value Winner", "market": "KOSPI"},
                {"ticker": "BBB", "name": "Value Loser", "market": "KOSPI"},
                {"ticker": "CCC", "name": "Middle", "market": "KOSDAQ"},
            ],
        )
        upsert_daily_prices(
            session,
            [
                {"ticker": "AAA", "date": lookback_date, "close": 100},
                {"ticker": "AAA", "date": as_of_date, "close": 130},
                {"ticker": "BBB", "date": lookback_date, "close": 100},
                {"ticker": "BBB", "date": as_of_date, "close": 90},
                {"ticker": "CCC", "date": lookback_date, "close": 100},
                {"ticker": "CCC", "date": as_of_date, "close": 105},
            ],
        )
        upsert_fundamentals(
            session,
            [
                {
                    "ticker": "AAA",
                    "date": as_of_date,
                    "per": 5,
                    "pbr": 0.5,
                    "eps": 10000,
                    "bps": 50000,
                    "div": 3.0,
                },
                {
                    "ticker": "BBB",
                    "date": as_of_date,
                    "per": 25,
                    "pbr": 3.0,
                    "eps": 1000,
                    "bps": 50000,
                    "div": 0.5,
                },
                {
                    "ticker": "CCC",
                    "date": as_of_date,
                    "per": 12,
                    "pbr": 1.2,
                    "eps": 5000,
                    "bps": 50000,
                    "div": 1.5,
                },
            ],
        )
    return as_of_date


def seed_quality_rank_data(engine):
    as_of_date = date(2026, 5, 15)
    lookback_date = date(2026, 5, 12)
    prior_date = date(2026, 5, 14)
    tickers = ["AAA", "BBB", "CCC"]
    with session_scope(engine) as session:
        upsert_stocks(
            session,
            [
                {"ticker": "AAA", "name": "High Quality", "market": "KOSPI"},
                {"ticker": "BBB", "name": "Low Quality", "market": "KOSPI"},
                {"ticker": "CCC", "name": "Mid Quality", "market": "KOSDAQ"},
            ],
        )
        upsert_daily_prices(
            session,
            [{"ticker": ticker, "date": lookback_date, "close": 100} for ticker in tickers]
            + [{"ticker": ticker, "date": prior_date, "close": 100} for ticker in tickers]
            + [{"ticker": ticker, "date": as_of_date, "close": 100} for ticker in tickers],
        )
        upsert_fundamentals(
            session,
            [
                {
                    "ticker": ticker,
                    "date": lookback_date,
                    "per": 10,
                    "pbr": 1,
                    "eps": 1000,
                    "bps": 10000,
                    "div": 1,
                }
                for ticker in tickers
            ],
        )
        upsert_quality_metrics(
            session,
            [
                {
                    "ticker": "AAA",
                    "fiscal_year": 2025,
                    "fiscal_quarter": 4,
                    "roe": 0.15,
                    "operating_margin": 0.10,
                    "debt_ratio": 0.50,
                    "published_at": date(2026, 3, 31),
                },
                {
                    "ticker": "BBB",
                    "fiscal_year": 2025,
                    "fiscal_quarter": 4,
                    "roe": -0.02,
                    "operating_margin": 0.00,
                    "debt_ratio": 3.00,
                    "published_at": date(2026, 3, 31),
                },
                {
                    "ticker": "CCC",
                    "fiscal_year": 2025,
                    "fiscal_quarter": 4,
                    "roe": 0.03,
                    "operating_margin": 0.05,
                    "debt_ratio": 1.20,
                    "published_at": date(2026, 3, 31),
                },
            ],
        )
    return as_of_date


def test_calculate_factor_scores_ranks_value_and_momentum_candidates():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    as_of_date = seed_factor_data(engine)

    raw = factor_engine._load_factor_inputs(engine, as_of_date=as_of_date, lookback_days=1)
    scores = factor_engine.calculate_factor_scores_from_df(
        raw,
        as_of_date=as_of_date,
        apply_buy_filters=False,
    )

    assert [score.ticker for score in scores] == ["AAA", "CCC", "BBB"]
    assert scores[0].rank == 1
    assert scores[0].value_score > scores[-1].value_score
    assert scores[0].momentum_score > scores[-1].momentum_score
    assert all(score.quality_score == 0.0 for score in scores)
    assert scores[0].yield_score > scores[-1].yield_score


def test_calculate_factor_scores_applies_busanstock_raw_score_as_small_overlay():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    as_of_date = seed_factor_data(engine)

    raw = factor_engine._load_factor_inputs(engine, as_of_date=as_of_date, lookback_days=1)
    without_signal = factor_engine.calculate_factor_scores_from_df(
        raw,
        as_of_date=as_of_date,
        apply_buy_filters=False,
    )
    with_signal = factor_engine.calculate_factor_scores_from_df(
        raw,
        as_of_date=as_of_date,
        busanstock_signals={"BBB": 1.0},
        apply_buy_filters=False,
    )

    before = {score.ticker: score for score in without_signal}
    after = {score.ticker: score for score in with_signal}
    assert after["BBB"].busanstock_score == 1.0
    weight_sum = (
        factor_engine.FACTOR.value_weight
        + factor_engine.FACTOR.quality_weight
        + factor_engine.FACTOR.momentum_weight
        + factor_engine.FACTOR.yield_weight
        + factor_engine.FACTOR.telegram_weight
        + factor_engine.FACTOR.busanstock_weight
        + factor_engine.FACTOR.investor_flow_weight
        + factor_engine.FACTOR.research_report_weight
    )
    assert after["BBB"].total_score == pytest.approx(before["BBB"].total_score + (
        factor_engine.FACTOR.busanstock_weight * 100.0 / weight_sum
    ))


def test_calculate_factor_scores_applies_investor_flow_raw_score_as_small_overlay():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    as_of_date = seed_factor_data(engine)

    raw = factor_engine._load_factor_inputs(engine, as_of_date=as_of_date, lookback_days=1)
    without_signal = factor_engine.calculate_factor_scores_from_df(
        raw,
        as_of_date=as_of_date,
        apply_buy_filters=False,
    )
    with_signal = factor_engine.calculate_factor_scores_from_df(
        raw,
        as_of_date=as_of_date,
        investor_flow_signals={"BBB": -1.0},
        apply_buy_filters=False,
    )

    before = {score.ticker: score for score in without_signal}
    after = {score.ticker: score for score in with_signal}
    assert after["BBB"].investor_flow_score == -1.0
    weight_sum = (
        factor_engine.FACTOR.value_weight
        + factor_engine.FACTOR.quality_weight
        + factor_engine.FACTOR.momentum_weight
        + factor_engine.FACTOR.yield_weight
        + factor_engine.FACTOR.telegram_weight
        + factor_engine.FACTOR.busanstock_weight
        + factor_engine.FACTOR.investor_flow_weight
        + factor_engine.FACTOR.research_report_weight
    )
    assert after["BBB"].total_score == pytest.approx(before["BBB"].total_score - (
        factor_engine.FACTOR.investor_flow_weight * 100.0 / weight_sum
    ))


def test_calculate_factor_scores_applies_research_report_score_as_small_overlay():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    as_of_date = seed_factor_data(engine)

    raw = factor_engine._load_factor_inputs(engine, as_of_date=as_of_date, lookback_days=1)
    without_report = factor_engine.calculate_factor_scores_from_df(
        raw,
        as_of_date=as_of_date,
        apply_buy_filters=False,
    )
    with_report = factor_engine.calculate_factor_scores_from_df(
        raw,
        as_of_date=as_of_date,
        research_report_signals={"BBB": 1.0},
        apply_buy_filters=False,
    )

    before = {score.ticker: score for score in without_report}
    after = {score.ticker: score for score in with_report}
    weight_sum = (
        factor_engine.FACTOR.value_weight
        + factor_engine.FACTOR.quality_weight
        + factor_engine.FACTOR.momentum_weight
        + factor_engine.FACTOR.yield_weight
        + factor_engine.FACTOR.telegram_weight
        + factor_engine.FACTOR.busanstock_weight
        + factor_engine.FACTOR.investor_flow_weight
        + factor_engine.FACTOR.research_report_weight
    )
    assert after["BBB"].research_report_score == 1.0
    assert after["BBB"].total_score == pytest.approx(before["BBB"].total_score + (
        factor_engine.FACTOR.research_report_weight * 100.0 / weight_sum
    ))


def test_calculate_factor_scores_excludes_stocks_without_required_data():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    as_of_date = seed_factor_data(engine)
    with session_scope(engine) as session:
        upsert_stocks(session, [{"ticker": "DDD", "name": "No Data", "market": "KOSPI"}])

    raw = factor_engine._load_factor_inputs(engine, as_of_date=as_of_date, lookback_days=1)
    scores = factor_engine.calculate_factor_scores_from_df(
        raw,
        as_of_date=as_of_date,
        apply_buy_filters=False,
    )

    assert "DDD" not in [score.ticker for score in scores]


def test_load_factor_inputs_skips_empty_latest_fundamental_snapshot():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    as_of_date = date(2026, 5, 13)
    prior_date = date(2026, 5, 12)
    lookback_date = date(2026, 5, 11)
    with session_scope(engine) as session:
        upsert_stocks(
            session,
            [{"ticker": "AAA", "name": "Valid Prior Fundamental", "market": "KOSPI"}],
        )
        upsert_daily_prices(
            session,
            [
                {"ticker": "AAA", "date": lookback_date, "close": 100},
                {"ticker": "AAA", "date": prior_date, "close": 105},
                {"ticker": "AAA", "date": as_of_date, "close": 110},
            ],
        )
        upsert_fundamentals(
            session,
            [
                {
                    "ticker": "AAA",
                    "date": prior_date,
                    "per": 8,
                    "pbr": 0.8,
                    "eps": 1000,
                    "bps": 10000,
                    "div": 2,
                },
                {
                    "ticker": "AAA",
                    "date": as_of_date,
                    "per": 0,
                    "pbr": 0,
                    "eps": 0,
                    "bps": 0,
                    "div": 0,
                },
            ],
        )

    raw = factor_engine._load_factor_inputs(engine, as_of_date=as_of_date, lookback_days=1)

    assert len(raw) == 1
    row = raw.iloc[0]
    assert row["ticker"] == "AAA"
    assert row["per"] == 8
    assert row["pbr"] == 0.8


def test_quality_score_ranks_high_roe_margin_low_debt_higher():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    as_of_date = seed_quality_rank_data(engine)

    raw = factor_engine._load_factor_inputs(engine, as_of_date=as_of_date, lookback_days=1)
    scores = factor_engine.calculate_factor_scores_from_df(
        raw,
        as_of_date=as_of_date,
        apply_buy_filters=False,
    )

    assert [score.ticker for score in scores] == ["AAA", "CCC", "BBB"]
    assert scores[0].quality_score > scores[1].quality_score > scores[2].quality_score
    assert scores[0].total_score > scores[1].total_score > scores[2].total_score


def test_quality_score_partial_metrics_uses_available_subset():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    as_of_date = seed_quality_rank_data(engine)
    with session_scope(engine) as session:
        upsert_quality_metrics(
            session,
            [
                {
                    "ticker": "BBB",
                    "fiscal_year": 2025,
                    "fiscal_quarter": 4,
                    "roe": 0.30,
                    "operating_margin": None,
                    "debt_ratio": None,
                    "published_at": date(2026, 3, 31),
                }
            ],
        )

    raw = factor_engine._load_factor_inputs(engine, as_of_date=as_of_date, lookback_days=1)
    scores = factor_engine.calculate_factor_scores_from_df(
        raw,
        as_of_date=as_of_date,
        apply_buy_filters=False,
    )
    score_by_ticker = {score.ticker: score for score in scores}

    assert score_by_ticker["BBB"].quality_score > score_by_ticker["AAA"].quality_score


def test_quality_score_debt_ratio_outlier_preserves_direction():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    as_of_date = seed_quality_rank_data(engine)
    with session_scope(engine) as session:
        upsert_quality_metrics(
            session,
            [
                {
                    "ticker": "BBB",
                    "fiscal_year": 2025,
                    "fiscal_quarter": 4,
                    "roe": 0.03,
                    "operating_margin": 0.05,
                    "debt_ratio": 30.00,
                    "published_at": date(2026, 3, 31),
                }
            ],
        )

    raw = factor_engine._load_factor_inputs(engine, as_of_date=as_of_date, lookback_days=1)
    scores = factor_engine.calculate_factor_scores_from_df(
        raw,
        as_of_date=as_of_date,
        apply_buy_filters=False,
    )
    score_by_ticker = {score.ticker: score for score in scores}

    assert score_by_ticker["AAA"].quality_score > score_by_ticker["BBB"].quality_score


def test_quality_score_ignores_future_published_metrics():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    as_of_date = seed_quality_rank_data(engine)
    with session_scope(engine) as session:
        upsert_quality_metrics(
            session,
            [
                {
                    "ticker": "AAA",
                    "fiscal_year": 2026,
                    "fiscal_quarter": 1,
                    "roe": 9.99,
                    "operating_margin": 9.99,
                    "debt_ratio": 0.01,
                    "published_at": date(2026, 5, 16),
                }
            ],
        )

    raw = factor_engine._load_factor_inputs(engine, as_of_date=as_of_date, lookback_days=1)
    scores = factor_engine.calculate_factor_scores_from_df(
        raw,
        as_of_date=as_of_date,
        apply_buy_filters=False,
    )
    score_by_ticker = {score.ticker: score for score in scores}

    assert score_by_ticker["AAA"].quality_score < 5.0


def test_quality_score_ignores_null_published_at_even_after_quarter_end_plus_45_days():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    as_of_date = seed_quality_rank_data(engine)
    with session_scope(engine) as session:
        upsert_quality_metrics(
            session,
            [
                {
                    "ticker": "BBB",
                    "fiscal_year": 2026,
                    "fiscal_quarter": 1,
                    "roe": 0.99,
                    "operating_margin": 0.99,
                    "debt_ratio": 0.01,
                    "published_at": None,
                }
            ],
        )

    raw = factor_engine._load_factor_inputs(engine, as_of_date=as_of_date, lookback_days=1)
    row = raw.set_index("ticker").loc["BBB"]

    assert row["roe"] == -0.02
    assert row["operating_margin"] == 0.00
    assert row["debt_ratio"] == 3.00


def test_quality_coverage_message_uses_debug_log(monkeypatch):
    messages = {"info": [], "debug": [], "trace": []}

    class FakeLogger:
        def info(self, message):
            messages["info"].append(message)

        def debug(self, message):
            messages["debug"].append(message)

        def trace(self, message):
            messages["trace"].append(message)

    monkeypatch.setattr(factor_engine, "logger", FakeLogger())
    raw = pd.DataFrame(
        [
            {
                "ticker": "AAA",
                "name": "AAA",
                "market": "KOSPI",
                "per": 10,
                "pbr": 1,
                "eps": 100,
                "bps": 1000,
                "div": 1,
                "roe": 0.1,
                "operating_margin": 0.2,
                "debt_ratio": 0.3,
                "momentum_return": 0.1,
            }
        ]
    )

    factor_engine.calculate_factor_scores_from_df(raw, as_of_date=date(2026, 5, 8))

    assert messages["info"] == []
    assert messages["debug"] == []
    assert len(messages["trace"]) == 1


def test_buy_filter_excludes_non_positive_per_or_pbr_candidates():
    raw = pd.DataFrame(
        [
            {
                "ticker": "AAA",
                "name": "Valid",
                "market": "KOSPI",
                "per": 10,
                "pbr": 1,
                "eps": 100,
                "bps": 1000,
                "div": 1,
                "roe": 0.1,
                "operating_margin": 0.1,
                "debt_ratio": 1.0,
                "momentum_return": 0.1,
            },
            {
                "ticker": "NEGPER",
                "name": "Negative PER",
                "market": "KOSPI",
                "per": -1,
                "pbr": 1,
                "eps": -100,
                "bps": 1000,
                "div": 1,
                "roe": 0.1,
                "operating_margin": 0.1,
                "debt_ratio": 1.0,
                "momentum_return": 0.2,
            },
            {
                "ticker": "ZEROPBR",
                "name": "Zero PBR",
                "market": "KOSPI",
                "per": 10,
                "pbr": 0,
                "eps": 100,
                "bps": 1000,
                "div": 1,
                "roe": 0.1,
                "operating_margin": 0.1,
                "debt_ratio": 1.0,
                "momentum_return": 0.3,
            },
        ]
    )

    scores = factor_engine.calculate_factor_scores_from_df(
        raw,
        as_of_date=date(2026, 5, 8),
    )

    assert [score.ticker for score in scores] == ["AAA"]


def test_buy_filter_excludes_low_quality_candidates_when_coverage_is_sufficient():
    raw = pd.DataFrame(
        [
            {
                "ticker": "AAA",
                "name": "Healthy",
                "market": "KOSPI",
                "per": 10,
                "pbr": 1,
                "eps": 100,
                "bps": 1000,
                "div": 1,
                "roe": 0.10,
                "operating_margin": 0.05,
                "debt_ratio": 1.0,
                "momentum_return": 0.1,
            },
            {
                "ticker": "BADROE",
                "name": "Bad ROE",
                "market": "KOSPI",
                "per": 10,
                "pbr": 1,
                "eps": 100,
                "bps": 1000,
                "div": 1,
                "roe": 0.0,
                "operating_margin": 0.05,
                "debt_ratio": 1.0,
                "momentum_return": 0.2,
            },
            {
                "ticker": "BADDEBT",
                "name": "Bad Debt",
                "market": "KOSPI",
                "per": 10,
                "pbr": 1,
                "eps": 100,
                "bps": 1000,
                "div": 1,
                "roe": 0.10,
                "operating_margin": 0.05,
                "debt_ratio": 3.0,
                "momentum_return": 0.3,
            },
        ]
    )

    scores = factor_engine.calculate_factor_scores_from_df(
        raw,
        as_of_date=date(2026, 5, 8),
    )

    assert [score.ticker for score in scores] == ["AAA"]


def test_buy_filter_keeps_low_quality_candidates_when_coverage_is_low():
    raw = pd.DataFrame(
        [
            {
                "ticker": "AAA",
                "name": "Healthy",
                "market": "KOSPI",
                "per": 10,
                "pbr": 1,
                "eps": 100,
                "bps": 1000,
                "div": 1,
                "roe": None,
                "operating_margin": None,
                "debt_ratio": None,
                "momentum_return": 0.1,
            },
            {
                "ticker": "LOWQ",
                "name": "Low Quality",
                "market": "KOSPI",
                "per": 10,
                "pbr": 1,
                "eps": 100,
                "bps": 1000,
                "div": 1,
                "roe": 0.0,
                "operating_margin": 0.05,
                "debt_ratio": 3.0,
                "momentum_return": 0.2,
            },
        ]
    )

    scores = factor_engine.calculate_factor_scores_from_df(
        raw,
        as_of_date=date(2026, 5, 8),
    )

    assert {score.ticker for score in scores} == {"AAA", "LOWQ"}


def test_buy_filter_returns_no_candidates_when_quality_coverage_is_critical():
    raw = pd.DataFrame(
        [
            {
                "ticker": "AAA",
                "name": "Missing Quality 1",
                "market": "KOSPI",
                "per": 10,
                "pbr": 1,
                "eps": 100,
                "bps": 1000,
                "div": 1,
                "roe": None,
                "operating_margin": None,
                "debt_ratio": None,
                "momentum_return": 0.1,
            },
            {
                "ticker": "BBB",
                "name": "Missing Quality 2",
                "market": "KOSPI",
                "per": 10,
                "pbr": 1,
                "eps": 100,
                "bps": 1000,
                "div": 1,
                "roe": None,
                "operating_margin": None,
                "debt_ratio": None,
                "momentum_return": 0.2,
            },
            {
                "ticker": "LOWQ",
                "name": "Low Quality",
                "market": "KOSPI",
                "per": 10,
                "pbr": 1,
                "eps": 100,
                "bps": 1000,
                "div": 1,
                "roe": 0.0,
                "operating_margin": 0.05,
                "debt_ratio": 3.0,
                "momentum_return": 0.3,
            },
        ]
    )

    scores = factor_engine.calculate_factor_scores_from_df(
        raw,
        as_of_date=date(2026, 5, 8),
    )

    assert scores == []


def test_buy_filter_excludes_two_quarter_severe_operating_loss_candidates():
    raw = pd.DataFrame(
        [
            {
                "ticker": "AAA",
                "name": "Healthy",
                "market": "KOSPI",
                "per": 10,
                "pbr": 1,
                "eps": 100,
                "bps": 1000,
                "div": 1,
                "roe": 0.10,
                "operating_margin": 0.05,
                "debt_ratio": 1.0,
                "recent_operating_margins": [0.01, -0.20],
                "momentum_return": 0.1,
            },
            {
                "ticker": "LOSS",
                "name": "Consecutive Severe Loss",
                "market": "KOSPI",
                "per": 10,
                "pbr": 1,
                "eps": 100,
                "bps": 1000,
                "div": 1,
                "roe": 0.10,
                "operating_margin": -0.20,
                "debt_ratio": 1.0,
                "recent_operating_margins": [-0.11, -0.20],
                "momentum_return": 0.2,
            },
        ]
    )

    scores = factor_engine.calculate_factor_scores_from_df(
        raw,
        as_of_date=date(2026, 5, 8),
    )

    assert [score.ticker for score in scores] == ["AAA"]


def test_technical_filter_keeps_candidate_with_three_of_four_conditions():
    closes = [100 + (idx * 0.1) for idx in range(80)]
    closes[-1] = 106
    raw = pd.DataFrame(
        [
            {
                "ticker": "AAA",
                "name": "Technically Valid",
                "market": "KOSPI",
                "per": 10,
                "pbr": 1,
                "eps": 100,
                "bps": 1000,
                "div": 1,
                "roe": 0.10,
                "operating_margin": 0.05,
                "debt_ratio": 1.0,
                "recent_closes": closes,
                "momentum_return": 0.1,
            },
        ]
    )

    scores = factor_engine.calculate_factor_scores_from_df(
        raw,
        as_of_date=date(2026, 5, 8),
    )

    assert [score.ticker for score in scores] == ["AAA"]


def test_technical_filter_excludes_candidate_with_two_or_fewer_conditions():
    closes = [100 - (idx * 0.1) for idx in range(80)]
    raw = pd.DataFrame(
        [
            {
                "ticker": "AAA",
                "name": "Technically Weak",
                "market": "KOSPI",
                "per": 10,
                "pbr": 1,
                "eps": 100,
                "bps": 1000,
                "div": 1,
                "roe": 0.10,
                "operating_margin": 0.05,
                "debt_ratio": 1.0,
                "recent_closes": closes,
                "momentum_return": -0.1,
            },
        ]
    )

    scores = factor_engine.calculate_factor_scores_from_df(
        raw,
        as_of_date=date(2026, 5, 8),
    )

    assert scores == []
