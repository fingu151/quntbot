from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import Engine

from config import MACRO_RISK
from src.data.database import session_scope
from src.data.repositories import get_recent_macro_indicator_releases
from src.trading.bond_yield_risk import (
    BondYieldAdjustment,
    calculate_bond_yield_adjustment,
    load_bond_yield_closes,
)
from src.trading.us_market_risk import (
    UsMarketBuyAdjustment,
    calculate_us_market_buy_adjustment,
    load_us_index_closes,
)


@dataclass(frozen=True)
class MacroExposureAdjustment:
    status: str
    buy_budget_multiplier: float
    cash_target: float
    signals: list[str]
    missing_sources: list[str]
    us_market: UsMarketBuyAdjustment
    bond_yield: BondYieldAdjustment
    indicator_signals: list[str]

    def as_dict(self, *, orders_generated: bool = False, execution_allowed: bool = True) -> dict[str, Any]:
        return {
            "status": self.status,
            "buy_budget_multiplier": self.buy_budget_multiplier,
            "cash_target": self.cash_target,
            "signals": self.signals,
            "missing_sources": self.missing_sources,
            "orders_generated": orders_generated,
            "execution_allowed": execution_allowed,
            "us_market": {
                "status": self.us_market.status,
                "buy_budget_multiplier": self.us_market.buy_budget_multiplier,
                "cash_target": self.us_market.cash_target,
                "reasons": self.us_market.reasons,
                "returns": self.us_market.returns,
            },
            "bond_yield": {
                "status": self.bond_yield.status,
                "buy_budget_multiplier": self.bond_yield.buy_budget_multiplier,
                "cash_target": self.bond_yield.cash_target,
                "reasons": self.bond_yield.reasons,
                "changes_bp": self.bond_yield.changes_bp,
            },
            "indicator_signals": self.indicator_signals,
        }


def load_macro_exposure_adjustment(
    engine: Engine,
    *,
    as_of_date: date,
) -> MacroExposureAdjustment:
    us_market = calculate_us_market_buy_adjustment(
        load_us_index_closes(engine, as_of_date=as_of_date),
        as_of_date=as_of_date,
    )
    bond_yield = calculate_bond_yield_adjustment(
        load_bond_yield_closes(engine, as_of_date=as_of_date),
        as_of_date=as_of_date,
    )
    if hasattr(engine, "connect"):
        with session_scope(engine) as session:
            indicator_releases = get_recent_macro_indicator_releases(session, as_of_date)
    else:
        indicator_releases = []
    return calculate_macro_exposure_adjustment(
        as_of_date=as_of_date,
        us_market=us_market,
        bond_yield=bond_yield,
        indicator_releases=indicator_releases,
    )


def calculate_macro_exposure_adjustment(
    *,
    as_of_date: date,
    us_market: UsMarketBuyAdjustment,
    bond_yield: BondYieldAdjustment,
    indicator_releases: list[dict[str, Any]],
    moderate_cash_target: float = MACRO_RISK.moderate_cash_target,
    severe_cash_target: float = MACRO_RISK.severe_cash_target,
    max_cash_target: float = MACRO_RISK.max_cash_target,
) -> MacroExposureAdjustment:
    del as_of_date
    indicator_status, indicator_multiplier, indicator_cash, indicator_signals = (
        _indicator_adjustment(indicator_releases, moderate_cash_target)
    )

    missing_sources: list[str] = []
    signals: list[str] = []
    multipliers = [us_market.buy_budget_multiplier, bond_yield.buy_budget_multiplier, indicator_multiplier]
    cash_targets = [us_market.cash_target, bond_yield.cash_target, indicator_cash]

    if us_market.status == "missing":
        missing_sources.extend(us_market.reasons)
    else:
        signals.extend(us_market.reasons)
    if bond_yield.status == "missing":
        missing_sources.extend(bond_yield.reasons)
    else:
        signals.extend(bond_yield.reasons)
    if not indicator_releases:
        missing_sources.append("macro_indicator_history_missing")
    signals.extend(indicator_signals)

    combined_multiplier = 1.0
    for multiplier in multipliers:
        combined_multiplier *= multiplier
    combined_multiplier = round(min(1.25, max(0.50, combined_multiplier)), 4)
    cash_target = round(min(max_cash_target, max(cash_targets)), 4)

    statuses = {us_market.status, bond_yield.status, indicator_status}
    if "risk_off" in statuses:
        status = "risk_off"
    elif "risk_on" in statuses:
        status = "risk_on"
    elif statuses == {"missing"} or (missing_sources and not signals):
        status = "missing"
    else:
        status = "neutral"

    if cash_target >= severe_cash_target:
        status = "risk_off"
    return MacroExposureAdjustment(
        status=status,
        buy_budget_multiplier=combined_multiplier,
        cash_target=cash_target,
        signals=signals,
        missing_sources=missing_sources,
        us_market=us_market,
        bond_yield=bond_yield,
        indicator_signals=indicator_signals,
    )


def _indicator_adjustment(
    rows: list[dict[str, Any]],
    moderate_cash_target: float,
) -> tuple[str, float, float, list[str]]:
    if not rows:
        return "missing", 1.0, 0.0, []

    signals: list[str] = []
    risk_off_count = 0
    risk_on_count = 0
    for row in rows:
        previous = row.get("previous_value")
        value = row.get("value")
        if previous is None or value is None:
            continue
        delta = float(value) - float(previous)
        indicator = str(row.get("indicator", "")).upper()
        rule = str(row.get("impact_rule", "")).lower()
        if rule == "inflation":
            # CPIAUCSL is an index level (~315), so compare m/m percent change,
            # not index-point deltas (0.3 points is only ~0.1% m/m).
            if float(previous) <= 0:
                continue
            pct_change = delta / float(previous)
            if pct_change >= 0.004:
                risk_off_count += 1
                signals.append(f"{indicator}:{pct_change:+.2%} inflation")
            elif pct_change <= -0.001:
                risk_on_count += 1
                signals.append(f"{indicator}:{pct_change:+.2%} inflation")
        elif rule == "labor" and indicator == "UNRATE" and delta >= 0.3:
            risk_off_count += 1
            signals.append(f"{indicator}:{delta:+.2f} labor")
        elif rule == "labor" and indicator == "PAYEMS" and delta <= -100:
            # PAYEMS is in thousands of persons: -100 = 100k jobs lost.
            risk_off_count += 1
            signals.append(f"{indicator}:{delta:+.0f}k labor")
        elif rule == "rate_policy" and delta >= 0.25:
            risk_off_count += 1
            signals.append(f"{indicator}:{delta:+.2f} rate_policy")
        elif rule == "rate_policy" and delta <= -0.25:
            risk_on_count += 1
            signals.append(f"{indicator}:{delta:+.2f} rate_policy")

    if risk_off_count:
        cash_target = max(moderate_cash_target, 0.20)
        return "risk_off", 0.85 if risk_off_count == 1 else 0.75, cash_target, signals
    if risk_on_count:
        multiplier = (
            MACRO_RISK.severe_risk_on_buy_multiplier
            if risk_on_count >= 2
            else MACRO_RISK.risk_on_buy_multiplier
        )
        return "risk_on", multiplier, 0.0, signals
    return "neutral", 1.0, 0.0, signals
