from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from io import BytesIO

import requests
from loguru import logger
from sqlalchemy import Engine

from src.data.database import session_scope
from src.data.repositories import (
    get_research_report_signals_by_keys,
    upsert_research_report_analyses,
    upsert_research_report_signals,
)
from src.signals.research_report_analysis import analyze_research_report_body
from src.signals.research_report_parser import (
    apply_report_body_text_signal,
    ParsedResearchReport,
    parse_korean_research_reports,
    reports_to_rows,
)


HtmlFetcher = Callable[[str], str]
PdfTextFetcher = Callable[[str], str | None]


class ResearchReportBodyUnavailable(RuntimeError):
    def __init__(self, status: str, message: str) -> None:
        super().__init__(message)
        self.status = status


@dataclass
class PdfTextTelemetry:
    pdf_text_attempted: int = 0
    pdf_text_extracted: int = 0
    pdf_text_length: int = 0
    body_signal_applied: int = 0
    analysis_rows_stored: int = 0
    analysis_success_count: int = 0
    analysis_failed_count: int = 0


def fetch_html(url: str) -> str:
    response = requests.get(url, timeout=20)
    response.raise_for_status()
    if "miraeasset.com" in url and "/bbsdocs/bbs-html/" in url:
        response.encoding = response.apparent_encoding or "cp949"
    else:
        response.encoding = response.encoding or response.apparent_encoding or "utf-8"
    return response.text


def fetch_pdf_text(url: str) -> str | None:
    try:
        from pypdf import PdfReader
    except ImportError:
        logger.warning("PDF body text fetch skipped: pypdf is not installed")
        return None

    response = requests.get(url, timeout=30)
    response.raise_for_status()
    content_type = response.headers.get("content-type", "").lower()
    if not response.content.lstrip().startswith(b"%PDF"):
        lowered_url = response.url.lower()
        lowered_text = response.text[:1000].lower()
        if "login" in lowered_url or "login" in lowered_text:
            raise ResearchReportBodyUnavailable("login_required", "PDF body requires login")
        raise ResearchReportBodyUnavailable(
            "not_pdf_response",
            f"Expected PDF response, got content_type={content_type or 'unknown'}",
        )
    reader = PdfReader(BytesIO(response.content))
    text_parts = [page.extract_text() or "" for page in reader.pages]
    text = "\n".join(part.strip() for part in text_parts if part.strip()).strip()
    return text or None


def fetch_and_store_korean_research_reports(
    engine: Engine,
    *,
    url: str,
    source: str,
    broker: str | None = None,
    html_fetcher: HtmlFetcher = fetch_html,
    include_pdf_text: bool = False,
    pdf_text_fetcher: PdfTextFetcher = fetch_pdf_text,
    pdf_telemetry: PdfTextTelemetry | None = None,
) -> int:
    try:
        html = html_fetcher(url)
    except Exception as exc:
        logger.warning(f"Korean research report fetch failed: source={source} error={exc}")
        return 0

    reports = parse_korean_research_reports(
        html,
        source=source,
        broker=broker,
        base_url=url,
        region="domestic",
    )
    telemetry = pdf_telemetry or PdfTextTelemetry()
    body_text_by_key: dict[tuple, str | None] = {}
    body_status_by_key: dict[tuple, str] = {}
    if include_pdf_text:
        enriched_reports = []
        for report in reports:
            body_text, body_status = _safe_fetch_pdf_text(
                report.source_url,
                pdf_text_fetcher,
                telemetry,
            )
            key = _report_key(report)
            body_text_by_key[key] = body_text
            body_status_by_key[key] = body_status
            enriched_report = apply_report_body_text_signal(report, body_text)
            if _body_signal_changed(report, enriched_report):
                telemetry.body_signal_applied += 1
            enriched_reports.append(enriched_report)
        reports = enriched_reports
        logger.info(
            "Research report PDF telemetry: "
            f"pdf_text_attempted={telemetry.pdf_text_attempted} "
            f"pdf_text_extracted={telemetry.pdf_text_extracted} "
            f"pdf_text_length={telemetry.pdf_text_length} "
            f"body_signal_applied={telemetry.body_signal_applied}"
        )
    else:
        for report in reports:
            body_text_by_key[_report_key(report)] = None
            body_status_by_key[_report_key(report)] = "not_requested"
    rows = reports_to_rows(reports)
    if not rows:
        logger.debug(f"No Korean research reports parsed: source={source}")
        return 0

    with session_scope(engine) as session:
        count = upsert_research_report_signals(session, rows)
        signals = get_research_report_signals_by_keys(
            session,
            (
                (row["report_date"], row["ticker"], row["source"], row["title"])
                for row in rows
            ),
        )
        analysis_rows = _analysis_rows_for_signals(
            reports,
            signals,
            body_text_by_key=body_text_by_key,
            body_status_by_key=body_status_by_key,
            telemetry=telemetry,
        )
        telemetry.analysis_rows_stored = upsert_research_report_analyses(session, analysis_rows)
    logger.info(f"Korean research reports stored: source={source} rows={count}")
    return count


def _safe_fetch_pdf_text(
    source_url: str | None,
    pdf_text_fetcher: PdfTextFetcher,
    telemetry: PdfTextTelemetry,
) -> tuple[str | None, str]:
    if not _looks_like_pdf_url(source_url):
        return None, "not_pdf"
    telemetry.pdf_text_attempted += 1
    try:
        text = pdf_text_fetcher(source_url)
    except ResearchReportBodyUnavailable as exc:
        logger.warning(f"Research report PDF text unavailable: url={source_url} status={exc.status}")
        return None, exc.status
    except Exception as exc:
        logger.warning(f"Research report PDF text fetch failed: url={source_url} error={exc}")
        return None, "fetch_failed"
    if text:
        telemetry.pdf_text_extracted += 1
        telemetry.pdf_text_length += len(text)
        return text, "extracted"
    return None, "empty"


def _analysis_rows_for_signals(
    reports: list[ParsedResearchReport],
    signals,
    *,
    body_text_by_key: dict[tuple, str | None],
    body_status_by_key: dict[tuple, str],
    telemetry: PdfTextTelemetry,
) -> list[dict[str, object]]:
    reports_by_key = {_report_key(report): report for report in reports}
    rows = []
    for signal in signals:
        key = (signal.report_date, signal.ticker, signal.source, signal.title)
        report = reports_by_key.get(key)
        if report is None:
            continue
        body_text = body_text_by_key.get(key)
        body_status = body_status_by_key.get(key, "not_requested")
        try:
            analysis = analyze_research_report_body(
                report,
                body_text,
                body_text_status=body_status,
            )
            telemetry.analysis_success_count += 1
        except Exception as exc:
            logger.warning(
                f"Research report body analysis failed: "
                f"source={signal.source} ticker={signal.ticker} error={exc}"
            )
            analysis = analyze_research_report_body(
                report,
                None,
                body_text_status="analysis_failed",
            )
            telemetry.analysis_failed_count += 1
        rows.append(
            {
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
        )
    return rows


def _report_key(report: ParsedResearchReport) -> tuple:
    return (report.report_date, report.ticker, report.source, report.title)


def _body_signal_changed(before, after) -> bool:
    fields = (
        "rating",
        "rating_score",
        "target_price",
        "previous_target_price",
        "target_price_change_pct",
        "sentiment_score",
        "raw_score",
    )
    return any(getattr(before, field) != getattr(after, field) for field in fields)


def _looks_like_pdf_url(source_url: str | None) -> bool:
    if not source_url:
        return False
    lowered = source_url.lower()
    return ".pdf" in lowered or "/pdf/" in lowered or lowered.endswith("/pdf")
