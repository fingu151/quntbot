from datetime import date

from sqlalchemy import select

from src.data.database import create_tables, get_engine, session_scope
from src.data.models import QualityMetric
from src.data.repositories import upsert_quality_metrics


def make_session():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    return engine


def test_upsert_quality_metrics_uses_ticker_year_quarter_as_unique_key():
    engine = make_session()
    row = {
        "ticker": "005930",
        "fiscal_year": 2026,
        "fiscal_quarter": 1,
        "roe": 0.15,
        "operating_margin": 0.12,
        "debt_ratio": 0.45,
        "published_at": date(2026, 5, 15),
    }

    with session_scope(engine) as session:
        inserted = upsert_quality_metrics(session, [row])
        updated = upsert_quality_metrics(
            session,
            [
                {
                    **row,
                    "roe": 0.16,
                    "operating_margin": 0.13,
                    "debt_ratio": 0.44,
                }
            ],
        )

    with session_scope(engine) as session:
        rows = session.scalars(select(QualityMetric)).all()

    assert inserted == 1
    assert updated == 1
    assert len(rows) == 1
    assert rows[0].ticker == "005930"
    assert rows[0].fiscal_year == 2026
    assert rows[0].fiscal_quarter == 1
    assert rows[0].roe == 0.16
    assert rows[0].operating_margin == 0.13
    assert rows[0].debt_ratio == 0.44
    assert rows[0].published_at == date(2026, 5, 15)


def test_upsert_quality_metrics_inserts_new_quarters_separately():
    engine = make_session()

    with session_scope(engine) as session:
        inserted = upsert_quality_metrics(
            session,
            [
                {
                    "ticker": "005930",
                    "fiscal_year": 2026,
                    "fiscal_quarter": 1,
                    "roe": 0.15,
                    "operating_margin": 0.12,
                    "debt_ratio": 0.45,
                    "published_at": date(2026, 5, 15),
                },
                {
                    "ticker": "005930",
                    "fiscal_year": 2026,
                    "fiscal_quarter": 2,
                    "roe": 0.17,
                    "operating_margin": 0.14,
                    "debt_ratio": 0.43,
                    "published_at": date(2026, 8, 15),
                },
            ],
        )

    with session_scope(engine) as session:
        rows = session.scalars(
            select(QualityMetric).order_by(QualityMetric.fiscal_quarter)
        ).all()

    assert inserted == 2
    assert [row.fiscal_quarter for row in rows] == [1, 2]
