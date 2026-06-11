from datetime import date
import json
from unittest.mock import MagicMock

from scripts import run_intraday_macro_risk_dry_run
from src.trading.bond_yield_risk import BondYieldAdjustment
from src.trading.macro_risk import MacroExposureAdjustment
from src.trading.us_market_risk import UsMarketBuyAdjustment


def _risk_off_adjustment() -> MacroExposureAdjustment:
    return MacroExposureAdjustment(
        status="risk_off",
        buy_budget_multiplier=0.6,
        cash_target=0.4,
        signals=["NASDAQ:-3.00%"],
        missing_sources=[],
        us_market=UsMarketBuyAdjustment("risk_off", 0.6, 0.4, ["NASDAQ:-3.00%"], {"NASDAQ": -0.03}),
        bond_yield=BondYieldAdjustment("neutral", 1.0, 0.0, [], {}),
        indicator_signals=[],
    )


def test_intraday_macro_risk_dry_run_writes_report_without_orders(tmp_path):
    client = MagicMock()
    client.get_balance.return_value = {
        "output1": [
            {
                "pdno": "AAA",
                "prdt_name": "AAA",
                "hldg_qty": "9",
                "pchs_avg_pric": "10000",
                "prpr": "10000",
                "evlu_pfls_amt": "0",
                "evlu_pfls_rt": "0.0",
            }
        ],
        "output2": [{"dnca_tot_amt": "10000"}],
    }
    json_path = tmp_path / "macro.json"
    md_path = tmp_path / "macro.md"
    args = run_intraday_macro_risk_dry_run.parse_args(
        [
            "--as-of-date",
            "2026-05-08",
            "--database-url",
            "sqlite:///:memory:",
            "--output-json",
            str(json_path),
            "--output-md",
            str(md_path),
        ]
    )

    exit_code = run_intraday_macro_risk_dry_run.run(
        args,
        client_factory=MagicMock(return_value=client),
        adjustment_loader=MagicMock(return_value=_risk_off_adjustment()),
    )

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    markdown = md_path.read_text(encoding="utf-8")

    assert exit_code == 0
    assert payload["dry_run"] is True
    assert payload["execution_allowed"] is False
    assert payload["macro_exposure_adjustment"]["orders_generated"] is True
    assert payload["orders"] == [
        {
            "side": "SELL",
            "ticker": "AAA",
            "qty": 3,
            "reason": "macro_risk_reduce to 40% cash target",
        }
    ]
    assert "# Intraday Macro Risk Dry-run" in markdown
    client.place_order.assert_not_called()
