from __future__ import annotations

import bisect
from collections import defaultdict
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

import pandas as pd
from sqlalchemy import Engine, select

from config import COST, EXIT_RULES, FACTOR, PORTFOLIO, REBALANCE
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
from src.data.models import DailyPrice, Fundamental, QualityMetric, Stock
from src.factors.engine import (
    _latest_available_quality_metric,
    _recent_available_operating_margins,
    calculate_factor_scores,
    calculate_factor_scores_from_df,
)
from src.factors.models import FactorScore
from src.trading.allocation import compute_score_weights
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
    rebalance_frequency: str = REBALANCE.frequency,
    profit_take_pct: float = EXIT_RULES.profit_take_pct,
    profit_take_sell_fraction: float = EXIT_RULES.profit_take_sell_fraction,
    breakeven_stop_pct: float = EXIT_RULES.breakeven_stop_pct,
    sell_rank_buffer: int = REBALANCE.sell_rank_buffer,
    min_holding_trading_days: int = REBALANCE.min_holding_trading_days,
    weighting: str = PORTFOLIO.weighting,
    min_position_weight: float = PORTFOLIO.min_position_weight,
    max_position_weight: float = PORTFOLIO.max_position_weight,
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
    prices_by_date = _group_prices_by_date(prices)
    markets = _load_markets(engine)
    trading_dates = sorted(prices_by_date)

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
    trading_day_index_by_date = {value: idx for idx, value in enumerate(trading_dates)}

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
        if should_rebalance and previous_trading_date is not None:
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
            target_scores = ranked_scores[:target_count]
            target_tickers = ranked_tickers[:target_count]
            keep_tickers = set(ranked_tickers[:max(target_count, sell_rank_buffer)])
            if target_tickers:
                last_rebalance_key = rebalance_key

        for ticker in list(positions):
            entry_date = entry_dates.get(ticker)
            held_trading_days = 0
            if entry_date is not None:
                held_trading_days = max(
                    0,
                    trading_day_index_by_date[trading_date] - trading_day_index_by_date[entry_date] - 1,
                )
            if (
                ticker not in keep_tickers
                and ticker not in forbidden_today
                and held_trading_days >= min_holding_trading_days
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

        equity_before_buys = cash + _positions_value(positions, close_prices)
        target_weights: dict[str, float] = {}
        if weighting == "score_weighted" and target_scores:
            target_weights = compute_score_weights(
                [(score.ticker, score.total_score) for score in target_scores],
                min_weight=min_position_weight,
                max_weight=max_position_weight,
            )
        equal_target_value = equity_before_buys / len(target_tickers) if target_tickers else 0.0
        for ticker in target_tickers:
            if ticker in positions:
                continue
            price = open_prices[ticker]
            if target_weights:
                target_value = equity_before_buys * target_weights.get(ticker, 0.0)
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
                    if return_from_entry <= stop_loss_pct:
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
                    if trail_qty > 0 and loss_from_peak <= trailing_stop_pct:
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
        (row.ticker, row.date): {"open": float(row.open), "close": float(row.close)}
        for row in rows
        if row.open is not None and row.close is not None
    }


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
    tax_rate = tax_rate_kosdaq if _is_kosdaq_market(market) else tax_rate_kospi
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
