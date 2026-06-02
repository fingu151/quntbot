from __future__ import annotations

import ast
import argparse
from datetime import datetime
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from scripts.generate_public_portfolio_snapshot import (
    _account_snapshot_from_kis_balance,
    build_snapshot,
    fetch_live_market_snapshot,
    load_json_file,
    run,
)


KST = ZoneInfo("Asia/Seoul")


def test_build_snapshot_summarizes_holdings_and_merges_dry_run_rationale() -> None:
    holdings = [
        {
            "ticker": "005930",
            "name": "Samsung Electronics",
            "qty": 10,
            "avg_price": 70000,
            "current_price": 72000,
            "eval_profit_loss": 20000,
            "profit_loss_rate": 2.86,
        }
    ]
    dry_run = {
        "as_of_date": "2026-05-12",
        "targets": [
            {
                "ticker": "005930",
                "name": "Samsung Electronics",
                "rank": 1,
                "total_score": 1.2345,
                "value_score": 0.1,
                "quality_score": 0.2,
                "momentum_score": 0.3,
                "yield_score": 0.4,
                "telegram_score": 0.5,
                "busanstock_score": 0.6,
                "investor_flow_score": 0.7,
            }
        ],
        "orders": [
            {
                "ticker": "005930",
                "side": "BUY",
                "qty": 10,
                "reason": "target allocation buy",
            }
        ],
    }

    snapshot = build_snapshot(
        holdings,
        dry_run=dry_run,
        account={
            "cash": {"available": 280000, "withdrawable": 270000},
            "realized": {"profit_loss": 12000, "source": "kis_balance"},
        },
        market={
            "kospi": {"value": 2780.5, "chg_pct": 0.5},
            "kosdaq": {"value": 900.2, "chg_pct": -0.1},
            "usdkrw": {"value": 1365.4, "chg_pct": 0.2},
        },
        generated_at=datetime(2026, 5, 12, 9, 15, tzinfo=KST),
    )

    assert snapshot["schema_version"] == 1
    assert snapshot["source"]["dashboard_calls_kis"] is False
    assert snapshot["summary"]["holding_count"] == 1
    assert snapshot["summary"]["total_market_value"] == 720000
    assert snapshot["summary"]["cash_balance"] == 280000
    assert snapshot["summary"]["total_asset_value"] == 1000000
    assert snapshot["summary"]["total_cost"] == 700000
    assert snapshot["summary"]["total_profit_loss"] == 20000
    assert snapshot["summary"]["total_profit_loss_rate"] == 2.86
    assert snapshot["cash"]["available"] == 280000
    assert snapshot["realized"]["profit_loss"] == 12000
    assert snapshot["market"]["kospi"]["value"] == 2780.5
    position = snapshot["positions"][0]
    assert position["market_value"] == 720000
    assert position["profit_loss"] == 20000
    assert position["rationale"]["rank"] == 1
    assert position["rationale"]["order_reason"] == "target allocation buy"
    assert position["rationale"]["factor_scores"]["investor_flow"] == 0.7


def test_fetch_live_market_snapshot_parses_yahoo_chart_responses() -> None:
    payloads = {
        "KS11": {
            "chart": {
                "result": [
                    {
                        "meta": {"regularMarketPrice": 2780.5, "chartPreviousClose": 2760.0},
                    }
                ]
            }
        },
        "KQ11": {
            "chart": {
                "result": [
                    {
                        "meta": {"regularMarketPrice": 900.2, "chartPreviousClose": 901.1},
                    }
                ]
            }
        },
        "KRW=X": {
            "chart": {
                "result": [
                    {
                        "meta": {"regularMarketPrice": 1365.4, "chartPreviousClose": 1360.0},
                    }
                ]
            }
        },
    }

    def fetcher(symbol: str) -> dict:
        return payloads[symbol]

    market = fetch_live_market_snapshot(
        fetcher=fetcher,
        generated_at=datetime(2026, 5, 22, 16, 30, tzinfo=KST),
    )

    assert market["kospi"] == {"value": 2780.5, "chg_pct": 0.7428}
    assert market["kosdaq"] == {"value": 900.2, "chg_pct": -0.0999}
    assert market["usdkrw"] == {"value": 1365.4, "chg_pct": 0.3971}
    assert market["status"] in {"OPEN", "CLOSED"}


def test_account_snapshot_from_kis_balance_extracts_cash_assets_and_realized() -> None:
    raw = {
        "output1": [
            {
                "pdno": "005930",
                "prdt_name": "Samsung Electronics",
                "hldg_qty": "10",
                "pchs_avg_pric": "70000",
                "prpr": "72000",
                "evlu_pfls_amt": "20000",
                "evlu_pfls_rt": "2.86",
            }
        ],
        "output2": [
            {
                "dnca_tot_amt": "280000",
                "nxdy_excc_amt": "270000",
                "tot_evlu_amt": "1000000",
                "scts_evlu_amt": "720000",
                "prvs_rcdl_excc_amt": "280000",
                "rlzt_pfls_amt": "12000",
            }
        ],
    }

    account = _account_snapshot_from_kis_balance(raw)

    assert account["holdings"][0]["ticker"] == "005930"
    assert account["cash"] == {
        "available": 280000,
        "withdrawable": 270000,
        "deposit_total": 280000,
        "derived_from_total_asset": 280000,
        "source": "kis_balance",
    }
    assert account["total_asset_value"] == 1000000
    assert account["realized"] == {"profit_loss": 12000, "source": "kis_balance"}


def test_build_snapshot_preserves_holding_when_rationale_is_missing() -> None:
    snapshot = build_snapshot(
        [
            {
                "ticker": "000660",
                "name": "SK hynix",
                "qty": 2,
                "avg_price": 100000,
                "current_price": 101000,
                "eval_profit_loss": 2000,
                "profit_loss_rate": 1.0,
            }
        ],
        dry_run={"targets": [], "orders": []},
        generated_at=datetime(2026, 5, 12, 9, 15, tzinfo=KST),
    )

    assert snapshot["positions"][0]["ticker"] == "000660"
    assert snapshot["positions"][0]["rationale"]["order_reason"] == ""
    assert "missing_rationale:000660" in snapshot["warnings"]


def test_build_snapshot_attaches_signal_details() -> None:
    snapshot = build_snapshot(
        [
            {
                "ticker": "005930",
                "name": "Samsung Electronics",
                "qty": 1,
                "avg_price": 70000,
                "current_price": 72000,
                "eval_profit_loss": 2000,
                "profit_loss_rate": 2.86,
            }
        ],
        dry_run={
            "targets": [{"ticker": "005930", "rank": 1, "total_score": 1.0}],
            "orders": [],
        },
        signal_details={
            "005930": [
                {
                    "source": "busanstock",
                    "detail": "TP up",
                    "raw_score": 1.0,
                }
            ]
        },
        generated_at=datetime(2026, 5, 12, 9, 15, tzinfo=KST),
    )

    assert snapshot["positions"][0]["rationale"]["signals"] == [
        {"source": "busanstock", "detail": "TP up", "raw_score": 1.0}
    ]


def test_build_snapshot_attaches_quality_and_investor_flow_context() -> None:
    snapshot = build_snapshot(
        [
            {
                "ticker": "005930",
                "name": "Samsung Electronics",
                "qty": 1,
                "avg_price": 70000,
                "current_price": 72000,
                "eval_profit_loss": 2000,
                "profit_loss_rate": 2.86,
            }
        ],
        dry_run={
            "targets": [{"ticker": "005930", "rank": 1, "total_score": 1.0}],
            "orders": [],
        },
        market_context={
            "005930": {
                "quality": {
                    "roe": 0.12,
                    "operating_margin": 0.2,
                    "debt_ratio": 0.4,
                    "published_at": "2026-03-31",
                },
                "investor_flow": {
                    "date": "2026-05-12",
                    "foreign_net_buy": 1000000.0,
                    "institution_net_buy": 2000000.0,
                    "individual_net_buy": -3000000.0,
                },
            }
        },
        generated_at=datetime(2026, 5, 12, 9, 15, tzinfo=KST),
    )

    context = snapshot["positions"][0]["rationale"]["market_context"]
    assert context["quality"]["roe"] == 0.12
    assert context["investor_flow"]["foreign_net_buy"] == 1000000.0


def test_build_snapshot_uses_factor_details_when_dry_run_target_has_only_total_score() -> None:
    snapshot = build_snapshot(
        [
            {
                "ticker": "000270",
                "name": "Kia",
                "qty": 1,
                "avg_price": 170100,
                "current_price": 171000,
                "eval_profit_loss": 900,
                "profit_loss_rate": 0.53,
            }
        ],
        dry_run={
            "targets": [
                {
                    "ticker": "000270",
                    "name": "Kia",
                    "rank": 6,
                    "total_score": 2.6049,
                }
            ],
            "orders": [],
        },
        factor_details={
            "000270": {
                "value": -0.1,
                "quality": 0.2,
                "momentum": 0.3,
                "yield": 0.4,
                "telegram": 0.0,
                "busanstock": 0.6,
                "investor_flow": 0.7,
                "research_report": 0.8,
            }
        },
        generated_at=datetime(2026, 5, 12, 9, 15, tzinfo=KST),
    )

    assert snapshot["positions"][0]["rationale"]["factor_scores"] == {
        "value": -0.1,
        "quality": 0.2,
        "momentum": 0.3,
        "yield": 0.4,
        "telegram": 0.0,
        "busanstock": 0.6,
        "investor_flow": 0.7,
        "research_report": 0.8,
    }


def test_telegram_signal_summary_does_not_expose_message_id() -> None:
    snapshot = build_snapshot(
        [
            {
                "ticker": "005930",
                "name": "Samsung Electronics",
                "qty": 1,
                "avg_price": 70000,
                "current_price": 72000,
                "eval_profit_loss": 2000,
                "profit_loss_rate": 2.86,
            }
        ],
        dry_run={"targets": [{"ticker": "005930"}], "orders": []},
        signal_details={
            "005930": [
                {
                    "source": "telegram",
                    "raw_score": 1.0,
                    "message_id": 12345,
                }
            ]
        },
        generated_at=datetime(2026, 5, 12, 9, 15, tzinfo=KST),
    )

    assert "message_id" not in snapshot["positions"][0]["rationale"]["signals"][0]


def test_snapshot_generator_does_not_import_order_execution_helpers() -> None:
    source = Path("scripts/generate_public_portfolio_snapshot.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden = {
        "TradingEngine",
        "execute_rebalance",
        "place_order",
        "buy",
        "sell",
        "scripts.execute_rebalance_from_dry_run",
    }

    imported_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported_names.update(alias.name for alias in node.names)
            if node.module:
                imported_names.add(node.module)
        elif isinstance(node, ast.Import):
            imported_names.update(alias.name for alias in node.names)

    assert forbidden.isdisjoint(imported_names)


def test_load_json_file_returns_empty_dict_for_missing_path(tmp_path: Path) -> None:
    assert load_json_file(tmp_path / "missing.json") == {}


def test_run_reuses_existing_snapshot_when_kis_holdings_are_unavailable(tmp_path: Path) -> None:
    output = tmp_path / "public_snapshot.json"
    output.write_text(
        json.dumps(
            {
                "positions": [
                    {
                        "ticker": "005930",
                        "name": "Samsung Electronics",
                        "qty": 2,
                        "avg_price": 70000,
                        "current_price": 72000,
                        "profit_loss": 4000,
                        "profit_loss_rate": 2.86,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    args = argparse.Namespace(
        dry_run_json=tmp_path / "missing_dry_run.json",
        execution_report_json=None,
        output=output,
        database_url="sqlite:///:memory:",
        as_of_date=None,
        fallback_existing_snapshot=True,
    )

    exit_code = run(
        args,
        holdings_provider=lambda: (_ for _ in ()).throw(RuntimeError("kis blocked")),
    )

    assert exit_code == 0
    snapshot = json.loads(output.read_text(encoding="utf-8"))
    assert snapshot["source"]["holdings"] == "previous_public_snapshot"
    assert snapshot["source"]["kis_called_by_snapshot"] is False
    assert snapshot["positions"][0]["ticker"] == "005930"
    assert "kis_holdings_unavailable_reused_previous_snapshot:RuntimeError" in snapshot["warnings"]
