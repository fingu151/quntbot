from __future__ import annotations

import argparse
import csv
from collections.abc import Callable, Sequence
from datetime import date
from pathlib import Path
import sys
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.report_portfolio_research_coverage import (
    build_portfolio_research_coverage,
    load_db_counts,
)
from scripts.public_portfolio_dashboard import (
    DEFAULT_SNAPSHOT_PATH,
    DEFAULT_TICKER_RESEARCH_BRIEF_PATH,
    load_snapshot,
    load_ticker_research_briefs,
)


DEFAULT_OUTPUT_PATH = "data/supplemental_research_reports.template.csv"
TEMPLATE_FIELDS = [
    "보충상태",
    "보충필요사유",
    "부족섹션",
    "종목코드",
    "종목명",
    "발간일",
    "증권사",
    "제목",
    "원문링크",
    "투자의견",
    "목표주가",
    "핵심요약",
    "의견",
    "종목의견",
    "실적",
    "업황",
    "신사업",
    "밸류",
    "리스크",
    "근거키워드",
    "신뢰도",
]

CoverageLoader = Callable[[argparse.Namespace], dict[str, Any]]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export a prefilled supplemental research CSV for portfolio tickers needing review."
    )
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT_PATH)
    parser.add_argument("--ticker-briefs", type=Path, default=DEFAULT_TICKER_RESEARCH_BRIEF_PATH)
    parser.add_argument("--output", type=Path, default=Path(DEFAULT_OUTPUT_PATH))
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--as-of-date", default=date.today().isoformat())
    parser.add_argument("--stale-days", type=int, default=45)
    return parser.parse_args(argv)


def run(
    args: argparse.Namespace,
    *,
    coverage_loader: CoverageLoader | None = None,
) -> int:
    coverage = coverage_loader(args) if coverage_loader else load_coverage_report(args)
    rows = build_template_rows(coverage, as_of_date=args.as_of_date)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=TEMPLATE_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"supplemental_template_rows={len(rows)}")
    print(f"wrote_template={args.output}")
    print("orders_submitted=0")
    return 0


def load_coverage_report(args: argparse.Namespace) -> dict[str, Any]:
    snapshot_result = load_snapshot(args.snapshot)
    brief_result = load_ticker_research_briefs(args.ticker_briefs)
    if snapshot_result.get("status") != "ok":
        raise RuntimeError(f"snapshot_status={snapshot_result.get('status')}")
    if brief_result.get("status") != "ok":
        raise RuntimeError(f"ticker_brief_status={brief_result.get('status')}")
    snapshot = snapshot_result["snapshot"]
    tickers = [str(row.get("ticker")) for row in snapshot.get("positions", []) if row.get("ticker")]
    return build_portfolio_research_coverage(
        snapshot,
        brief_result["artifact"],
        db_counts=load_db_counts(tickers, database_url=args.database_url),
        as_of_date=args.as_of_date,
        stale_days=args.stale_days,
    )


def build_template_rows(
    coverage_report: dict[str, Any],
    *,
    as_of_date: str | None = None,
) -> list[dict[str, str]]:
    report_date = as_of_date or date.today().isoformat()
    rows: list[dict[str, str]] = []
    for item in coverage_report.get("items", []):
        status = str(item.get("status") or "")
        if status == "ok":
            continue
        rows.append(
            {
                "보충상태": status,
                "보충필요사유": ", ".join(str(reason) for reason in item.get("reasons", [])),
                "부족섹션": ", ".join(str(section) for section in item.get("missing_sections", [])),
                "종목코드": str(item.get("ticker") or ""),
                "종목명": str(item.get("name") or ""),
                "발간일": report_date,
                "증권사": "",
                "제목": "",
                "원문링크": "",
                "투자의견": "",
                "목표주가": "",
                "핵심요약": "",
                "의견": "",
                "종목의견": "",
                "실적": "",
                "업황": "",
                "신사업": "",
                "밸류": "",
                "리스크": "",
                "근거키워드": "",
                "신뢰도": "",
            }
        )
    return rows


def main(argv: Sequence[str] | None = None) -> int:
    return run(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
