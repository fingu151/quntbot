from datetime import date

from src.trading.bond_yield_risk import BondYieldAdjustment
from src.trading.macro_risk import calculate_macro_exposure_adjustment
from src.trading.us_market_risk import UsMarketBuyAdjustment


def test_macro_overlay_combines_bond_yield_and_us_market_risk_off():
    adjustment = calculate_macro_exposure_adjustment(
        as_of_date=date(2026, 5, 8),
        us_market=UsMarketBuyAdjustment(
            status="risk_off",
            buy_budget_multiplier=0.60,
            cash_target=0.40,
            reasons=["NASDAQ:-3.00%"],
            returns={"NASDAQ": -0.03},
        ),
        bond_yield=BondYieldAdjustment(
            status="risk_off",
            buy_budget_multiplier=0.70,
            cash_target=0.30,
            reasons=["US10Y:+30bp"],
            changes_bp={"US10Y": 30.0},
        ),
        indicator_releases=[],
    )

    assert adjustment.status == "risk_off"
    assert adjustment.cash_target == 0.40
    assert adjustment.buy_budget_multiplier == 0.50
    assert "NASDAQ:-3.00%" in adjustment.signals
    assert "US10Y:+30bp" in adjustment.signals


def test_macro_overlay_marks_inflation_and_labor_releases_as_risk_off():
    adjustment = calculate_macro_exposure_adjustment(
        as_of_date=date(2026, 5, 8),
        us_market=UsMarketBuyAdjustment("neutral", 1.0, 0.0, [], {}),
        bond_yield=BondYieldAdjustment("neutral", 1.0, 0.0, [], {}),
        indicator_releases=[
            {
                # CPIAUCSL is an index level: 314.0 -> 315.6 = +0.51% m/m (hot).
                "indicator": "CPI",
                "release_date": date(2026, 5, 7),
                "value": 315.6,
                "previous_value": 314.0,
                "impact_rule": "inflation",
            },
            {
                "indicator": "UNRATE",
                "release_date": date(2026, 5, 7),
                "value": 4.5,
                "previous_value": 4.1,
                "impact_rule": "labor",
            },
        ],
    )

    assert adjustment.status == "risk_off"
    assert adjustment.cash_target >= 0.20
    assert adjustment.buy_budget_multiplier < 1.0
    assert "CPI:+0.51% inflation" in adjustment.signals
    assert "UNRATE:+0.40 labor" in adjustment.signals


def test_macro_overlay_ignores_normal_cpi_index_growth():
    """평범한 CPI 지수 증가(+0.2% m/m)는 risk_off 신호가 아니다."""
    adjustment = calculate_macro_exposure_adjustment(
        as_of_date=date(2026, 5, 8),
        us_market=UsMarketBuyAdjustment("neutral", 1.0, 0.0, [], {}),
        bond_yield=BondYieldAdjustment("neutral", 1.0, 0.0, [], {}),
        indicator_releases=[
            {
                # 314.0 -> 314.63 = +0.20% m/m: 지수 포인트 delta(+0.63)는 크지만 정상 범위.
                "indicator": "CPI",
                "release_date": date(2026, 5, 7),
                "value": 314.63,
                "previous_value": 314.0,
                "impact_rule": "inflation",
            },
        ],
    )

    assert adjustment.status == "neutral"  # 데이터가 멀쩡한 평온한 날은 missing이 아니다
    assert adjustment.buy_budget_multiplier == 1.0
    assert adjustment.cash_target == 0.0
    assert not any("inflation" in signal for signal in adjustment.signals)


def test_macro_overlay_marks_payems_job_losses_in_thousands_as_risk_off():
    """PAYEMS는 천 명 단위이므로 -150은 15만 명 감소다."""
    adjustment = calculate_macro_exposure_adjustment(
        as_of_date=date(2026, 5, 8),
        us_market=UsMarketBuyAdjustment("neutral", 1.0, 0.0, [], {}),
        bond_yield=BondYieldAdjustment("neutral", 1.0, 0.0, [], {}),
        indicator_releases=[
            {
                "indicator": "PAYEMS",
                "release_date": date(2026, 5, 7),
                "value": 157_850.0,
                "previous_value": 158_000.0,
                "impact_rule": "labor",
            },
        ],
    )

    assert adjustment.status == "risk_off"
    assert adjustment.buy_budget_multiplier < 1.0
    assert "PAYEMS:-150k labor" in adjustment.signals


def test_macro_overlay_keeps_missing_sources_as_report_reasons_not_blockers():
    adjustment = calculate_macro_exposure_adjustment(
        as_of_date=date(2026, 5, 8),
        us_market=UsMarketBuyAdjustment("missing", 1.0, 0.0, ["us_index_history_missing"], {}),
        bond_yield=BondYieldAdjustment("missing", 1.0, 0.0, ["bond_yield_history_missing"], {}),
        indicator_releases=[],
    )

    assert adjustment.status == "missing"
    assert adjustment.cash_target == 0.0
    assert adjustment.buy_budget_multiplier == 1.0
    assert adjustment.missing_sources == [
        "us_index_history_missing",
        "bond_yield_history_missing",
        "macro_indicator_history_missing",
    ]
