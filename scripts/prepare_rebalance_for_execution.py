from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from datetime import date
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import PORTFOLIO, REBALANCE
import scripts.dry_run_rebalance as dry_run
from src.trading.rebalancer import _assert_preflight_report_allows_orders


DryRunFunction = Callable[[argparse.Namespace], int]
PreflightFunction = Callable[..., None]
DEFAULT_QUOTE_RETRIES = 4
DEFAULT_QUOTE_DELAY_SEC = 0.5


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare a clean PAPER rebalance dry-run report for later execution."
    )
    default_json = REBALANCE.dry_run_preflight_report_path
    parser.add_argument("--as-of-date", type=_parse_date, default=date.today())
    parser.add_argument("--top-n", type=int, default=PORTFOLIO.n_holdings)
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--output-json", type=Path, default=default_json)
    parser.add_argument("--output-md", type=Path, default=default_json.with_suffix(".md"))
    parser.add_argument("--quote-retries", type=int, default=DEFAULT_QUOTE_RETRIES)
    parser.add_argument("--quote-delay-sec", type=float, default=DEFAULT_QUOTE_DELAY_SEC)
    args = parser.parse_args(argv)
    if args.top_n <= 0:
        parser.error("--top-n must be greater than 0")
    if args.quote_retries < 0:
        parser.error("--quote-retries must be zero or greater")
    if args.quote_delay_sec < 0:
        parser.error("--quote-delay-sec must be zero or greater")
    return args


def run(
    args: argparse.Namespace,
    *,
    dry_run_func: DryRunFunction = dry_run.run,
    preflight_func: PreflightFunction = _assert_preflight_report_allows_orders,
) -> int:
    dry_run_args = dry_run.parse_args(_build_dry_run_argv(args))
    result = dry_run_func(dry_run_args)
    if result != 0:
        print(f"dry_run_failed={result}")
        return result

    try:
        preflight_func(
            args.output_json,
            expected_preflight_date=args.as_of_date,
        )
    except RuntimeError as exc:
        print(f"prepare_blocked={exc}")
        return 1

    print(f"prepare_ready={args.output_json}")
    print(f"expected_date={args.as_of_date}")
    print("orders_submitted=0")
    return 0


def _build_dry_run_argv(args: argparse.Namespace) -> list[str]:
    argv = [
        "--as-of-date",
        str(args.as_of_date),
        "--top-n",
        str(args.top_n),
        "--output-json",
        str(args.output_json),
        "--output-md",
        str(args.output_md),
        "--price-fallback",
        "none",
        "--quote-retries",
        str(args.quote_retries),
        "--quote-delay-sec",
        str(args.quote_delay_sec),
    ]
    if args.database_url:
        argv.extend(["--database-url", str(args.database_url)])
    return argv


def main(argv: Sequence[str] | None = None) -> int:
    return run(parse_args(argv))


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


if __name__ == "__main__":
    raise SystemExit(main())
