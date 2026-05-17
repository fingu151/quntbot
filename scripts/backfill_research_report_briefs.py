from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from pathlib import Path
import sys

from sqlalchemy import Engine, select

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.data.database import create_tables, get_engine, session_scope
from src.data.models import ResearchReportAnalysis, ResearchReportBrief, ResearchReportSignal
from src.data.repositories import upsert_research_report_briefs
from src.signals.research_report_briefing import ResearchReportBriefing, build_research_report_briefing
from src.signals.research_report_parser import ParsedResearchReport


EngineFactory = Callable[[str | None], Engine]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create missing research report brief rows from existing analysis rows."
    )
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def run(
    args: argparse.Namespace,
    *,
    engine_factory: EngineFactory = get_engine,
) -> int:
    engine = engine_factory(args.database_url)
    create_tables(engine)
    with session_scope(engine) as session:
        missing = _load_missing_brief_pairs(session, limit=args.limit)
        brief_rows = [_brief_row(signal, analysis) for signal, analysis in missing]
        stored = 0 if args.dry_run else upsert_research_report_briefs(session, brief_rows)

    print(f"missing_brief_rows_seen={len(missing)}")
    print(f"brief_rows_prepared={len(brief_rows)}")
    print(f"brief_rows_stored={stored}")
    print(f"dry_run={str(bool(args.dry_run)).lower()}")
    print("orders_submitted=0")
    return 0


def _load_missing_brief_pairs(session, *, limit: int | None) -> list[tuple[ResearchReportSignal, ResearchReportAnalysis]]:
    brief_signal_ids = select(ResearchReportBrief.report_signal_id)
    statement = (
        select(ResearchReportSignal, ResearchReportAnalysis)
        .join(
            ResearchReportAnalysis,
            ResearchReportAnalysis.report_signal_id == ResearchReportSignal.id,
        )
        .where(ResearchReportSignal.id.not_in(brief_signal_ids))
        .order_by(ResearchReportSignal.report_date.desc(), ResearchReportSignal.ticker.asc())
    )
    if limit is not None:
        statement = statement.limit(max(0, limit))
    return list(session.execute(statement).all())


def _brief_row(signal: ResearchReportSignal, analysis: ResearchReportAnalysis) -> dict[str, object]:
    report = ParsedResearchReport(
        report_date=signal.report_date,
        ticker=signal.ticker,
        source=signal.source,
        region=signal.region,
        broker=signal.broker,
        rating=signal.rating,
        rating_score=signal.rating_score,
        target_price=signal.target_price,
        previous_target_price=signal.previous_target_price,
        target_price_change_pct=signal.target_price_change_pct,
        sentiment_score=signal.sentiment_score,
        raw_score=signal.raw_score,
        title=signal.title,
        source_url=signal.source_url,
    )
    try:
        briefing = build_research_report_briefing(report, None, analysis)
    except Exception:
        briefing = _fallback_briefing(report, analysis)
    return {
        "report_signal_id": signal.id,
        "ticker": signal.ticker,
        "report_date": signal.report_date,
        "source": signal.source,
        "broker": signal.broker,
        "title": signal.title,
        "source_url": signal.source_url,
        "report_type": briefing.report_type,
        "headline": briefing.headline,
        "opinion": briefing.opinion,
        "stock_view": briefing.stock_view,
        "earnings": briefing.earnings,
        "industry": briefing.industry,
        "new_business": briefing.new_business,
        "valuation": briefing.valuation,
        "risks": briefing.risks,
        "source_quality": briefing.source_quality,
        "brief_version": briefing.brief_version,
        "confidence": briefing.confidence,
    }


def _fallback_briefing(report: ParsedResearchReport, analysis: ResearchReportAnalysis) -> ResearchReportBriefing:
    return ResearchReportBriefing(
        report_type="stock_report",
        headline=analysis.summary or f"{report.ticker}: {report.title}",
        opinion=analysis.investment_opinion,
        stock_view=analysis.buy_thesis,
        earnings=analysis.earnings_drivers,
        industry=analysis.growth_drivers,
        new_business="",
        valuation=analysis.valuation_view or analysis.target_price_rationale,
        risks=analysis.risk_factors or analysis.sell_or_risk_thesis,
        source_quality=analysis.body_text_status or "brief_failed",
        brief_version="brief-backfill-v1",
        confidence=max(0.0, min(1.0, float(analysis.confidence or 0.0) - 0.05)),
    )


def main(argv: Sequence[str] | None = None) -> int:
    return run(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
