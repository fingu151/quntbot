from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
import json
from pathlib import Path
import sys
from typing import Any

from sqlalchemy import Engine, case, func, select

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import DART
from src.data.database import create_tables, get_engine
from src.data.database import session_scope
from src.data.models import QualityMetric, Stock
from src.data.quality_collector import sync_phase1_quality
from src.data.quality_provider import DartFssFundamentalsProvider, _parse_quality_metric_rows
from src.data.rate_limiter import RateLimiter


SyncFunction = Callable[..., dict[str, Any]]
RateLimiterFactory = Callable[..., RateLimiter]
ProviderFactory = Callable[..., DartFssFundamentalsProvider]
DEFAULT_EXCEPTIONS_FILE = ROOT_DIR / "src" / "data" / "quality_sync_exceptions.json"


@dataclass(frozen=True)
class QualitySyncExceptions:
    financial_null_operating_margin: set[str]
    partial_source_absence: set[str]
    no_source: set[str]
    partial_metric_source_absence: set[str]
    low_debt_source_backed: set[str]


@dataclass(frozen=True)
class ValidationIssue:
    ticker: str
    name: str
    rows: int
    roe_nonnull: int
    operating_margin_nonnull: int
    debt_ratio_nonnull: int
    min_debt_ratio: float | None
    issues: list[str]


@dataclass(frozen=True)
class ValidationReport:
    coverage: tuple[int, int]
    active_count: int
    unexpected_issue_count: int
    issues: list[ValidationIssue]
    null_counts: tuple[int, int, int]
    rows_lt_8_count: int
    unsynced: list[tuple[str, str]]


class SingleAccountOnlyProvider:
    def __init__(self, base_provider: DartFssFundamentalsProvider) -> None:
        self._base_provider = base_provider

    def get_quality_metrics(
        self,
        ticker: str,
        *,
        year_from: int,
        year_to: int,
    ) -> list[dict[str, Any]]:
        corp_code = self._base_provider.stock_to_corp_code.get(ticker)
        if corp_code is None:
            return []
        payload = self._base_provider._payload_from_single_account_api(
            corp_code=corp_code,
            year_from=year_from,
            year_to=year_to,
        )
        if payload is None:
            return []
        return _parse_quality_metric_rows(
            ticker=ticker,
            payload=payload,
            year_from=year_from,
            year_to=year_to,
        )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    current_year = date.today().year
    parser = argparse.ArgumentParser(
        description="Sync Phase 1 DART quality metrics into SQLite."
    )
    parser.add_argument("--year-from", type=int, default=current_year)
    parser.add_argument("--year-to", type=int, default=current_year)
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--api-key", default=DART.api_key)
    parser.add_argument("--requests-per-minute", type=int, default=DART.requests_per_minute)
    parser.add_argument("--daily-quota", type=int, default=DART.daily_quota)
    parser.add_argument(
        "--ticker",
        dest="ticker_values",
        action="append",
        default=None,
        help="Limit sync to one ticker. Repeat for multiple tickers.",
    )
    parser.add_argument(
        "--tickers",
        dest="tickers_values",
        action="append",
        default=None,
        help="Comma-separated ticker list. Can be combined with --ticker.",
    )
    parser.add_argument("--refresh-corp-list", action="store_true", default=False)
    parser.add_argument(
        "--single-account-only",
        action="store_true",
        default=False,
        help="Use OpenDART single-account API directly instead of dart-fss full extract.",
    )
    parser.add_argument(
        "--only-unsynced",
        action="store_true",
        default=False,
        help="When no tickers are specified, sync only active stocks without quality rows.",
    )
    parser.add_argument(
        "--include-known-no-source",
        action="store_true",
        default=False,
        help="Do not exclude documented no-source tickers from --only-unsynced selection.",
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--validate", action="store_true", default=False)
    parser.add_argument("--exceptions-file", default=str(DEFAULT_EXCEPTIONS_FILE))
    args = parser.parse_args(argv)
    args.tickers = _parse_tickers(args.ticker_values, args.tickers_values)
    del args.ticker_values
    del args.tickers_values

    if args.year_from > args.year_to:
        parser.error("--year-from must be on or before --year-to")
    if args.requests_per_minute <= 0:
        parser.error("--requests-per-minute must be greater than 0")
    if args.daily_quota <= 0:
        parser.error("--daily-quota must be greater than 0")
    if args.limit is not None and args.limit <= 0:
        parser.error("--limit must be greater than 0")
    return args


def run(
    args: argparse.Namespace,
    *,
    rate_limiter_factory: RateLimiterFactory = RateLimiter,
    provider_factory: ProviderFactory = DartFssFundamentalsProvider,
    sync_func: SyncFunction = sync_phase1_quality,
) -> int:
    if not args.api_key:
        raise ValueError("DART_API_KEY is required for quality sync.")

    engine = get_engine(args.database_url)
    create_tables(engine)
    rate_limiter = rate_limiter_factory(
        requests_per_minute=args.requests_per_minute,
        daily_quota=args.daily_quota,
    )
    provider = provider_factory(
        api_key=args.api_key,
        rate_limiter=rate_limiter,
        refresh_corp_list=args.refresh_corp_list,
    )
    if args.single_account_only:
        provider = SingleAccountOnlyProvider(provider)

    exceptions = load_exception_sets(args.exceptions_file)
    tickers = args.tickers
    if tickers is None and args.only_unsynced:
        tickers = select_quality_sync_tickers(
            engine,
            only_unsynced=True,
            limit=args.limit,
            exclude_known_no_source=not args.include_known_no_source,
            exceptions=exceptions,
        )

    result = sync_func(
        engine=engine,
        provider=provider,
        year_from=args.year_from,
        year_to=args.year_to,
        tickers=tickers,
    )
    print(
        "Phase 1 quality sync complete: "
        f"status={result['status']} "
        f"metric_count={result['metric_count']}"
    )
    if args.validate:
        report = validate_quality_metrics(engine, exceptions=exceptions)
        print(
            "Quality validation: "
            f"coverage={report.coverage[0]}/{report.coverage[1]} "
            f"active={report.active_count} "
            f"unexpected_issues={report.unexpected_issue_count} "
            f"unsynced={len(report.unsynced)} "
            f"nulls={report.null_counts}"
        )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    try:
        return run(parse_args(argv))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2


def _parse_tickers(
    ticker_values: list[str] | None,
    tickers_values: list[str] | None,
) -> list[str] | None:
    values: list[str] = []
    for item in ticker_values or []:
        values.extend(part.strip() for part in item.split(","))
    for item in tickers_values or []:
        values.extend(part.strip() for part in item.split(","))
    values = [value for value in values if value]
    return values or None


def select_quality_sync_tickers(
    engine: Engine,
    *,
    only_unsynced: bool,
    limit: int | None,
    exclude_known_no_source: bool,
    exceptions: QualitySyncExceptions | None = None,
) -> list[str]:
    exceptions = exceptions or load_exception_sets()
    with session_scope(engine) as session:
        statement = select(Stock.ticker).where(Stock.is_active.is_(True)).order_by(Stock.updated_at)
        if only_unsynced:
            synced = select(QualityMetric.ticker).distinct()
            statement = statement.where(Stock.ticker.not_in(synced))
        if exclude_known_no_source:
            statement = statement.where(Stock.ticker.not_in(exceptions.no_source))
        if limit is not None:
            statement = statement.limit(limit)
        return list(session.scalars(statement))


def validate_quality_metrics(
    engine: Engine,
    *,
    exceptions: QualitySyncExceptions | None = None,
) -> ValidationReport:
    exceptions = exceptions or load_exception_sets()
    with session_scope(engine) as session:
        coverage = (
            session.scalar(select(func.count(func.distinct(QualityMetric.ticker)))) or 0,
            session.scalar(select(func.count()).select_from(QualityMetric)) or 0,
        )
        active_count = session.scalar(
            select(func.count()).select_from(Stock).where(Stock.is_active.is_(True))
        ) or 0
        null_counts = (
            session.scalar(
                select(func.count()).select_from(QualityMetric).where(QualityMetric.roe.is_(None))
            ) or 0,
            session.scalar(
                select(func.count())
                .select_from(QualityMetric)
                .where(QualityMetric.operating_margin.is_(None))
            ) or 0,
            session.scalar(
                select(func.count())
                .select_from(QualityMetric)
                .where(QualityMetric.debt_ratio.is_(None))
            ) or 0,
        )
        unsynced = session.execute(
            select(Stock.ticker, Stock.name)
            .where(Stock.is_active.is_(True))
            .where(Stock.ticker.not_in(select(QualityMetric.ticker).distinct()))
            .order_by(Stock.updated_at)
        ).all()
        grouped = session.execute(
            select(
                Stock.ticker,
                Stock.name,
                func.count(QualityMetric.ticker),
                func.sum(case((QualityMetric.roe.is_not(None), 1), else_=0)),
                func.sum(case((QualityMetric.operating_margin.is_not(None), 1), else_=0)),
                func.sum(case((QualityMetric.debt_ratio.is_not(None), 1), else_=0)),
                func.min(QualityMetric.debt_ratio),
            )
            .join(QualityMetric, QualityMetric.ticker == Stock.ticker, isouter=True)
            .where(Stock.is_active.is_(True))
            .group_by(Stock.ticker, Stock.name)
            .order_by(Stock.updated_at)
        ).all()

    issues: list[ValidationIssue] = []
    rows_lt_8_count = 0
    for ticker, name, rows, roe_count, opm_count, debt_count, min_debt in grouped:
        rows = int(rows or 0)
        roe_count = int(roe_count or 0)
        opm_count = int(opm_count or 0)
        debt_count = int(debt_count or 0)
        row_issues: list[str] = []
        if rows == 0 and ticker not in exceptions.no_source:
            row_issues.append("rows=0")
        if 0 < rows < 8:
            rows_lt_8_count += 1
            if ticker not in exceptions.partial_source_absence:
                row_issues.append(f"rows={rows}")
        if rows and ticker not in exceptions.partial_metric_source_absence:
            if roe_count != rows:
                row_issues.append(f"roe={roe_count}/{rows}")
            if debt_count != rows:
                row_issues.append(f"debt={debt_count}/{rows}")
            if opm_count != rows and ticker not in exceptions.financial_null_operating_margin:
                row_issues.append(f"opm={opm_count}/{rows}")
        if rows and (min_debt is None or min_debt < 0.05):
            if ticker not in exceptions.low_debt_source_backed:
                row_issues.append(f"min_debt={min_debt}")
        if row_issues:
            issues.append(
                ValidationIssue(
                    ticker=ticker,
                    name=name,
                    rows=rows,
                    roe_nonnull=roe_count,
                    operating_margin_nonnull=opm_count,
                    debt_ratio_nonnull=debt_count,
                    min_debt_ratio=min_debt,
                    issues=row_issues,
                )
            )
    return ValidationReport(
        coverage=coverage,
        active_count=active_count,
        unexpected_issue_count=len(issues),
        issues=issues,
        null_counts=null_counts,
        rows_lt_8_count=rows_lt_8_count,
        unsynced=list(unsynced),
    )


def load_exception_sets(path: str | Path | None = None) -> QualitySyncExceptions:
    exceptions_path = Path(path) if path is not None else DEFAULT_EXCEPTIONS_FILE
    with exceptions_path.open("r", encoding="utf-8") as file:
        raw = json.load(file)
    return QualitySyncExceptions(
        financial_null_operating_margin=set(raw.get("financial_null_operating_margin", [])),
        partial_source_absence=set(raw.get("partial_source_absence", [])),
        no_source=set(raw.get("no_source", [])),
        partial_metric_source_absence=set(raw.get("partial_metric_source_absence", [])),
        low_debt_source_backed=set(raw.get("low_debt_source_backed", [])),
    )


if __name__ == "__main__":
    raise SystemExit(main())
