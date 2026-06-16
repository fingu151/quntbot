from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import Engine, select

from src.data.database import session_scope
from src.data.models import MarketIndexPrice


BOND_YIELD_SYMBOLS = ("KR10Y", "US10Y")


@dataclass(frozen=True)
class BondYieldAdjustment:
    status: str
    buy_budget_multiplier: float
    cash_target: float
    reasons: list[str]
    changes_bp: dict[str, float]


def load_bond_yield_closes(
    engine: Engine,
    *,
    as_of_date: date,
    symbols: tuple[str, ...] = BOND_YIELD_SYMBOLS,
) -> dict[str, list[tuple[date, float]]]:
    if not hasattr(engine, "connect"):
        return {}
    with session_scope(engine) as session:
        rows = session.scalars(
            select(MarketIndexPrice)
            .where(
                MarketIndexPrice.symbol.in_(symbols),
                MarketIndexPrice.date < as_of_date,
            )
            .order_by(MarketIndexPrice.symbol, MarketIndexPrice.date)
        ).all()
    closes: dict[str, list[tuple[date, float]]] = {symbol: [] for symbol in symbols}
    for row in rows:
        if row.close is not None and row.close > 0:
            closes.setdefault(row.symbol, []).append((row.date, float(row.close)))
    return {symbol: values[-2:] for symbol, values in closes.items()}


def calculate_bond_yield_adjustment(
    closes_by_symbol: dict[str, list[tuple[date, float]]],
    *,
    as_of_date: date,
    moderate_move_bp: float = 15.0,
    severe_move_bp: float = 30.0,
) -> BondYieldAdjustment:
    del as_of_date
    changes_bp: dict[str, float] = {}
    for symbol in BOND_YIELD_SYMBOLS:
        rows = closes_by_symbol.get(symbol, [])
        if len(rows) < 2:
            continue
        previous = rows[-2][1]
        latest = rows[-1][1]
        if previous > 0 and latest > 0:
            changes_bp[symbol] = round((latest - previous) * 100.0, 1)

    if not changes_bp:
        return BondYieldAdjustment(
            status="missing",
            buy_budget_multiplier=1.0,
            cash_target=0.0,
            reasons=["bond_yield_history_missing"],
            changes_bp={},
        )

    moderate_rises = [
        symbol for symbol, value in changes_bp.items() if value >= moderate_move_bp
    ]
    severe_rises = [
        symbol for symbol, value in changes_bp.items() if value >= severe_move_bp
    ]
    moderate_falls = [
        symbol for symbol, value in changes_bp.items() if value <= -moderate_move_bp
    ]
    severe_falls = [
        symbol for symbol, value in changes_bp.items() if value <= -severe_move_bp
    ]
    reasons = [
        f"{symbol}:{changes_bp[symbol]:+,.0f}bp" for symbol in sorted(changes_bp)
    ]

    if severe_rises or len(moderate_rises) >= 2:
        return BondYieldAdjustment("risk_off", 0.70, 0.30, reasons, changes_bp)
    if severe_falls or len(moderate_falls) >= 2:
        return BondYieldAdjustment("risk_on", 1.20, 0.0, reasons, changes_bp)
    if moderate_rises and not moderate_falls:
        return BondYieldAdjustment("risk_off", 0.85, 0.15, reasons, changes_bp)
    if moderate_falls and not moderate_rises:
        return BondYieldAdjustment("risk_on", 1.10, 0.0, reasons, changes_bp)
    return BondYieldAdjustment("neutral", 1.0, 0.0, reasons, changes_bp)


def combine_buy_budget_multipliers(*multipliers: float) -> float:
    combined = 1.0
    for multiplier in multipliers:
        combined *= multiplier
    return round(combined, 4)
