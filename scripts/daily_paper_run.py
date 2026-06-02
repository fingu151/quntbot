from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from datetime import date, datetime, time, timedelta
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import PORTFOLIO, REBALANCE, TRADE_MODE
import scripts.check_rebalance_readiness as readiness
import scripts.execute_rebalance_from_dry_run as execute
import scripts.prepare_and_review_rebalance as prepare_review
import scripts.review_rebalance_reports as review_reports
import scripts.sync_phase1_data as sync_phase1
from src.data.database import create_tables, get_engine
from src.trading.engine import TradingEngine
from src.trading.kis_client import KisClient
from src.trading.scheduler import BlockingScheduler, _load_daily_price_atr, _stop_loss_job


RunFunction = Callable[[argparse.Namespace], int]
MonitorRunFunction = Callable[[], None]
CONFIRM_TOKEN = execute.CONFIRM_TOKEN
KST = ZoneInfo("Asia/Seoul")
MONITOR_OPEN = time(9, 0)
MONITOR_CLOSE = time(15, 20)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the daily PAPER flow: sync, dry-run review, readiness, execution, "
            "post-review, then intraday stop monitor scheduler."
        )
    )
    parser.add_argument("--as-of-date", type=_parse_date, default=date.today())
    parser.add_argument("--start-date", type=_parse_date, default=None)
    parser.add_argument("--top-n", type=int, default=PORTFOLIO.n_holdings)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--dry-run-json", type=Path, default=REBALANCE.dry_run_preflight_report_path)
    parser.add_argument(
        "--dry-run-md",
        type=Path,
        default=REBALANCE.dry_run_preflight_report_path.with_suffix(".md"),
    )
    parser.add_argument("--execution-report-json", type=Path, default=None)
    parser.add_argument("--quote-retries", type=int, default=4)
    parser.add_argument("--quote-delay-sec", type=float, default=0.5)
    parser.add_argument("--confirm", default="")
    parser.add_argument("--force-overwrite-report", action="store_true")
    parser.add_argument("--force-market-closed", action="store_true")
    args = parser.parse_args(argv)

    if args.start_date is None:
        args.start_date = args.as_of_date - timedelta(days=30)
    if args.start_date > args.as_of_date:
        parser.error("--start-date must be on or before --as-of-date")
    if args.top_n <= 0:
        parser.error("--top-n must be greater than 0")
    if args.workers <= 0:
        parser.error("--workers must be greater than 0")
    if args.quote_retries < 0:
        parser.error("--quote-retries must be zero or greater")
    if args.quote_delay_sec < 0:
        parser.error("--quote-delay-sec must be zero or greater")
    if args.execution_report_json is None:
        args.execution_report_json = Path("data") / f"rebalance_execution_{args.as_of_date}.json"
    return args


def run(
    args: argparse.Namespace,
    *,
    sync_run: RunFunction = sync_phase1.run,
    prepare_review_run: RunFunction = prepare_review.run,
    readiness_run: RunFunction = readiness.run,
    execute_run: RunFunction = execute.run,
    post_review_run: RunFunction = review_reports.run,
    monitor_run: MonitorRunFunction | None = None,
) -> int:
    if args.confirm != CONFIRM_TOKEN:
        print(f"confirmation_required={CONFIRM_TOKEN}")
        return 1
    if TRADE_MODE != "PAPER":
        print(f"trade_mode_blocked={TRADE_MODE}")
        print("trade_mode_required=PAPER")
        return 1

    steps: list[tuple[str, RunFunction, argparse.Namespace]] = [
        ("sync", sync_run, _sync_args(args)),
        ("prepare_review", prepare_review_run, _prepare_review_args(args)),
        ("readiness", readiness_run, _readiness_args(args)),
        ("execute", execute_run, _execute_args(args)),
        ("post_review", post_review_run, _post_review_args(args)),
    ]
    for name, step_run, step_args in steps:
        print(f"daily_step_started={name}")
        result = step_run(step_args)
        print(f"daily_step_finished={name},exit_code={result}")
        if result != 0:
            print(f"daily_flow_blocked_at={name}")
            return result

    print("daily_step_started=intraday_stop_monitor")
    print("intraday_stop_monitor_note=keep_this_terminal_open; press Ctrl+C to stop monitoring")
    (monitor_run or run_intraday_stop_monitor)()
    return 0


def run_intraday_stop_monitor(now: datetime | None = None) -> None:
    """Start only the intraday stop-loss/trailing-stop monitor.

    The daily one-shot script already executed the rebalance. This monitor avoids
    registering another rebalance job in the same process.
    """
    db_engine = get_engine()
    create_tables(db_engine)
    engine = TradingEngine(
        KisClient(),
        atr_lookup=lambda ticker, as_of_date, window: _load_daily_price_atr(
            db_engine,
            ticker,
            as_of_date=as_of_date,
            window=window,
        ),
    )
    scheduler = BlockingScheduler(timezone="Asia/Seoul")
    scheduler.add_job(
        _stop_loss_job,
        trigger="cron",
        day_of_week="mon-fri",
        hour="9-15",
        minute="*/10",
        kwargs={"engine": engine},
        id="intraday_stop_loss",
    )
    if _is_monitor_time(now):
        _stop_loss_job(engine)
    else:
        print("intraday_stop_monitor_initial_check=skipped_outside_market_hours")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("intraday_stop_monitor_stopped=true")


def _is_monitor_time(now: datetime | None = None) -> bool:
    current = now or datetime.now(KST)
    current = current.astimezone(KST)
    return current.weekday() < 5 and MONITOR_OPEN <= current.time() <= MONITOR_CLOSE


def _sync_args(args: argparse.Namespace) -> argparse.Namespace:
    argv = [
        "--start-date",
        str(args.start_date),
        "--end-date",
        str(args.as_of_date),
        "--workers",
        str(args.workers),
    ]
    if args.database_url:
        argv.extend(["--database-url", str(args.database_url)])
    return sync_phase1.parse_args(argv)


def _prepare_review_args(args: argparse.Namespace) -> argparse.Namespace:
    argv = [
        "--as-of-date",
        str(args.as_of_date),
        "--top-n",
        str(args.top_n),
        "--output-json",
        str(args.dry_run_json),
        "--output-md",
        str(args.dry_run_md),
        "--quote-retries",
        str(args.quote_retries),
        "--quote-delay-sec",
        str(args.quote_delay_sec),
    ]
    if args.database_url:
        argv.extend(["--database-url", str(args.database_url)])
    return prepare_review.parse_args(argv)


def _readiness_args(args: argparse.Namespace) -> argparse.Namespace:
    return readiness.parse_args([
        "--dry-run-json",
        str(args.dry_run_json),
        "--expected-date",
        str(args.as_of_date),
    ])


def _execute_args(args: argparse.Namespace) -> argparse.Namespace:
    argv = [
        "--dry-run-json",
        str(args.dry_run_json),
        "--expected-date",
        str(args.as_of_date),
        "--confirm",
        str(args.confirm),
        "--review-before-execute",
        "--execution-report-json",
        str(args.execution_report_json),
    ]
    if args.force_overwrite_report:
        argv.append("--force-overwrite-report")
    if args.force_market_closed:
        argv.append("--force-market-closed")
    return execute.parse_args(argv)


def _post_review_args(args: argparse.Namespace) -> argparse.Namespace:
    return review_reports.parse_args([
        "--dry-run-json",
        str(args.dry_run_json),
        "--execution-report-json",
        str(args.execution_report_json),
    ])


def main(argv: Sequence[str] | None = None) -> int:
    return run(parse_args(argv))


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


if __name__ == "__main__":
    raise SystemExit(main())
