from __future__ import annotations

import argparse
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from html.parser import HTMLParser
import json
from pathlib import Path
import sys
from typing import Any
from urllib.parse import urljoin

from sqlalchemy import Engine

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.data.database import create_tables, get_engine, session_scope
from src.data.models import ResearchReportSignal
from src.data.repositories import (
    get_research_report_signals_by_keys,
    upsert_research_report_analyses,
    upsert_research_report_briefs,
    upsert_research_report_signals,
)
from src.signals.research_report_analysis import analyze_research_report_body
from src.signals.research_report_briefing import build_research_report_briefing
from src.signals.research_report_parser import ParsedResearchReport
from src.signals.research_report_reader import fetch_html, fetch_pdf_text, looks_like_research_report_pdf_url


DEFAULT_INPUT_PATH = "data/supplemental_research_sources.json"
SUPPLEMENTAL_SOURCE_VERSION = "supplemental-source-v1"
MAX_SOURCE_TEXT_CHARS = 30000

EngineFactory = Callable[[str | None], Engine]
SourceLoader = Callable[[str], list[dict[str, Any]]]
TextFetcher = Callable[[dict[str, Any]], str | None]


@dataclass(frozen=True)
class SupplementalSourceIngestResult:
    input_count: int
    valid_count: int
    skipped_count: int
    signal_rows_stored: int
    analysis_rows_stored: int
    brief_rows_stored: int


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if text:
            self.parts.append(text)

    def text(self) -> str:
        return " ".join(self.parts)


class _PdfLinkExtractor(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        attr_map = {name.lower(): value for name, value in attrs if value}
        href = attr_map.get("href")
        if not href:
            return
        url = urljoin(self.base_url, href)
        if looks_like_research_report_pdf_url(url) and url not in self.links:
            self.links.append(url)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch configured public research URLs and store supplemental report briefs."
    )
    parser.add_argument("--input", default=DEFAULT_INPUT_PATH)
    parser.add_argument("--database-url", default=None)
    return parser.parse_args(argv)


def run(
    args: argparse.Namespace,
    *,
    engine_factory: EngineFactory = get_engine,
    source_loader: SourceLoader | None = None,
    text_fetcher: TextFetcher | None = None,
) -> int:
    loader = source_loader or load_sources
    sources = loader(args.input)
    engine = engine_factory(args.database_url)
    create_tables(engine)
    result = ingest_supplemental_research_sources(
        engine,
        sources,
        text_fetcher=text_fetcher or fetch_source_text,
    )
    print(f"supplemental_source_input_count={result.input_count}")
    print(f"supplemental_source_valid_count={result.valid_count}")
    print(f"supplemental_source_skipped_count={result.skipped_count}")
    print(f"supplemental_source_signal_rows_stored={result.signal_rows_stored}")
    print(f"supplemental_source_analysis_rows_stored={result.analysis_rows_stored}")
    print(f"supplemental_source_brief_rows_stored={result.brief_rows_stored}")
    print("orders_submitted=0")
    return 0 if result.valid_count > 0 or result.input_count == 0 else 1


def load_sources(path: str) -> list[dict[str, Any]]:
    source_path = Path(path)
    if not source_path.exists():
        return []
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("supplemental research source JSON must be a list")
    return [item for item in payload if isinstance(item, dict)]


def ingest_supplemental_research_sources(
    engine: Engine,
    sources: Iterable[dict[str, Any]],
    *,
    text_fetcher: TextFetcher | None = None,
) -> SupplementalSourceIngestResult:
    prepared = list(sources)
    normalized = [_normalize_source(source) for source in prepared]
    valid_sources = [source for source in normalized if source is not None]
    signal_rows = [_signal_row(source) for source in valid_sources]
    keys = [
        (row["report_date"], row["ticker"], row["source"], row["title"])
        for row in signal_rows
    ]
    body_texts: dict[tuple[date, str, str, str], str] = {}
    fetcher = text_fetcher or fetch_source_text
    for source in valid_sources:
        key = (source["report_date"], source["ticker"], source["source"], source["title"])
        inline_body_text = _clean_text(source.get("body_text"))
        if inline_body_text:
            body_texts[key] = inline_body_text[:MAX_SOURCE_TEXT_CHARS]
            continue
        try:
            body_texts[key] = fetcher(source) or ""
        except Exception:
            body_texts[key] = ""
    with session_scope(engine) as session:
        signal_count = upsert_research_report_signals(session, signal_rows)
        signals = get_research_report_signals_by_keys(session, keys)
        signal_lookup = _signal_lookup(signals)
        analysis_rows: list[dict[str, Any]] = []
        brief_rows: list[dict[str, Any]] = []
        for source in valid_sources:
            signal = signal_lookup.get((source["report_date"], source["ticker"], source["source"], source["title"]))
            if signal is None:
                continue
            body_text = body_texts.get((source["report_date"], source["ticker"], source["source"], source["title"]), "")
            analysis_row, brief_row = _rows_for_signal(source, signal, body_text)
            analysis_rows.append(analysis_row)
            brief_rows.append(brief_row)
        analysis_count = upsert_research_report_analyses(session, analysis_rows)
        brief_count = upsert_research_report_briefs(session, brief_rows)
    return SupplementalSourceIngestResult(
        input_count=len(prepared),
        valid_count=len(valid_sources),
        skipped_count=len(prepared) - len(valid_sources),
        signal_rows_stored=signal_count,
        analysis_rows_stored=analysis_count,
        brief_rows_stored=brief_count,
    )


def fetch_source_text(source: dict[str, Any]) -> str | None:
    url = str(source.get("source_url") or "").strip()
    if not url:
        return None
    source_type = str(source.get("source_type") or "").strip().lower()
    if source_type == "pdf" or looks_like_research_report_pdf_url(url):
        text = fetch_pdf_text(url)
        return _limit_text(text)
    html_text = fetch_html(url)
    parser = _TextExtractor()
    parser.feed(html_text)
    parser.close()
    parts = [parser.text()]
    for pdf_url in _extract_pdf_links(html_text, url)[:3]:
        try:
            pdf_text = fetch_pdf_text(pdf_url)
        except Exception:
            pdf_text = None
        if pdf_text:
            parts.append(pdf_text)
    return _limit_text("\n".join(part for part in parts if part))


def _extract_pdf_links(html_text: str, base_url: str) -> list[str]:
    parser = _PdfLinkExtractor(base_url)
    parser.feed(html_text)
    parser.close()
    return parser.links


def _normalize_source(row: dict[str, Any]) -> dict[str, Any] | None:
    report_date = _parse_date(row.get("report_date"))
    ticker = _normalize_ticker(row.get("ticker"))
    title = _clean_text(row.get("title"))
    source_url = _clean_text(row.get("source_url"))
    if not report_date or not ticker or not title or not source_url:
        return None
    return {
        **row,
        "report_date": report_date,
        "ticker": ticker,
        "source": _clean_text(row.get("source")) or "supplemental_public_source",
        "region": _clean_text(row.get("region")) or "domestic",
        "broker": _clean_text(row.get("broker")),
        "title": title,
        "source_url": source_url,
        "rating": _clean_text(row.get("rating")),
        "rating_score": _optional_float(row.get("rating_score")),
        "target_price": _optional_float(row.get("target_price")),
        "previous_target_price": _optional_float(row.get("previous_target_price")),
        "target_price_change_pct": _optional_float(row.get("target_price_change_pct")),
        "sentiment_score": _optional_float(row.get("sentiment_score")),
        "raw_score": _float_or_default(row.get("raw_score"), 0.0),
    }


def _signal_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "report_date": row["report_date"],
        "ticker": row["ticker"],
        "source": row["source"],
        "region": row["region"],
        "broker": row["broker"],
        "rating": row["rating"],
        "rating_score": row["rating_score"],
        "target_price": row["target_price"],
        "previous_target_price": row["previous_target_price"],
        "target_price_change_pct": row["target_price_change_pct"],
        "sentiment_score": row["sentiment_score"],
        "raw_score": row["raw_score"],
        "title": row["title"],
        "source_url": row["source_url"],
    }


def _rows_for_signal(
    source: dict[str, Any],
    signal: ResearchReportSignal,
    body_text: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    report = _signal_as_report(signal)
    body_status = "extracted" if body_text else "empty"
    analysis = analyze_research_report_body(report, body_text, body_text_status=body_status)
    briefing = build_research_report_briefing(report, body_text, analysis)
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
        "analysis_version": SUPPLEMENTAL_SOURCE_VERSION,
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


def _signal_as_report(signal: ResearchReportSignal) -> ParsedResearchReport:
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


def _signal_lookup(signals: Iterable[ResearchReportSignal]) -> dict[tuple[date, str, str, str], ResearchReportSignal]:
    return {
        (signal.report_date, signal.ticker, signal.source, signal.title): signal
        for signal in signals
    }


def _parse_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    text = _clean_text(value)
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _normalize_ticker(value: Any) -> str | None:
    text = _clean_text(value)
    if not text:
        return None
    digits = "".join(ch for ch in text if ch.isdigit())
    if digits and len(digits) <= 6:
        return digits.zfill(6)
    return text


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_float(value: Any) -> float | None:
    text = _clean_text(value)
    if not text:
        return None
    try:
        return float(text.replace(",", ""))
    except ValueError:
        return None


def _float_or_default(value: Any, default: float) -> float:
    parsed = _optional_float(value)
    return default if parsed is None else parsed


def _limit_text(text: str | None) -> str | None:
    if not text:
        return text
    return text[:MAX_SOURCE_TEXT_CHARS]


def main(argv: Sequence[str] | None = None) -> int:
    return run(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
