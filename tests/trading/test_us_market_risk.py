from datetime import date

from src.trading.us_market_risk import calculate_us_market_buy_adjustment


def test_us_market_risk_reduces_buy_budget_after_broad_drop():
    adjustment = calculate_us_market_buy_adjustment(
        {
            "NASDAQ": [(date(2026, 5, 6), 100.0), (date(2026, 5, 7), 97.0)],
            "SP500": [(date(2026, 5, 6), 100.0), (date(2026, 5, 7), 98.4)],
            "DOW": [(date(2026, 5, 6), 100.0), (date(2026, 5, 7), 99.0)],
        },
        as_of_date=date(2026, 5, 8),
    )

    assert adjustment.buy_budget_multiplier == 0.60
    assert adjustment.cash_target == 0.40
    assert "NASDAQ:-3.00%" in adjustment.reasons
    assert adjustment.status == "risk_off"


def test_us_market_risk_increases_buy_budget_after_broad_rally():
    adjustment = calculate_us_market_buy_adjustment(
        {
            "NASDAQ": [(date(2026, 5, 6), 100.0), (date(2026, 5, 7), 102.1)],
            "SP500": [(date(2026, 5, 6), 100.0), (date(2026, 5, 7), 101.6)],
            "DOW": [(date(2026, 5, 6), 100.0), (date(2026, 5, 7), 101.0)],
        },
        as_of_date=date(2026, 5, 8),
    )

    assert adjustment.buy_budget_multiplier == 1.20
    assert adjustment.cash_target == 0.0
    assert adjustment.status == "risk_on"


def test_us_market_risk_marks_missing_when_index_history_is_unavailable():
    adjustment = calculate_us_market_buy_adjustment({}, as_of_date=date(2026, 5, 8))

    assert adjustment.buy_budget_multiplier == 1.0
    assert adjustment.cash_target == 0.0
    assert adjustment.status == "missing"
