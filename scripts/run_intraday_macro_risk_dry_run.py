from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Sequence
from datetime import date
from pathlib import Path
import sys
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import DATA_DIR
from scripts.dry_run_rebalance import _parse_holdings
from src.data.database import create_tables, get_engine
from src.trading.kis_client import KisClient
from src.trading.macro_risk import MacroExposureAdjustment, load_macro_exposure_adjustment
from src.trading.rebalancer import RebalanceOrder, compute_macro_reduction_orders


ClientFactory = Callable[[], Any]
AdjustmentLoader = Callable[..., MacroExposureAdjustment]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate intraday macro risk dry-run reduction report.")
    parser.add_argument("--as-of-date", type=_parse_date, default=date.today())
    parser.add_argument("--database-url", default=None)
    parser.add_argument(
        "--output-json",
        type=Path,
        default=DATA_DIR / "macro_risk_rebalance_latest.json",
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        default=DATA_DIR / "macro_risk_rebalance_latest.md",
    )
    return parser.parse_args(argv)


def run(
    args: argparse.Namespace,
    *,
    client_factory: ClientFactory = KisClient,
    adjustment_loader: AdjustmentLoader = load_macro_exposure_adjustment,
) -> int:
    engine = get_engine(args.database_url)
    create_tables(engine)
    adjustment = adjustment_loader(engine, as_of_date=args.as_of_date)
    client = client_factory()
    balance = client.get_balance()
    holdings = _parse_holdings(balance)
    output2 = (balance.get("output2") or [{}])[0]
    cash = int(output2.get("dnca_tot_amt", 0) or 0)
    prices = {
        holding["ticker"]: int(holding.get("current_price", 0) or 0)
        for holding in holdings
    }
    orders: list[RebalanceOrder] = []
    skipped: list[dict[str, str]] = []
    if adjustment.status == "risk_off" and adjustment.cash_target > 0:
        orders, skipped = compute_macro_reduction_orders(
            holdings=holdings,
            prices=prices,
            cash=cash,
            target_cash_ratio=adjustment.cash_target,
            existing_sells=[],
        )

    payload = _json_report(
        as_of_date=args.as_of_date,
        cash=cash,
        holdings=holdings,
        orders=orders,
        skipped=skipped,
        adjustment=adjustment,
    )
    markdown = _markdown_report(payload)

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.write_text(markdown, encoding="utf-8")
    print(f"output_json={args.output_json}")
    print(f"output_md={args.output_md}")
    print("execution_allowed=false")
    return 0


def _json_report(
    *,
    as_of_date: date,
    cash: int,
    holdings: list[dict[str, Any]],
    orders: list[RebalanceOrder],
    skipped: list[dict[str, str]],
    adjustment: MacroExposureAdjustment,
) -> dict[str, Any]:
    return {
        "dry_run": True,
        "intraday": True,
        "execution_allowed": False,
        "as_of_date": str(as_of_date),
        "cash": cash,
        "holdings_count": len(holdings),
        "sell_count": len(orders),
        "macro_exposure_adjustment": adjustment.as_dict(
            orders_generated=bool(orders),
            execution_allowed=False,
        ),
        "orders": [
            {"side": order.side, "ticker": order.ticker, "qty": order.qty, "reason": order.reason}
            for order in orders
        ],
        "macro_reduction_skipped": skipped,
    }


def _markdown_report(payload: dict[str, Any]) -> str:
    macro = payload["macro_exposure_adjustment"]
    lines = [
        "# Intraday Macro Risk Dry-run",
        "",
        f"- as_of_date: `{payload['as_of_date']}`",
        f"- execution_allowed: `{payload['execution_allowed']}`",
        f"- macro_status: `{macro['status']}`",
        f"- macro_cash_target: `{macro['cash_target']:.2%}`",
        f"- macro_buy_budget_multiplier: `{macro['buy_budget_multiplier']:.2f}`",
        f"- sell_count: `{payload['sell_count']}`",
        "",
        "## Planned Reduction Orders",
        "",
        "| side | ticker | qty | reason |",
        "| --- | --- | ---: | --- |",
    ]
    if not payload["orders"]:
        lines.append("| - | - | 0 | No macro reduction needed |")
    for order in payload["orders"]:
        lines.append(f"| {order['side']} | {order['ticker']} | {order['qty']} | {order['reason']} |")
    lines.append("")
    return "\n".join(lines)


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def main(argv: Sequence[str] | None = None) -> int:
    return run(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
