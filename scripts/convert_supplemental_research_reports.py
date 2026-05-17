from __future__ import annotations

import argparse
import csv
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
import json
from pathlib import Path
import sys
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


DEFAULT_OUTPUT_PATH = "data/supplemental_research_reports.json"

FIELD_ALIASES = {
    "report_date": ("report_date", "date", "발간일", "리포트일", "작성일"),
    "ticker": ("ticker", "code", "종목코드", "종목", "티커"),
    "source": ("source", "출처", "소스"),
    "region": ("region", "지역"),
    "broker": ("broker", "증권사", "작성기관"),
    "title": ("title", "제목", "리포트제목", "보고서명"),
    "source_url": ("source_url", "url", "링크", "원문링크"),
    "rating": ("rating", "투자의견", "등급"),
    "rating_score": ("rating_score", "의견점수"),
    "target_price": ("target_price", "목표주가", "목표가"),
    "raw_score": ("raw_score", "점수"),
    "report_type": ("report_type", "리포트유형"),
    "headline": ("headline", "핵심요약", "한줄요약"),
    "opinion": ("opinion", "의견", "요약의견"),
    "stock_view": ("stock_view", "종목의견", "종목관점"),
    "earnings": ("earnings", "실적", "실적내용"),
    "industry": ("industry", "업황", "산업"),
    "new_business": ("new_business", "신사업", "모멘텀"),
    "valuation": ("valuation", "밸류", "밸류에이션"),
    "risks": ("risks", "리스크", "위험"),
    "summary": ("summary", "요약", "핵심내용"),
    "investment_opinion": ("investment_opinion", "투자판단"),
    "buy_thesis": ("buy_thesis", "매수근거", "긍정근거"),
    "sell_or_risk_thesis": ("sell_or_risk_thesis", "매도위험근거", "부정근거"),
    "growth_drivers": ("growth_drivers", "성장동력", "성장요인"),
    "earnings_drivers": ("earnings_drivers", "실적동력", "실적요인"),
    "valuation_view": ("valuation_view", "밸류의견"),
    "target_price_rationale": ("target_price_rationale", "목표주가근거"),
    "risk_factors": ("risk_factors", "위험요인"),
    "evidence_terms": ("evidence_terms", "근거키워드"),
    "confidence": ("confidence", "신뢰도"),
}
NUMERIC_FIELDS = {
    "rating_score",
    "target_price",
    "raw_score",
    "confidence",
}


@dataclass(frozen=True)
class SupplementalTableConvertResult:
    input_count: int
    valid_count: int
    skipped_count: int
    reports: list[dict[str, Any]] = field(default_factory=list, compare=False)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert CSV, TSV, or XLSX supplemental research rows to JSON."
    )
    parser.add_argument("--input", required=True, help="Input CSV, TSV, or XLSX file.")
    parser.add_argument("--output", default=DEFAULT_OUTPUT_PATH)
    parser.add_argument(
        "--format",
        choices=["auto", "csv", "tsv", "xlsx"],
        default="auto",
        help="Input format. Defaults to extension-based detection.",
    )
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> int:
    rows = load_table_rows(Path(args.input), file_format=args.format)
    result = convert_table_rows(rows)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result.reports, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"supplemental_table_input_count={result.input_count}")
    print(f"supplemental_table_valid_count={result.valid_count}")
    print(f"supplemental_table_skipped_count={result.skipped_count}")
    print(f"wrote_json={output_path}")
    print("orders_submitted=0")
    return 0


def load_table_rows(path: Path, *, file_format: str = "auto") -> list[dict[str, Any]]:
    resolved_format = _resolve_format(path, file_format)
    if resolved_format in {"csv", "tsv"}:
        delimiter = "\t" if resolved_format == "tsv" else ","
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle, delimiter=delimiter)]
    if resolved_format == "xlsx":
        return _load_xlsx_rows(path)
    raise ValueError(f"unsupported input format: {resolved_format}")


def convert_table_rows(rows: Iterable[dict[str, Any]]) -> SupplementalTableConvertResult:
    prepared = list(rows)
    reports: list[dict[str, Any]] = []
    for row in prepared:
        normalized = _normalize_table_row(row)
        if normalized is not None:
            reports.append(normalized)
    return SupplementalTableConvertResult(
        input_count=len(prepared),
        valid_count=len(reports),
        skipped_count=len(prepared) - len(reports),
        reports=reports,
    )


def _normalize_table_row(row: dict[str, Any]) -> dict[str, Any] | None:
    normalized = {
        canonical: _coerce_field(canonical, _first_value(row, aliases))
        for canonical, aliases in FIELD_ALIASES.items()
    }
    report_date = normalized.get("report_date")
    ticker = _normalize_ticker(normalized.get("ticker"))
    title = normalized.get("title")
    if not report_date or not ticker or not title:
        return None

    normalized["ticker"] = ticker
    normalized["source"] = normalized.get("source") or "supplemental_research"
    normalized["region"] = normalized.get("region") or "domestic"
    normalized["report_type"] = normalized.get("report_type") or "stock_report"
    if normalized.get("headline") and not normalized.get("summary"):
        normalized["summary"] = normalized["headline"]
    if normalized.get("summary") and not normalized.get("headline"):
        normalized["headline"] = normalized["summary"]
    if normalized.get("opinion") and not normalized.get("investment_opinion"):
        normalized["investment_opinion"] = normalized["opinion"]
    if normalized.get("investment_opinion") and not normalized.get("opinion"):
        normalized["opinion"] = normalized["investment_opinion"]
    if normalized.get("risks") and not normalized.get("risk_factors"):
        normalized["risk_factors"] = normalized["risks"]
    if normalized.get("risk_factors") and not normalized.get("risks"):
        normalized["risks"] = normalized["risk_factors"]
    return {key: value for key, value in normalized.items() if value not in (None, "")}


def _first_value(row: dict[str, Any], aliases: Sequence[str]) -> Any:
    lookup = {str(key).strip().lower(): value for key, value in row.items()}
    for alias in aliases:
        value = lookup.get(alias.lower())
        if _clean_text(value):
            return value
    return None


def _coerce_field(field_name: str, value: Any) -> Any:
    if field_name in NUMERIC_FIELDS:
        return _optional_float(value)
    return _clean_text(value)


def _normalize_ticker(value: Any) -> str | None:
    text = _clean_text(value)
    if not text:
        return None
    digits = "".join(ch for ch in text if ch.isdigit())
    if digits and len(digits) <= 6:
        return digits.zfill(6)
    return text


def _optional_float(value: Any) -> float | None:
    text = _clean_text(value)
    if not text:
        return None
    try:
        return float(text.replace(",", ""))
    except ValueError:
        return None


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _resolve_format(path: Path, file_format: str) -> str:
    if file_format != "auto":
        return file_format
    suffix = path.suffix.lower()
    if suffix == ".tsv":
        return "tsv"
    if suffix == ".xlsx":
        return "xlsx"
    return "csv"


def _load_xlsx_rows(path: Path) -> list[dict[str, Any]]:
    try:
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError("XLSX input requires pandas and an Excel engine such as openpyxl.") from exc
    try:
        frame = pd.read_excel(path, dtype=str).fillna("")
    except ImportError as exc:
        raise RuntimeError("XLSX input requires an Excel engine such as openpyxl.") from exc
    return [
        {str(column): value for column, value in row.items()}
        for row in frame.to_dict(orient="records")
    ]


def main(argv: Sequence[str] | None = None) -> int:
    return run(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
