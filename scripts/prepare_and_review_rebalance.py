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
import scripts.prepare_rebalance_for_execution as prepare
import scripts.review_rebalance_reports as review


PrepareRun = Callable[[argparse.Namespace], int]
ReviewRun = Callable[[argparse.Namespace], int]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare and review a PAPER rebalance dry-run without placing orders."
    )
    default_json = REBALANCE.dry_run_preflight_report_path
    parser.add_argument("--as-of-date", type=_parse_date, default=date.today())
    parser.add_argument("--top-n", type=int, default=PORTFOLIO.n_holdings)
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--output-json", type=Path, default=default_json)
    parser.add_argument("--output-md", type=Path, default=default_json.with_suffix(".md"))
    parser.add_argument("--quote-retries", type=int, default=prepare.DEFAULT_QUOTE_RETRIES)
    parser.add_argument("--quote-delay-sec", type=float, default=prepare.DEFAULT_QUOTE_DELAY_SEC)
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
    prepare_run: PrepareRun = prepare.run,
    review_run: ReviewRun = review.run,
) -> int:
    prepare_result = prepare_run(_prepare_args(args))
    if prepare_result != 0:
        return prepare_result
    return review_run(_review_args(args))


def _prepare_args(args: argparse.Namespace) -> argparse.Namespace:
    argv = [
        "--as-of-date",
        str(args.as_of_date),
        "--top-n",
        str(args.top_n),
        "--output-json",
        str(args.output_json),
        "--output-md",
        str(args.output_md),
        "--quote-retries",
        str(args.quote_retries),
        "--quote-delay-sec",
        str(args.quote_delay_sec),
    ]
    if args.database_url:
        argv.extend(["--database-url", str(args.database_url)])
    return prepare.parse_args(argv)


def _review_args(args: argparse.Namespace) -> argparse.Namespace:
    return review.parse_args(["--dry-run-json", str(args.output_json)])


def main(argv: Sequence[str] | None = None) -> int:
    return run(parse_args(argv))


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


if __name__ == "__main__":
    raise SystemExit(main())
