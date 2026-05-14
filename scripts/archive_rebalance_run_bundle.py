from __future__ import annotations

import argparse
import io
import json
import shutil
from collections.abc import Callable, Sequence
from contextlib import redirect_stdout
from datetime import date
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import PORTFOLIO, REBALANCE
import scripts.check_rebalance_readiness as readiness
import scripts.print_rebalance_operations_checklist as checklist
import scripts.review_rebalance_reports as review


RunFunction = Callable[[argparse.Namespace], int]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Archive a no-order PAPER rebalance operations bundle for one run date."
    )
    parser.add_argument("--as-of-date", type=_parse_date, default=date.today())
    parser.add_argument("--top-n", type=int, default=PORTFOLIO.n_holdings)
    parser.add_argument("--dry-run-json", type=Path, default=REBALANCE.dry_run_preflight_report_path)
    parser.add_argument("--dry-run-md", type=Path, default=None)
    parser.add_argument("--execution-report-json", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args(argv)
    if args.top_n <= 0:
        parser.error("--top-n must be greater than 0")
    if args.dry_run_md is None:
        args.dry_run_md = args.dry_run_json.with_suffix(".md")
    if args.execution_report_json is None:
        args.execution_report_json = Path("data") / f"rebalance_execution_{args.as_of_date}.json"
    if args.output_dir is None:
        args.output_dir = Path("logs") / f"rebalance_run_{args.as_of_date}"
    return args


def run(
    args: argparse.Namespace,
    *,
    checklist_run: RunFunction = checklist.run,
    readiness_run: RunFunction = readiness.run,
    review_run: RunFunction = review.run,
) -> int:
    args.output_dir.mkdir(parents=True, exist_ok=True)

    checklist_result, checklist_output = _capture_run(
        checklist_run,
        checklist.parse_args([
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
        ]),
    )
    readiness_result, readiness_output = _capture_run(
        readiness_run,
        readiness.parse_args([
            "--dry-run-json",
            str(args.dry_run_json),
            "--expected-date",
            str(args.as_of_date),
        ]),
    )
    review_argv = ["--dry-run-json", str(args.dry_run_json)]
    if args.execution_report_json.exists():
        review_argv.extend(["--execution-report-json", str(args.execution_report_json)])
    review_result, review_output = _capture_run(review_run, review.parse_args(review_argv))

    (args.output_dir / "checklist.txt").write_text(checklist_output, encoding="utf-8")
    (args.output_dir / "readiness.txt").write_text(readiness_output, encoding="utf-8")
    (args.output_dir / "review.txt").write_text(review_output, encoding="utf-8")

    artifacts = {
        "dry_run_json": _copy_if_exists(args.dry_run_json, args.output_dir / "dry_run_rebalance.json"),
        "dry_run_md": _copy_if_exists(args.dry_run_md, args.output_dir / "dry_run_rebalance.md"),
        "execution_report_json": _copy_if_exists(
            args.execution_report_json,
            args.output_dir / "rebalance_execution.json",
        ),
    }
    status = _infer_bundle_status(
        readiness_result=readiness_result,
        readiness_output=readiness_output,
        review_result=review_result,
        review_output=review_output,
        execution_report_copied=artifacts["execution_report_json"]["copied"],
    )
    manifest = {
        "rebalance_run_bundle": True,
        "as_of_date": str(args.as_of_date),
        "top_n": args.top_n,
        "bundle_status": status,
        "output_dir": str(args.output_dir),
        "checklist_result": checklist_result,
        "readiness_result": readiness_result,
        "review_result": review_result,
        "artifacts": artifacts,
        "orders_submitted": 0,
    }
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )

    print(f"bundle_status={status}")
    print(f"bundle_dir={args.output_dir}")
    print("orders_submitted=0")
    return 0 if status in {"prepared", "executed_clean"} else 1


def _capture_run(run_func: RunFunction, run_args: argparse.Namespace) -> tuple[int, str]:
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        result = run_func(run_args)
    return result, buffer.getvalue()


def _copy_if_exists(source: Path, destination: Path) -> dict[str, object]:
    if not source.exists():
        return {"source": str(source), "destination": str(destination), "copied": False}
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    return {"source": str(source), "destination": str(destination), "copied": True}


def _infer_bundle_status(
    *,
    readiness_result: int,
    readiness_output: str,
    review_result: int,
    review_output: str,
    execution_report_copied: bool,
) -> str:
    if "preflight_status=blocked" in readiness_output or "dry_run_status=blocked" in review_output:
        return "blocked_by_preflight"
    if execution_report_copied:
        if review_result == 0 and "execution_status=clean" in review_output:
            return "executed_clean"
        return "executed_with_failures"
    if readiness_result == 0 and "execution_ready=true" in readiness_output:
        return "prepared"
    if "market_time_status=blocked" in readiness_output:
        return "ready_blocked_market_time"
    return "blocked_by_preflight"


def main(argv: Sequence[str] | None = None) -> int:
    return run(parse_args(argv))


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


if __name__ == "__main__":
    raise SystemExit(main())
