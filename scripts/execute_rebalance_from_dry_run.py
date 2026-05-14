from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Sequence
from datetime import date, datetime, time
from pathlib import Path
import sys
from typing import Any
from zoneinfo import ZoneInfo

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import REBALANCE
import scripts.review_rebalance_reports as review_reports
from src.trading.engine import TradingEngine
from src.trading.kis_client import KisClient
from src.trading.rebalancer import RebalanceOrder, execute_rebalance


CONFIRM_TOKEN = "EXECUTE_PAPER_REBALANCE"
KST = ZoneInfo("Asia/Seoul")
MARKET_OPEN = time(9, 0)
MARKET_CLOSE_GUARD = time(15, 20)
EngineFactory = Callable[[], Any]
ExecuteFunction = Callable[..., dict[str, list[str]]]
ReviewFunction = Callable[[argparse.Namespace], int]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Execute PAPER rebalance orders from a clean dry-run JSON report."
    )
    parser.add_argument("--dry-run-json", type=Path, default=REBALANCE.dry_run_preflight_report_path)
    parser.add_argument("--expected-date", type=_parse_date, default=date.today())
    parser.add_argument("--confirm", default="")
    parser.add_argument("--execution-report-json", type=Path, default=None)
    parser.add_argument("--force-overwrite-report", action="store_true")
    parser.add_argument("--review-before-execute", action="store_true")
    parser.add_argument(
        "--force-market-closed",
        action="store_true",
        help="Bypass the weekday 09:00-15:20 KST guard for intentional rejection tests.",
    )
    return parser.parse_args(argv)


def run(
    args: argparse.Namespace,
    *,
    engine_factory: EngineFactory | None = None,
    execute_func: ExecuteFunction = execute_rebalance,
    review_func: ReviewFunction = review_reports.run,
    now: datetime | None = None,
) -> int:
    if args.confirm != CONFIRM_TOKEN:
        print(f"confirmation_required={CONFIRM_TOKEN}")
        return 1
    if (
        args.execution_report_json
        and args.execution_report_json.exists()
        and not args.force_overwrite_report
    ):
        print(f"execution_report_exists={args.execution_report_json}")
        print("force_required=--force-overwrite-report")
        return 1
    if not args.force_market_closed and not is_regular_market_time(now):
        print("market_time_required=weekday 09:00-15:20 KST")
        return 1
    if args.review_before_execute:
        review_result = review_func(
            review_reports.parse_args(["--dry-run-json", str(args.dry_run_json)])
        )
        if review_result != 0:
            print(f"pre_execution_review_blocked={review_result}")
            return 1

    try:
        payload = json.loads(args.dry_run_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        review_reports.print_report_load_error("dry_run", args.dry_run_json, exc)
        return 1

    sells, buys = _orders_from_payload(payload)
    factory = engine_factory or _default_engine_factory
    engine = factory()

    try:
        result = execute_func(
            engine,
            sells,
            buys,
            preflight_report_path=args.dry_run_json,
            expected_preflight_date=args.expected_date,
        )
    except RuntimeError as exc:
        print(f"execution_blocked={exc}")
        return 1
    print(
        f"sold={len(result['sold'])},"
        f"bought={len(result['bought'])},"
        f"failed={len(result['failed'])}"
    )
    if args.execution_report_json:
        _write_execution_report(
            args.execution_report_json,
            dry_run_json=args.dry_run_json,
            expected_date=args.expected_date,
            executed_at=now,
            planned_sells=sells,
            planned_buys=buys,
            result=result,
        )
        print(f"execution_report_json={args.execution_report_json}")
    return 0 if not result["failed"] else 1


def _orders_from_payload(payload: dict[str, Any]) -> tuple[list[RebalanceOrder], list[RebalanceOrder]]:
    sells: list[RebalanceOrder] = []
    buys: list[RebalanceOrder] = []
    for item in payload.get("orders") or []:
        order = RebalanceOrder(
            ticker=str(item["ticker"]),
            side=str(item["side"]),
            qty=int(item["qty"]),
            reason=str(item.get("reason", "")),
        )
        if order.side == "SELL":
            sells.append(order)
        elif order.side == "BUY":
            buys.append(order)
        else:
            raise ValueError(f"Unsupported order side: {order.side!r}")
    return sells, buys


def _default_engine_factory() -> TradingEngine:
    return TradingEngine(KisClient())


def is_regular_market_time(now: datetime | None = None) -> bool:
    current = now or datetime.now(KST)
    current = current.astimezone(KST)
    return current.weekday() < 5 and MARKET_OPEN <= current.time() <= MARKET_CLOSE_GUARD


def _write_execution_report(
    path: Path,
    *,
    dry_run_json: Path,
    expected_date: date,
    executed_at: datetime | None,
    planned_sells: list[RebalanceOrder],
    planned_buys: list[RebalanceOrder],
    result: dict[str, list[str]],
) -> None:
    current = executed_at or datetime.now(KST)
    current = current.astimezone(KST)
    plan_check = _compare_planned_and_executed_orders(
        planned_sells=planned_sells,
        planned_buys=planned_buys,
        result=result,
    )
    payload = {
        "paper_execution": True,
        "dry_run_json": str(dry_run_json),
        "expected_date": str(expected_date),
        "executed_at": current.isoformat(),
        "sold": result["sold"],
        "bought": result["bought"],
        "failed": result["failed"],
        "sold_count": len(result["sold"]),
        "bought_count": len(result["bought"]),
        "failed_count": len(result["failed"]),
        **plan_check,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")


def _compare_planned_and_executed_orders(
    *,
    planned_sells: list[RebalanceOrder],
    planned_buys: list[RebalanceOrder],
    result: dict[str, list[str]],
) -> dict[str, Any]:
    planned_sell_tickers = [order.ticker for order in planned_sells]
    planned_buy_tickers = [order.ticker for order in planned_buys]
    sold = [str(ticker) for ticker in result.get("sold", [])]
    bought = [str(ticker) for ticker in result.get("bought", [])]

    missing_sells = _ordered_difference(planned_sell_tickers, sold)
    missing_buys = _ordered_difference(planned_buy_tickers, bought)
    unexpected_sells = _ordered_difference(sold, planned_sell_tickers)
    unexpected_buys = _ordered_difference(bought, planned_buy_tickers)
    mismatches = missing_sells or missing_buys or unexpected_sells or unexpected_buys

    return {
        "planned_sells": planned_sell_tickers,
        "planned_buys": planned_buy_tickers,
        "planned_sell_count": len(planned_sell_tickers),
        "planned_buy_count": len(planned_buy_tickers),
        "execution_match_status": "mismatched" if mismatches else "matched",
        "missing_sells": missing_sells,
        "missing_buys": missing_buys,
        "unexpected_sells": unexpected_sells,
        "unexpected_buys": unexpected_buys,
    }


def _ordered_difference(left: list[str], right: list[str]) -> list[str]:
    right_set = set(right)
    return [item for item in left if item not in right_set]


def main(argv: Sequence[str] | None = None) -> int:
    return run(parse_args(argv))


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


if __name__ == "__main__":
    raise SystemExit(main())
