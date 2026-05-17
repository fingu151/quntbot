from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import quote_plus


DEFAULT_QUEUE_PATH = Path("data/research_quality_review_queue.json")
DEFAULT_TICKER_BRIEF_PATH = Path("data/research_report_ticker_briefs.json")
DEFAULT_LATEST_REPORT_FOLLOWUP_PATH = Path("data/latest_report_followup_queue.json")
DEFAULT_JSON_OUTPUT_PATH = Path("data/supplemental_source_candidates.json")
DEFAULT_CSV_OUTPUT_PATH = Path("data/supplemental_source_candidates.csv")
DEFAULT_MARKDOWN_OUTPUT_PATH = Path("data/supplemental_source_candidates.md")

CSV_FIELDS = [
    "ticker",
    "name",
    "primary_action",
    "candidate_source",
    "latest_report_date",
    "missing_sections",
    "reasons",
    "source_quality",
    "confidence",
    "report_count",
    "report_age_days",
    "latest_broker",
    "latest_title",
    "latest_url",
    "search_query",
    "suggested_next_step",
]

PUBLIC_RESEARCH_SOURCE_TEMPLATES = [
    {
        "provider": "hankyung_consensus",
        "label": "Hankyung consensus list",
        "kind": "provider_list",
        "url": "https://consensus.hankyung.com/analysis/list",
    },
    {
        "provider": "mirae_asset",
        "label": "Mirae Asset research list",
        "kind": "provider_list",
        "url": "https://securities.miraeasset.com/bbs/board/message/list.do?categoryId=1533",
    },
    {
        "provider": "kiwoom_public_research",
        "label": "Kiwoom Bing report search",
        "kind": "web_search",
        "search_engine": "bing",
        "search_url_template": "https://www.bing.com/search?q={query_plus}",
        "query_template": "{name} {ticker} site:bbn.kiwoom.com rfCR",
    },
    {
        "provider": "kiwoom_public_research_naver",
        "label": "Kiwoom Naver report search",
        "kind": "web_search",
        "search_engine": "naver",
        "search_url_template": "https://search.naver.com/search.naver?query={query_plus}",
        "query_template": "{name} {ticker} site:bbn.kiwoom.com rfCR",
    },
    {
        "provider": "yuanta_pdf",
        "label": "Yuanta Bing PDF search",
        "kind": "web_search",
        "search_engine": "bing",
        "search_url_template": "https://www.bing.com/search?q={query_plus}",
        "query_template": "{name} {ticker} site:file.myasset.com pdf",
    },
    {
        "provider": "yuanta_pdf_naver",
        "label": "Yuanta Naver PDF search",
        "kind": "web_search",
        "search_engine": "naver",
        "search_url_template": "https://search.naver.com/search.naver?query={query_plus}",
        "query_template": "{name} {ticker} site:file.myasset.com pdf",
    },
    {
        "provider": "newspim_report_briefing",
        "label": "NewsPim Bing report briefing search",
        "kind": "web_search",
        "search_engine": "bing",
        "search_url_template": "https://www.bing.com/search?q={query_plus}",
        "query_template": "{name} {ticker} securities report newspim",
    },
]


def export_supplemental_source_candidates(
    *,
    queue_path: Path | str = DEFAULT_QUEUE_PATH,
    ticker_brief_path: Path | str = DEFAULT_TICKER_BRIEF_PATH,
    latest_report_followup_queue_path: Path | str | None = None,
    json_output_path: Path | str = DEFAULT_JSON_OUTPUT_PATH,
    csv_output_path: Path | str | None = DEFAULT_CSV_OUTPUT_PATH,
    markdown_output_path: Path | str | None = DEFAULT_MARKDOWN_OUTPUT_PATH,
) -> dict[str, Any]:
    queue = _read_json(queue_path)
    ticker_briefs = _read_json(ticker_brief_path)
    brief_lookup = {
        str(item.get("ticker") or ""): item
        for item in ticker_briefs.get("tickers", [])
        if isinstance(item, dict) and item.get("ticker")
    }
    candidates = [
        _candidate(item, brief_lookup.get(str(item.get("ticker") or ""), {}))
        for item in queue.get("items", [])
        if item.get("primary_action") == "supplemental_source_needed"
    ]
    if latest_report_followup_queue_path is not None:
        followup = _read_json(latest_report_followup_queue_path)
        candidates.extend(
            _latest_report_candidate(item)
            for item in followup.get("items", [])
            if item.get("primary_action") == "latest_report_not_found"
        )

    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_queue": str(queue_path),
        "source_ticker_briefs": str(ticker_brief_path),
        "source_latest_report_followup_queue": (
            str(latest_report_followup_queue_path) if latest_report_followup_queue_path is not None else ""
        ),
        "summary": {
            "candidate_count": len(candidates),
            "candidate_source_counts": _candidate_source_counts(candidates),
            "missing_section_counts": _missing_section_counts(candidates),
            "provider_count": len(PUBLIC_RESEARCH_SOURCE_TEMPLATES),
        },
        "provider_templates": PUBLIC_RESEARCH_SOURCE_TEMPLATES,
        "candidates": candidates,
    }
    json_output = Path(json_output_path)
    json_output.parent.mkdir(parents=True, exist_ok=True)
    json_output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if csv_output_path is not None:
        _write_csv(Path(csv_output_path), candidates)
    if markdown_output_path is not None:
        markdown_output = Path(markdown_output_path)
        markdown_output.parent.mkdir(parents=True, exist_ok=True)
        markdown_output.write_text(_markdown(payload), encoding="utf-8")
    return payload


def _read_json(path: Path | str) -> dict[str, Any]:
    json_path = Path(path)
    if not json_path.exists():
        return {}
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _candidate(queue_item: dict[str, Any], brief: dict[str, Any]) -> dict[str, Any]:
    ticker = str(queue_item.get("ticker") or "")
    source_reports = list(brief.get("source_reports") or [])
    latest_report = source_reports[0] if source_reports else {}
    title = str(latest_report.get("title") or brief.get("headline") or "")
    name = str(brief.get("name") or _name_from_title(title, ticker) or "")
    missing_sections = [str(section) for section in queue_item.get("missing_sections", []) if section]
    reasons = [str(reason) for reason in queue_item.get("reasons", []) if reason]
    latest_broker = str(latest_report.get("broker") or "")
    latest_url = str(latest_report.get("url") or latest_report.get("source_url") or "")
    search_query = _section_search_query(ticker=ticker, name=name, missing_sections=missing_sections)
    return {
        "ticker": ticker,
        "name": name,
        "primary_action": str(queue_item.get("primary_action") or ""),
        "candidate_source": "research_quality_review_queue",
        "latest_report_date": str(queue_item.get("latest_report_date") or ""),
        "missing_sections": missing_sections,
        "reasons": reasons,
        "source_quality": str(queue_item.get("source_quality") or ""),
        "confidence": float(queue_item.get("confidence") or 0.0),
        "report_count": int(queue_item.get("report_count") or 0),
        "report_age_days": queue_item.get("report_age_days"),
        "latest_broker": latest_broker,
        "latest_title": title,
        "latest_url": latest_url,
        "source_reports": source_reports,
        "search_query": search_query,
        "provider_searches": _provider_searches(ticker=ticker, name=name, search_query=search_query),
        "suggested_next_step": _section_next_step(missing_sections),
    }


def _latest_report_candidate(followup_item: dict[str, Any]) -> dict[str, Any]:
    ticker = str(followup_item.get("ticker") or "")
    name = str(followup_item.get("name") or "")
    search_query = str(followup_item.get("search_query") or "").strip()
    if not search_query:
        search_query = _latest_report_search_query(ticker=ticker, name=name)
    return {
        "ticker": ticker,
        "name": name,
        "primary_action": str(followup_item.get("primary_action") or ""),
        "candidate_source": "latest_report_followup_queue",
        "latest_report_date": str(followup_item.get("latest_report_date") or ""),
        "missing_sections": ["latest_report"],
        "reasons": ["latest_report_not_found"],
        "source_quality": "latest_report_not_found",
        "confidence": float(followup_item.get("confidence") or 0.0),
        "report_count": int(followup_item.get("report_count") or 0),
        "report_age_days": followup_item.get("report_age_days"),
        "latest_broker": str(followup_item.get("latest_broker") or ""),
        "latest_title": str(followup_item.get("latest_title") or ""),
        "latest_url": str(followup_item.get("latest_url") or ""),
        "source_reports": [],
        "search_query": search_query,
        "provider_searches": _provider_searches(ticker=ticker, name=name, search_query=search_query),
        "suggested_next_step": str(followup_item.get("next_step") or "")
        or "Check provider_searches for a newer public report or PDF.",
    }


def _name_from_title(title: str, ticker: str) -> str:
    marker = f"({ticker}"
    if marker in title:
        return title.split(marker, 1)[0].strip()
    if ticker and ticker in title:
        return title.replace(ticker, "").strip(" ()-/")
    return ""


def _section_search_query(*, ticker: str, name: str, missing_sections: list[str]) -> str:
    target = name or ticker
    section_terms = {
        "stock_view": "investment view",
        "growth": "growth momentum",
        "earnings": "earnings outlook",
        "risk": "risk",
    }
    terms = " ".join(section_terms.get(section, section) for section in missing_sections)
    return " ".join(part for part in [target, ticker if name else "", "securities report", terms] if part).strip()


def _latest_report_search_query(*, ticker: str, name: str) -> str:
    target = name or ticker
    return " ".join(part for part in [target, ticker if name else "", "latest securities report"] if part).strip()


def _provider_searches(*, ticker: str, name: str, search_query: str) -> list[dict[str, str]]:
    target_name = name or ticker
    searches: list[dict[str, str]] = []
    for template in PUBLIC_RESEARCH_SOURCE_TEMPLATES:
        kind = str(template.get("kind") or "")
        if kind == "web_search":
            query = str(template.get("query_template") or search_query).format(
                ticker=ticker,
                name=target_name,
                search_query=search_query,
            )
            url_template = str(template.get("search_url_template") or "https://www.bing.com/search?q={query_plus}")
            url = url_template.format(query=quote_plus(query), query_plus=quote_plus(query))
        else:
            query = search_query
            url = str(template.get("url") or "")
        searches.append(
            {
                "provider": str(template.get("provider") or ""),
                "label": str(template.get("label") or template.get("provider") or ""),
                "kind": kind,
                "search_engine": str(template.get("search_engine") or ""),
                "query": query,
                "url": url,
            }
        )
    return searches


def _section_next_step(missing_sections: list[str]) -> str:
    if missing_sections == ["risk"]:
        return "Find a source that states downside risks or assumptions."
    if "risk" in missing_sections:
        return "Find a fuller report/news source with risks plus the missing thesis sections."
    return "Find a fuller report/news source for the missing sections."


def _candidate_source_counts(candidates: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for candidate in candidates:
        source = str(candidate.get("candidate_source") or "")
        counts[source] = counts.get(source, 0) + 1
    return dict(sorted(counts.items()))


def _missing_section_counts(candidates: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for candidate in candidates:
        for section in candidate.get("missing_sections", []):
            counts[section] = counts.get(section, 0) + 1
    return dict(sorted(counts.items()))


def _write_csv(path: Path, candidates: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for candidate in candidates:
            writer.writerow({field: _csv_value(candidate.get(field)) for field in CSV_FIELDS})


def _csv_value(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    if value is None:
        return ""
    return str(value)


def _markdown(payload: dict[str, Any]) -> str:
    summary = payload.get("summary", {})
    lines = [
        "# Supplemental Source Candidates",
        "",
        f"- Candidates: {summary.get('candidate_count', 0)}",
        f"- Candidate sources: {summary.get('candidate_source_counts', {})}",
        f"- Missing sections: {summary.get('missing_section_counts', {})}",
        f"- Provider templates: {summary.get('provider_count', 0)}",
        "",
        "| Ticker | Name | Source | Missing | Confidence | Search query |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for candidate in payload.get("candidates", []):
        lines.append(
            "| "
            f"{candidate.get('ticker', '')} | "
            f"{candidate.get('name', '')} | "
            f"{candidate.get('candidate_source', '')} | "
            f"{', '.join(candidate.get('missing_sections') or [])} | "
            f"{candidate.get('confidence', 0):.2f} | "
            f"{candidate.get('search_query', '')} |"
        )
    lines.append("")
    return "\n".join(lines)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export supplemental-source candidates from quality/follow-up queues.")
    parser.add_argument("--queue", type=Path, default=DEFAULT_QUEUE_PATH)
    parser.add_argument("--ticker-briefs", type=Path, default=DEFAULT_TICKER_BRIEF_PATH)
    parser.add_argument("--latest-report-followup-queue", type=Path, default=None)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT_PATH)
    parser.add_argument("--csv-output", type=Path, default=DEFAULT_CSV_OUTPUT_PATH)
    parser.add_argument("--markdown-output", type=Path, default=DEFAULT_MARKDOWN_OUTPUT_PATH)
    parser.add_argument("--no-csv", action="store_true")
    parser.add_argument("--no-markdown", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    payload = export_supplemental_source_candidates(
        queue_path=args.queue,
        ticker_brief_path=args.ticker_briefs,
        latest_report_followup_queue_path=args.latest_report_followup_queue,
        json_output_path=args.json_output,
        csv_output_path=None if args.no_csv else args.csv_output,
        markdown_output_path=None if args.no_markdown else args.markdown_output,
    )
    summary = payload["summary"]
    print(f"supplemental_source_candidate_count={summary.get('candidate_count', 0)}")
    for source, count in summary.get("candidate_source_counts", {}).items():
        print(f"candidate_source_count.{source}={count}")
    for section, count in summary.get("missing_section_counts", {}).items():
        print(f"missing_section_count.{section}={count}")
    print(f"provider_template_count={summary.get('provider_count', 0)}")
    print(f"json_output={args.json_output}")
    if not args.no_csv:
        print(f"csv_output={args.csv_output}")
    if not args.no_markdown:
        print(f"markdown_output={args.markdown_output}")
    print("orders_submitted=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
