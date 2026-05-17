from __future__ import annotations

import argparse
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import date
import json
from pathlib import Path
import sys
from typing import Any

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


DEFAULT_INPUT_PATH = "data/supplemental_research_reports.json"
SUPPLEMENTAL_VERSION = "supplemental-v1"

EngineFactory = Callable[[str | None], Engine]
ReportLoader = Callable[[str], list[dict[str, Any]]]


@dataclass(frozen=True)
class SupplementalReportIngestResult:
    input_count: int
    valid_count: int
    skipped_count: int
    signal_rows_stored: int
    analysis_rows_stored: int
    brief_rows_stored: int


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest manually curated supplemental research reports into the report DB."
    )
    parser.add_argument("--input", default=DEFAULT_INPUT_PATH, help="Path to supplemental report JSON.")
    parser.add_argument("--database-url", default=None)
    return parser.parse_args(argv)


def run(
    args: argparse.Namespace,
    *,
    engine_factory: EngineFactory = get_engine,
    report_loader: ReportLoader = None,
) -> int:
    loader = report_loader or load_report_rows
    reports = loader(args.input)
    engine = engine_factory(args.database_url)
    create_tables(engine)
    result = ingest_supplemental_reports(engine, reports)

    print(f"supplemental_research_report_input_count={result.input_count}")
    print(f"supplemental_research_report_valid_count={result.valid_count}")
    print(f"supplemental_research_report_skipped_count={result.skipped_count}")
    print(f"supplemental_research_report_signal_rows_stored={result.signal_rows_stored}")
    print(f"supplemental_research_report_analysis_rows_stored={result.analysis_rows_stored}")
    print(f"supplemental_research_report_brief_rows_stored={result.brief_rows_stored}")
    print("orders_submitted=0")
    return 0 if result.valid_count > 0 or result.input_count == 0 else 1


def load_report_rows(path: str) -> list[dict[str, Any]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("supplemental report JSON must be a list of objects")
    rows: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError("each supplemental report must be an object")
        rows.append(item)
    return rows


def ingest_supplemental_reports(
    engine: Engine,
    reports: Iterable[dict[str, Any]],
) -> SupplementalReportIngestResult:
    prepared_reports = list(reports)
    valid_reports = [_normalize_report(row) for row in prepared_reports]
    valid_reports = [row for row in valid_reports if row is not None]
    signal_rows = [_signal_row(row) for row in valid_reports]
    keys = [
        (row["report_date"], row["ticker"], row["source"], row["title"])
        for row in signal_rows
    ]

    with session_scope(engine) as session:
        signal_count = upsert_research_report_signals(session, signal_rows)
        signal_lookup = _signal_lookup(get_research_report_signals_by_keys(session, keys))
        analysis_rows: list[dict[str, Any]] = []
        brief_rows: list[dict[str, Any]] = []
        for row in valid_reports:
            signal = signal_lookup.get((row["report_date"], row["ticker"], row["source"], row["title"]))
            if signal is None:
                continue
            analysis_rows.append(_analysis_row(row, signal))
            brief_rows.append(_brief_row(row, signal))
        analysis_count = upsert_research_report_analyses(session, analysis_rows)
        brief_count = upsert_research_report_briefs(session, brief_rows)

    return SupplementalReportIngestResult(
        input_count=len(prepared_reports),
        valid_count=len(valid_reports),
        skipped_count=len(prepared_reports) - len(valid_reports),
        signal_rows_stored=signal_count,
        analysis_rows_stored=analysis_count,
        brief_rows_stored=brief_count,
    )


def _normalize_report(row: dict[str, Any]) -> dict[str, Any] | None:
    report_date = _parse_report_date(row.get("report_date"))
    ticker = _clean_text(row.get("ticker"))
    source = _clean_text(row.get("source")) or "supplemental_research"
    title = _clean_text(row.get("title"))
    if not report_date or not ticker or not title:
        return None
    return {
        **row,
        "report_date": report_date,
        "ticker": ticker,
        "source": source,
        "region": _clean_text(row.get("region")) or "domestic",
        "broker": _clean_text(row.get("broker")),
        "title": title,
        "source_url": _clean_text(row.get("source_url")),
        "rating": _clean_text(row.get("rating")),
        "rating_score": _optional_float(row.get("rating_score")),
        "target_price": _optional_float(row.get("target_price")),
        "previous_target_price": _optional_float(row.get("previous_target_price")),
        "target_price_change_pct": _optional_float(row.get("target_price_change_pct")),
        "sentiment_score": _optional_float(row.get("sentiment_score")),
        "raw_score": _float_or_default(row.get("raw_score"), 0.0),
        "confidence": _clamp(_float_or_default(row.get("confidence"), 0.5), 0.0, 1.0),
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


def _analysis_row(row: dict[str, Any], signal: ResearchReportSignal) -> dict[str, Any]:
    summary = _first_text(row, "summary", "headline", "title")
    return {
        "report_signal_id": signal.id,
        "ticker": signal.ticker,
        "report_date": signal.report_date,
        "source": signal.source,
        "broker": signal.broker,
        "title": signal.title,
        "source_url": signal.source_url,
        "body_text_status": _clean_text(row.get("body_text_status")) or "supplemental_summary",
        "body_text_chars": int(_optional_float(row.get("body_text_chars")) or len(summary)),
        "summary": summary,
        "investment_opinion": _clean_text(row.get("investment_opinion")) or _opinion(row),
        "buy_thesis": _clean_text(row.get("buy_thesis")) or _clean_text(row.get("stock_view")),
        "sell_or_risk_thesis": _clean_text(row.get("sell_or_risk_thesis")) or _clean_text(row.get("risks")),
        "growth_drivers": _clean_text(row.get("growth_drivers")) or _clean_text(row.get("industry")),
        "earnings_drivers": _clean_text(row.get("earnings_drivers")) or _clean_text(row.get("earnings")),
        "valuation_view": _clean_text(row.get("valuation_view")) or _clean_text(row.get("valuation")),
        "target_price_rationale": _clean_text(row.get("target_price_rationale")),
        "risk_factors": _clean_text(row.get("risk_factors")) or _clean_text(row.get("risks")),
        "evidence_terms": _clean_text(row.get("evidence_terms")),
        "analysis_version": _clean_text(row.get("analysis_version")) or SUPPLEMENTAL_VERSION,
        "confidence": row["confidence"],
    }


def _brief_row(row: dict[str, Any], signal: ResearchReportSignal) -> dict[str, Any]:
    return {
        "report_signal_id": signal.id,
        "ticker": signal.ticker,
        "report_date": signal.report_date,
        "source": signal.source,
        "broker": signal.broker,
        "title": signal.title,
        "source_url": signal.source_url,
        "report_type": _clean_text(row.get("report_type")) or "stock_report",
        "headline": _first_text(row, "headline", "summary", "title"),
        "opinion": _opinion(row),
        "stock_view": _clean_text(row.get("stock_view")) or _clean_text(row.get("buy_thesis")),
        "earnings": _clean_text(row.get("earnings")) or _clean_text(row.get("earnings_drivers")),
        "industry": _clean_text(row.get("industry")) or _clean_text(row.get("growth_drivers")),
        "new_business": _clean_text(row.get("new_business")),
        "valuation": _clean_text(row.get("valuation")) or _clean_text(row.get("valuation_view")),
        "risks": _clean_text(row.get("risks")) or _clean_text(row.get("risk_factors")),
        "source_quality": _clean_text(row.get("source_quality")) or "supplemental_summary",
        "brief_version": _clean_text(row.get("brief_version")) or SUPPLEMENTAL_VERSION,
        "confidence": row["confidence"],
    }


def _signal_lookup(signals: Iterable[ResearchReportSignal]) -> dict[tuple[date, str, str, str], ResearchReportSignal]:
    return {
        (signal.report_date, signal.ticker, signal.source, signal.title): signal
        for signal in signals
    }


def _first_text(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = _clean_text(row.get(key))
        if value:
            return value
    return "Supplemental research report."


def _opinion(row: dict[str, Any]) -> str:
    opinion = _clean_text(row.get("opinion") or row.get("investment_opinion"))
    if opinion:
        return opinion
    raw_score = row.get("raw_score") or 0.0
    if raw_score > 0.15:
        return "positive"
    if raw_score < -0.15:
        return "negative"
    return "neutral"


def _parse_report_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return date.fromisoformat(value.strip())
        except ValueError:
            return None
    return None


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _float_or_default(value: Any, default: float) -> float:
    parsed = _optional_float(value)
    return default if parsed is None else parsed


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def main(argv: Sequence[str] | None = None) -> int:
    return run(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
