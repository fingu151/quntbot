"""Operational rebalance policy helpers shared by scheduler and dry-run."""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from loguru import logger
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
    """Return holdings eligible for rebalance sells after the rank buffer gate."""
    del entry_dates, db_engine, as_of_date, min_holding_trading_days
    eligible: list[str] = []
    for holding in holdings:
        ticker = str(holding.get("ticker") or "")
        if not ticker or ticker in buffer_tickers:
            continue
        if int(holding.get("qty", 0) or 0) <= 0:
            continue
        eligible.append(ticker)

    return sorted(eligible)
