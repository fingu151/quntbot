from __future__ import annotations

from datetime import date
from statistics import mean, pstdev

from loguru import logger
import pandas as pd
from sqlalchemy import Engine, select

from config import FACTOR
from src.data.database import session_scope
from src.data.models import DailyPrice, Fundamental, QualityMetric, Stock
from src.data.repositories import (
    get_latest_busanstock_signals,
    get_latest_telegram_signals,
    get_recent_investor_flow_scores,
    get_recent_research_report_scores,
)
from src.factors.models import FactorScore
from src.factors.scoring import combine_scores, score_series


MIN_QUALITY_COVERAGE_RATIO = 0.70
MIN_QUALITY_SAFETY_COVERAGE_RATIO = 0.50
MIN_QUALITY_METRIC_COUNT = 2
MAX_DEBT_RATIO = 3.0
SEVERE_LOSS_MARGIN_THRESHOLD = -0.10
SEVERE_LOSS_QUARTERS = 2
TECH_MA_SHORT_WINDOW = 20
TECH_MA_MEDIUM_WINDOW = 60
TECH_MA_SLOPE_LOOKBACK = 20
TECH_RSI_WINDOW = 14
TECH_MAX_RSI = 75.0
TECH_VOLATILITY_WINDOW = 20
TECH_MAX_DAILY_VOLATILITY = 0.05
TECH_MIN_PASSED_CONDITIONS = 3


def calculate_factor_scores(
    engine: Engine,
    *,
    as_of_date: date,
    lookback_days: int | None = None,
) -> list[FactorScore]:
    lookback = lookback_days or FACTOR.momentum_lookback_days
    raw = _load_factor_inputs(engine, as_of_date=as_of_date, lookback_days=lookback)
    if raw.empty:
        return []
    with session_scope(engine) as session:
        telegram_signals = get_latest_telegram_signals(session, as_of_date)
        busanstock_signals = get_latest_busanstock_signals(session, as_of_date)
        investor_flow_signals = get_recent_investor_flow_scores(session, as_of_date)
        research_report_signals = get_recent_research_report_scores(session, as_of_date)
    return calculate_factor_scores_from_df(
        raw,
        as_of_date=as_of_date,
        telegram_signals=telegram_signals,
        busanstock_signals=busanstock_signals,
        investor_flow_signals=investor_flow_signals,
        research_report_signals=research_report_signals,
    )


def calculate_factor_scores_from_df(
    raw: pd.DataFrame,
    *,
    as_of_date: date,
    telegram_signals: dict[str, float] | None = None,
    busanstock_signals: dict[str, float] | None = None,
    investor_flow_signals: dict[str, float] | None = None,
    research_report_signals: dict[str, float] | None = None,
    apply_buy_filters: bool = True,
) -> list[FactorScore]:
    """DataFrame(ticker,name,market,per,pbr,eps,bps,div,momentum_return) → FactorScore 리스트."""
    df = raw.copy()
    if apply_buy_filters:
        df = _apply_buy_candidate_filters(df, as_of_date=as_of_date)
        if df.empty:
            return []

    # --- 가치 팩터 ---
    df["per_score"] = score_series(
        df["per"], higher_is_better=False, method=FACTOR.scoring_method, require_positive=True
    )
    df["pbr_score"] = score_series(
        df["pbr"], higher_is_better=False, method=FACTOR.scoring_method, require_positive=True
    )
    df["value_score"] = df[["per_score", "pbr_score"]].mean(axis=1)

    # --- Quality factor: DART ROE / operating margin / debt ratio ---
    for column in ("roe", "operating_margin", "debt_ratio"):
        if column not in df:
            df[column] = float("nan")
    df["roe_score"] = score_series(
        df["roe"], higher_is_better=True, method=FACTOR.scoring_method
    )
    df["opm_score"] = score_series(
        df["operating_margin"], higher_is_better=True, method=FACTOR.scoring_method
    )
    df["debt_score"] = score_series(
        df["debt_ratio"], higher_is_better=False, method=FACTOR.scoring_method
    )
    df["quality_score"] = df[["roe_score", "opm_score", "debt_score"]].mean(axis=1)
    total = len(df)
    covered = int(df["quality_score"].notna().sum())
    if total:
        logger.trace(
            f"quality_score covered {covered}/{total} ({covered / total:.0%}) on {as_of_date}"
        )

    # --- 모멘텀 팩터 ---
    df["momentum_score"] = score_series(
        df["momentum_return"], higher_is_better=True, method=FACTOR.scoring_method
    )

    # --- 배당수익률 팩터 ---
    df["yield_score"] = score_series(
        df["div"], higher_is_better=True, method=FACTOR.scoring_method
    )

    # --- 텔레그램 모닝 신호 팩터 ---
    if telegram_signals:
        df["telegram_raw"] = df["ticker"].map(telegram_signals)
    else:
        df["telegram_raw"] = float("nan")
    df["telegram_score"] = score_series(
        df["telegram_raw"], higher_is_better=True, method=FACTOR.scoring_method
    )

    # NaN → 0 (해당 팩터 데이터 없는 종목도 나머지 팩터로 편입 가능)
    df["quality_score"] = df["quality_score"].fillna(0.0)
    df["yield_score"] = df["yield_score"].fillna(0.0)
    df["telegram_score"] = df["telegram_score"].fillna(0.0)
    if busanstock_signals:
        df["busanstock_score"] = df["ticker"].map(busanstock_signals).fillna(0.0)
    else:
        df["busanstock_score"] = 0.0
    if investor_flow_signals:
        df["investor_flow_score"] = df["ticker"].map(investor_flow_signals).fillna(0.0)
    else:
        df["investor_flow_score"] = 0.0
    if research_report_signals:
        df["research_report_score"] = df["ticker"].map(research_report_signals).fillna(0.0)
    else:
        df["research_report_score"] = 0.0

    df["total_score"] = combine_scores(
        df,
        weights={
            "value_score": FACTOR.value_weight,
            "quality_score": FACTOR.quality_weight,
            "momentum_score": FACTOR.momentum_weight,
            "yield_score": FACTOR.yield_weight,
            "telegram_score": FACTOR.telegram_weight,
            "busanstock_score": FACTOR.busanstock_weight,
            "investor_flow_score": FACTOR.investor_flow_weight,
            "research_report_score": FACTOR.research_report_weight,
        },
        scale_to=100.0,
    )
    ranked = df.dropna(subset=["value_score", "momentum_score", "total_score"]).sort_values(
        ["total_score", "ticker"],
        ascending=[False, True],
    )

    results: list[FactorScore] = []
    for rank, (_, row) in enumerate(ranked.iterrows(), start=1):
        results.append(
            FactorScore(
                ticker=row["ticker"],
                name=row["name"],
                market=row["market"],
                as_of_date=as_of_date,
                value_score=float(row["value_score"]),
                quality_score=float(row["quality_score"]),
                momentum_score=float(row["momentum_score"]),
                yield_score=float(row["yield_score"]),
                telegram_score=float(row["telegram_score"]),
                total_score=float(row["total_score"]),
                rank=rank,
                busanstock_score=float(row["busanstock_score"]),
                investor_flow_score=float(row["investor_flow_score"]),
                research_report_score=float(row["research_report_score"]),
            )
        )
    return results


def _apply_buy_candidate_filters(raw: pd.DataFrame, *, as_of_date: date) -> pd.DataFrame:
    df = raw.copy()
    before_count = len(df)
    for column in ("per", "pbr", "roe", "operating_margin", "debt_ratio"):
        if column not in df:
            df[column] = float("nan")

    per = pd.to_numeric(df["per"], errors="coerce")
    pbr = pd.to_numeric(df["pbr"], errors="coerce")
    df = df[(per > 0) & (pbr > 0)].copy()

    metric_counts = df[["roe", "operating_margin", "debt_ratio"]].notna().sum(axis=1)
    quality_coverage = float((metric_counts >= MIN_QUALITY_METRIC_COUNT).mean()) if len(df) else 0.0
    if quality_coverage >= MIN_QUALITY_COVERAGE_RATIO:
        roe = pd.to_numeric(df["roe"], errors="coerce")
        debt_ratio = pd.to_numeric(df["debt_ratio"], errors="coerce")
        df = df[
            (metric_counts >= MIN_QUALITY_METRIC_COUNT)
            & (roe > 0)
            & (debt_ratio < MAX_DEBT_RATIO)
        ].copy()
    elif len(df):
        logger.warning(
            f"quality_coverage_low on {as_of_date}: "
            f"{quality_coverage:.0%} < {MIN_QUALITY_COVERAGE_RATIO:.0%}"
        )
        if quality_coverage < MIN_QUALITY_SAFETY_COVERAGE_RATIO:
            logger.error(
                f"quality_coverage_critical on {as_of_date}: "
                f"{quality_coverage:.0%} < {MIN_QUALITY_SAFETY_COVERAGE_RATIO:.0%}; "
                "buy candidates skipped"
            )
            return df.iloc[0:0].copy()

    if "recent_operating_margins" in df:
        df = df[
            ~df["recent_operating_margins"].apply(_has_consecutive_severe_operating_loss)
        ].copy()

    if "recent_closes" in df:
        df = df[df["recent_closes"].apply(_technical_filter_passes)].copy()

    excluded_count = before_count - len(df)
    if excluded_count:
        logger.info(f"buy_filter_excluded={excluded_count} on {as_of_date}")
    return df


def _has_consecutive_severe_operating_loss(value: object) -> bool:
    if not isinstance(value, (list, tuple)):
        return False
    margins = []
    for item in value[:SEVERE_LOSS_QUARTERS]:
        try:
            margins.append(float(item))
        except (TypeError, ValueError):
            return False
    if len(margins) < SEVERE_LOSS_QUARTERS:
        return False
    return all(margin < SEVERE_LOSS_MARGIN_THRESHOLD for margin in margins)


def _technical_filter_passes(value: object) -> bool:
    if not isinstance(value, (list, tuple)):
        return False
    try:
        closes = [float(item) for item in value if item is not None]
    except (TypeError, ValueError):
        return False
    if not closes:
        return False

    signal_close = closes[-1]
    ma20 = _moving_average(closes, TECH_MA_SHORT_WINDOW)
    ma60_today = _moving_average(closes, TECH_MA_MEDIUM_WINDOW)
    ma60_20d_ago = _moving_average(closes[:-TECH_MA_SLOPE_LOOKBACK], TECH_MA_MEDIUM_WINDOW)
    rsi14 = _rsi(closes, TECH_RSI_WINDOW)
    volatility_20d = _daily_return_volatility(closes, TECH_VOLATILITY_WINDOW)

    conditions = [
        ma20 is not None and signal_close > ma20,
        ma60_today is not None and ma60_20d_ago is not None and ma60_today > ma60_20d_ago,
        rsi14 is not None and rsi14 < TECH_MAX_RSI,
        volatility_20d is not None and volatility_20d < TECH_MAX_DAILY_VOLATILITY,
    ]
    return sum(conditions) >= TECH_MIN_PASSED_CONDITIONS


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
    average_gain = mean(gains)
    average_loss = mean(losses)
    if average_loss == 0:
        return 100.0 if average_gain > 0 else 50.0
    relative_strength = average_gain / average_loss
    return 100.0 - (100.0 / (1.0 + relative_strength))


def _daily_return_volatility(values: list[float], window: int) -> float | None:
    if len(values) <= window:
        return None
    recent = values[-window - 1 :]
    returns = [
        (current / previous) - 1.0
        for previous, current in zip(recent, recent[1:])
        if previous > 0
    ]
    if len(returns) < window:
        return None
    return pstdev(returns)


def _load_factor_inputs(engine: Engine, *, as_of_date: date, lookback_days: int) -> pd.DataFrame:
    with session_scope(engine) as session:
        stocks = session.scalars(select(Stock).where(Stock.is_active.is_(True))).all()
        rows = []
        for stock in stocks:
            prices = session.scalars(
                select(DailyPrice)
                .where(DailyPrice.ticker == stock.ticker, DailyPrice.date <= as_of_date)
                .order_by(DailyPrice.date.desc())
                .limit(lookback_days + 1)
            ).all()
            if len(prices) <= lookback_days:
                continue

            current_price = prices[0]   # desc 순서: 최신
            lookback_price = prices[-1]  # desc 순서: 가장 오래된 = lookback 시점
            if not current_price.close or not lookback_price.close:
                continue

            fundamentals = session.scalars(
                select(Fundamental)
                .where(Fundamental.ticker == stock.ticker, Fundamental.date <= as_of_date)
                .order_by(Fundamental.date.desc())
            ).all()
            fundamental = _latest_non_empty_fundamental(fundamentals)
            if fundamental is None:
                continue
            quality = _latest_available_quality_metric(
                quality_metrics := session.scalars(
                    select(QualityMetric)
                    .where(QualityMetric.ticker == stock.ticker)
                    .order_by(
                        QualityMetric.fiscal_year.desc(),
                        QualityMetric.fiscal_quarter.desc(),
                    )
                ).all(),
                as_of_date=as_of_date,
            )
            recent_operating_margins = _recent_available_operating_margins(
                quality_metrics,
                as_of_date=as_of_date,
            )
            recent_closes = [float(price.close) for price in reversed(prices) if price.close is not None]

            rows.append(
                {
                    "ticker": stock.ticker,
                    "name": stock.name,
                    "market": stock.market,
                    "per": fundamental.per,
                    "pbr": fundamental.pbr,
                    "eps": fundamental.eps,
                    "bps": fundamental.bps,
                    "div": fundamental.div,
                    "roe": quality.roe if quality is not None else None,
                    "operating_margin": quality.operating_margin if quality is not None else None,
                    "debt_ratio": quality.debt_ratio if quality is not None else None,
                    "recent_operating_margins": recent_operating_margins,
                    "recent_closes": recent_closes,
                    "momentum_return": (current_price.close / lookback_price.close) - 1.0,
                }
            )
    return pd.DataFrame(rows)


def _latest_non_empty_fundamental(fundamentals: list[Fundamental]) -> Fundamental | None:
    for fundamental in fundamentals:
        if not _is_empty_fundamental_snapshot(fundamental):
            return fundamental
    return None


def _is_empty_fundamental_snapshot(fundamental: Fundamental) -> bool:
    values = (
        fundamental.bps,
        fundamental.per,
        fundamental.pbr,
        fundamental.eps,
        fundamental.div,
        fundamental.dps,
    )
    return all(value is None or float(value) == 0.0 for value in values)


def _latest_available_quality_metric(
    metrics: list[QualityMetric],
    *,
    as_of_date: date,
) -> QualityMetric | None:
    for metric in metrics:
        if _quality_metric_available_on(metric, as_of_date):
            return metric
    return None


def _recent_available_operating_margins(
    metrics: list[QualityMetric],
    *,
    as_of_date: date,
) -> list[float]:
    margins: list[float] = []
    for metric in metrics:
        if not _quality_metric_available_on(metric, as_of_date):
            continue
        if metric.operating_margin is None:
            continue
        margins.append(float(metric.operating_margin))
        if len(margins) >= SEVERE_LOSS_QUARTERS:
            break
    return margins


def _quality_metric_available_on(metric: QualityMetric, as_of_date: date) -> bool:
    available_date = metric.published_at
    if available_date is None:
        return False
    return available_date <= as_of_date


def _quarter_end_date(fiscal_year: int, fiscal_quarter: int) -> date:
    if fiscal_quarter == 1:
        return date(fiscal_year, 3, 31)
    if fiscal_quarter == 2:
        return date(fiscal_year, 6, 30)
    if fiscal_quarter == 3:
        return date(fiscal_year, 9, 30)
    if fiscal_quarter == 4:
        return date(fiscal_year, 12, 31)
    raise ValueError(f"Invalid fiscal quarter: {fiscal_quarter}")
