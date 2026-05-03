from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from src.data.models import DailyPrice, Fundamental, Stock, utc_now


def _upsert_many(
    session: Session,
    model: type,
    rows: Iterable[dict[str, Any]],
    conflict_columns: list[str],
    update_columns: list[str],
) -> int:
    prepared = [{**row, "updated_at": utc_now()} for row in rows]
    if not prepared:
        return 0

    statement = insert(model).values(prepared)
    excluded = statement.excluded
    update_values = {column: getattr(excluded, column) for column in update_columns}
    update_values["updated_at"] = utc_now()

    statement = statement.on_conflict_do_update(
        index_elements=conflict_columns,
        set_=update_values,
    )
    session.execute(statement)
    return len(prepared)


def upsert_stocks(session: Session, rows: Iterable[dict[str, Any]]) -> int:
    return _upsert_many(
        session,
        Stock,
        rows,
        conflict_columns=["ticker"],
        update_columns=["name", "market", "is_active"],
    )


def upsert_daily_prices(session: Session, rows: Iterable[dict[str, Any]]) -> int:
    return _upsert_many(
        session,
        DailyPrice,
        rows,
        conflict_columns=["ticker", "date"],
        update_columns=[
            "open",
            "high",
            "low",
            "close",
            "volume",
            "trading_value",
            "market_cap",
        ],
    )


def upsert_fundamentals(session: Session, rows: Iterable[dict[str, Any]]) -> int:
    return _upsert_many(
        session,
        Fundamental,
        rows,
        conflict_columns=["ticker", "date"],
        update_columns=["bps", "per", "pbr", "eps", "div", "dps"],
    )


def count_rows(session: Session) -> dict[str, int]:
    return {
        "stocks": session.scalar(select(func.count()).select_from(Stock)) or 0,
        "daily_prices": session.scalar(select(func.count()).select_from(DailyPrice)) or 0,
        "fundamentals": session.scalar(select(func.count()).select_from(Fundamental)) or 0,
    }
