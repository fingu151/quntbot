from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import Engine, func, select

from src.data.database import session_scope


def latest_row_status(
    engine: Engine,
    *,
    model: type,
    date_column: Any,
    as_of_date: date,
) -> tuple[date | None, int]:
    with session_scope(engine) as session:
        latest_date = session.scalar(
            select(func.max(date_column)).where(date_column <= as_of_date)
        )
        if latest_date is None:
            return None, 0
        latest_count = session.scalar(
            select(func.count()).select_from(model).where(date_column == latest_date)
        )
    return latest_date, int(latest_count or 0)
