from datetime import datetime

from sqlalchemy import inspect, select

from src.data.database import create_tables, get_engine, session_scope
from src.data.models import QualitySyncRun


def make_session():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    return engine


def test_create_tables_creates_quality_sync_runs_table():
    engine = make_session()

    assert "quality_sync_runs" in inspect(engine).get_table_names()


def test_quality_sync_run_persists_status_window_counts_and_error():
    engine = make_session()
    finished_at = datetime(2026, 5, 7, 12, 30, 0)

    with session_scope(engine) as session:
        session.add(
            QualitySyncRun(
                status="failed",
                finished_at=finished_at,
                year_from=2024,
                year_to=2026,
                metric_count=12,
                error_message="dart down",
            )
        )

    with session_scope(engine) as session:
        row = session.scalars(select(QualitySyncRun)).one()

    assert row.status == "failed"
    assert row.started_at is not None
    assert row.finished_at == finished_at
    assert row.year_from == 2024
    assert row.year_to == 2026
    assert row.metric_count == 12
    assert row.error_message == "dart down"
