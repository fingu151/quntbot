from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from math import sqrt
from statistics import mean, pstdev


TRADING_DAYS_PER_YEAR = 252


def calculate_total_return(*, initial_equity: float, final_equity: float) -> float:
    if initial_equity <= 0:
        raise ValueError("initial_equity must be positive")
    return (final_equity / initial_equity) - 1.0


def calculate_cagr(*, initial_equity: float, final_equity: float, start_date: date, end_date: date) -> float:
    if initial_equity <= 0:
        raise ValueError("initial_equity must be positive")
    days = (end_date - start_date).days
    if days <= 0:
        return 0.0
    years = days / 365.0
    return (final_equity / initial_equity) ** (1 / years) - 1.0


def calculate_max_drawdown(equity_values: Sequence[float]) -> float:
    if not equity_values:
        return 0.0
    peak = equity_values[0]
    max_drawdown = 0.0
    for equity in equity_values:
        peak = max(peak, equity)
        if peak > 0:
            drawdown = (equity / peak) - 1.0
            max_drawdown = min(max_drawdown, drawdown)
    return max_drawdown


def calculate_sharpe_ratio(daily_returns: Sequence[float]) -> float:
    if len(daily_returns) < 2:
        return 0.0
    volatility = pstdev(daily_returns)
    if volatility == 0:
        return 0.0
    return (mean(daily_returns) / volatility) * sqrt(TRADING_DAYS_PER_YEAR)


def calculate_win_rate(trade_returns: Sequence[float]) -> float:
    if not trade_returns:
        return 0.0
    wins = sum(1 for value in trade_returns if value > 0)
    return wins / len(trade_returns)


def average_holding_days(holding_days: Sequence[int]) -> float:
    if not holding_days:
        return 0.0
    return mean(holding_days)
