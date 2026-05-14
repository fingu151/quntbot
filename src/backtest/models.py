from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class BacktestTrade:
    date: date
    ticker: str
    side: str
    quantity: float
    price: float
    gross_amount: float
    cost: float
    reason: str


@dataclass(frozen=True)
class EquityPoint:
    date: date
    equity: float
    cash: float
    positions_value: float


@dataclass(frozen=True)
class BacktestResult:
    initial_capital: float
    final_equity: float
    total_return: float
    cagr: float
    max_drawdown: float
    sharpe_ratio: float
    win_rate: float
    average_holding_days: float
    trades: list[BacktestTrade]
    equity_curve: list[EquityPoint]
