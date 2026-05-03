from datetime import date

from sqlalchemy import select

from src.data.database import create_tables, get_engine, session_scope
from src.data.models import DailyPrice, Fundamental, Stock
from src.data.repositories import (
    count_rows,
    upsert_daily_prices,
    upsert_fundamentals,
    upsert_stocks,
)


def make_session():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    return engine


def test_upsert_stocks_inserts_and_updates_existing_ticker():
    engine = make_session()

    with session_scope(engine) as session:
        inserted = upsert_stocks(
            session,
            [{"ticker": "005930", "name": "삼성전자", "market": "KOSPI200"}],
        )
        updated = upsert_stocks(
            session,
            [{"ticker": "005930", "name": "삼성전자우아님", "market": "KOSPI200"}],
        )

    with session_scope(engine) as session:
        rows = session.scalars(select(Stock)).all()

    assert inserted == 1
    assert updated == 1
    assert len(rows) == 1
    assert rows[0].name == "삼성전자우아님"


def test_upsert_daily_prices_uses_ticker_and_date_as_unique_key():
    engine = make_session()
    row = {
        "ticker": "005930",
        "date": date(2026, 5, 1),
        "open": 70000,
        "high": 71000,
        "low": 69000,
        "close": 70500,
        "volume": 1000,
    }

    with session_scope(engine) as session:
        upsert_daily_prices(session, [row])
        upsert_daily_prices(session, [{**row, "close": 70600}])

    with session_scope(engine) as session:
        rows = session.scalars(select(DailyPrice)).all()

    assert len(rows) == 1
    assert rows[0].close == 70600


def test_upsert_fundamentals_uses_ticker_and_date_as_unique_key():
    engine = make_session()
    row = {
        "ticker": "005930",
        "date": date(2026, 5, 1),
        "bps": 50000,
        "per": 12.5,
        "pbr": 1.3,
        "eps": 5000,
        "div": 2.0,
        "dps": 1500,
    }

    with session_scope(engine) as session:
        upsert_fundamentals(session, [row])
        upsert_fundamentals(session, [{**row, "per": 13.0}])

    with session_scope(engine) as session:
        rows = session.scalars(select(Fundamental)).all()

    assert len(rows) == 1
    assert rows[0].per == 13.0


def test_count_rows_returns_table_counts():
    engine = make_session()

    with session_scope(engine) as session:
        upsert_stocks(session, [{"ticker": "005930", "name": "삼성전자", "market": "KOSPI200"}])
        counts = count_rows(session)

    assert counts["stocks"] == 1
    assert counts["daily_prices"] == 0
    assert counts["fundamentals"] == 0
