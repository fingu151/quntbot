from datetime import date, timedelta

from src.data.database import create_tables, get_engine, session_scope
from src.data.repositories import upsert_daily_prices, upsert_fundamentals, upsert_stocks
from src.factors.engine import calculate_factor_scores


def seed_factor_data(engine):
    as_of_date = date(2026, 5, 1)
    lookback_date = as_of_date - timedelta(days=2)
    with session_scope(engine) as session:
        upsert_stocks(
            session,
            [
                {"ticker": "AAA", "name": "저평가상승", "market": "KOSPI200"},
                {"ticker": "BBB", "name": "고평가하락", "market": "KOSPI200"},
                {"ticker": "CCC", "name": "중간", "market": "KOSDAQ150"},
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
                {"ticker": "AAA", "date": as_of_date, "per": 5, "pbr": 0.5},
                {"ticker": "BBB", "date": as_of_date, "per": 25, "pbr": 3.0},
                {"ticker": "CCC", "date": as_of_date, "per": 12, "pbr": 1.2},
            ],
        )
    return as_of_date


def test_calculate_factor_scores_ranks_value_and_momentum_candidates():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    as_of_date = seed_factor_data(engine)

    scores = calculate_factor_scores(engine, as_of_date=as_of_date, lookback_days=1)

    assert [score.ticker for score in scores] == ["AAA", "CCC", "BBB"]
    assert scores[0].rank == 1
    assert scores[0].value_score > scores[-1].value_score
    assert scores[0].momentum_score > scores[-1].momentum_score
    assert all(score.quality_score == 0.0 for score in scores)


def test_calculate_factor_scores_excludes_stocks_without_required_data():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    as_of_date = seed_factor_data(engine)
    with session_scope(engine) as session:
        upsert_stocks(session, [{"ticker": "DDD", "name": "데이터없음", "market": "KOSPI200"}])

    scores = calculate_factor_scores(engine, as_of_date=as_of_date, lookback_days=1)

    assert "DDD" not in [score.ticker for score in scores]
