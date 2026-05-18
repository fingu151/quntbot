"""Operational rebalance policy helpers shared by scheduler and dry-run."""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from loguru import logger
from sqlalchemy import select

from src.data.database import session_scope
from src.data.models import DailyPrice
from src.trading.exit_state import ExitStateStore


def load_exit_entry_dates(path: Path) -> dict[str, date]:
    """Load local PAPER exit-state entry dates by ticker."""
    entry_dates: dict[str, date] = {}
    for ticker, state in ExitStateStore(path).load().items():
        try:
            entry_dates[ticker] = date.fromisoformat(state.entry_date)
        except ValueError:
            logger.warning(
                f"rebalance entry date ignored: ticker={ticker}, "
                f"entry_date={state.entry_date}"
            )
    return entry_dates


def compute_rebalance_sell_eligible_tickers(
    *,
    holdings: list[dict[str, Any]],
    buffer_tickers: set[str],
    entry_dates: dict[str, date],
    db_engine: object,
    as_of_date: date,
    min_holding_trading_days: int,
) -> list[str]:
    """Return holdings eligible for rebalance sells after buffer and age gates."""
    eligible: list[str] = []
    for holding in holdings:
        ticker = str(holding.get("ticker") or "")
        if not ticker or ticker in buffer_tickers:
            continue
        if int(holding.get("qty", 0) or 0) <= 0:
            continue

        entry_date = entry_dates.get(ticker)
        if entry_date is None:
            logger.warning(
                f"rebalance sell blocked: ticker={ticker}, reason=missing_entry_date"
            )
            continue

        held_days = count_trading_days_held(
            db_engine,
            entry_date=entry_date,
            as_of_date=as_of_date,
        )
        if held_days < min_holding_trading_days:
            logger.info(
                f"rebalance sell blocked: ticker={ticker}, held_trading_days={held_days}, "
                f"required={min_holding_trading_days}"
            )
            continue

        eligible.append(ticker)

    return sorted(eligible)


def count_trading_days_held(
    db_engine: object,
    *,
    entry_date: date,
    as_of_date: date,
) -> int:
    """Count market trading dates strictly after entry through as-of date."""
    if entry_date >= as_of_date:
        return 0

    with session_scope(db_engine) as session:
        rows = session.scalars(
            select(DailyPrice.date)
            .where(
                DailyPrice.date > entry_date,
                DailyPrice.date <= as_of_date,
            )
            .distinct()
        ).all()
    return len(set(rows))
