from datetime import date, timedelta

from config import InverseEtfHedgeConfig
from src.trading.bond_yield_risk import BondYieldAdjustment
from src.trading.inverse_etf_hedge import (
    calculate_inverse_etf_signal,
    compute_inverse_etf_orders,
)
from src.trading.macro_risk import MacroExposureAdjustment
from src.trading.us_market_risk import UsMarketBuyAdjustment


def _macro(
    *,
    status: str = "neutral",
    cash_target: float = 0.0,
    returns: dict[str, float] | None = None,
) -> MacroExposureAdjustment:
    return MacroExposureAdjustment(
        status=status,
        buy_budget_multiplier=0.7 if status == "risk_off" else 1.0,
        cash_target=cash_target,
        signals=[],
        missing_sources=[],
        us_market=UsMarketBuyAdjustment(
            status=status,
            buy_budget_multiplier=0.7 if status == "risk_off" else 1.0,
            cash_target=cash_target,
            reasons=[],
            returns=returns or {},
        ),
        bond_yield=BondYieldAdjustment(
            status="neutral",
            buy_budget_multiplier=1.0,
            cash_target=0.0,
            reasons=[],
            changes_bp={},
        ),
        indicator_signals=[],
    )


def _config() -> InverseEtfHedgeConfig:
    # enabled를 명시해 실행자의 .env(INVERSE_ETF_HEDGE_ENABLED)에 의존하지 않게 한다.
    return InverseEtfHedgeConfig(
        enabled=True,
        allowed_tickers=("INV1", "INV2"),
        leveraged_tickers=("INV2",),
    )


def test_conservative_mode_does_not_enter_on_macro_risk_off_alone():
    config = InverseEtfHedgeConfig(
        enabled=True,
        allowed_tickers=("INV1", "INV2"),
        leveraged_tickers=("INV2",),
        require_market_confirmation=True,
    )

    signal = calculate_inverse_etf_signal(
        as_of_date=date(2026, 5, 8),
        macro_adjustment=_macro(status="risk_off", cash_target=0.40),
        domestic_index_closes={},
        config=config,
    )

    assert signal.status == "hedge_off"
    assert signal.evidence == []


def test_market_drop_creates_1x_inverse_etf_target():
    signal = calculate_inverse_etf_signal(
        as_of_date=date(2026, 5, 8),
        macro_adjustment=_macro(returns={"NASDAQ": -0.031, "SP500": -0.01}),
        domestic_index_closes={},
        config=_config(),
    )

    assert signal.status == "hedge_on"
    assert signal.target_weight == 0.05
    assert signal.selected_tickers == ["INV1"]
    assert any(item["reason"] == "inverse_etf_hedge_market_drop" for item in signal.evidence)


def test_severe_drop_adds_capped_2x_inverse_etf_target():
    signal = calculate_inverse_etf_signal(
        as_of_date=date(2026, 5, 8),
        macro_adjustment=_macro(status="risk_off", cash_target=0.40, returns={"NASDAQ": -0.052}),
        domestic_index_closes={},
        config=_config(),
    )

    assert signal.status == "hedge_on"
    assert signal.target_weight == 0.10
    assert signal.selected_tickers == ["INV1", "INV2"]
    assert signal.target_weights == {"INV1": 0.07, "INV2": 0.03}
    assert signal.leverage_type == "mixed"


def test_overbought_domestic_index_creates_2x_signal_when_severe():
    # 강한 랠리 후 고점에서 꺾인 시계열: RSI14는 여전히 과매수, 종가는 5일선 아래.
    closes = [100.0 + idx for idx in range(18)] + [116.5, 115.5]
    signal = calculate_inverse_etf_signal(
        as_of_date=date(2026, 5, 8),
        macro_adjustment=_macro(),
        domestic_index_closes={"KOSPI": closes},
        config=_config(),
    )

    assert signal.status == "hedge_on"
    assert "INV2" in signal.selected_tickers
    assert any(item["reason"] == "inverse_etf_hedge_overbought" for item in signal.evidence)


def test_overbought_alone_does_not_trigger_while_uptrend_intact():
    """상승 추세 한복판(종가 > 5일선)에서는 RSI 과매수만으로 인버스에 진입하지 않는다."""
    closes = [100.0 + idx for idx in range(20)]  # 강한 연속 상승: RSI=100
    signal = calculate_inverse_etf_signal(
        as_of_date=date(2026, 5, 8),
        macro_adjustment=_macro(),
        domestic_index_closes={"KOSPI": closes},
        config=_config(),
    )

    assert signal.status == "hedge_off"
    assert signal.evidence == []


def test_compute_orders_buys_missing_inverse_target_and_records_evidence():
    signal = calculate_inverse_etf_signal(
        as_of_date=date(2026, 5, 8),
        macro_adjustment=_macro(status="risk_off", cash_target=0.40, returns={"NASDAQ": -0.052}),
        domestic_index_closes={},
        config=_config(),
    )

    orders, skipped = compute_inverse_etf_orders(
        holdings=[],
        prices={"INV1": 10_000, "INV2": 5_000},
        cash=1_000_000,
        portfolio_value=10_000_000,
        signal=signal,
        entry_dates={},
        as_of_date=date(2026, 5, 8),
        config=_config(),
    )

    assert skipped == []
    assert orders[0].ticker == "INV1"
    assert orders[0].side == "BUY"
    assert orders[0].qty == 70
    assert "inverse_etf_hedge_market_drop" in orders[0].reason
    assert orders[1].ticker == "INV2"
    assert orders[1].qty == 60


def test_compute_orders_sells_inverse_etf_when_risk_clears():
    orders, skipped = compute_inverse_etf_orders(
        holdings=[
            {
                "ticker": "INV2",
                "qty": 10,
                "avg_price": 10_000,
                "current_price": 10_500,
            }
        ],
        prices={"INV2": 10_500},
        cash=1_000_000,
        portfolio_value=2_000_000,
        signal=calculate_inverse_etf_signal(
            as_of_date=date(2026, 5, 8),
            macro_adjustment=_macro(),
            domestic_index_closes={},
            config=_config(),
        ),
        entry_dates={"INV2": date(2026, 5, 7)},
        as_of_date=date(2026, 5, 8),
        config=_config(),
    )

    assert skipped == []
    assert orders == [
        orders[0].__class__(
            "INV2",
            "SELL",
            10,
            "inverse_etf_hedge_risk_cleared target 0.00%",
        )
    ]


def test_compute_orders_sells_on_stop_profit_and_max_holding_rules():
    as_of_date = date(2026, 5, 20)
    signal = calculate_inverse_etf_signal(
        as_of_date=as_of_date,
        macro_adjustment=_macro(status="risk_off", cash_target=0.40),
        domestic_index_closes={},
        config=_config(),
    )

    stop_orders, _ = compute_inverse_etf_orders(
        holdings=[{"ticker": "INV1", "qty": 10, "avg_price": 10_000, "current_price": 9_200}],
        prices={"INV1": 9_200},
        cash=0,
        portfolio_value=100_000,
        signal=signal,
        entry_dates={"INV1": as_of_date},
        as_of_date=as_of_date,
        config=_config(),
    )
    profit_orders, _ = compute_inverse_etf_orders(
        holdings=[{"ticker": "INV1", "qty": 10, "avg_price": 10_000, "current_price": 11_300}],
        prices={"INV1": 11_300},
        cash=0,
        portfolio_value=200_000,
        signal=signal,
        entry_dates={"INV1": as_of_date},
        as_of_date=as_of_date,
        config=_config(),
    )
    aged_orders, _ = compute_inverse_etf_orders(
        holdings=[{"ticker": "INV2", "qty": 10, "avg_price": 10_000, "current_price": 10_100}],
        prices={"INV2": 10_100},
        cash=0,
        portfolio_value=1_000_000,
        signal=signal,
        entry_dates={"INV2": as_of_date - timedelta(days=11)},
        as_of_date=as_of_date,
        config=_config(),
    )

    assert stop_orders[0].reason.startswith("inverse_etf_hedge_stop_loss")
    assert profit_orders[0].reason.startswith("inverse_etf_hedge_take_profit")
    assert aged_orders[0].reason.startswith("inverse_etf_hedge_max_holding_days")
