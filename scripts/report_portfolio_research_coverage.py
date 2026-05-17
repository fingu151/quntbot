from __future__ import annotations

import argparse
from datetime import date, datetime
import json
from pathlib import Path
from typing import Any, Sequence

from sqlalchemy import func, select

from config import DATABASE_URL
from scripts.public_portfolio_dashboard import (
    DEFAULT_SNAPSHOT_PATH,
    DEFAULT_TICKER_RESEARCH_BRIEF_PATH,
    load_snapshot,
    load_ticker_research_briefs,
)
from src.data.database import get_engine, session_scope
from src.data.models import ResearchReportAnalysis, ResearchReportBrief, ResearchReportSignal


def build_portfolio_research_coverage(
    snapshot: dict[str, Any],
    ticker_brief_artifact: dict[str, Any],
    *,
    db_counts: dict[str, dict[str, int]] | None = None,
    as_of_date: str | date | None = None,
    stale_days: int = 45,
) -> dict[str, Any]:
    positions = [row for row in snapshot.get("positions", []) if row.get("ticker")]
    by_ticker = {
        str(row.get("ticker")): row
        for row in ticker_brief_artifact.get("tickers", [])
        if isinstance(row, dict) and row.get("ticker")
    }
    counts = db_counts or {}
    reference = _as_date(as_of_date) or date.today()

    items: list[dict[str, Any]] = []
    required_sections = ("stock_view", "growth", "earnings", "risk")
    for position in positions:
        ticker = str(position.get("ticker"))
        brief = by_ticker.get(ticker)
        ticker_counts = counts.get(ticker, {})
        if not brief:
            status = "missing_brief"
            age_days = None
            missing_sections = list(required_sections)
            reasons = ["missing_brief"]
            source_quality = ""
            confidence = 0.0
        else:
            latest = _as_date(brief.get("latest_report_date"))
            age_days = (reference - latest).days if latest else None
            sections = brief.get("sections") or {}
            quality = brief.get("quality") or {}
            missing_sections = [
                section for section in required_sections if not str(sections.get(section) or "").strip()
            ]
            source_quality = str(quality.get("source_quality") or "")
            confidence = float(quality.get("confidence") or 0.0)
            reasons = []
            if missing_sections:
                reasons.append("missing_sections")
            if age_days is not None and age_days > stale_days:
                reasons.append("stale_report")
            if confidence < 0.5:
                reasons.append("low_confidence")
            if source_quality not in {"full_text", "partial_text"}:
                reasons.append("weak_source_quality")
            if "stale_report" in reasons:
                status = "stale_brief"
            elif reasons:
                status = "needs_review"
            else:
                status = "ok"
        items.append(
            {
                "ticker": ticker,
                "name": str(position.get("name") or ""),
                "status": status,
                "latest_report_date": str(brief.get("latest_report_date") or "") if brief else "",
                "report_age_days": age_days,
                "db_counts": {
                    "signals": int(ticker_counts.get("signals", 0)),
                    "analyses": int(ticker_counts.get("analyses", 0)),
                    "briefs": int(ticker_counts.get("briefs", 0)),
                },
                "report_count": int((brief.get("quality") or {}).get("report_count", 0)) if brief else 0,
                "missing_sections": missing_sections,
                "reasons": reasons,
                "source_quality": source_quality,
                "confidence": confidence,
            }
        )

    priority = {"missing_brief": 0, "stale_brief": 1, "needs_review": 2, "ok": 3}
    items.sort(key=lambda item: (priority.get(item["status"], 9), item["ticker"]))
    summary = {
        "holding_count": len(items),
        "matched_brief_count": sum(1 for item in items if item["status"] != "missing_brief"),
        "missing_brief_count": sum(1 for item in items if item["status"] == "missing_brief"),
        "stale_brief_count": sum(1 for item in items if item["status"] == "stale_brief"),
        "needs_review_count": sum(1 for item in items if item["status"] == "needs_review"),
        "clean_count": sum(1 for item in items if item["status"] == "ok"),
    }
    return {"summary": summary, "items": items}


def load_db_counts(tickers: list[str], *, database_url: str | None = None) -> dict[str, dict[str, int]]:
    engine = get_engine(database_url or DATABASE_URL)
    result = {ticker: {"signals": 0, "analyses": 0, "briefs": 0} for ticker in tickers}
    with session_scope(engine) as session:
        for model, key in (
            (ResearchReportSignal, "signals"),
            (ResearchReportAnalysis, "analyses"),
            (ResearchReportBrief, "briefs"),
        ):
            rows = session.execute(
                select(model.ticker, func.count()).where(model.ticker.in_(tickers)).group_by(model.ticker)
            ).all()
            for ticker, count in rows:
                result[str(ticker)][key] = int(count)
    return result


def _as_date(value: str | date | object | None) -> date | None:
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text[:10]).date()
    except ValueError:
        return None


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report research brief coverage for current holdings.")
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT_PATH)
    parser.add_argument("--ticker-briefs", type=Path, default=DEFAULT_TICKER_RESEARCH_BRIEF_PATH)
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--as-of-date", default=date.today().isoformat())
    parser.add_argument("--stale-days", type=int, default=45)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    snapshot_result = load_snapshot(args.snapshot)
    brief_result = load_ticker_research_briefs(args.ticker_briefs)
    if snapshot_result.get("status") != "ok":
        print(f"snapshot_status={snapshot_result.get('status')}")
        return 1
    if brief_result.get("status") != "ok":
        print(f"ticker_brief_status={brief_result.get('status')}")
        return 1

    snapshot = snapshot_result["snapshot"]
    tickers = [str(row.get("ticker")) for row in snapshot.get("positions", []) if row.get("ticker")]
    report = build_portfolio_research_coverage(
        snapshot,
        brief_result["artifact"],
        db_counts=load_db_counts(tickers, database_url=args.database_url),
        as_of_date=args.as_of_date,
        stale_days=args.stale_days,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("summary=" + json.dumps(report["summary"], ensure_ascii=False))
        for item in report["items"]:
            print(
                "ticker={ticker} name={name} status={status} latest={latest_report_date} "
                "age={report_age_days} signals={signals} analyses={analyses} briefs={briefs}".format(
                    **item,
                    **item["db_counts"],
                )
            )
    print("orders_submitted=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
