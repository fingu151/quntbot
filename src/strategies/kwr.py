from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from statistics import mean
from typing import Any

from sqlalchemy import Engine, select

from src.data.database import session_scope
from src.data.models import DailyPrice, MarketIndexPrice, Stock


KWR_MIN_HISTORY_DAYS = 35
KWR_LONG_HISTORY_DAYS = 220


@dataclass(frozen=True)
class KwrCandidate:
    ticker: str
    name: str
    market: str
    as_of_date: date
    kwr_score: float
    hold_days: int
    variant: str = "risk_guard"


@dataclass(frozen=True)
class _IndicatorSnapshot:
    close: float
    gap: float
    ibs: float
    ret1: float
    down_streak: int
    rsi14: float | None
    mfi14: float | None
    connors_rsi: float | None
    adx14: float | None
    ma200: float | None
    bb_z20: float | None
    vol_ratio20: float | None


def calculate_kwr_candidates(
    engine: Engine,
    *,
    as_of_date: date,
    variant: str = "risk_guard",
    max_candidates: int | None = None,
) -> list[KwrCandidate]:
    if variant != "risk_guard":
        raise ValueError(f"Unsupported KWR variant: {variant}")

    with session_scope(engine) as session:
        stocks = session.scalars(
            select(Stock).where(Stock.is_active.is_(True)).order_by(Stock.ticker)
        ).all()
        index_rows = session.scalars(
            select(MarketIndexPrice)
            .where(MarketIndexPrice.date <= as_of_date)
            .order_by(MarketIndexPrice.symbol, MarketIndexPrice.date)
        ).all()

        index_by_symbol: dict[str, list[MarketIndexPrice]] = {}
        for row in index_rows:
            index_by_symbol.setdefault(row.symbol, []).append(row)

        candidates: list[KwrCandidate] = []
        for stock in stocks:
            regime = _index_regime_for_market(
                stock.market,
                index_by_symbol=index_by_symbol,
                as_of_date=as_of_date,
            )
            if regime is None:
                continue
            prices = session.scalars(
                select(DailyPrice)
                .where(DailyPrice.ticker == stock.ticker, DailyPrice.date <= as_of_date)
                .order_by(DailyPrice.date.desc())
                .limit(KWR_LONG_HISTORY_DAYS + 5)
            ).all()
            rows = list(reversed(prices))
            if not rows or _get(rows[-1], "date") != regime["latest_date"]:
                continue
            score = calculate_kwr_score_from_rows(rows, market=stock.market)
            if score <= 0:
                continue
            hold_days = risk_guard_signal(
                market=stock.market,
                kwr_score=score,
                index_ret20=regime["ret20"],
                index_dd60=regime["dd60"],
                index_below_ma200=regime["below_ma200"],
            )
            if hold_days is None:
                continue
            candidates.append(
                KwrCandidate(
                    ticker=stock.ticker,
                    name=stock.name,
                    market=stock.market,
                    as_of_date=as_of_date,
                    kwr_score=score,
                    hold_days=hold_days,
                    variant=variant,
                )
            )

    candidates.sort(key=lambda item: (-item.kwr_score, item.market, item.ticker))
    if max_candidates is not None:
        return candidates[:max_candidates]
    return candidates


def calculate_kwr_score_from_rows(rows: list[Any], *, market: str) -> float:
    snapshot = _indicator_snapshot(rows)
    if snapshot is None:
        return 0.0

    gap_washout = snapshot.gap <= -0.03 and snapshot.ibs <= 0.2
    deep_gap_washout = snapshot.gap <= -0.04 and snapshot.ibs <= 0.3
    mfi_capitulation = (
        snapshot.mfi14 is not None and snapshot.mfi14 <= 10 and snapshot.down_streak >= 3
    )
    rsi_capitulation = (
        snapshot.rsi14 is not None and snapshot.rsi14 <= 20 and snapshot.down_streak >= 3
    )
    connors_extreme = snapshot.connors_rsi is not None and snapshot.connors_rsi <= 7
    trend_connors = (
        connors_extreme and snapshot.ma200 is not None and snapshot.close > snapshot.ma200
    )
    adx_pullback = (
        snapshot.adx14 is not None
        and snapshot.rsi14 is not None
        and snapshot.ma200 is not None
        and snapshot.adx14 >= 25
        and snapshot.rsi14 <= 35
        and snapshot.close > snapshot.ma200
    )
    panic_volume = (
        snapshot.vol_ratio20 is not None
        and snapshot.ret1 <= -0.15
        and snapshot.vol_ratio20 >= 1.2
    )
    bb_extreme_trend = (
        snapshot.bb_z20 is not None
        and snapshot.ma200 is not None
        and snapshot.bb_z20 <= -2.5
        and snapshot.close > snapshot.ma200
    )
    liquidity_spike = snapshot.vol_ratio20 is not None and snapshot.vol_ratio20 >= 1.2

    score = 0.0
    if market == "KOSPI":
        score += 35 if gap_washout else 0
        score += 10 if deep_gap_washout else 0
        score += 25 if mfi_capitulation else 0
        score += 20 if rsi_capitulation else 0
        score += 20 if panic_volume else 0
        score += 10 if adx_pullback else 0
        score += 5 if liquidity_spike else 0
    else:
        score += 35 if trend_connors else 0
        score += 15 if connors_extreme else 0
        score += 25 if adx_pullback else 0
        score += 20 if bb_extreme_trend else 0
        score += 15 if rsi_capitulation else 0
        score += 15 if mfi_capitulation else 0
        score += 25 if panic_volume else 0
        score += 5 if liquidity_spike else 0
    return min(score, 100.0)


def risk_guard_signal(
    *,
    market: str,
    kwr_score: float,
    index_ret20: float | None,
    index_dd60: float | None,
    index_below_ma200: bool,
) -> int | None:
    ret20_crash = index_ret20 is not None and index_ret20 <= -0.10
    dd60_mid = index_dd60 is not None and -0.20 < index_dd60 <= -0.10

    if market == "KOSPI":
        if kwr_score >= 45 and (ret20_crash or dd60_mid):
            return 20
        return None

    if ret20_crash or not index_below_ma200:
        return 20 if kwr_score >= 40 else None
    return 10 if kwr_score >= 45 else None


def _indicator_snapshot(rows: list[Any]) -> _IndicatorSnapshot | None:
    cleaned = [
        row
        for row in rows
        if _positive(row, "open")
        and _positive(row, "high")
        and _positive(row, "low")
        and _positive(row, "close")
    ]
    if len(cleaned) < KWR_MIN_HISTORY_DAYS:
        return None

    closes = [_float(_get(row, "close")) for row in cleaned]
    highs = [_float(_get(row, "high")) for row in cleaned]
    lows = [_float(_get(row, "low")) for row in cleaned]
    opens = [_float(_get(row, "open")) for row in cleaned]
    volumes = [_float(_get(row, "volume")) for row in cleaned]
    latest_close = closes[-1]
    previous_close = closes[-2]
    latest_high = highs[-1]
    latest_low = lows[-1]

    return _IndicatorSnapshot(
        close=latest_close,
        gap=(opens[-1] / previous_close) - 1.0 if previous_close > 0 else 0.0,
        ibs=_ibs(latest_close, latest_high, latest_low),
        ret1=(latest_close / previous_close) - 1.0 if previous_close > 0 else 0.0,
        down_streak=_down_streak(closes),
        rsi14=_rsi(closes, 14),
        mfi14=_mfi(highs, lows, closes, volumes, 14),
        connors_rsi=_connors_rsi(closes),
        adx14=_adx(highs, lows, closes, 14),
        ma200=_moving_average(closes, 200),
        bb_z20=_bb_z(closes, 20),
        vol_ratio20=_volume_ratio(volumes, 20),
    )


def _index_regime_for_market(
    market: str,
    *,
    index_by_symbol: dict[str, list[MarketIndexPrice]],
    as_of_date: date,
) -> dict[str, Any] | None:
    symbol = "KOSPI" if market == "KOSPI" else "KOSDAQ"
    rows = [
        row
        for row in index_by_symbol.get(symbol, [])
        if row.date <= as_of_date and row.close is not None and row.close > 0
    ]
    if len(rows) < 61:
        return None
    closes = [_float(row.close) for row in rows]
    close = closes[-1]
    ma200 = _moving_average(closes, 200)
    return {
        "latest_date": rows[-1].date,
        "ret20": (close / closes[-21]) - 1.0 if len(closes) >= 21 else None,
        "dd60": (close / max(closes[-60:])) - 1.0 if len(closes) >= 60 else None,
        "below_ma200": ma200 is not None and close < ma200,
    }


def _ibs(close: float, high: float, low: float) -> float:
    if high <= low:
        return 0.5
    return (close - low) / (high - low)


def _down_streak(closes: list[float]) -> int:
    streak = 0
    for previous, current in reversed(list(zip(closes[:-1], closes[1:]))):
        if current < previous:
            streak += 1
        else:
            break
    return streak


def _moving_average(values: list[float], window: int) -> float | None:
    if len(values) < window:
        return None
    return mean(values[-window:])


def _rsi(values: list[float], window: int) -> float | None:
    if len(values) <= window:
        return None
    changes = [current - previous for previous, current in zip(values[-window - 1 :], values[-window:])]
    gains = [max(change, 0.0) for change in changes]
    losses = [abs(min(change, 0.0)) for change in changes]
    avg_gain = mean(gains)
    avg_loss = mean(losses)
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _mfi(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    volumes: list[float],
    window: int,
) -> float | None:
    if len(closes) <= window or not any(volume > 0 for volume in volumes[-window:]):
        return None
    typical = [(high + low + close) / 3.0 for high, low, close in zip(highs, lows, closes)]
    positive = 0.0
    negative = 0.0
    for idx in range(len(typical) - window, len(typical)):
        flow = typical[idx] * max(volumes[idx], 0.0)
        if typical[idx] > typical[idx - 1]:
            positive += flow
        elif typical[idx] < typical[idx - 1]:
            negative += flow
    if negative == 0:
        return 100.0 if positive > 0 else 50.0
    ratio = positive / negative
    return 100.0 - (100.0 / (1.0 + ratio))


def _connors_rsi(closes: list[float]) -> float | None:
    rsi3 = _rsi(closes, 3)
    streaks = _streak_series(closes)
    streak_rsi = _rsi(streaks, 2)
    percent_rank = _return_percent_rank(closes, 100)
    if rsi3 is None or streak_rsi is None or percent_rank is None:
        return None
    return (rsi3 + streak_rsi + percent_rank) / 3.0


def _streak_series(closes: list[float]) -> list[float]:
    streaks = [0.0]
    streak = 0
    for previous, current in zip(closes[:-1], closes[1:]):
        if current > previous:
            streak = streak + 1 if streak > 0 else 1
        elif current < previous:
            streak = streak - 1 if streak < 0 else -1
        else:
            streak = 0
        streaks.append(float(streak))
    return streaks


def _return_percent_rank(closes: list[float], window: int) -> float | None:
    if len(closes) <= window + 1:
        return None
    returns = [
        (current / previous) - 1.0
        for previous, current in zip(closes[-window - 1 :], closes[-window:])
        if previous > 0
    ]
    if len(returns) < window:
        return None
    latest = returns[-1]
    return 100.0 * sum(1 for value in returns if value <= latest) / len(returns)


def _adx(highs: list[float], lows: list[float], closes: list[float], window: int) -> float | None:
    if len(closes) <= (window * 2):
        return None
    plus_dm: list[float] = []
    minus_dm: list[float] = []
    true_ranges: list[float] = []
    for idx in range(1, len(closes)):
        up_move = highs[idx] - highs[idx - 1]
        down_move = lows[idx - 1] - lows[idx]
        plus_dm.append(up_move if up_move > down_move and up_move > 0 else 0.0)
        minus_dm.append(down_move if down_move > up_move and down_move > 0 else 0.0)
        true_ranges.append(
            max(
                highs[idx] - lows[idx],
                abs(highs[idx] - closes[idx - 1]),
                abs(lows[idx] - closes[idx - 1]),
            )
        )
    dx_values: list[float] = []
    for end in range(window, len(true_ranges) + 1):
        tr_sum = sum(true_ranges[end - window : end])
        if tr_sum <= 0:
            continue
        plus_di = 100.0 * sum(plus_dm[end - window : end]) / tr_sum
        minus_di = 100.0 * sum(minus_dm[end - window : end]) / tr_sum
        denom = plus_di + minus_di
        if denom > 0:
            dx_values.append(100.0 * abs(plus_di - minus_di) / denom)
    if len(dx_values) < window:
        return None
    return mean(dx_values[-window:])


def _bb_z(values: list[float], window: int) -> float | None:
    if len(values) < window:
        return None
    recent = values[-window:]
    avg = mean(recent)
    variance = sum((value - avg) ** 2 for value in recent) / len(recent)
    std = variance ** 0.5
    if std == 0:
        return 0.0
    return (values[-1] - avg) / std


def _volume_ratio(values: list[float], window: int) -> float | None:
    if len(values) <= window or values[-1] <= 0:
        return None
    base = [value for value in values[-window - 1 : -1] if value > 0]
    if not base:
        return None
    return values[-1] / mean(base)


def _positive(row: Any, field: str) -> bool:
    value = _get(row, field)
    return value is not None and float(value) > 0


def _get(row: Any, field: str) -> Any:
    if isinstance(row, dict):
        return row.get(field)
    return getattr(row, field, None)


def _float(value: Any) -> float:
    return float(value or 0.0)
