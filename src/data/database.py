from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from config import DATABASE_URL
from src.data.models import Base


def get_engine(database_url: str | None = None) -> Engine:
    return create_engine(database_url or DATABASE_URL, future=True)


def create_tables(engine: Engine) -> None:
    Base.metadata.create_all(engine)
    _ensure_sqlite_stock_instrument_type(engine)


def _ensure_sqlite_stock_instrument_type(engine: Engine) -> None:
    if engine.dialect.name != "sqlite":
        return
    inspector = inspect(engine)
    if "stocks" not in inspector.get_table_names():
        return
    stock_columns = {column["name"] for column in inspector.get_columns("stocks")}
    if "instrument_type" in stock_columns:
        return
    with engine.begin() as connection:
        connection.execute(
            text("ALTER TABLE stocks ADD COLUMN instrument_type VARCHAR(20) NOT NULL DEFAULT 'COMMON_STOCK'")
        )


@contextmanager
def session_scope(engine: Engine) -> Iterator[Session]:
    session_factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
