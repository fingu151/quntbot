from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from datetime import date
from pathlib import Path
import sys

from sqlalchemy import Engine

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import RESEARCH_REPORT
from src.data.database import create_tables, get_engine
from src.signals.research_report_reader import (
    PdfTextTelemetry,
    fetch_and_store_korean_research_reports,
)


EngineFactory = Callable[[str | None], Engine]
ReportFetcher = Callable[..., int]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch Korean broker research report metadata and store scoring signals."
    )
    parser.add_argument("--url", default=RESEARCH_REPORT.url, help="Korean research report list URL.")
    parser.add_argument("--source", default=RESEARCH_REPORT.source)
    parser.add_argument("--broker", default=RESEARCH_REPORT.broker)
    parser.add_argument("--database-url", default=None)
    parser.add_argument(
        "--include-pdf-text",
        action="store_true",
        help="Download linked PDFs and fold body-text sentiment into the score.",
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=1,
        help="Number of public list pages to fetch when the provider supports pagination.",
    )
    parser.add_argument("--start-date", type=_parse_date, default=None)
    parser.add_argument("--end-date", type=_parse_date, default=None)
    return parser.parse_args(argv)


def run(
    args: argparse.Namespace,
    *,
    engine_factory: EngineFactory = get_engine,
    report_fetcher: ReportFetcher = fetch_and_store_korean_research_reports,
) -> int:
    engine = engine_factory(args.database_url)
    create_tables(engine)
    pdf_telemetry = PdfTextTelemetry()
    stored = report_fetcher(
        engine,
        url=args.url,
        source=args.source,
        broker=args.broker,
        include_pdf_text=args.include_pdf_text,
        pdf_telemetry=pdf_telemetry,
        pages=args.pages,
        start_date=args.start_date,
        end_date=args.end_date,
    )
    print(f"korean_research_report_rows_stored={stored}")
    print(f"pdf_text_attempted={pdf_telemetry.pdf_text_attempted}")
    print(f"pdf_text_extracted={pdf_telemetry.pdf_text_extracted}")
    print(f"pdf_text_length={pdf_telemetry.pdf_text_length}")
    print(f"body_signal_applied={pdf_telemetry.body_signal_applied}")
    print(f"analysis_rows_stored={pdf_telemetry.analysis_rows_stored}")
    print(f"analysis_success_count={pdf_telemetry.analysis_success_count}")
    print(f"analysis_failed_count={pdf_telemetry.analysis_failed_count}")
    print(f"pages_requested={args.pages}")
    print(f"start_date={args.start_date.isoformat() if args.start_date else ''}")
    print(f"end_date={args.end_date.isoformat() if args.end_date else ''}")
    print("orders_submitted=0")
    return 0 if stored > 0 else 1


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def main(argv: Sequence[str] | None = None) -> int:
    return run(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
