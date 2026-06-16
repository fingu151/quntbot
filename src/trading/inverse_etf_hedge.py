from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Any

from config import INVERSE_ETF, InverseEtfHedgeConfig
from src.trading.macro_risk import MacroExposureAdjustment
from src.trading.rebalancer import RebalanceOrder


@dataclass(frozen=True)
class InverseEtfSignal:
    status: str
    target_weight: float
    target_weights: dict[str, float]
    selected_tickers: list[str]
    leverage_type: str
    signals: list[str]
    evidence: list[dict[str, Any]]
    thresholds: dict[str, Any]
    missing_sources: list[str]

    def as_dict(
        self,
        *,
        orders: list[RebalanceOrder] | None = None,
        skipped: list[dict[str, str]] | None = None,
        execution_allowed: bool = True,
    ) -> dict[str, Any]:
        return {
            "status": self.status,
            "target_weight": self.target_weight,
            "target_weights": self.target_weights,
            "selected_tickers": self.selected_tickers,
            "leverage_type": self.leverage_type,
            "signals": self.signals,
            "evidence": self.evidence,
            "thresholds": self.thresholds,
            "missing_sources": self.missing_sources,
            "orders": [
                {"side": order.side, "ticker": order.ticker, "qty": order.qty, "reason": order.reason}
                for order in (orders or [])
            ],
            "skipped": skipped or [],
            "orders_generated": bool(orders),
            "execution_allowed": execution_allowed,
        }


def calculate_inverse_etf_signal(
    *,
    as_of_date: date,
    macro_adjustment: MacroExposureAdjustment,
    domestic_index_closes: dict[str, list[float]],
    config: InverseEtfHedgeConfig = INVERSE_ETF,
) -> InverseEtfSignal:
    thresholds = {
        "market_drop_threshold": config.market_drop_threshold,
        "severe_market_drop_threshold": config.severe_market_drop_threshold,
        "overbought_rsi_threshold": config.overbought_rsi_threshold,
        "severe_overbought_rsi_threshold": config.severe_overbought_rsi_threshold,
        "max_total_weight": config.max_total_weight,
        "max_1x_weight": config.max_1x_weight,
        "max_2x_weight": config.max_2x_weight,
    }
    if not config.enabled:
        return _empty_signal("disabled", thresholds)
    if not config.allowed_tickers:
        return _empty_signal("missing", thresholds, missing_sources=["inverse_etf_allowed_tickers_missing"])

    evidence: list[dict[str, Any]] = []
    signals: list[str] = []
    severe = False
    macro_evidence: dict[str, Any] | None = None
    macro_signal: str | None = None

    market_returns = macro_adjustment.us_market.returns
    for symbol, value in sorted(market_returns.items()):
        if value <= config.severe_market_drop_threshold:
            severe = True
            reason = "inverse_etf_hedge_market_drop"
            signals.append(f"{symbol}:{value:.2%}")
            evidence.append({
                "reason": reason,
                "symbol": symbol,
                "date": str(as_of_date),
                "return": round(value, 6),
                "threshold": config.severe_market_drop_threshold,
                "severity": "severe",
            })
        elif value <= config.market_drop_threshold:
            reason = "inverse_etf_hedge_market_drop"
            signals.append(f"{symbol}:{value:.2%}")
            evidence.append({
                "reason": reason,
                "symbol": symbol,
                "date": str(as_of_date),
                "return": round(value, 6),
                "threshold": config.market_drop_threshold,
                "severity": "moderate",
            })

    if macro_adjustment.status == "risk_off":
        if macro_adjustment.cash_target >= 0.40:
            severe = True
        macro_signal = f"macro:{macro_adjustment.status}:{macro_adjustment.cash_target:.2%}"
        macro_evidence = {
            "reason": "inverse_etf_hedge_macro_risk_off",
            "date": str(as_of_date),
            "macro_status": macro_adjustment.status,
            "cash_target": macro_adjustment.cash_target,
            "severity": "severe" if macro_adjustment.cash_target >= 0.40 else "moderate",
        }

    for symbol, closes in sorted(domestic_index_closes.items()):
        rsi = _rsi_from_closes(closes, 14)
        if rsi is None:
            continue
        # 과매수 단독으로는 진입하지 않는다: 상승 추세 한복판의 역추세 숏을 막기 위해
        # 단기 모멘텀이 꺾였을 때(종가 < 5일 이동평균)만 과매수 헤지를 허용한다.
        if not _momentum_rolling_over(closes):
            continue
        if rsi >= config.severe_overbought_rsi_threshold:
            severe = True
            signals.append(f"{symbol}:RSI{rsi:.1f}")
            evidence.append({
                "reason": "inverse_etf_hedge_overbought",
                "symbol": symbol,
                "date": str(as_of_date),
                "rsi": round(rsi, 4),
                "threshold": config.severe_overbought_rsi_threshold,
                "severity": "severe",
            })
        elif rsi >= config.overbought_rsi_threshold:
            signals.append(f"{symbol}:RSI{rsi:.1f}")
            evidence.append({
                "reason": "inverse_etf_hedge_overbought",
                "symbol": symbol,
                "date": str(as_of_date),
                "rsi": round(rsi, 4),
                "threshold": config.overbought_rsi_threshold,
                "severity": "moderate",
            })

    if macro_evidence is not None and (
        not config.require_market_confirmation or evidence
    ):
        if macro_signal is not None:
            signals.append(macro_signal)
        evidence.append(macro_evidence)

    if not evidence:
        return _empty_signal("hedge_off", thresholds)

    target_weights = _allocate_target_weights(config, severe=severe)
    if not target_weights:
        return _empty_signal(
            "missing",
            thresholds,
            missing_sources=["eligible_inverse_etf_tickers_missing"],
            evidence=evidence,
            signals=signals,
        )
    selected = list(target_weights)
    leverage_type = "mixed" if _has_1x(selected, config) and _has_2x(selected, config) else "2x" if _has_2x(selected, config) else "1x"
    return InverseEtfSignal(
        status="hedge_on",
        target_weight=round(sum(target_weights.values()), 6),
        target_weights=target_weights,
        selected_tickers=selected,
        leverage_type=leverage_type,
        signals=signals,
        evidence=evidence,
        thresholds=thresholds,
        missing_sources=[],
    )


def compute_inverse_etf_orders(
    *,
    holdings: list[dict[str, Any]],
    prices: dict[str, int | float],
    cash: int | float,
    portfolio_value: int | float,
    signal: InverseEtfSignal,
    entry_dates: dict[str, date],
    as_of_date: date,
    config: InverseEtfHedgeConfig = INVERSE_ETF,
) -> tuple[list[RebalanceOrder], list[dict[str, str]]]:
    del cash
    if not config.enabled or not config.allowed_tickers:
        return [], []

    allowed = set(config.allowed_tickers)
    target_weights = signal.target_weights if signal.status == "hedge_on" else {}
    holding_by_ticker = {str(row.get("ticker", "")): row for row in holdings}
    orders: list[RebalanceOrder] = []
    skipped: list[dict[str, str]] = []

    for ticker in sorted(allowed & set(holding_by_ticker)):
        holding = holding_by_ticker[ticker]
        qty = int(holding.get("qty", 0) or 0)
        if qty <= 0:
            continue
        price = _holding_price(ticker, holding, prices)
        if price <= 0:
            skipped.append({"ticker": ticker, "reason": "missing_price"})
            continue
        sell_reason = _forced_sell_reason(
            ticker=ticker,
            holding=holding,
            price=price,
            signal=signal,
            entry_dates=entry_dates,
            as_of_date=as_of_date,
            config=config,
        )
        target_value = float(portfolio_value) * target_weights.get(ticker, 0.0)
        current_value = qty * price
        if sell_reason is None and current_value > target_value and target_weights.get(ticker, 0.0) > 0:
            reduce_value = current_value - target_value
            reduce_qty = math.floor(reduce_value / price)
            if reduce_qty > 0:
                sell_reason = f"inverse_etf_hedge_trim target {target_weights[ticker]:.2%}"
                qty = min(qty, reduce_qty)
        if sell_reason is not None:
            orders.append(RebalanceOrder(ticker, "SELL", qty, sell_reason))

    sell_tickers = {order.ticker for order in orders if order.side == "SELL"}
    if signal.status != "hedge_on" or portfolio_value <= 0:
        return orders, skipped

    reason = _entry_reason(signal)
    for ticker, target_weight in target_weights.items():
        if ticker in sell_tickers:
            continue
        price = float(prices.get(ticker) or 0)
        if price <= 0:
            skipped.append({"ticker": ticker, "reason": "missing_price"})
            continue
        holding = holding_by_ticker.get(ticker, {})
        current_qty = int(holding.get("qty", 0) or 0)
        current_value = current_qty * price
        target_value = float(portfolio_value) * target_weight
        buy_value = target_value - current_value
        qty = math.floor(buy_value / price)
        if qty <= 0:
            continue
        orders.append(RebalanceOrder(ticker, "BUY", qty, f"{reason} target {target_weight:.2%}"))

    return orders, skipped


def _allocate_target_weights(config: InverseEtfHedgeConfig, *, severe: bool) -> dict[str, float]:
    allowed = list(config.allowed_tickers)
    leveraged = set(config.leveraged_tickers) if config.allow_leveraged else set()
    one_x = [ticker for ticker in allowed if ticker not in leveraged]
    two_x = [ticker for ticker in allowed if ticker in leveraged]
    total = min(config.severe_target_weight if severe else config.moderate_target_weight, config.max_total_weight)
    if total <= 0:
        return {}
    weights: dict[str, float] = {}
    if severe and two_x:
        two_x_weight = min(config.severe_2x_target_weight, config.max_2x_weight, total)
        weights[two_x[0]] = round(two_x_weight, 6)
    one_x_weight = min(total - sum(weights.values()), config.max_1x_weight)
    if one_x and one_x_weight > 0:
        weights = {one_x[0]: round(one_x_weight, 6), **weights}
    elif not weights and two_x and config.allow_leveraged:
        weights[two_x[0]] = round(min(total, config.max_2x_weight), 6)
    return {ticker: weight for ticker, weight in weights.items() if weight > 0}


def _forced_sell_reason(
    *,
    ticker: str,
    holding: dict[str, Any],
    price: float,
    signal: InverseEtfSignal,
    entry_dates: dict[str, date],
    as_of_date: date,
    config: InverseEtfHedgeConfig,
) -> str | None:
    avg_price = float(holding.get("avg_price", 0) or 0)
    if avg_price > 0:
        return_pct = price / avg_price - 1.0
        if return_pct <= config.stop_loss_pct:
            return f"inverse_etf_hedge_stop_loss {return_pct:.2%}"
        if return_pct >= config.take_profit_pct:
            return f"inverse_etf_hedge_take_profit {return_pct:.2%}"
    entry_date = entry_dates.get(ticker)
    if entry_date is not None and (as_of_date - entry_date).days > config.max_holding_days:
        return f"inverse_etf_hedge_max_holding_days {config.max_holding_days}d"
    if signal.status != "hedge_on" or ticker not in signal.target_weights:
        return "inverse_etf_hedge_risk_cleared target 0.00%"
    return None


def _entry_reason(signal: InverseEtfSignal) -> str:
    reasons = []
    for item in signal.evidence:
        reason = str(item.get("reason", ""))
        if reason and reason not in reasons:
            reasons.append(reason)
    return "+".join(reasons) if reasons else "inverse_etf_hedge_enter"


def _holding_price(ticker: str, holding: dict[str, Any], prices: dict[str, int | float]) -> float:
    return float(prices.get(ticker) or holding.get("current_price") or 0)


def _empty_signal(
    status: str,
    thresholds: dict[str, Any],
    *,
    missing_sources: list[str] | None = None,
    evidence: list[dict[str, Any]] | None = None,
    signals: list[str] | None = None,
) -> InverseEtfSignal:
    return InverseEtfSignal(
        status=status,
        target_weight=0.0,
        target_weights={},
        selected_tickers=[],
        leverage_type="none",
        signals=signals or [],
        evidence=evidence or [],
        thresholds=thresholds,
        missing_sources=missing_sources or [],
    )


def _has_1x(tickers: list[str], config: InverseEtfHedgeConfig) -> bool:
    leveraged = set(config.leveraged_tickers)
    return any(ticker not in leveraged for ticker in tickers)


def _has_2x(tickers: list[str], config: InverseEtfHedgeConfig) -> bool:
    leveraged = set(config.leveraged_tickers)
    return any(ticker in leveraged for ticker in tickers)


def _momentum_rolling_over(closes: list[float], window: int = 5) -> bool:
    if len(closes) < window:
        return False
    moving_average = sum(closes[-window:]) / window
    return closes[-1] < moving_average


def _rsi_from_closes(closes: list[float], window: int) -> float | None:
    if len(closes) <= window:
        return None
    changes = [
        current - previous
        for previous, current in zip(closes[-window - 1 :], closes[-window:])
    ]
    gains = [max(change, 0.0) for change in changes]
    losses = [abs(min(change, 0.0)) for change in changes]
    average_gain = sum(gains) / window
    average_loss = sum(losses) / window
    if average_loss == 0:
        return 100.0 if average_gain > 0 else 50.0
    relative_strength = average_gain / average_loss
    return 100.0 - (100.0 / (1.0 + relative_strength))
