from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from statistics import pstdev

from sqlalchemy import Engine, select

from config import FACTOR
from src.backtest.engine import _make_fast_score_func, run_backtest
from src.backtest.models import BacktestResult
from src.data.database import session_scope
from src.data.models import DailyPrice
from src.factors.engine import calculate_factor_scores
from src.factors.models import FactorScore


BaseScorer = Callable[..., list[FactorScore]]
RunBacktestFunction = Callable[..., BacktestResult]


@dataclass(frozen=True)
class AdaptiveAlphaConfig:
    top_n: int = 30
    sell_rank_buffer: int = 40
    min_position_weight: float = 0.03
    max_position_weight: float = 0.12
    stop_loss_pct: float = -0.07
    trailing_stop_pct: float = -0.08
    stop_cooldown_days: int = 3
    profit_take_pct: float = 0.16
    profit_take_sell_fraction: float = 0.45
    breakeven_stop_pct: float = 0.0
    atr_window: int = 14
    atr_multiplier: float = 2.2
    technical_weight: float = 0.30
    volatility_penalty_weight: float = 0.15
    lookback_days: int = 90
    ma_short_window: int = 20
    ma_long_window: int = 60
    momentum_window: int = 20
    max_preferred_daily_volatility: float = 0.035
    market_risk_rsi_threshold: float = 72.0
    one_market_overheat_cash_target: float = 0.18
    both_markets_overheat_cash_target: float = 0.30
    nasdaq_moderate_drop_pct: float = -0.018
    nasdaq_severe_drop_pct: float = -0.032
    nasdaq_moderate_cash_target: float = 0.22
    nasdaq_severe_cash_target: float = 0.38


DEFAULT_ADAPTIVE_ALPHA = AdaptiveAlphaConfig()


def calculate_adaptive_alpha_scores(
    engine: Engine,
    *,
    as_of_date: date,
    base_scorer: BaseScorer = calculate_factor_scores,
    config: AdaptiveAlphaConfig = DEFAULT_ADAPTIVE_ALPHA,
    price_history_by_ticker: dict[str, list[tuple[date, float]]] | None = None,
) -> list[FactorScore]:
    base_scores = base_scorer(engine, as_of_date=as_of_date)
    if not base_scores:
        return []

    tickers = [score.ticker for score in base_scores]
    if price_history_by_ticker is None:
        price_history = _load_price_history(
            engine,
            tickers=tickers,
            as_of_date=as_of_date,
            lookback_days=config.lookback_days,
        )
    else:
        price_history = {
            ticker: _slice_preloaded_history(
                price_history_by_ticker.get(ticker, []),
                as_of_date=as_of_date,
                lookback_days=config.lookback_days,
            )
            for ticker in tickers
        }
    adjusted = [
        _with_adaptive_score(score, price_history.get(score.ticker, []), config)
        for score in base_scores
    ]
    adjusted.sort(key=lambda score: (score.total_score, score.ticker), reverse=True)
    return [
        FactorScore(
            ticker=score.ticker,
            name=score.name,
            market=score.market,
            as_of_date=score.as_of_date,
            value_score=score.value_score,
            quality_score=score.quality_score,
            momentum_score=score.momentum_score,
            yield_score=score.yield_score,
            technical_score=score.technical_score,
            auxiliary_score=score.auxiliary_score,
            total_score=score.total_score,
            rank=rank,
            busanstock_score=score.busanstock_score,
            investor_flow_score=score.investor_flow_score,
            research_report_score=score.research_report_score,
        )
        for rank, score in enumerate(adjusted, start=1)
    ]


def run_adaptive_alpha_backtest(
    engine: Engine,
    *,
    start_date: date,
    end_date: date,
    config: AdaptiveAlphaConfig = DEFAULT_ADAPTIVE_ALPHA,
    run_backtest_func: RunBacktestFunction = run_backtest,
    **overrides: object,
) -> BacktestResult:
    base_scorer = _make_fast_score_func(
        engine,
        lookback_days=FACTOR.momentum_lookback_days,
        start_date=start_date,
        end_date=end_date,
    )
    price_history_by_ticker = preload_adaptive_price_history(
        engine,
        start_date=start_date,
        end_date=end_date,
        lookback_days=config.lookback_days,
    )

    def scoring_func(engine: Engine, *, as_of_date: date) -> list[FactorScore]:
        return calculate_adaptive_alpha_scores(
            engine,
            as_of_date=as_of_date,
            base_scorer=base_scorer,
            config=config,
            price_history_by_ticker=price_history_by_ticker,
        )

    params = {
        "start_date": start_date,
        "end_date": end_date,
        "scoring_func": scoring_func,
        "top_n": config.top_n,
        "stop_loss_pct": config.stop_loss_pct,
        "trailing_stop_pct": config.trailing_stop_pct,
        "stop_cooldown_days": config.stop_cooldown_days,
        "enable_atr_stop": True,
        "atr_window": config.atr_window,
        "atr_multiplier": config.atr_multiplier,
        "profit_take_pct": config.profit_take_pct,
        "profit_take_sell_fraction": config.profit_take_sell_fraction,
        "breakeven_stop_pct": config.breakeven_stop_pct,
        "sell_rank_buffer": config.sell_rank_buffer,
        "min_holding_trading_days": 0,
        "weighting": "score_weighted",
        "min_position_weight": config.min_position_weight,
        "max_position_weight": config.max_position_weight,
        "enable_market_risk_overlay": True,
        "market_risk_rsi_threshold": config.market_risk_rsi_threshold,
        "one_market_overheat_cash_target": config.one_market_overheat_cash_target,
        "both_markets_overheat_cash_target": config.both_markets_overheat_cash_target,
        "nasdaq_moderate_drop_pct": config.nasdaq_moderate_drop_pct,
        "nasdaq_severe_drop_pct": config.nasdaq_severe_drop_pct,
        "nasdaq_moderate_cash_target": config.nasdaq_moderate_cash_target,
        "nasdaq_severe_cash_target": config.nasdaq_severe_cash_target,
    }
    params.update(overrides)
    return run_backtest_func(engine, **params)


def _with_adaptive_score(
    score: FactorScore,
    closes: list[float],
    config: AdaptiveAlphaConfig,
) -> FactorScore:
    technical_quality = _technical_quality(closes, config)
    volatility_penalty = _volatility_penalty(closes, config)
    multiplier = 1.0 + (config.technical_weight * technical_quality)
    multiplier -= config.volatility_penalty_weight * volatility_penalty
    adjusted_total = max(0.0, score.total_score * multiplier)
    return FactorScore(
        ticker=score.ticker,
        name=score.name,
        market=score.market,
        as_of_date=score.as_of_date,
        value_score=score.value_score,
        quality_score=score.quality_score,
        momentum_score=score.momentum_score,
        yield_score=score.yield_score,
        technical_score=score.technical_score,
        auxiliary_score=score.auxiliary_score,
        total_score=adjusted_total,
        rank=score.rank,
        busanstock_score=score.busanstock_score,
        investor_flow_score=score.investor_flow_score,
        research_report_score=score.research_report_score,
    )


def _technical_quality(closes: list[float], config: AdaptiveAlphaConfig) -> float:
    if len(closes) < config.ma_long_window:
        return 0.0
    latest = closes[-1]
    short_ma = _mean(closes[-config.ma_short_window :])
    long_ma = _mean(closes[-config.ma_long_window :])
    previous_short_ma = _mean(closes[-config.ma_short_window - 5 : -5])
    momentum_base = closes[-config.momentum_window]
    conditions = [
        latest > short_ma,
        latest > long_ma,
        short_ma > long_ma,
        short_ma > previous_short_ma,
        momentum_base > 0 and latest / momentum_base - 1.0 > 0,
    ]
    return sum(1 for item in conditions if item) / len(conditions)


def _volatility_penalty(closes: list[float], config: AdaptiveAlphaConfig) -> float:
    if len(closes) < config.momentum_window + 1:
        return 0.0
    returns = [
        current / previous - 1.0
        for previous, current in zip(closes[-config.momentum_window - 1 :], closes[-config.momentum_window :])
        if previous > 0
    ]
    if len(returns) < 2:
        return 0.0
    volatility = pstdev(returns)
    if volatility <= config.max_preferred_daily_volatility:
        return 0.0
    return min(1.0, volatility / config.max_preferred_daily_volatility - 1.0)


def _load_price_history(
    engine: Engine,
    *,
    tickers: list[str],
    as_of_date: date,
    lookback_days: int,
) -> dict[str, list[float]]:
    if not tickers:
        return {}
    start_date = as_of_date - timedelta(days=lookback_days * 2)
    with session_scope(engine) as session:
        rows = session.scalars(
            select(DailyPrice)
            .where(
                DailyPrice.ticker.in_(tickers),
                DailyPrice.date >= start_date,
                DailyPrice.date <= as_of_date,
            )
            .order_by(DailyPrice.ticker, DailyPrice.date)
        ).all()
    history: dict[str, list[float]] = {ticker: [] for ticker in tickers}
    for row in rows:
        if row.close is not None and row.close > 0:
            history.setdefault(row.ticker, []).append(float(row.close))
    return {ticker: values[-lookback_days:] for ticker, values in history.items()}


def preload_adaptive_price_history(
    engine: Engine,
    *,
    start_date: date,
    end_date: date,
    lookback_days: int,
) -> dict[str, list[tuple[date, float]]]:
    query_start = start_date - timedelta(days=lookback_days * 2)
    with session_scope(engine) as session:
        rows = session.scalars(
            select(DailyPrice)
            .where(
                DailyPrice.date >= query_start,
                DailyPrice.date <= end_date,
            )
            .order_by(DailyPrice.ticker, DailyPrice.date)
        ).all()
    history: dict[str, list[tuple[date, float]]] = {}
    for row in rows:
        if row.close is not None and row.close > 0:
            history.setdefault(row.ticker, []).append((row.date, float(row.close)))
    return history


def _slice_preloaded_history(
    rows: list[tuple[date, float]],
    *,
    as_of_date: date,
    lookback_days: int,
) -> list[float]:
    values = [close for price_date, close in rows if price_date <= as_of_date]
    return values[-lookback_days:]


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0
