from datetime import date

from sqlalchemy import select

from src.data.database import create_tables, get_engine, session_scope
from src.data.models import QualityMetric, QualitySyncRun, Stock
from src.data.quality_collector import QuotaExhausted, sync_phase1_quality
from src.data.repositories import upsert_stocks


class FakeQualityMetricsProvider:
    def get_quality_metrics(self, ticker, *, year_from, year_to):
        return [
            {
                "ticker": ticker,
                "fiscal_year": year_from,
                "fiscal_quarter": 1,
                "roe": 0.10,
                "operating_margin": 0.08,
                "debt_ratio": 0.50,
                "published_at": date(year_from, 5, 15),
            },
            {
                "ticker": ticker,
                "fiscal_year": year_to,
                "fiscal_quarter": 2,
                "roe": 0.12,
                "operating_margin": 0.09,
                "debt_ratio": 0.48,
                "published_at": date(year_to, 8, 15),
            },
        ]


def make_engine_with_stocks():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    with session_scope(engine) as session:
        upsert_stocks(
            session,
            [
                {"ticker": "005930", "name": "Samsung", "market": "KOSPI"},
                {"ticker": "000660", "name": "SK Hynix", "market": "KOSPI"},
            ],
        )
    return engine


def test_sync_phase1_quality_success_stores_metrics_and_success_run():
    engine = make_engine_with_stocks()

    result = sync_phase1_quality(
        engine=engine,
        provider=FakeQualityMetricsProvider(),
        year_from=2024,
        year_to=2025,
    )

    with session_scope(engine) as session:
        metrics = session.scalars(select(QualityMetric)).all()
        sync_run = session.scalars(select(QualitySyncRun)).one()

    assert result == {"metric_count": 4, "status": "success"}
    assert len(metrics) == 4
    assert sync_run.status == "success"
    assert sync_run.year_from == 2024
    assert sync_run.year_to == 2025
    assert sync_run.metric_count == 4
    assert sync_run.finished_at is not None
    assert sync_run.error_message is None


def test_sync_phase1_quality_records_failed_run_when_provider_raises():
    class BrokenProvider:
        def get_quality_metrics(self, ticker, *, year_from, year_to):
            raise RuntimeError("dart down")

    engine = make_engine_with_stocks()

    try:
        sync_phase1_quality(
            engine=engine,
            provider=BrokenProvider(),
            year_from=2024,
            year_to=2025,
        )
    except RuntimeError:
        pass

    with session_scope(engine) as session:
        metrics = session.scalars(select(QualityMetric)).all()
        sync_run = session.scalars(select(QualitySyncRun)).one()

    assert metrics == []
    assert sync_run.status == "failed"
    assert sync_run.year_from == 2024
    assert sync_run.year_to == 2025
    assert sync_run.metric_count == 0
    assert sync_run.error_message == "dart down"
    assert sync_run.finished_at is not None


def test_sync_phase1_quality_skips_single_ticker_failure_and_keeps_successful_rows():
    class PartiallyBrokenProvider(FakeQualityMetricsProvider):
        def get_quality_metrics(self, ticker, *, year_from, year_to):
            if ticker == "000660":
                raise RuntimeError("dart parser failed")
            return super().get_quality_metrics(ticker, year_from=year_from, year_to=year_to)

    engine = make_engine_with_stocks()

    result = sync_phase1_quality(
        engine=engine,
        provider=PartiallyBrokenProvider(),
        year_from=2024,
        year_to=2025,
        tickers=["005930", "000660"],
    )

    with session_scope(engine) as session:
        metrics = session.scalars(select(QualityMetric)).all()
        sync_run = session.scalars(select(QualitySyncRun)).one()

    assert result == {"metric_count": 2, "status": "partial_success"}
    assert len(metrics) == 2
    assert {row.ticker for row in metrics} == {"005930"}
    assert sync_run.status == "partial_success"
    assert sync_run.metric_count == 2
    assert sync_run.error_message is not None
    assert "000660" in sync_run.error_message
    assert "dart parser failed" in sync_run.error_message


def test_sync_phase1_quality_records_quota_exhausted_and_keeps_saved_rows():
    class QuotaProvider(FakeQualityMetricsProvider):
        def get_quality_metrics(self, ticker, *, year_from, year_to):
            if ticker == "000660":
                raise QuotaExhausted("DART daily quota reached")
            return super().get_quality_metrics(ticker, year_from=year_from, year_to=year_to)

    engine = make_engine_with_stocks()

    result = sync_phase1_quality(
        engine=engine,
        provider=QuotaProvider(),
        year_from=2024,
        year_to=2025,
        tickers=["005930", "000660"],
    )

    with session_scope(engine) as session:
        metrics = session.scalars(select(QualityMetric)).all()
        sync_run = session.scalars(select(QualitySyncRun)).one()

    assert result == {"metric_count": 2, "status": "quota_exhausted"}
    assert len(metrics) == 2
    assert {row.ticker for row in metrics} == {"005930"}
    assert sync_run.status == "quota_exhausted"
    assert sync_run.metric_count == 2
    assert sync_run.error_message == "DART daily quota reached"


def test_sync_phase1_quality_accepts_explicit_tickers_without_stock_rows():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)

    result = sync_phase1_quality(
        engine=engine,
        provider=FakeQualityMetricsProvider(),
        year_from=2024,
        year_to=2025,
        tickers=["005930"],
    )

    with session_scope(engine) as session:
        stocks = session.scalars(select(Stock)).all()
        metrics = session.scalars(select(QualityMetric)).all()

    assert result == {"metric_count": 2, "status": "success"}
    assert stocks == []
    assert len(metrics) == 2
