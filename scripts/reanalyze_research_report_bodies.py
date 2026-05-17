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
from src.data.models import ResearchReportSignal
from src.data.repositories import upsert_research_report_analyses, upsert_research_report_briefs
from src.signals.research_report_analysis import analyze_research_report_body
from src.signals.research_report_briefing import ResearchReportBriefing, build_research_report_briefing
from src.signals.research_report_reader import (
    PdfTextFetcher,
    PdfTextTelemetry,
    ResearchReportBodyUnavailable,
    fetch_pdf_text,
    looks_like_research_report_pdf_url,
)


EngineFactory = Callable[[str | None], Engine]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Re-fetch stored research report PDFs and refresh body-analysis rows."
    )
    parser.add_argument("--source", default="mirae_asset")
    parser.add_argument("--broker", default="미래에셋증권")
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--ticker",
        action="append",
        default=[],
        help="Restrict reanalysis to one ticker. Repeat for multiple tickers.",
    )
    return parser.parse_args(argv)


def run(
    args: argparse.Namespace,
    *,
    engine_factory: EngineFactory = get_engine,
    pdf_text_fetcher: PdfTextFetcher = fetch_pdf_text,
    pdf_telemetry: PdfTextTelemetry | None = None,
) -> int:
    engine = engine_factory(args.database_url)
    create_tables(engine)
    telemetry = pdf_telemetry or PdfTextTelemetry()
    with session_scope(engine) as session:
        signals = _load_signals(
            session,
            source=args.source,
            broker=args.broker,
            limit=args.limit,
            tickers=args.ticker,
        )
        analysis_rows = []
        brief_rows = []
        for signal in signals:
            analysis_row, brief_row = _rows_for_signal(signal, pdf_text_fetcher, telemetry)
            analysis_rows.append(analysis_row)
            brief_rows.append(brief_row)
        telemetry.analysis_rows_stored = upsert_research_report_analyses(
            session,
            analysis_rows,
        )
        brief_rows_stored = upsert_research_report_briefs(session, brief_rows)

    print(f"research_report_rows_seen={len(signals)}")
    print(f"pdf_text_attempted={telemetry.pdf_text_attempted}")
    print(f"pdf_text_extracted={telemetry.pdf_text_extracted}")
    print(f"pdf_text_length={telemetry.pdf_text_length}")
    print(f"analysis_rows_stored={telemetry.analysis_rows_stored}")
    print(f"brief_rows_stored={brief_rows_stored}")
    print(f"analysis_success_count={telemetry.analysis_success_count}")
    print(f"analysis_failed_count={telemetry.analysis_failed_count}")
    print("orders_submitted=0")
    return 0 if signals else 1


def _load_signals(
    session,
    *,
    source: str,
    broker: str | None,
    limit: int | None,
    tickers: Sequence[str] | None = None,
) -> list[ResearchReportSignal]:
    normalized_tickers = sorted({str(ticker).strip() for ticker in (tickers or []) if str(ticker).strip()})
    statement = (
        select(ResearchReportSignal)
        .where(ResearchReportSignal.source == source)
        .order_by(ResearchReportSignal.report_date.desc(), ResearchReportSignal.ticker.asc())
    )
    if broker:
        statement = statement.where(ResearchReportSignal.broker == broker)
    if normalized_tickers:
        statement = statement.where(ResearchReportSignal.ticker.in_(normalized_tickers))
    if limit is not None:
        statement = statement.limit(max(0, limit))
    return list(session.scalars(statement).all())


def _analysis_row_for_signal(
    signal: ResearchReportSignal,
    pdf_text_fetcher: PdfTextFetcher,
    telemetry: PdfTextTelemetry,
) -> dict[str, object]:
    body_text, body_status = _fetch_body_text(signal.source_url, pdf_text_fetcher, telemetry)
    report = _signal_as_report(signal)
    try:
        analysis = analyze_research_report_body(
            report,
            body_text,
            body_text_status=body_status,
        )
        telemetry.analysis_success_count += 1
    except Exception:
        analysis = analyze_research_report_body(
            report,
            None,
            body_text_status="analysis_failed",
        )
        telemetry.analysis_failed_count += 1
    return {
        "report_signal_id": signal.id,
        "ticker": signal.ticker,
        "report_date": signal.report_date,
        "source": signal.source,
        "broker": signal.broker,
        "title": signal.title,
        "source_url": signal.source_url,
        "body_text_status": analysis.body_text_status,
        "body_text_chars": analysis.body_text_chars,
        "summary": analysis.summary,
        "investment_opinion": analysis.investment_opinion,
        "buy_thesis": analysis.buy_thesis,
        "sell_or_risk_thesis": analysis.sell_or_risk_thesis,
        "growth_drivers": analysis.growth_drivers,
        "earnings_drivers": analysis.earnings_drivers,
        "valuation_view": analysis.valuation_view,
        "target_price_rationale": analysis.target_price_rationale,
        "risk_factors": analysis.risk_factors,
        "evidence_terms": analysis.evidence_terms,
        "analysis_version": analysis.analysis_version,
        "confidence": analysis.confidence,
    }


def _rows_for_signal(
    signal: ResearchReportSignal,
    pdf_text_fetcher: PdfTextFetcher,
    telemetry: PdfTextTelemetry,
) -> tuple[dict[str, object], dict[str, object]]:
    body_text, body_status = _fetch_body_text(signal.source_url, pdf_text_fetcher, telemetry)
    report = _signal_as_report(signal)
    try:
        analysis = analyze_research_report_body(
            report,
            body_text,
            body_text_status=body_status,
        )
        telemetry.analysis_success_count += 1
    except Exception:
        analysis = analyze_research_report_body(
            report,
            None,
            body_text_status="analysis_failed",
        )
        telemetry.analysis_failed_count += 1
    try:
        briefing = build_research_report_briefing(report, body_text, analysis)
    except Exception:
        briefing = _fallback_briefing(report, analysis)
    analysis_row = {
        "report_signal_id": signal.id,
        "ticker": signal.ticker,
        "report_date": signal.report_date,
        "source": signal.source,
        "broker": signal.broker,
        "title": signal.title,
        "source_url": signal.source_url,
        "body_text_status": analysis.body_text_status,
        "body_text_chars": analysis.body_text_chars,
        "summary": analysis.summary,
        "investment_opinion": analysis.investment_opinion,
        "buy_thesis": analysis.buy_thesis,
        "sell_or_risk_thesis": analysis.sell_or_risk_thesis,
        "growth_drivers": analysis.growth_drivers,
        "earnings_drivers": analysis.earnings_drivers,
        "valuation_view": analysis.valuation_view,
        "target_price_rationale": analysis.target_price_rationale,
        "risk_factors": analysis.risk_factors,
        "evidence_terms": analysis.evidence_terms,
        "analysis_version": analysis.analysis_version,
        "confidence": analysis.confidence,
    }
    brief_row = {
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
    return analysis_row, brief_row


def _fallback_briefing(report, analysis) -> ResearchReportBriefing:
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
        source_quality="brief_failed",
        brief_version="brief-rule-v3-fallback",
        confidence=max(0.0, min(1.0, float(analysis.confidence or 0.0) - 0.1)),
    )


def _fetch_body_text(
    source_url: str | None,
    pdf_text_fetcher: PdfTextFetcher,
    telemetry: PdfTextTelemetry,
) -> tuple[str | None, str]:
    if not looks_like_research_report_pdf_url(source_url):
        return None, "not_pdf"
    telemetry.pdf_text_attempted += 1
    try:
        text = pdf_text_fetcher(source_url)
    except ResearchReportBodyUnavailable as exc:
        return None, exc.status
    except Exception:
        return None, "fetch_failed"
    if text:
        telemetry.pdf_text_extracted += 1
        telemetry.pdf_text_length += len(text)
        return text, "extracted"
    return None, "empty"


def _signal_as_report(signal: ResearchReportSignal):
    from src.signals.research_report_parser import ParsedResearchReport

    return ParsedResearchReport(
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


def main(argv: Sequence[str] | None = None) -> int:
    return run(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
