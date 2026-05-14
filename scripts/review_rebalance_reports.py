from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
import sys
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import REBALANCE


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Review dry-run and optional PAPER execution rebalance reports."
    )
    parser.add_argument("--dry-run-json", type=Path, default=REBALANCE.dry_run_preflight_report_path)
    parser.add_argument("--execution-report-json", type=Path, default=None)
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> int:
    try:
        dry_run = _load_json(args.dry_run_json)
    except (OSError, json.JSONDecodeError) as exc:
        print_report_load_error("dry_run", args.dry_run_json, exc)
        return 1

    dry_run_clean = _print_dry_run_summary(dry_run)

    execution_clean = True
    if args.execution_report_json:
        try:
            execution = _load_json(args.execution_report_json)
        except (OSError, json.JSONDecodeError) as exc:
            print_report_load_error("execution", args.execution_report_json, exc)
            return 1
        execution_clean = _print_execution_summary(execution)

    return 0 if dry_run_clean and execution_clean else 1


def _print_dry_run_summary(payload: dict[str, Any]) -> bool:
    fallback_count = int(payload.get("price_fallback_count", 0) or 0)
    failed_count = int(payload.get("price_lookup_failed_count", 0) or 0)
    skipped_buys = payload.get("skipped_buys") or []
    price_retry_attempts = payload.get("price_retry_attempts") or []
    orders = payload.get("orders") or []
    is_clean = payload.get("dry_run") is True and fallback_count == 0 and failed_count == 0

    print(f"dry_run_status={'clean' if is_clean else 'blocked'}")
    print(f"as_of_date={payload.get('as_of_date', '')}")
    print(f"target_count={int(payload.get('target_count', 0) or 0)}")
    print(f"sell_count={int(payload.get('sell_count', 0) or 0)}")
    print(f"buy_count={int(payload.get('buy_count', 0) or 0)}")
    print(f"skipped_buy_count={int(payload.get('skipped_buy_count', len(skipped_buys)) or 0)}")
    print(f"orders={len(orders)}")
    print(f"price_fallback_count={fallback_count}")
    print(f"price_lookup_failed_count={failed_count}")
    print(f"price_retry_success_count={int(payload.get('price_retry_success_count', 0) or 0)}")
    print(f"price_retry_failed_count={int(payload.get('price_retry_failed_count', 0) or 0)}")
    print("side,ticker,qty,reason")
    for order in orders:
        print(
            f"{order.get('side', '')},"
            f"{order.get('ticker', '')},"
            f"{order.get('qty', '')},"
            f"{order.get('reason', '')}"
        )
    for item in skipped_buys:
        print(
            f"skipped_buy,{item.get('ticker', '')},"
            f"{item.get('reason', '')},"
            f"{item.get('execution_price', '')},"
            f"{item.get('previous_close', '')},"
            f"{float(item.get('gap_pct', 0.0) or 0.0):.2%},"
            f"{float(item.get('threshold_pct', 0.0) or 0.0):.2%}"
        )
    for item in price_retry_attempts:
        print(
            f"price_retry,{item.get('ticker', '')},"
            f"{item.get('status', '')},"
            f"{item.get('attempt_count', '')},"
            f"{item.get('last_error', '')}"
        )
    return is_clean


def _print_execution_summary(payload: dict[str, Any]) -> bool:
    failed = [str(ticker) for ticker in payload.get("failed", [])]
    match_status = str(payload.get("execution_match_status", "unknown") or "unknown")
    is_clean = payload.get("paper_execution") is True and not failed and match_status in {"matched", "unknown"}

    print(f"execution_status={'clean' if is_clean else 'failed'}")
    print(f"executed_at={payload.get('executed_at', '')}")
    print(f"sold_count={int(payload.get('sold_count', 0) or 0)}")
    print(f"bought_count={int(payload.get('bought_count', 0) or 0)}")
    print(f"failed_count={int(payload.get('failed_count', 0) or 0)}")
    print(f"planned_sell_count={int(payload.get('planned_sell_count', 0) or 0)}")
    print(f"planned_buy_count={int(payload.get('planned_buy_count', 0) or 0)}")
    print(f"execution_match_status={match_status}")
    print(f"missing_sells={_join_tickers(payload.get('missing_sells', []))}")
    print(f"missing_buys={_join_tickers(payload.get('missing_buys', []))}")
    print(f"unexpected_sells={_join_tickers(payload.get('unexpected_sells', []))}")
    print(f"unexpected_buys={_join_tickers(payload.get('unexpected_buys', []))}")
    if failed:
        print(f"failed_tickers={','.join(failed)}")
    return is_clean


def _join_tickers(value: Any) -> str:
    return ",".join(str(ticker) for ticker in (value or []))


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def print_report_load_error(label: str, path: Path, exc: Exception) -> None:
    print(f"{label}_status=missing_or_invalid")
    print(f"report_path={path}")
    print(f"report_error={exc}")


def main(argv: Sequence[str] | None = None) -> int:
    return run(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
