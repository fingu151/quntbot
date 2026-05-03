from datetime import date

from sqlalchemy import select

from src.data.collectors import sync_phase1_data
from src.data.database import create_tables, get_engine, session_scope
from src.data.models import SyncRun
from src.data.repositories import count_rows


class FakeProvider:
    def get_universe(self):
        return [
            {"ticker": "005930", "name": "삼성전자", "market": "KOSPI200"},
            {"ticker": "091990", "name": "셀트리온헬스케어", "market": "KOSDAQ150"},
        ]

    def get_daily_prices(self, ticker, start_date, end_date):
        return [
            {
                "ticker": ticker,
                "date": start_date,
                "open": 100,
                "high": 110,
                "low": 90,
                "close": 105,
                "volume": 1000,
            }
        ]

    def get_fundamentals(self, ticker, start_date, end_date):
        return [
            {
                "ticker": ticker,
                "date": end_date,
                "bps": 1000,
                "per": 10,
                "pbr": 1,
                "eps": 100,
                "div": 2,
                "dps": 50,
            }
        ]


def test_sync_phase1_data_stores_universe_prices_fundamentals_and_success_run():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)

    result = sync_phase1_data(
        engine=engine,
        provider=FakeProvider(),
        start_date=date(2026, 5, 1),
        end_date=date(2026, 5, 2),
    )

    with session_scope(engine) as session:
        counts = count_rows(session)
        sync_runs = session.scalars(select(SyncRun)).all()

    assert result == {"universe_count": 2, "price_count": 2, "fundamental_count": 2}
    assert counts == {"stocks": 2, "daily_prices": 2, "fundamentals": 2}
    assert len(sync_runs) == 1
    assert sync_runs[0].status == "success"
    assert sync_runs[0].finished_at is not None


def test_sync_phase1_data_records_failed_run_when_provider_raises():
    class BrokenProvider(FakeProvider):
        def get_universe(self):
            raise RuntimeError("provider down")

    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)

    try:
        sync_phase1_data(
            engine=engine,
            provider=BrokenProvider(),
            start_date=date(2026, 5, 1),
            end_date=date(2026, 5, 2),
        )
    except RuntimeError:
        pass

    with session_scope(engine) as session:
        sync_runs = session.scalars(select(SyncRun)).all()

    assert len(sync_runs) == 1
    assert sync_runs[0].status == "failed"
    assert sync_runs[0].error_message == "provider down"
