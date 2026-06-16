from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from datetime import date, datetime, time, timedelta
import os
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
import scripts.archive_rebalance_run_bundle as archive_bundle
import scripts.run_hankyung_research_readonly_pipeline as hankyung_research
import scripts.run_mirae_research_readonly_pipeline as mirae_research
import scripts.sync_phase1_data as sync_phase1
from src.data.database import create_tables, get_engine
from src.trading.engine import TradingEngine
from src.trading.kis_client import KisClient
from src.trading.scheduler import BlockingScheduler, _load_daily_price_atr, _stop_loss_job
from src.trading.trade_journal import TradeJournalRecorder


RunFunction = Callable[[argparse.Namespace], int]
MonitorRunFunction = Callable[[], None]
CONFIRM_TOKEN = execute.CONFIRM_TOKEN
KST = ZoneInfo("Asia/Seoul")
MONITOR_OPEN = time(9, 0)
MONITOR_CLOSE = time(15, 20)
DAILY_GUARD_DIR = ROOT_DIR / ".tmp"
DAILY_RUN_LOCK_PATH = DAILY_GUARD_DIR / "daily_paper_run.lock"
DAILY_RUN_SUCCESS_MARKER_PATH = DAILY_GUARD_DIR / "daily_paper_run_success.txt"
DAILY_RUN_STALE_LOCK_AFTER = timedelta(hours=12)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    argv_list = list(argv) if argv is not None else None
    parser = argparse.ArgumentParser(
        description=(
            "Run the daily PAPER flow: read-only research refresh, sync, dry-run "
            "review, readiness, execution, post-review, archive, then intraday "
            "stop monitor scheduler."
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
    parser.add_argument(
        "--force-daily-run",
        action="store_true",
        help="Allow a same-date rerun after a completed daily PAPER flow.",
    )
    args = parser.parse_args(argv_list)

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
        execution_report_json = Path("data") / f"rebalance_execution_{args.as_of_date}.json"
        if not args.force_overwrite_report:
            execution_report_json = _first_available_execution_report_path(execution_report_json)
        args.execution_report_json = execution_report_json
    return args


def run(
    args: argparse.Namespace,
    *,
    hankyung_research_run: RunFunction = hankyung_research.run,
    mirae_research_run: RunFunction = mirae_research.run,
    sync_run: RunFunction = sync_phase1.run,
    prepare_review_run: RunFunction = prepare_review.run,
    readiness_run: RunFunction = readiness.run,
    execute_run: RunFunction = execute.run,
    post_review_run: RunFunction = review_reports.run,
    archive_run: RunFunction = archive_bundle.run,
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
        ("research_hankyung", hankyung_research_run, _hankyung_research_args(args)),
        ("research_mirae", mirae_research_run, _mirae_research_args(args)),
        ("sync", sync_run, _sync_args(args)),
        ("prepare_review", prepare_review_run, _prepare_review_args(args)),
        ("readiness", readiness_run, _readiness_args(args)),
        ("execute", execute_run, _execute_args(args)),
        ("post_review", post_review_run, _post_review_args(args)),
        ("archive", archive_run, _archive_args(args)),
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
    kis_client = KisClient()
    trade_journal_recorder = TradeJournalRecorder(db_engine, kis_client)
    engine = TradingEngine(
        kis_client,
        atr_lookup=lambda ticker, as_of_date, window: _load_daily_price_atr(
            db_engine,
            ticker,
            as_of_date=as_of_date,
            window=window,
        ),
        trade_journal_recorder=trade_journal_recorder,
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


def _hankyung_research_args(args: argparse.Namespace) -> argparse.Namespace:
    argv = [
        "--as-of-date",
        str(args.as_of_date),
        "--top-n",
        str(args.top_n),
    ]
    if args.database_url:
        argv.extend(["--database-url", str(args.database_url)])
    return hankyung_research.parse_args(argv)


def _mirae_research_args(args: argparse.Namespace) -> argparse.Namespace:
    argv = [
        "--as-of-date",
        str(args.as_of_date),
        "--top-n",
        str(args.top_n),
    ]
    if args.database_url:
        argv.extend(["--database-url", str(args.database_url)])
    return mirae_research.parse_args(argv)


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
    if args.database_url:
        argv.extend(["--database-url", str(args.database_url)])
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


def _archive_args(args: argparse.Namespace) -> argparse.Namespace:
    return archive_bundle.parse_args([
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
    return run_with_daily_guard(parse_args(argv))


def run_with_daily_guard(
    args: argparse.Namespace,
    *,
    run_func: Callable[[argparse.Namespace], int] = run,
    lock_path: Path = DAILY_RUN_LOCK_PATH,
    success_marker_path: Path = DAILY_RUN_SUCCESS_MARKER_PATH,
    stale_lock_after: timedelta = DAILY_RUN_STALE_LOCK_AFTER,
) -> int:
    """Prevent duplicate scheduled PAPER flows for the same trading day."""
    run_date = str(args.as_of_date)
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    if not args.force_daily_run and success_marker_path.exists():
        last_success = success_marker_path.read_text(encoding="utf-8").strip()
        if last_success == run_date:
            print(f"daily_flow_skipped=already_completed date={run_date}")
            print("orders_submitted=0")
            return 0

    if lock_path.exists():
        lock_age = datetime.now().timestamp() - lock_path.stat().st_mtime
        if lock_age <= stale_lock_after.total_seconds():
            print(f"daily_flow_skipped=already_running lock={lock_path}")
            print("orders_submitted=0")
            return 0
        print(f"daily_flow_stale_lock_removed lock={lock_path}")
        lock_path.unlink()

    fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        lock_text = (
            f"pid={os.getpid()}\n"
            f"as_of_date={run_date}\n"
            f"started_at={datetime.now(KST).isoformat()}\n"
        )
        os.write(fd, lock_text.encode("utf-8"))
        result = run_func(args)
        if result == 0:
            success_marker_path.write_text(f"{run_date}\n", encoding="utf-8")
        return result
    finally:
        os.close(fd)
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def _first_available_execution_report_path(path: Path) -> Path:
    if not path.exists():
        return path
    for retry_index in range(1, 1000):
        candidate = path.with_name(f"{path.stem}_retry_{retry_index}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"could not find available execution report path for {path}")


if __name__ == "__main__":
    raise SystemExit(main())
