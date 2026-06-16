from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import Engine, select

from src.data.database import session_scope
from src.data.models import MarketIndexPrice


US_INDEX_SYMBOLS = ("NASDAQ", "SP500", "DOW")


@dataclass(frozen=True)
class UsMarketBuyAdjustment:
    status: str
    buy_budget_multiplier: float
    cash_target: float
    reasons: list[str]
    returns: dict[str, float]


def load_us_index_closes(
    engine: Engine,
    *,
    as_of_date: date,
    symbols: tuple[str, ...] = US_INDEX_SYMBOLS,
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


def calculate_us_market_buy_adjustment(
    closes_by_symbol: dict[str, list[tuple[date, float]]],
    *,
    as_of_date: date,
    moderate_drop_pct: float = -0.015,
    severe_drop_pct: float = -0.030,
    moderate_rally_pct: float = 0.015,
    broad_rally_pct: float = 0.010,
) -> UsMarketBuyAdjustment:
    del as_of_date
    returns: dict[str, float] = {}
    for symbol in US_INDEX_SYMBOLS:
        rows = closes_by_symbol.get(symbol, [])
        if len(rows) < 2:
            continue
        previous = rows[-2][1]
        latest = rows[-1][1]
        if previous > 0 and latest > 0:
            returns[symbol] = latest / previous - 1.0

    if not returns:
        return UsMarketBuyAdjustment(
            status="missing",
            buy_budget_multiplier=1.0,
            cash_target=0.0,
            reasons=["us_index_history_missing"],
            returns={},
        )

    severe_drops = [symbol for symbol, value in returns.items() if value <= severe_drop_pct]
    moderate_drops = [symbol for symbol, value in returns.items() if value <= moderate_drop_pct]
    broad_rallies = [symbol for symbol, value in returns.items() if value >= broad_rally_pct]
    moderate_rallies = [symbol for symbol, value in returns.items() if value >= moderate_rally_pct]

    reasons = [f"{symbol}:{returns[symbol]:.2%}" for symbol in sorted(returns)]
    if severe_drops:
        return UsMarketBuyAdjustment("risk_off", 0.60, 0.40, reasons, returns)
    if len(moderate_drops) >= 2:
        return UsMarketBuyAdjustment("risk_off", 0.70, 0.30, reasons, returns)
    if moderate_drops:
        return UsMarketBuyAdjustment("risk_off", 0.80, 0.20, reasons, returns)
    if len(moderate_rallies) >= 2:
        return UsMarketBuyAdjustment("risk_on", 1.20, 0.0, reasons, returns)
    if len(broad_rallies) >= 2:
        return UsMarketBuyAdjustment("risk_on", 1.10, 0.0, reasons, returns)
    return UsMarketBuyAdjustment("neutral", 1.0, 0.0, reasons, returns)


def scale_target_weights(
    target_weights: dict[str, float],
    multiplier: float,
) -> dict[str, float]:
    if multiplier == 1.0:
        return dict(target_weights)
    return {ticker: round(weight * multiplier, 12) for ticker, weight in target_weights.items()}
