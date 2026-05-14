from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import date
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import PORTFOLIO, REBALANCE


CONFIRM_TOKEN = "EXECUTE_PAPER_REBALANCE"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Print the safe PAPER rebalance operations command sequence."
    )
    parser.add_argument("--as-of-date", type=_parse_date, default=date.today())
    parser.add_argument("--top-n", type=int, default=PORTFOLIO.n_holdings)
    parser.add_argument("--dry-run-json", type=Path, default=REBALANCE.dry_run_preflight_report_path)
    parser.add_argument("--dry-run-md", type=Path, default=None)
    parser.add_argument("--execution-report-json", type=Path, default=None)
    args = parser.parse_args(argv)
    if args.top_n <= 0:
        parser.error("--top-n must be greater than 0")
    if args.dry_run_md is None:
        args.dry_run_md = args.dry_run_json.with_suffix(".md")
    if args.execution_report_json is None:
        args.execution_report_json = Path("data") / f"rebalance_execution_{args.as_of_date}.json"
    return args


def run(args: argparse.Namespace) -> int:
    as_of_date = str(args.as_of_date)
    print(f"rebalance_operations_date={as_of_date}")
    print("orders_submitted=0")
    print("step,command")
    print(f"prepare_and_review,{_prepare_and_review_command(args)}")
    print(f"readiness_check,{_readiness_command(args)}")
    print(f"execute_paper_orders,{_execute_command(args)}")
    print(f"post_execution_review,{_post_review_command(args)}")
    print(f"archive_run_bundle,{_archive_bundle_command(args)}")
    return 0


def _prepare_and_review_command(args: argparse.Namespace) -> str:
    return " ".join([
        r".\venv\Scripts\python.exe",
        r"scripts\prepare_and_review_rebalance.py",
        "--as-of-date",
        str(args.as_of_date),
        "--top-n",
        str(args.top_n),
        "--output-json",
        str(args.dry_run_json),
        "--output-md",
        str(args.dry_run_md),
    ])


def _readiness_command(args: argparse.Namespace) -> str:
    return " ".join([
        r".\venv\Scripts\python.exe",
        r"scripts\check_rebalance_readiness.py",
        "--dry-run-json",
        str(args.dry_run_json),
        "--expected-date",
        str(args.as_of_date),
    ])


def _execute_command(args: argparse.Namespace) -> str:
    return " ".join([
        r".\venv\Scripts\python.exe",
        r"scripts\execute_rebalance_from_dry_run.py",
        "--dry-run-json",
        str(args.dry_run_json),
        "--expected-date",
        str(args.as_of_date),
        "--confirm",
        CONFIRM_TOKEN,
        "--review-before-execute",
        "--execution-report-json",
        str(args.execution_report_json),
    ])


def _post_review_command(args: argparse.Namespace) -> str:
    return " ".join([
        r".\venv\Scripts\python.exe",
        r"scripts\review_rebalance_reports.py",
        "--dry-run-json",
        str(args.dry_run_json),
        "--execution-report-json",
        str(args.execution_report_json),
    ])


def _archive_bundle_command(args: argparse.Namespace) -> str:
    return " ".join([
        r".\venv\Scripts\python.exe",
        r"scripts\archive_rebalance_run_bundle.py",
        "--as-of-date",
        str(args.as_of_date),
        "--top-n",
        str(args.top_n),
        "--dry-run-json",
        str(args.dry_run_json),
        "--dry-run-md",
        str(args.dry_run_md),
        "--execution-report-json",
        str(args.execution_report_json),
    ])


def main(argv: Sequence[str] | None = None) -> int:
    return run(parse_args(argv))


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


if __name__ == "__main__":
    raise SystemExit(main())
