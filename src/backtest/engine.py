from __future__ import annotations

import bisect
from collections import defaultdict
from collections.abc import Callable
from datetime import date, timedelta
import math
from typing import Any

import pandas as pd
from sqlalchemy import Engine, select

from config import (
    COST,
    EXIT_RULES,
    FACTOR,
    INVERSE_ETF,
    MACRO_RISK,
    MARKET_RISK,
    PORTFOLIO,
    REBALANCE,
    InverseEtfHedgeConfig,
)
from src.backtest.metrics import (
    average_holding_days,
    calculate_cagr,
    calculate_max_drawdown,
    calculate_sharpe_ratio,
    calculate_total_return,
    calculate_win_rate,
)
from src.backtest.models import BacktestResult, BacktestTrade, EquityPoint
from src.data.database import session_scope
from src.data.models import DailyPrice, Fundamental, InvestorFlow, MarketIndexPrice, QualityMetric, Stock
from src.factors.engine import (
    _latest_available_quality_metric,
    _recent_available_operating_margins,
    calculate_factor_scores,
    calculate_factor_scores_from_df,
)
from src.factors.models import FactorScore
from src.trading.allocation import compute_score_weights
from src.trading.inverse_etf_hedge import (
    calculate_inverse_etf_signal,
    compute_inverse_etf_orders,
)
from src.trading.macro_risk import load_macro_exposure_adjustment
from src.trading.rebalancer import is_execution_gap_too_large


ScoreFunction = Callable[..., list[FactorScore]]


def run_backtest(
    engine: Engine,
    *,
    start_date: date,
    end_date: date,
    scoring_func: ScoreFunction = calculate_factor_scores,
    initial_capital: float | None = None,
    top_n: int | None = None,
    commission_rate: float = COST.commission_rate,
    tax_rate_kospi: float = COST.tax_rate_kospi,
    tax_rate_kosdaq: float = COST.tax_rate_kosdaq,
    slippage_rate: float = COST.slippage_rate,
    enable_stops: bool = True,
    stop_loss_pct: float = EXIT_RULES.stop_loss_pct,
    trailing_stop_pct: float = EXIT_RULES.trailing_stop_pct,
    stop_cooldown_days: int = EXIT_RULES.stop_cooldown_days,
    enable_atr_stop: bool = EXIT_RULES.enable_atr_stop,
    atr_window: int = EXIT_RULES.atr_window,
    atr_multiplier: float = EXIT_RULES.atr_multiplier,
    atr_only_stop: bool = EXIT_RULES.atr_only_stop,
    rebalance_frequency: str = REBALANCE.frequency,
    profit_take_pct: float = EXIT_RULES.profit_take_pct,
    profit_take_sell_fraction: float = EXIT_RULES.profit_take_sell_fraction,
    post_profit_trailing_stop_pct: float = EXIT_RULES.post_profit_trailing_stop_pct,
    breakeven_stop_pct: float = EXIT_RULES.breakeven_stop_pct,
    sell_rank_buffer: int = REBALANCE.sell_rank_buffer,
    min_holding_trading_days: int = REBALANCE.min_holding_trading_days,
    weighting: str = PORTFOLIO.weighting,
    min_position_weight: float = PORTFOLIO.min_position_weight,
    max_position_weight: float = PORTFOLIO.max_position_weight,
    enable_market_risk_overlay: bool = MARKET_RISK.enable_overlay,
    market_risk_rsi_window: int = MARKET_RISK.rsi_window,
    market_risk_rsi_threshold: float = MARKET_RISK.rsi_overheat_threshold,
    one_market_overheat_cash_target: float = MARKET_RISK.one_market_overheat_cash_target,
    both_markets_overheat_cash_target: float = MARKET_RISK.both_markets_overheat_cash_target,
    nasdaq_moderate_drop_pct: float = MARKET_RISK.nasdaq_moderate_drop_pct,
    nasdaq_severe_drop_pct: float = MARKET_RISK.nasdaq_severe_drop_pct,
    nasdaq_moderate_cash_target: float = MARKET_RISK.nasdaq_moderate_cash_target,
    nasdaq_severe_cash_target: float = MARKET_RISK.nasdaq_severe_cash_target,
    enable_macro_risk_overlay: bool = MACRO_RISK.enable_overlay,
    baseline_cash_target: float = 0.0,
    baseline_cash_reduce_reason: str = "baseline_cash_reserve",
    enable_volatility_cash_overlay: bool = False,
    volatility_cash_window: int = 20,
    volatility_moderate_annualized: float = 0.25,
    volatility_severe_annualized: float = 0.35,
    volatility_moderate_cash_target: float = 0.20,
    volatility_severe_cash_target: float = 0.30,
    enable_flow_breadth_cash_overlay: bool = False,
    flow_breadth_window: int = 20,
    flow_breadth_moderate_threshold: float = 0.45,
    flow_breadth_severe_threshold: float = 0.40,
    flow_breadth_moderate_cash_target: float = 0.20,
    flow_breadth_severe_cash_target: float = 0.30,
    enable_price_breadth_cash_overlay: bool = False,
    price_breadth_ma_days: int = 60,
    price_breadth_min_count: int = 50,
    price_breadth_moderate_threshold: float = 0.45,
    price_breadth_severe_threshold: float = 0.35,
    price_breadth_moderate_cash_target: float = 0.20,
    price_breadth_severe_cash_target: float = 0.35,
    enable_crash_guard: bool = False,
    crash_guard_moderate_5d_drop_pct: float = -0.03,
    crash_guard_severe_5d_drop_pct: float = -0.05,
    crash_guard_moderate_20d_drop_pct: float = -0.05,
    crash_guard_severe_20d_drop_pct: float = -0.08,
    crash_guard_moderate_cash_target: float = 0.35,
    crash_guard_severe_cash_target: float = 0.55,
    enable_crash_guard_reentry: bool = False,
    crash_guard_reentry_cash_target: float = 0.15,
    crash_guard_reentry_ma_days: int = 20,
    crash_guard_reentry_rsi_window: int = 14,
    crash_guard_reentry_rsi_threshold: float = 45.0,
    crash_guard_reentry_positive_days: int = 3,
    enable_dynamic_top_n: bool = False,
    defensive_top_n: int | None = None,
    severe_defensive_top_n: int | None = None,
    enable_inverse_etf_hedge: bool = INVERSE_ETF.enabled,
    inverse_etf_allowed_tickers: tuple[str, ...] = INVERSE_ETF.allowed_tickers,
    inverse_etf_leveraged_tickers: tuple[str, ...] = INVERSE_ETF.leveraged_tickers,
    inverse_etf_require_market_confirmation: bool = INVERSE_ETF.require_market_confirmation,
) -> BacktestResult:
    # 기본 스코어러는 날짜마다 DB를 재쿼리해서 매우 느림.
    # 벌크 로딩 클로저로 교체하면 동일한 결과를 훨씬 빠르게 얻음.
    if scoring_func is calculate_factor_scores:
        scoring_func = _make_fast_score_func(
            engine,
            lookback_days=FACTOR.momentum_lookback_days,
            start_date=start_date,
            end_date=end_date,
        )

    capital = float(initial_capital or PORTFOLIO.initial_capital)
    target_count = int(top_n or PORTFOLIO.n_holdings)
    prices = _load_prices(engine, start_date=start_date, end_date=end_date)
    atr_cache = _build_atr_cache(prices, window=atr_window) if enable_stops and enable_atr_stop else {}
    prices_by_date = _group_prices_by_date(prices)
    index_prices = _load_market_index_prices(engine, end_date=end_date)
    investor_flows_by_date = (
        _load_investor_flows(engine, start_date=start_date, end_date=end_date)
        if enable_flow_breadth_cash_overlay
        else {}
    )
    price_breadth_closes = (
        _load_price_breadth_closes(
            engine,
            start_date=start_date,
            end_date=end_date,
            lookback_days=max(price_breadth_ma_days * 3, price_breadth_ma_days + 5),
        )
        if enable_price_breadth_cash_overlay
        else {}
    )
    markets = _load_markets(engine)
    inverse_config = InverseEtfHedgeConfig(
        enabled=enable_inverse_etf_hedge,
        allowed_tickers=inverse_etf_allowed_tickers,
        allow_leveraged=INVERSE_ETF.allow_leveraged,
        leveraged_tickers=inverse_etf_leveraged_tickers,
        max_total_weight=INVERSE_ETF.max_total_weight,
        max_1x_weight=INVERSE_ETF.max_1x_weight,
        max_2x_weight=INVERSE_ETF.max_2x_weight,
        moderate_target_weight=INVERSE_ETF.moderate_target_weight,
        severe_target_weight=INVERSE_ETF.severe_target_weight,
        severe_2x_target_weight=INVERSE_ETF.severe_2x_target_weight,
        overbought_rsi_threshold=INVERSE_ETF.overbought_rsi_threshold,
        severe_overbought_rsi_threshold=INVERSE_ETF.severe_overbought_rsi_threshold,
        market_drop_threshold=INVERSE_ETF.market_drop_threshold,
        severe_market_drop_threshold=INVERSE_ETF.severe_market_drop_threshold,
        require_market_confirmation=inverse_etf_require_market_confirmation,
        max_holding_days=INVERSE_ETF.max_holding_days,
        stop_loss_pct=INVERSE_ETF.stop_loss_pct,
        take_profit_pct=INVERSE_ETF.take_profit_pct,
    )
    inverse_allowed = set(inverse_config.allowed_tickers)
    trading_dates = sorted(prices_by_date)

    # 오버레이와 헤지가 같은 날짜로 매크로 상태를 두 번 조회하므로 날짜별로 캐시한다.
    macro_adjustment_cache: dict[date, Any] = {}

    def _macro_adjustment_for(target_date: date) -> Any:
        if target_date not in macro_adjustment_cache:
            macro_adjustment_cache[target_date] = load_macro_exposure_adjustment(
                engine, as_of_date=target_date
            )
        return macro_adjustment_cache[target_date]

    cash = capital
    positions: dict[str, float] = {}
    entry_dates: dict[str, date] = {}
    entry_values: dict[str, float] = {}
    entry_prices: dict[str, float] = {}
    peak_prices: dict[str, float] = {}
    cooldown_until: dict[str, date] = {}
    pending_exits: list[tuple[str, str, float | None]] = []
    profit_taken: set[str] = set()
    trailing_bucket_qty: dict[str, float] = {}
    breakeven_bucket_qty: dict[str, float] = {}
    trades: list[BacktestTrade] = []
    closed_trade_returns: list[float] = []
    closed_holding_days: list[int] = []
    equity_curve: list[EquityPoint] = []
    last_rebalance_key: tuple[int, ...] | None = None
    previous_trading_date: date | None = None
    for trading_date in trading_dates:
        today_prices = prices_by_date[trading_date]
        close_prices = {ticker: price["close"] for ticker, price in today_prices.items()}
        open_prices = {ticker: price["open"] for ticker, price in today_prices.items()}
        if not close_prices:
            continue

        forbidden_today: set[str] = set()
        if enable_stops and pending_exits:
            remaining_pending: list[tuple[str, str, float | None]] = []
            for ticker, reason, pending_quantity in pending_exits:
                if ticker not in positions or ticker not in today_prices:
                    remaining_pending.append((ticker, reason, pending_quantity))
                    continue
                current_quantity = positions[ticker]
                quantity = current_quantity if pending_quantity is None else min(pending_quantity, current_quantity)
                if quantity <= 0:
                    continue
                entry_value = entry_prices.get(ticker, 0.0) * quantity
                cash, trade, trade_return, holding_days = _sell_position(
                    ticker=ticker,
                    quantity=quantity,
                    price=today_prices[ticker]["open"],
                    trade_date=trading_date,
                    cash=cash,
                    market=markets.get(ticker, ""),
                    entry_date=entry_dates[ticker],
                    entry_value=entry_value,
                    commission_rate=commission_rate,
                    tax_rate_kospi=tax_rate_kospi,
                    tax_rate_kosdaq=tax_rate_kosdaq,
                    slippage_rate=slippage_rate,
                    reason=reason,
                )
                trades.append(trade)
                closed_trade_returns.append(trade_return)
                closed_holding_days.append(holding_days)
                forbidden_today.add(ticker)
                remaining_quantity = current_quantity - quantity
                if remaining_quantity <= 1e-9:
                    positions.pop(ticker, None)
                    entry_dates.pop(ticker, None)
                    entry_values.pop(ticker, None)
                    entry_prices.pop(ticker, None)
                    peak_prices.pop(ticker, None)
                    profit_taken.discard(ticker)
                    trailing_bucket_qty.pop(ticker, None)
                    breakeven_bucket_qty.pop(ticker, None)
                else:
                    positions[ticker] = remaining_quantity
                    entry_values[ticker] = max(
                        0.0,
                        entry_values.get(ticker, 0.0) - entry_value,
                    )
                if pending_quantity is None and stop_cooldown_days > 0:
                    cooldown_until[ticker] = trading_date + timedelta(days=stop_cooldown_days)
            pending_exits = remaining_pending

        rebalance_key = _rebalance_key(trading_date, rebalance_frequency)
        should_rebalance = not positions or rebalance_key != last_rebalance_key
        target_tickers = list(positions)
        target_scores: list[FactorScore] = []
        keep_tickers = set(target_tickers)
        risk_cash_target = 0.0
        buy_budget_multiplier = 1.0
        risk_reduce_reason = "market_risk_reduce"
        if should_rebalance and previous_trading_date is not None:
            if baseline_cash_target > 0:
                risk_cash_target = min(max(baseline_cash_target, 0.0), 1.0)
                risk_reduce_reason = baseline_cash_reduce_reason
            if enable_volatility_cash_overlay:
                volatility_cash_target = _volatility_cash_target(
                    index_prices,
                    as_of_date=previous_trading_date,
                    window=volatility_cash_window,
                    moderate_annualized=volatility_moderate_annualized,
                    severe_annualized=volatility_severe_annualized,
                    moderate_cash_target=volatility_moderate_cash_target,
                    severe_cash_target=volatility_severe_cash_target,
                )
                if volatility_cash_target > risk_cash_target:
                    risk_cash_target = volatility_cash_target
                    risk_reduce_reason = "volatility_cash_reduce"
            if enable_flow_breadth_cash_overlay:
                flow_cash_target = _flow_breadth_cash_target(
                    investor_flows_by_date,
                    as_of_date=previous_trading_date,
                    window=flow_breadth_window,
                    moderate_threshold=flow_breadth_moderate_threshold,
                    severe_threshold=flow_breadth_severe_threshold,
                    moderate_cash_target=flow_breadth_moderate_cash_target,
                    severe_cash_target=flow_breadth_severe_cash_target,
                )
                if flow_cash_target > risk_cash_target:
                    risk_cash_target = flow_cash_target
                    risk_reduce_reason = "flow_breadth_cash_reduce"
            if enable_price_breadth_cash_overlay:
                price_breadth_cash_target = _price_breadth_cash_target(
                    price_breadth_closes,
                    as_of_date=previous_trading_date,
                    ma_days=price_breadth_ma_days,
                    min_count=price_breadth_min_count,
                    moderate_threshold=price_breadth_moderate_threshold,
                    severe_threshold=price_breadth_severe_threshold,
                    moderate_cash_target=price_breadth_moderate_cash_target,
                    severe_cash_target=price_breadth_severe_cash_target,
                )
                if price_breadth_cash_target > risk_cash_target:
                    risk_cash_target = price_breadth_cash_target
                    risk_reduce_reason = "price_breadth_cash_reduce"
            if enable_market_risk_overlay:
                market_cash_target = _market_risk_cash_target(
                    index_prices,
                    as_of_date=previous_trading_date,
                    rsi_window=market_risk_rsi_window,
                    rsi_threshold=market_risk_rsi_threshold,
                    one_market_overheat_cash_target=one_market_overheat_cash_target,
                    both_markets_overheat_cash_target=both_markets_overheat_cash_target,
                    nasdaq_moderate_drop_pct=nasdaq_moderate_drop_pct,
                    nasdaq_severe_drop_pct=nasdaq_severe_drop_pct,
                    nasdaq_moderate_cash_target=nasdaq_moderate_cash_target,
                    nasdaq_severe_cash_target=nasdaq_severe_cash_target,
                )
                if market_cash_target > risk_cash_target:
                    risk_cash_target = market_cash_target
                    risk_reduce_reason = "market_risk_reduce"
            if enable_macro_risk_overlay:
                macro_adjustment = _macro_adjustment_for(previous_trading_date)
                buy_budget_multiplier = macro_adjustment.buy_budget_multiplier
                if macro_adjustment.cash_target >= risk_cash_target:
                    risk_cash_target = macro_adjustment.cash_target
                    if macro_adjustment.status == "risk_off":
                        risk_reduce_reason = "macro_risk_reduce"
            if enable_crash_guard:
                crash_cash_target = _crash_guard_cash_target(
                    index_prices,
                    as_of_date=previous_trading_date,
                    moderate_5d_drop_pct=crash_guard_moderate_5d_drop_pct,
                    severe_5d_drop_pct=crash_guard_severe_5d_drop_pct,
                    moderate_20d_drop_pct=crash_guard_moderate_20d_drop_pct,
                    severe_20d_drop_pct=crash_guard_severe_20d_drop_pct,
                    moderate_cash_target=crash_guard_moderate_cash_target,
                    severe_cash_target=crash_guard_severe_cash_target,
                    enable_reentry=enable_crash_guard_reentry,
                    reentry_cash_target=crash_guard_reentry_cash_target,
                    reentry_ma_days=crash_guard_reentry_ma_days,
                    reentry_rsi_window=crash_guard_reentry_rsi_window,
                    reentry_rsi_threshold=crash_guard_reentry_rsi_threshold,
                    reentry_positive_days=crash_guard_reentry_positive_days,
                )
                if crash_cash_target > risk_cash_target:
                    risk_cash_target = crash_cash_target
                    risk_reduce_reason = "crash_guard_reduce"
            active_target_count = _dynamic_target_count(
                base_target_count=target_count,
                risk_cash_target=risk_cash_target,
                enable_dynamic_top_n=enable_dynamic_top_n,
                moderate_cash_target=crash_guard_moderate_cash_target,
                severe_cash_target=crash_guard_severe_cash_target,
                defensive_top_n=defensive_top_n,
                severe_defensive_top_n=severe_defensive_top_n,
            )
            previous_close_prices = {
                ticker: price["close"]
                for ticker, price in prices_by_date[previous_trading_date].items()
            }
            scores = scoring_func(engine, as_of_date=previous_trading_date)
            ranked_scores = [
                score
                for score in scores
                if score.ticker in open_prices and score.ticker not in forbidden_today
                and cooldown_until.get(score.ticker, date.min) < trading_date
                and not is_execution_gap_too_large(
                    execution_price=open_prices[score.ticker],
                    previous_close=previous_close_prices.get(score.ticker),
                    max_abs_gap_pct=PORTFOLIO.max_abs_open_gap_pct,
                )
            ]
            ranked_tickers = [score.ticker for score in ranked_scores]
            target_scores = ranked_scores[:active_target_count]
            target_tickers = ranked_tickers[:active_target_count]
            keep_tickers = set(ranked_tickers[:max(active_target_count, sell_rank_buffer)])
            if target_tickers:
                last_rebalance_key = rebalance_key

        for ticker in list(positions):
            if (
                ticker not in keep_tickers
                and ticker not in inverse_allowed
                and ticker not in forbidden_today
                and ticker in open_prices
            ):
                quantity = positions[ticker]
                entry_value = entry_prices.get(ticker, 0.0) * quantity
                cash, trade, trade_return, holding_days = _sell_position(
                    ticker=ticker,
                    quantity=positions.pop(ticker),
                    price=open_prices[ticker],
                    trade_date=trading_date,
                    cash=cash,
                    market=markets.get(ticker, ""),
                    entry_date=entry_dates.pop(ticker),
                    entry_value=entry_value,
                    commission_rate=commission_rate,
                    tax_rate_kospi=tax_rate_kospi,
                    tax_rate_kosdaq=tax_rate_kosdaq,
                    slippage_rate=slippage_rate,
                    reason="rebalance",
                )
                entry_prices.pop(ticker, None)
                entry_values.pop(ticker, None)
                peak_prices.pop(ticker, None)
                profit_taken.discard(ticker)
                trailing_bucket_qty.pop(ticker, None)
                breakeven_bucket_qty.pop(ticker, None)
                trades.append(trade)
                closed_trade_returns.append(trade_return)
                closed_holding_days.append(holding_days)

        if risk_cash_target > 0 and positions:
            cash = _reduce_to_cash_target(
                positions=positions,
                entry_dates=entry_dates,
                entry_values=entry_values,
                entry_prices=entry_prices,
                peak_prices=peak_prices,
                profit_taken=profit_taken,
                trailing_bucket_qty=trailing_bucket_qty,
                breakeven_bucket_qty=breakeven_bucket_qty,
                close_prices=close_prices,
                open_prices=open_prices,
                markets=markets,
                trade_date=trading_date,
                cash=cash,
                cash_target=risk_cash_target,
                commission_rate=commission_rate,
                tax_rate_kospi=tax_rate_kospi,
                tax_rate_kosdaq=tax_rate_kosdaq,
                slippage_rate=slippage_rate,
                reason=risk_reduce_reason,
                trades=trades,
                closed_trade_returns=closed_trade_returns,
                closed_holding_days=closed_holding_days,
                excluded_tickers=inverse_allowed,
            )

        if enable_inverse_etf_hedge and previous_trading_date is not None and inverse_allowed:
            inverse_signal = calculate_inverse_etf_signal(
                as_of_date=previous_trading_date,
                macro_adjustment=_macro_adjustment_for(previous_trading_date),
                domestic_index_closes=_domestic_index_closes_until(
                    index_prices,
                    previous_trading_date,
                ),
                config=inverse_config,
            )
            cash = _apply_inverse_etf_orders(
                positions=positions,
                entry_dates=entry_dates,
                entry_values=entry_values,
                entry_prices=entry_prices,
                peak_prices=peak_prices,
                profit_taken=profit_taken,
                trailing_bucket_qty=trailing_bucket_qty,
                breakeven_bucket_qty=breakeven_bucket_qty,
                open_prices=open_prices,
                close_prices=close_prices,
                markets=markets,
                trade_date=trading_date,
                cash=cash,
                signal=inverse_signal,
                config=inverse_config,
                commission_rate=commission_rate,
                tax_rate_kospi=tax_rate_kospi,
                tax_rate_kosdaq=tax_rate_kosdaq,
                slippage_rate=slippage_rate,
                trades=trades,
                closed_trade_returns=closed_trade_returns,
                closed_holding_days=closed_holding_days,
            )

        equity_before_buys = cash + _positions_value(positions, close_prices)
        investable_equity = (
            equity_before_buys
            * max(0.0, 1.0 - risk_cash_target)
            * max(0.0, buy_budget_multiplier)
        )
        target_weights: dict[str, float] = {}
        if weighting == "score_weighted" and target_scores:
            target_weights = compute_score_weights(
                [(score.ticker, score.total_score) for score in target_scores],
                min_weight=min_position_weight,
                max_weight=max_position_weight,
            )
        equal_target_value = investable_equity / len(target_tickers) if target_tickers else 0.0
        for ticker in target_tickers:
            if ticker in positions:
                continue
            if ticker in inverse_allowed:
                # 비리밸런스 날 target_tickers=list(positions) 폴백에 헤지 포지션이
                # 들어오는데, 같은 날 헤지 매도 후 일반 매수로 되사면 안 된다.
                continue
            price = open_prices[ticker]
            if target_weights:
                target_value = investable_equity * target_weights.get(ticker, 0.0)
            else:
                target_value = equal_target_value
            quantity = target_value / price if price > 0 else 0.0
            gross_amount = quantity * price
            cost = gross_amount * (commission_rate + slippage_rate)
            total_cash_needed = gross_amount + cost
            if quantity <= 0 or total_cash_needed > cash:
                continue
            cash -= total_cash_needed
            positions[ticker] = quantity
            entry_dates[ticker] = trading_date
            entry_values[ticker] = gross_amount + cost
            entry_prices[ticker] = (gross_amount + cost) / quantity
            peak_prices[ticker] = price
            trades.append(
                BacktestTrade(
                    date=trading_date,
                    ticker=ticker,
                    side="BUY",
                    quantity=quantity,
                    price=price,
                    gross_amount=gross_amount,
                    cost=cost,
                    reason="rebalance",
                )
            )

        if enable_stops:
            for ticker in list(positions):
                if ticker in inverse_allowed:
                    # 인버스 헤지 포지션은 헤지 모듈 규칙으로만 청산한다 (이중 관리 방지).
                    continue
                if ticker not in close_prices:
                    continue
                close = close_prices[ticker]
                peak_prices[ticker] = max(peak_prices.get(ticker, close), close)
                entry = entry_prices.get(ticker)
                if entry is None:
                    continue
                return_from_entry = (close / entry) - 1.0
                loss_from_peak = (close / peak_prices[ticker]) - 1.0
                if ticker not in profit_taken:
                    atr = atr_cache.get((ticker, trading_date)) if enable_atr_stop else None
                    atr_stop_price = entry - (atr * atr_multiplier) if atr is not None else None
                    if atr_stop_price is not None and close <= atr_stop_price:
                        pending_exits.append((ticker, "atr_stop", None))
                    elif (
                        not (atr_only_stop and atr_stop_price is not None)
                        and return_from_entry <= stop_loss_pct
                    ):
                        pending_exits.append((ticker, "stop_loss", None))
                    elif return_from_entry >= profit_take_pct:
                        sell_qty = positions[ticker] * profit_take_sell_fraction
                        if sell_qty > 0:
                            pending_exits.append((ticker, "profit_take_20", sell_qty))
                            profit_taken.add(ticker)
                            remaining_qty = positions[ticker] - sell_qty
                            trailing_bucket_qty[ticker] = remaining_qty * 0.50
                            breakeven_bucket_qty[ticker] = remaining_qty - trailing_bucket_qty[ticker]
                else:
                    trail_qty = trailing_bucket_qty.get(ticker, 0.0)
                    breakeven_qty = breakeven_bucket_qty.get(ticker, 0.0)
                    if trail_qty > 0 and loss_from_peak <= post_profit_trailing_stop_pct:
                        pending_exits.append((ticker, "post_profit_trailing_stop", trail_qty))
                        trailing_bucket_qty[ticker] = 0.0
                    if breakeven_qty > 0 and return_from_entry <= breakeven_stop_pct:
                        pending_exits.append((ticker, "post_profit_breakeven_stop", breakeven_qty))
                        breakeven_bucket_qty[ticker] = 0.0

        positions_value = _positions_value(positions, close_prices)
        equity_curve.append(
            EquityPoint(
                date=trading_date,
                equity=round(cash + positions_value, 10),
                cash=round(cash, 10),
                positions_value=round(positions_value, 10),
            )
        )
        previous_trading_date = trading_date

    if enable_stops and pending_exits and trading_dates:
        last_date = trading_dates[-1]
        last_prices = prices_by_date[last_date]
        for ticker, reason, pending_quantity in pending_exits:
            if ticker not in positions or ticker not in last_prices:
                continue
            current_quantity = positions[ticker]
            quantity = current_quantity if pending_quantity is None else min(pending_quantity, current_quantity)
            if quantity <= 0:
                continue
            fallback_reason = f"{reason}_close_fallback"
            entry_value = entry_prices.get(ticker, 0.0) * quantity
            cash, trade, trade_return, holding_days = _sell_position(
                ticker=ticker,
                quantity=quantity,
                price=last_prices[ticker]["close"],
                trade_date=last_date,
                cash=cash,
                market=markets.get(ticker, ""),
                entry_date=entry_dates[ticker],
                entry_value=entry_value,
                commission_rate=commission_rate,
                tax_rate_kospi=tax_rate_kospi,
                tax_rate_kosdaq=tax_rate_kosdaq,
                slippage_rate=slippage_rate,
                reason=fallback_reason,
            )
            remaining_quantity = current_quantity - quantity
            if remaining_quantity <= 1e-9:
                positions.pop(ticker, None)
                entry_dates.pop(ticker, None)
                entry_values.pop(ticker, None)
                entry_prices.pop(ticker, None)
                peak_prices.pop(ticker, None)
                profit_taken.discard(ticker)
                trailing_bucket_qty.pop(ticker, None)
                breakeven_bucket_qty.pop(ticker, None)
            else:
                positions[ticker] = remaining_quantity
                entry_values[ticker] = max(
                    0.0,
                    entry_values.get(ticker, 0.0) - entry_value,
                )
            trades.append(trade)
            closed_trade_returns.append(trade_return)
            closed_holding_days.append(holding_days)
        if equity_curve:
            positions_value = _positions_value(
                positions,
                {ticker: price["close"] for ticker, price in last_prices.items()},
            )
            equity_curve[-1] = EquityPoint(
                date=last_date,
                equity=round(cash + positions_value, 10),
                cash=round(cash, 10),
                positions_value=round(positions_value, 10),
            )

    final_equity = equity_curve[-1].equity if equity_curve else capital
    daily_returns = _equity_returns([point.equity for point in equity_curve])
    return BacktestResult(
        initial_capital=capital,
        final_equity=final_equity,
        total_return=calculate_total_return(initial_equity=capital, final_equity=final_equity),
        cagr=calculate_cagr(
            initial_equity=capital,
            final_equity=final_equity,
            start_date=start_date,
            end_date=end_date,
        ),
        max_drawdown=calculate_max_drawdown([point.equity for point in equity_curve]),
        sharpe_ratio=calculate_sharpe_ratio(daily_returns),
        win_rate=calculate_win_rate(closed_trade_returns),
        average_holding_days=average_holding_days(closed_holding_days),
        trades=trades,
        equity_curve=equity_curve,
    )


def _load_close_prices(engine: Engine, *, start_date: date, end_date: date) -> dict[tuple[str, date], float]:
    with session_scope(engine) as session:
        rows = session.scalars(
            select(DailyPrice).where(DailyPrice.date >= start_date, DailyPrice.date <= end_date)
        ).all()
    return {(row.ticker, row.date): float(row.close) for row in rows if row.close is not None}


def _load_prices(engine: Engine, *, start_date: date, end_date: date) -> dict[tuple[str, date], dict[str, float]]:
    with session_scope(engine) as session:
        rows = session.scalars(
            select(DailyPrice).where(DailyPrice.date >= start_date, DailyPrice.date <= end_date)
        ).all()
    return {
        (row.ticker, row.date): {
            "open": float(row.open),
            "high": float(row.high if row.high is not None else row.close),
            "low": float(row.low if row.low is not None else row.close),
            "close": float(row.close),
        }
        for row in rows
        if row.open is not None and row.close is not None
    }


def _load_market_index_prices(engine: Engine, *, end_date: date) -> dict[str, list[dict[str, Any]]]:
    with session_scope(engine) as session:
        rows = session.scalars(
            select(MarketIndexPrice)
            .where(MarketIndexPrice.date <= end_date)
            .order_by(MarketIndexPrice.symbol, MarketIndexPrice.date)
        ).all()
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.close is None:
            continue
        grouped[row.symbol.upper()].append(
            {
                "date": row.date,
                "open": float(row.open if row.open is not None else row.close),
                "high": float(row.high if row.high is not None else row.close),
                "low": float(row.low if row.low is not None else row.close),
                "close": float(row.close),
            }
        )
    return grouped


def _load_investor_flows(
    engine: Engine,
    *,
    start_date: date,
    end_date: date,
) -> dict[date, list[dict[str, float | str]]]:
    flow_start = start_date - timedelta(days=90)
    with session_scope(engine) as session:
        rows = session.scalars(
            select(InvestorFlow)
            .where(InvestorFlow.date >= flow_start, InvestorFlow.date <= end_date)
            .order_by(InvestorFlow.date, InvestorFlow.ticker)
        ).all()
    grouped: dict[date, list[dict[str, float | str]]] = defaultdict(list)
    for row in rows:
        grouped[row.date].append(
            {
                "ticker": row.ticker,
                "foreign": float(row.foreign_net_buy or 0.0),
                "institution": float(row.institution_net_buy or 0.0),
            }
        )
    return grouped


def _load_price_breadth_closes(
    engine: Engine,
    *,
    start_date: date,
    end_date: date,
    lookback_days: int,
) -> dict[str, tuple[list[date], list[float]]]:
    price_start = start_date - timedelta(days=max(lookback_days, 0))
    with session_scope(engine) as session:
        active_common_tickers = session.scalars(
            select(Stock.ticker).where(
                Stock.is_active.is_(True),
                Stock.instrument_type == "COMMON_STOCK",
            )
        ).all()
        if not active_common_tickers:
            return {}
        rows = session.scalars(
            select(DailyPrice)
            .where(
                DailyPrice.date >= price_start,
                DailyPrice.date <= end_date,
                DailyPrice.ticker.in_(active_common_tickers),
            )
            .order_by(DailyPrice.ticker, DailyPrice.date)
        ).all()

    grouped: dict[str, tuple[list[date], list[float]]] = {}
    for row in rows:
        if row.close is None or row.close <= 0:
            continue
        dates, closes = grouped.setdefault(row.ticker, ([], []))
        dates.append(row.date)
        closes.append(float(row.close))
    return grouped


def _load_markets(engine: Engine) -> dict[str, str]:
    with session_scope(engine) as session:
        rows = session.scalars(select(Stock)).all()
    return {row.ticker: row.market for row in rows}


def _group_prices_by_date(prices: dict[tuple[str, date], Any]) -> dict[date, dict[str, Any]]:
    grouped: dict[date, dict[str, Any]] = defaultdict(dict)
    for (ticker, price_date), price in prices.items():
        grouped[price_date][ticker] = price
    return grouped


def _positions_value(positions: dict[str, float], prices: dict[str, float]) -> float:
    return sum(quantity * prices[ticker] for ticker, quantity in positions.items() if ticker in prices)


def _reduce_to_cash_target(
    *,
    positions: dict[str, float],
    entry_dates: dict[str, date],
    entry_values: dict[str, float],
    entry_prices: dict[str, float],
    peak_prices: dict[str, float],
    profit_taken: set[str],
    trailing_bucket_qty: dict[str, float],
    breakeven_bucket_qty: dict[str, float],
    close_prices: dict[str, float],
    open_prices: dict[str, float],
    markets: dict[str, str],
    trade_date: date,
    cash: float,
    cash_target: float,
    commission_rate: float,
    tax_rate_kospi: float,
    tax_rate_kosdaq: float,
    slippage_rate: float,
    trades: list[BacktestTrade],
    closed_trade_returns: list[float],
    closed_holding_days: list[int],
    reason: str = "market_risk_reduce",
    excluded_tickers: set[str] | None = None,
) -> float:
    equity = cash + _positions_value(positions, close_prices)
    target_cash = equity * cash_target
    cash_needed = target_cash - cash
    if cash_needed <= 0:
        return cash

    position_value = _positions_value(positions, open_prices)
    if position_value <= 0:
        return cash

    sell_fraction = min(1.0, cash_needed / position_value)
    excluded_tickers = excluded_tickers or set()
    for ticker in list(positions):
        if ticker in excluded_tickers or ticker not in open_prices or ticker not in entry_dates:
            continue
        current_quantity = positions[ticker]
        quantity = current_quantity * sell_fraction
        if quantity <= 0:
            continue
        entry_value = entry_prices.get(ticker, 0.0) * quantity
        cash, trade, trade_return, holding_days = _sell_position(
            ticker=ticker,
            quantity=quantity,
            price=open_prices[ticker],
            trade_date=trade_date,
            cash=cash,
            market=markets.get(ticker, ""),
            entry_date=entry_dates[ticker],
            entry_value=entry_value,
            commission_rate=commission_rate,
            tax_rate_kospi=tax_rate_kospi,
            tax_rate_kosdaq=tax_rate_kosdaq,
            slippage_rate=slippage_rate,
            reason=reason,
        )
        trades.append(trade)
        closed_trade_returns.append(trade_return)
        closed_holding_days.append(holding_days)
        remaining_quantity = current_quantity - quantity
        if remaining_quantity <= 1e-9:
            positions.pop(ticker, None)
            entry_dates.pop(ticker, None)
            entry_values.pop(ticker, None)
            entry_prices.pop(ticker, None)
            peak_prices.pop(ticker, None)
            profit_taken.discard(ticker)
            trailing_bucket_qty.pop(ticker, None)
            breakeven_bucket_qty.pop(ticker, None)
        else:
            positions[ticker] = remaining_quantity
            entry_values[ticker] = max(
                0.0,
                entry_values.get(ticker, 0.0) - entry_value,
            )
            if ticker in trailing_bucket_qty:
                trailing_bucket_qty[ticker] *= 1.0 - sell_fraction
            if ticker in breakeven_bucket_qty:
                breakeven_bucket_qty[ticker] *= 1.0 - sell_fraction
    return cash


def _apply_inverse_etf_orders(
    *,
    positions: dict[str, float],
    entry_dates: dict[str, date],
    entry_values: dict[str, float],
    entry_prices: dict[str, float],
    peak_prices: dict[str, float],
    profit_taken: set[str],
    trailing_bucket_qty: dict[str, float],
    breakeven_bucket_qty: dict[str, float],
    open_prices: dict[str, float],
    close_prices: dict[str, float],
    markets: dict[str, str],
    trade_date: date,
    cash: float,
    signal: Any,
    config: InverseEtfHedgeConfig,
    commission_rate: float,
    tax_rate_kospi: float,
    tax_rate_kosdaq: float,
    slippage_rate: float,
    trades: list[BacktestTrade],
    closed_trade_returns: list[float],
    closed_holding_days: list[int],
) -> float:
    holdings = [
        {
            "ticker": ticker,
            "qty": int(quantity),
            "avg_price": entry_prices.get(ticker, 0.0),
            "current_price": open_prices.get(ticker, close_prices.get(ticker, 0.0)),
        }
        for ticker, quantity in positions.items()
        if ticker in config.allowed_tickers and quantity > 0
    ]
    portfolio_value = cash + _positions_value(positions, close_prices)
    orders, _ = compute_inverse_etf_orders(
        holdings=holdings,
        prices=open_prices,
        cash=cash,
        portfolio_value=portfolio_value,
        signal=signal,
        entry_dates=entry_dates,
        as_of_date=trade_date,
        config=config,
    )
    for order in orders:
        if order.ticker not in open_prices:
            continue
        price = open_prices[order.ticker]
        if order.side == "SELL":
            if order.ticker not in positions or order.ticker not in entry_dates:
                continue
            quantity = min(float(order.qty), positions[order.ticker])
            if quantity <= 0:
                continue
            entry_value = entry_prices.get(order.ticker, 0.0) * quantity
            cash, trade, trade_return, holding_days = _sell_position(
                ticker=order.ticker,
                quantity=quantity,
                price=price,
                trade_date=trade_date,
                cash=cash,
                market=markets.get(order.ticker, "ETF"),
                entry_date=entry_dates[order.ticker],
                entry_value=entry_value,
                commission_rate=commission_rate,
                tax_rate_kospi=tax_rate_kospi,
                tax_rate_kosdaq=tax_rate_kosdaq,
                slippage_rate=slippage_rate,
                reason=order.reason,
            )
            trades.append(trade)
            closed_trade_returns.append(trade_return)
            closed_holding_days.append(holding_days)
            remaining_quantity = positions[order.ticker] - quantity
            if remaining_quantity <= 1e-9:
                positions.pop(order.ticker, None)
                entry_dates.pop(order.ticker, None)
                entry_values.pop(order.ticker, None)
                entry_prices.pop(order.ticker, None)
                peak_prices.pop(order.ticker, None)
                profit_taken.discard(order.ticker)
                trailing_bucket_qty.pop(order.ticker, None)
                breakeven_bucket_qty.pop(order.ticker, None)
            else:
                positions[order.ticker] = remaining_quantity
                entry_values[order.ticker] = max(
                    0.0,
                    entry_values.get(order.ticker, 0.0) - entry_value,
                )
        elif order.side == "BUY":
            quantity = float(order.qty)
            gross_amount = quantity * price
            cost = gross_amount * (commission_rate + slippage_rate)
            total_cash_needed = gross_amount + cost
            if quantity <= 0 or total_cash_needed > cash:
                continue
            cash -= total_cash_needed
            positions[order.ticker] = positions.get(order.ticker, 0.0) + quantity
            entry_dates[order.ticker] = trade_date
            entry_values[order.ticker] = entry_values.get(order.ticker, 0.0) + gross_amount + cost
            entry_prices[order.ticker] = entry_values[order.ticker] / positions[order.ticker]
            peak_prices[order.ticker] = price
            trades.append(
                BacktestTrade(
                    date=trade_date,
                    ticker=order.ticker,
                    side="BUY",
                    quantity=quantity,
                    price=price,
                    gross_amount=gross_amount,
                    cost=cost,
                    reason=order.reason,
                )
            )
    return cash


def _sell_position(
    *,
    ticker: str,
    quantity: float,
    price: float,
    trade_date: date,
    cash: float,
    market: str,
    entry_date: date,
    entry_value: float,
    commission_rate: float,
    tax_rate_kospi: float,
    tax_rate_kosdaq: float,
    slippage_rate: float,
    reason: str,
) -> tuple[float, BacktestTrade, float, int]:
    gross_amount = quantity * price
    tax_rate = 0.0 if market == "ETF" else tax_rate_kosdaq if _is_kosdaq_market(market) else tax_rate_kospi
    cost = gross_amount * (commission_rate + tax_rate + slippage_rate)
    cash += gross_amount - cost
    trade_return = ((gross_amount - cost) / entry_value) - 1.0 if entry_value > 0 else 0.0
    holding_days = (trade_date - entry_date).days
    return (
        cash,
        BacktestTrade(
            date=trade_date,
            ticker=ticker,
            side="SELL",
            quantity=quantity,
            price=price,
            gross_amount=gross_amount,
            cost=cost,
            reason=reason,
        ),
        trade_return,
        holding_days,
    )


def _equity_returns(equity_values: list[float]) -> list[float]:
    returns = []
    for previous, current in zip(equity_values, equity_values[1:]):
        if previous > 0:
            returns.append((current / previous) - 1.0)
    return returns


def _is_kosdaq_market(market: str) -> bool:
    return market in {"KOSDAQ", "KOSDAQ150"}


def _rebalance_key(value: date, frequency: str) -> tuple[int, ...]:
    if frequency == "daily":
        return (value.year, value.month, value.day)
    if frequency == "weekly":
        iso_year, iso_week, _ = value.isocalendar()
        return (iso_year, iso_week)
    if frequency == "monthly":
        return (value.year, value.month)
    raise ValueError("rebalance_frequency must be one of: daily, weekly, monthly")


def _market_risk_cash_target(
    index_prices: dict[str, list[dict[str, Any]]],
    *,
    as_of_date: date,
    rsi_window: int,
    rsi_threshold: float,
    one_market_overheat_cash_target: float,
    both_markets_overheat_cash_target: float,
    nasdaq_moderate_drop_pct: float,
    nasdaq_severe_drop_pct: float,
    nasdaq_moderate_cash_target: float,
    nasdaq_severe_cash_target: float,
) -> float:
    cash_target = 0.0
    overheated = 0
    for symbol in ("KOSPI", "KOSDAQ"):
        closes = _index_closes_until(index_prices.get(symbol, []), as_of_date)
        rsi = _rsi_from_closes(closes, rsi_window)
        if rsi is not None and rsi >= rsi_threshold:
            overheated += 1
    if overheated == 1:
        cash_target = max(cash_target, one_market_overheat_cash_target)
    elif overheated >= 2:
        cash_target = max(cash_target, both_markets_overheat_cash_target)

    nasdaq_closes = _index_closes_until(index_prices.get("NASDAQ", []), as_of_date)
    if len(nasdaq_closes) >= 2 and nasdaq_closes[-2] > 0:
        nasdaq_return = (nasdaq_closes[-1] / nasdaq_closes[-2]) - 1.0
        if nasdaq_return <= nasdaq_severe_drop_pct:
            cash_target = max(cash_target, nasdaq_severe_cash_target)
        elif nasdaq_return <= nasdaq_moderate_drop_pct:
            cash_target = max(cash_target, nasdaq_moderate_cash_target)
    return min(max(cash_target, 0.0), 1.0)


def _volatility_cash_target(
    index_prices: dict[str, list[dict[str, Any]]],
    *,
    as_of_date: date,
    window: int,
    moderate_annualized: float,
    severe_annualized: float,
    moderate_cash_target: float,
    severe_cash_target: float,
) -> float:
    if window <= 1:
        return 0.0
    cash_target = 0.0
    for symbol in ("KOSPI", "KOSDAQ"):
        closes = _index_closes_until(index_prices.get(symbol, []), as_of_date)
        if len(closes) <= window:
            continue
        recent = closes[-window - 1 :]
        returns = [
            (current / previous) - 1.0
            for previous, current in zip(recent, recent[1:])
            if previous > 0
        ]
        if len(returns) < window:
            continue
        mean_return = sum(returns) / len(returns)
        variance = sum((value - mean_return) ** 2 for value in returns) / len(returns)
        annualized_volatility = math.sqrt(variance) * math.sqrt(252)
        if annualized_volatility >= severe_annualized:
            cash_target = max(cash_target, severe_cash_target)
        elif annualized_volatility >= moderate_annualized:
            cash_target = max(cash_target, moderate_cash_target)
    return min(max(cash_target, 0.0), 1.0)


def _flow_breadth_cash_target(
    investor_flows_by_date: dict[date, list[dict[str, float | str]]],
    *,
    as_of_date: date,
    window: int,
    moderate_threshold: float,
    severe_threshold: float,
    moderate_cash_target: float,
    severe_cash_target: float,
) -> float:
    if window <= 0:
        return 0.0
    flow_dates = [flow_date for flow_date in sorted(investor_flows_by_date) if flow_date <= as_of_date]
    if not flow_dates:
        return 0.0
    selected_dates = flow_dates[-window:]
    by_ticker: dict[str, float] = defaultdict(float)
    for flow_date in selected_dates:
        for row in investor_flows_by_date.get(flow_date, []):
            ticker = str(row["ticker"])
            by_ticker[ticker] += float(row["foreign"]) + float(row["institution"])
    if not by_ticker:
        return 0.0
    positive_ratio = sum(1 for value in by_ticker.values() if value > 0) / len(by_ticker)
    if positive_ratio <= severe_threshold:
        return min(max(severe_cash_target, 0.0), 1.0)
    if positive_ratio <= moderate_threshold:
        return min(max(moderate_cash_target, 0.0), 1.0)
    return 0.0


def _price_breadth_cash_target(
    price_breadth_closes: dict[str, tuple[list[date], list[float]]],
    *,
    as_of_date: date,
    ma_days: int,
    min_count: int,
    moderate_threshold: float,
    severe_threshold: float,
    moderate_cash_target: float,
    severe_cash_target: float,
) -> float:
    if ma_days <= 1 or min_count <= 0:
        return 0.0
    eligible_count = 0
    above_ma_count = 0
    for dates, closes in price_breadth_closes.values():
        idx = bisect.bisect_right(dates, as_of_date)
        if idx < ma_days:
            continue
        recent = closes[idx - ma_days : idx]
        if len(recent) < ma_days:
            continue
        moving_average = sum(recent) / ma_days
        current_close = closes[idx - 1]
        eligible_count += 1
        if current_close >= moving_average:
            above_ma_count += 1
    if eligible_count < min_count:
        return 0.0

    participation_ratio = above_ma_count / eligible_count
    if participation_ratio <= severe_threshold:
        return min(max(severe_cash_target, 0.0), 1.0)
    if participation_ratio <= moderate_threshold:
        return min(max(moderate_cash_target, 0.0), 1.0)
    return 0.0


def _crash_guard_cash_target(
    index_prices: dict[str, list[dict[str, Any]]],
    *,
    as_of_date: date,
    moderate_5d_drop_pct: float,
    severe_5d_drop_pct: float,
    moderate_20d_drop_pct: float,
    severe_20d_drop_pct: float,
    moderate_cash_target: float,
    severe_cash_target: float,
    enable_reentry: bool = False,
    reentry_cash_target: float = 0.15,
    reentry_ma_days: int = 20,
    reentry_rsi_window: int = 14,
    reentry_rsi_threshold: float = 45.0,
    reentry_positive_days: int = 3,
) -> float:
    cash_target = 0.0
    reentry_confirmed = False
    for symbol in ("KOSPI", "KOSDAQ"):
        rows = [
            row
            for row in index_prices.get(symbol, [])
            if row["date"] <= as_of_date and row["close"] > 0
        ]
        if not rows:
            continue
        rows.sort(key=lambda row: row["date"])
        closes = [float(row["close"]) for row in rows]
        current = closes[-1]
        severe = False
        moderate = False
        if len(closes) >= 6:
            return_5d = (current / closes[-6]) - 1.0
            severe = severe or return_5d <= severe_5d_drop_pct
            moderate = moderate or return_5d <= moderate_5d_drop_pct
        if len(closes) >= 21:
            return_20d = (current / closes[-21]) - 1.0
            severe = severe or return_20d <= severe_20d_drop_pct
            moderate = moderate or return_20d <= moderate_20d_drop_pct
        if len(closes) >= 120:
            ma20 = sum(closes[-20:]) / 20
            ma60 = sum(closes[-60:]) / 60
            ma120 = sum(closes[-120:]) / 120
            severe = severe or (current < ma120 and ma20 < ma60)
            moderate = moderate or (current < ma60 and ma20 < ma60)
        reentry_confirmed = reentry_confirmed or _crash_guard_reentry_confirmed(
            closes,
            ma_days=reentry_ma_days,
            rsi_window=reentry_rsi_window,
            rsi_threshold=reentry_rsi_threshold,
            positive_days=reentry_positive_days,
        )
        if severe:
            cash_target = max(cash_target, severe_cash_target)
        elif moderate:
            cash_target = max(cash_target, moderate_cash_target)
    if enable_reentry and cash_target > 0 and reentry_confirmed:
        cash_target = min(cash_target, reentry_cash_target)
    return min(max(cash_target, 0.0), 1.0)


def _crash_guard_reentry_confirmed(
    closes: list[float],
    *,
    ma_days: int,
    rsi_window: int,
    rsi_threshold: float,
    positive_days: int,
) -> bool:
    required = max(ma_days, rsi_window + 1, positive_days + 1)
    if required <= 0 or len(closes) < required:
        return False
    recent = closes[-positive_days - 1 :]
    if any(current <= previous for previous, current in zip(recent, recent[1:])):
        return False
    moving_average = sum(closes[-ma_days:]) / ma_days
    if closes[-1] < moving_average:
        return False
    rsi = _rsi_from_closes(closes, rsi_window)
    return rsi is not None and rsi >= rsi_threshold


def _dynamic_target_count(
    *,
    base_target_count: int,
    risk_cash_target: float,
    enable_dynamic_top_n: bool,
    moderate_cash_target: float,
    severe_cash_target: float,
    defensive_top_n: int | None,
    severe_defensive_top_n: int | None,
) -> int:
    if not enable_dynamic_top_n or risk_cash_target <= 0:
        return base_target_count
    if severe_defensive_top_n is not None and risk_cash_target >= severe_cash_target:
        return max(1, min(base_target_count, severe_defensive_top_n))
    if defensive_top_n is not None and risk_cash_target >= moderate_cash_target:
        return max(1, min(base_target_count, defensive_top_n))
    return base_target_count


def _index_closes_until(rows: list[dict[str, Any]], as_of_date: date) -> list[float]:
    return [float(row["close"]) for row in rows if row["date"] <= as_of_date and row["close"] > 0]


def _domestic_index_closes_until(
    index_prices: dict[str, list[dict[str, Any]]],
    as_of_date: date,
) -> dict[str, list[float]]:
    return {
        symbol: _index_closes_until(index_prices.get(symbol, []), as_of_date)
        for symbol in ("KOSPI", "KOSDAQ")
    }


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


def _build_atr_cache(
    prices: dict[tuple[str, date], dict[str, float]],
    *,
    window: int,
) -> dict[tuple[str, date], float]:
    grouped: dict[str, list[tuple[date, dict[str, float]]]] = defaultdict(list)
    for (ticker, price_date), price in prices.items():
        grouped[ticker].append((price_date, price))

    cache: dict[tuple[str, date], float] = {}
    for ticker, rows in grouped.items():
        rows.sort(key=lambda item: item[0])
        true_ranges: list[float] = []
        for (_, previous), (current_date, current) in zip(rows, rows[1:]):
            previous_close = previous["close"]
            true_ranges.append(
                max(
                    current["high"] - current["low"],
                    abs(current["high"] - previous_close),
                    abs(current["low"] - previous_close),
                )
            )
            if len(true_ranges) >= window:
                cache[(ticker, current_date)] = sum(true_ranges[-window:]) / window
    return cache


def _average_true_range(
    prices: dict[tuple[str, date], dict[str, float]],
    *,
    ticker: str,
    as_of_date: date,
    window: int,
) -> float | None:
    rows = [
        (price_date, price)
        for (price_ticker, price_date), price in prices.items()
        if price_ticker == ticker and price_date <= as_of_date
    ]
    rows.sort(key=lambda item: item[0])
    if len(rows) <= window:
        return None
    true_ranges: list[float] = []
    for (_, previous), (_, current) in zip(rows[-window - 1 :], rows[-window:]):
        previous_close = previous["close"]
        true_ranges.append(
            max(
                current["high"] - current["low"],
                abs(current["high"] - previous_close),
                abs(current["low"] - previous_close),
            )
        )
    if len(true_ranges) < window:
        return None
    return sum(true_ranges) / window


def _make_fast_score_func(
    engine: Engine,
    *,
    lookback_days: int,
    start_date: date,
    end_date: date,
) -> ScoreFunction:
    """모든 시세·펀더멘털을 한 번에 로드하고 날짜별로 메모리 내 bisect로 스코어를 계산한다.

    백테스트 루프에서 날짜마다 DB를 재쿼리하는 N+1 문제를 해소하기 위해 사용한다.
    모멘텀 룩백에 필요한 사전 데이터를 포함하도록 price_start를 앞당겨 로드한다.
    """
    from datetime import timedelta

    # 룩백 기간 + 비영업일 여유분(×2)만큼 앞당겨 로드
    price_start = start_date - timedelta(days=lookback_days * 2)

    price_dates: dict[str, list[date]] = defaultdict(list)
    price_closes: dict[str, list[float]] = defaultdict(list)
    fund_dates: dict[str, list[date]] = defaultdict(list)
    fund_data: dict[str, list[tuple[Any, ...]]] = defaultdict(list)
    quality_data: dict[str, list[QualityMetric]] = defaultdict(list)

    with session_scope(engine) as session:
        stock_info: dict[str, tuple[str, str]] = {
            s.ticker: (s.name, s.market)
            for s in session.scalars(select(Stock).where(Stock.is_active.is_(True))).all()
        }
        for row in session.scalars(
            select(DailyPrice).where(
                DailyPrice.date >= price_start, DailyPrice.date <= end_date
            )
        ).all():
            if row.close is not None:
                price_dates[row.ticker].append(row.date)
                price_closes[row.ticker].append(float(row.close))
        for row in session.scalars(
            select(Fundamental).where(Fundamental.date <= end_date)
        ).all():
            fund_dates[row.ticker].append(row.date)
            fund_data[row.ticker].append((row.per, row.pbr, row.eps, row.bps, row.div))
        for row in session.scalars(
            select(QualityMetric).order_by(
                QualityMetric.fiscal_year.desc(),
                QualityMetric.fiscal_quarter.desc(),
            )
        ).all():
            quality_data[row.ticker].append(row)

    # 날짜 오름차순 정렬 (bisect_right 사용 전제)
    for ticker in price_dates:
        pairs = sorted(zip(price_dates[ticker], price_closes[ticker]))
        price_dates[ticker] = [p[0] for p in pairs]
        price_closes[ticker] = [p[1] for p in pairs]
    for ticker in fund_dates:
        pairs = sorted(zip(fund_dates[ticker], fund_data[ticker]))
        fund_dates[ticker] = [p[0] for p in pairs]
        fund_data[ticker] = [p[1] for p in pairs]

    def _scorer(_engine: Any, *, as_of_date: date, lookback_days: int = lookback_days) -> list[FactorScore]:
        rows = []
        for ticker, (name, market) in stock_info.items():
            p_dates = price_dates.get(ticker, [])
            p_closes = price_closes.get(ticker, [])
            idx = bisect.bisect_right(p_dates, as_of_date)
            if idx <= lookback_days:
                continue
            current_close = p_closes[idx - 1]
            lookback_close = p_closes[idx - lookback_days - 1]
            if not current_close or not lookback_close:
                continue

            f_dates = fund_dates.get(ticker, [])
            fidx = bisect.bisect_right(f_dates, as_of_date)
            if fidx == 0:
                continue
            per, pbr, eps, bps, div = fund_data[ticker][fidx - 1]
            quality = _latest_available_quality_metric(
                quality_data.get(ticker, []),
                as_of_date=as_of_date,
            )
            recent_operating_margins = _recent_available_operating_margins(
                quality_data.get(ticker, []),
                as_of_date=as_of_date,
            )

            rows.append({
                "ticker": ticker,
                "name": name,
                "market": market,
                "per": per,
                "pbr": pbr,
                "eps": eps,
                "bps": bps,
                "div": div,
                "roe": quality.roe if quality is not None else None,
                "operating_margin": quality.operating_margin if quality is not None else None,
                "debt_ratio": quality.debt_ratio if quality is not None else None,
                "recent_operating_margins": recent_operating_margins,
                "recent_closes": p_closes[max(0, idx - 100):idx],
                "momentum_return": (current_close / lookback_close) - 1.0,
            })
        if not rows:
            return []
        return calculate_factor_scores_from_df(pd.DataFrame(rows), as_of_date=as_of_date)

    return _scorer
