from datetime import date

from src.trading.bond_yield_risk import calculate_bond_yield_adjustment


def test_bond_yield_risk_reduces_buy_budget_after_yields_rise():
    adjustment = calculate_bond_yield_adjustment(
        {
            "KR10Y": [(date(2026, 5, 6), 3.40), (date(2026, 5, 7), 3.57)],
            "US10Y": [(date(2026, 5, 6), 4.30), (date(2026, 5, 7), 4.47)],
        },
        as_of_date=date(2026, 5, 8),
    )

    assert adjustment.status == "risk_off"
    assert adjustment.buy_budget_multiplier == 0.70
    assert adjustment.cash_target == 0.30
    assert adjustment.changes_bp == {"KR10Y": 17.0, "US10Y": 17.0}
    assert "KR10Y:+17bp" in adjustment.reasons


def test_bond_yield_risk_increases_buy_budget_after_yields_fall():
    adjustment = calculate_bond_yield_adjustment(
        {
            "KR10Y": [(date(2026, 5, 6), 3.40), (date(2026, 5, 7), 3.08)],
            "US10Y": [(date(2026, 5, 6), 4.30), (date(2026, 5, 7), 4.12)],
        },
        as_of_date=date(2026, 5, 8),
    )

    assert adjustment.status == "risk_on"
    assert adjustment.buy_budget_multiplier == 1.20
    assert adjustment.cash_target == 0.0
    assert adjustment.changes_bp == {"KR10Y": -32.0, "US10Y": -18.0}


def test_bond_yield_risk_marks_missing_when_yield_history_is_unavailable():
    adjustment = calculate_bond_yield_adjustment({}, as_of_date=date(2026, 5, 8))

    assert adjustment.status == "missing"
    assert adjustment.buy_budget_multiplier == 1.0
    assert adjustment.cash_target == 0.0
    assert adjustment.reasons == ["bond_yield_history_missing"]
