from sqlalchemy import inspect

from src.data.database import create_tables, get_engine, session_scope
from src.data.models import Stock


def test_create_tables_creates_phase1_tables():
    engine = get_engine("sqlite:///:memory:")

    create_tables(engine)

    table_names = set(inspect(engine).get_table_names())
    assert {
        "stocks",
        "daily_prices",
        "fundamentals",
        "sync_runs",
        "busanstock_signals",
        "investor_flows",
        "macro_indicator_releases",
    } <= table_names
    stock_columns = {column["name"] for column in inspect(engine).get_columns("stocks")}
    assert "instrument_type" in stock_columns
    macro_columns = {
        column["name"] for column in inspect(engine).get_columns("macro_indicator_releases")
    }
    assert {
        "indicator",
        "period_date",
        "release_date",
        "value",
        "previous_value",
        "unit",
        "source",
        "source_url",
        "impact_rule",
        "importance",
        "updated_at",
    } <= macro_columns


def test_session_scope_commits_changes():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)

    with session_scope(engine) as session:
        session.add(Stock(ticker="005930", name="삼성전자", market="KOSPI"))

    with session_scope(engine) as session:
        saved = session.get(Stock, "005930")

    assert saved is not None
    assert saved.name == "삼성전자"
