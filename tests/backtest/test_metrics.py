from datetime import date

import pytest

from src.backtest.metrics import (
    average_holding_days,
    calculate_cagr,
    calculate_max_drawdown,
    calculate_sharpe_ratio,
    calculate_total_return,
    calculate_win_rate,
)


def test_calculate_total_return():
    assert calculate_total_return(initial_equity=100.0, final_equity=125.0) == 0.25


def test_calculate_cagr_for_one_year():
    assert calculate_cagr(
        initial_equity=100.0,
        final_equity=121.0,
        start_date=date(2025, 1, 1),
        end_date=date(2026, 1, 1),
    ) == pytest.approx(0.21, abs=0.001)


def test_calculate_max_drawdown():
    equity = [100.0, 120.0, 90.0, 110.0]

    assert calculate_max_drawdown(equity) == pytest.approx(-0.25)


def test_calculate_sharpe_ratio_positive_returns():
    returns = [0.01, 0.02, -0.005, 0.015]

    assert calculate_sharpe_ratio(returns) > 0


def test_calculate_win_rate():
    assert calculate_win_rate([10.0, -3.0, 0.0, 2.0]) == pytest.approx(0.5)


def test_average_holding_days():
    holding_days = [3, 7, 10]

    assert average_holding_days(holding_days) == pytest.approx(20 / 3)
