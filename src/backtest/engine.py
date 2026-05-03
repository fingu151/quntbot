from __future__ import annotations

from collections.abc import Callable
from datetime import date

from sqlalchemy import Engine, select

from config import COST, PORTFOLIO
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
from src.data.models import DailyPrice, Stock
from src.factors.engine import calculate_factor_scores
from src.factors.models import FactorScore


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
) -> BacktestResult:
    capital = float(initial_capital or PORTFOLIO.initial_capital)
    target_count = int(top_n or PORTFOLIO.n_holdings)
    prices = _load_close_prices(engine, start_date=start_date, end_date=end_date)
    markets = _load_markets(engine)
    trading_dates = sorted({key[1] for key in prices})

    cash = capital
    positions: dict[str, float] = {}
    entry_dates: dict[str, date] = {}
    entry_values: dict[str, float] = {}
    trades: list[BacktestTrade] = []
    closed_trade_returns: list[float] = []
    closed_holding_days: list[int] = []
    equity_curve: list[EquityPoint] = []

    for trading_date in trading_dates:
        available_prices = {ticker: price for (ticker, price_date), price in prices.items() if price_date == trading_date}
        if not available_prices:
            continue

        scores = scoring_func(engine, as_of_date=trading_date)
        target_tickers = [score.ticker for score in scores if score.ticker in available_prices][:target_count]

        for ticker in list(positions):
            if ticker not in target_tickers and ticker in available_prices:
                cash, trade, trade_return, holding_days = _sell_position(
                    ticker=ticker,
                    quantity=positions.pop(ticker),
                    price=available_prices[ticker],
                    trade_date=trading_date,
                    cash=cash,
                    market=markets.get(ticker, ""),
                    entry_date=entry_dates.pop(ticker),
                    entry_value=entry_values.pop(ticker),
                    commission_rate=commission_rate,
                    tax_rate_kospi=tax_rate_kospi,
                    tax_rate_kosdaq=tax_rate_kosdaq,
                    slippage_rate=slippage_rate,
                    reason="rebalance",
                )
                trades.append(trade)
                closed_trade_returns.append(trade_return)
                closed_holding_days.append(holding_days)

        equity_before_buys = cash + _positions_value(positions, available_prices)
        target_value = equity_before_buys / len(target_tickers) if target_tickers else 0.0
        for ticker in target_tickers:
            if ticker in positions:
                continue
            price = available_prices[ticker]
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

        positions_value = _positions_value(positions, available_prices)
        equity_curve.append(
            EquityPoint(
                date=trading_date,
                equity=round(cash + positions_value, 10),
                cash=round(cash, 10),
                positions_value=round(positions_value, 10),
            )
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


def _load_markets(engine: Engine) -> dict[str, str]:
    with session_scope(engine) as session:
        rows = session.scalars(select(Stock)).all()
    return {row.ticker: row.market for row in rows}


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
    tax_rate = tax_rate_kosdaq if market == "KOSDAQ150" else tax_rate_kospi
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
