from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from datetime import date, datetime
import json
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import PORTFOLIO, REBALANCE
from scripts.execute_rebalance_from_dry_run import is_regular_market_time
from src.trading.rebalancer import _assert_preflight_report_allows_orders


PreflightFunction = Callable[..., None]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check PAPER rebalance execution readiness without placing orders."
    )
    parser.add_argument("--dry-run-json", type=Path, default=REBALANCE.dry_run_preflight_report_path)
    parser.add_argument("--expected-date", type=_parse_date, default=date.today())
    return parser.parse_args(argv)


def run(
    args: argparse.Namespace,
    *,
    now: datetime | None = None,
    preflight_func: PreflightFunction = _assert_preflight_report_allows_orders,
) -> int:
    market_ready = is_regular_market_time(now)
    print(f"market_time_status={'ready' if market_ready else 'blocked'}")
    print("market_time_required=weekday 09:00-15:20 KST")
    print(f"dry_run_json={args.dry_run_json}")
    print(f"expected_date={args.expected_date}")

    preflight_ready = True
    try:
        preflight_func(args.dry_run_json, expected_preflight_date=args.expected_date)
    except (RuntimeError, OSError, json.JSONDecodeError) as exc:
        preflight_ready = False
        print("preflight_status=blocked")
        print(f"preflight_error={exc}")
        print(_build_next_prepare_command(args.expected_date))
    else:
        print("preflight_status=clean")

    execution_ready = market_ready and preflight_ready
    print(f"execution_ready={str(execution_ready).lower()}")
    return 0 if execution_ready else 1


def main(argv: Sequence[str] | None = None) -> int:
    return run(parse_args(argv))


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def _build_next_prepare_command(expected_date: date) -> str:
    return (
        "next_prepare_command=.\\venv\\Scripts\\python.exe "
        f"scripts\\prepare_rebalance_for_execution.py --as-of-date {expected_date} "
        f"--top-n {PORTFOLIO.n_holdings}"
    )


if __name__ == "__main__":
    raise SystemExit(main())
