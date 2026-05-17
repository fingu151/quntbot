from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable, Sequence
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import requests

from src.signals.research_report_parser import ParsedResearchReport, parse_korean_research_reports
from src.signals.research_report_reader import looks_like_research_report_pdf_url


DEFAULT_CANDIDATE_PATH = Path("data/supplemental_source_candidates.json")
DEFAULT_DISCOVERY_OUTPUT_PATH = Path("data/supplemental_source_discovery_results.json")
DEFAULT_SOURCE_DRAFT_OUTPUT_PATH = Path("data/supplemental_research_sources_draft.json")
MAX_CANDIDATES = 112
MAX_URLS_PER_CANDIDATE = 8

Fetcher = Callable[[str], dict[str, Any]]


class _LinkExtractor(HTMLParser):
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
        if url not in self.links:
            self.links.append(url)


def discover_supplemental_research_sources(
    *,
    candidate_path: Path | str = DEFAULT_CANDIDATE_PATH,
    output_path: Path | str = DEFAULT_DISCOVERY_OUTPUT_PATH,
    max_candidates: int = MAX_CANDIDATES,
    max_urls_per_candidate: int = MAX_URLS_PER_CANDIDATE,
    fetcher: Fetcher | None = None,
) -> dict[str, Any]:
    candidates_payload = _read_json(candidate_path)
    candidates = [
        item
        for item in candidates_payload.get("candidates", [])
        if isinstance(item, dict)
    ][: max(0, int(max_candidates))]
    checked_url_count = 0
    usable_source_count = 0
    results: list[dict[str, Any]] = []
    fetch = fetcher or fetch_url

    for candidate in candidates:
        checks = []
        discovered_sources = []
        for search in _candidate_searches(candidate)[: max(0, int(max_urls_per_candidate))]:
            url = str(search.get("url") or "").strip()
            if not url:
                continue
            checked_url_count += 1
            check = _check_url(candidate, search, fetch)
            checks.append(check)
            discovered_sources.extend(check.get("discovered_sources", []))
        usable_source_count += len(discovered_sources)
        results.append(
            {
                "ticker": str(candidate.get("ticker") or ""),
                "name": str(candidate.get("name") or ""),
                "latest_report_date": str(candidate.get("latest_report_date") or ""),
                "latest_title": str(candidate.get("latest_title") or ""),
                "search_query": str(candidate.get("search_query") or ""),
                "checks": checks,
                "discovered_sources": discovered_sources,
            }
        )

    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_candidates": str(candidate_path),
        "summary": {
            "candidate_count": len(candidates),
            "checked_url_count": checked_url_count,
            "usable_source_count": usable_source_count,
        },
        "results": results,
    }
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def convert_discovery_results_to_sources(
    *,
    discovery_path: Path | str = DEFAULT_DISCOVERY_OUTPUT_PATH,
    output_path: Path | str = DEFAULT_SOURCE_DRAFT_OUTPUT_PATH,
    report_date: str | None = None,
) -> list[dict[str, Any]]:
    payload = _read_json(discovery_path)
    selected_report_date = report_date or datetime.now(timezone.utc).date().isoformat()
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for result in payload.get("results", []):
        if not isinstance(result, dict):
            continue
        ticker = str(result.get("ticker") or "")
        name = str(result.get("name") or ticker)
        for source in result.get("discovered_sources", []):
            if not isinstance(source, dict):
                continue
            source_url = str(source.get("source_url") or "")
            if not ticker or not source_url:
                continue
            key = (ticker, source_url)
            if key in seen:
                continue
            seen.add(key)
            provider = str(source.get("provider") or "supplemental_public_source")
            title = str(source.get("title") or f"{name} latest public research candidate")
            rows.append(
                {
                    "report_date": str(source.get("report_date") or selected_report_date),
                    "ticker": ticker,
                    "source": provider,
                    "region": "domestic",
                    "broker": str(source.get("broker") or provider),
                    "title": title,
                    "source_url": source_url,
                    "source_type": str(source.get("source_type") or "html"),
                    "discovery_status": str(source.get("status") or ""),
                    "raw_score": float(source.get("raw_score") or 0.0),
                }
            )
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    return rows


def fetch_url(url: str) -> dict[str, Any]:
    response = requests.get(
        url,
        timeout=20,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            )
        },
    )
    content_type = response.headers.get("content-type", "")
    response.encoding = response.encoding or response.apparent_encoding or "utf-8"
    return {
        "status_code": response.status_code,
        "content_type": content_type,
        "text": response.text[:200000],
        "final_url": response.url,
    }


def _check_url(candidate: dict[str, Any], search: dict[str, Any], fetcher: Fetcher) -> dict[str, Any]:
    url = str(search.get("url") or "")
    provider = str(search.get("provider") or "")
    label = str(search.get("label") or provider)
    kind = str(search.get("kind") or "")
    try:
        response = fetcher(url)
    except Exception as exc:
        return {
            "provider": provider,
            "label": label,
            "url": url,
            "status": "fetch_failed",
            "error": str(exc),
            "discovered_sources": [],
        }

    status_code = int(response.get("status_code") or 0)
    content_type = str(response.get("content_type") or "").lower()
    text = str(response.get("text") or "")
    final_url = str(response.get("final_url") or url)
    discovered_sources: list[dict[str, Any]] = []
    is_pdf_response = status_code < 400 and (
        "pdf" in content_type or looks_like_research_report_pdf_url(final_url)
    )
    if kind == "provider_list" and status_code < 400:
        discovered_sources.extend(_matching_provider_list_sources(candidate, provider, text, final_url))
        status = "provider_list_match_found" if discovered_sources else "provider_list_reachable"
    elif kind == "reference_url" and is_pdf_response:
        discovered_sources.append(
            _source_result(candidate, provider=provider, source_url=final_url, source_type="pdf", status="reference_pdf")
        )
        status = "reference_pdf"
    elif kind == "reference_url" and status_code < 400:
        status = f"{kind}_reachable"
    elif kind in {"provider_list", "reference_url"}:
        status = "http_error"
    elif is_pdf_response:
        discovered_sources.append(
            _source_result(candidate, provider=provider, source_url=final_url, source_type="pdf", status="usable_pdf")
        )
        status = "usable_pdf"
    elif status_code < 400:
        links = (
            _extract_search_result_pdf_links(text, final_url)
            if kind == "web_search"
            else _extract_pdf_links(text, final_url)
        )
        if kind == "web_search":
            links = _filter_search_result_pdf_links(candidate, links)
        discovered_sources.extend(
            _source_result(candidate, provider=provider, source_url=link, source_type="pdf", status="linked_pdf")
            for link in links
        )
        status = "search_result_pdf_found" if kind == "web_search" and links else "linked_pdf_found" if links else "reachable_html"
    elif kind == "web_search" and status_code == 429:
        status = "search_rate_limited"
    else:
        status = "http_error"
    result = {
        "provider": provider,
        "label": label,
        "url": url,
        "final_url": final_url,
        "status_code": status_code,
        "content_type": content_type,
        "status": status,
        "discovered_sources": discovered_sources,
    }
    if kind == "web_search":
        result["query"] = str(search.get("query") or "")
        result["search_engine"] = str(search.get("search_engine") or "")
    if status == "search_rate_limited":
        result["manual_next_step"] = f"Open or retry this search manually: {url}"
    return result


def _source_result(
    candidate: dict[str, Any],
    *,
    provider: str,
    source_url: str,
    source_type: str,
    status: str,
    report: ParsedResearchReport | None = None,
) -> dict[str, Any]:
    result = {
        "provider": provider or "supplemental_public_source",
        "source_url": source_url,
        "source_type": source_type,
        "status": status,
        "ticker": str(candidate.get("ticker") or ""),
        "name": str(candidate.get("name") or ""),
    }
    if report is not None:
        result["report_date"] = report.report_date.isoformat()
        result["title"] = report.title
        result["broker"] = report.broker or provider
        result["raw_score"] = report.raw_score
    else:
        embedded_date = _embedded_url_date(source_url)
        if embedded_date:
            result["report_date"] = embedded_date
    return result


def _candidate_searches(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    searches = [
        search
        for search in candidate.get("provider_searches", [])
        if isinstance(search, dict)
    ]
    latest_url = str(candidate.get("latest_url") or "").strip()
    if latest_url:
        primary_action = str(candidate.get("primary_action") or "")
        if primary_action not in {"latest_report_not_found", "supplemental_source_needed"}:
            searches.insert(
                0,
                {
                    "provider": "latest_report_url",
                    "label": "Latest known report URL",
                    "kind": "reference_url",
                    "url": latest_url,
                },
            )
    return searches


def _extract_pdf_links(html_text: str, base_url: str) -> list[str]:
    parser = _LinkExtractor(base_url)
    parser.feed(html_text)
    parser.close()
    return [link for link in parser.links if looks_like_research_report_pdf_url(link)]


def _extract_search_result_pdf_links(html_text: str, base_url: str) -> list[str]:
    parser = _LinkExtractor(base_url)
    parser.feed(html_text)
    parser.close()
    links: list[str] = []
    for link in parser.links:
        target = _unwrap_search_result_url(link)
        if target and looks_like_research_report_pdf_url(target) and target not in links:
            links.append(target)
    return links


def _filter_search_result_pdf_links(candidate: dict[str, Any], links: list[str]) -> list[str]:
    latest_date = _iso_date_text(candidate.get("latest_report_date"))
    if not latest_date:
        return []
    filtered = []
    for link in links:
        embedded_date = _embedded_url_date(link)
        if embedded_date and embedded_date > latest_date and link not in filtered:
            filtered.append(link)
    return filtered


def _matching_provider_list_sources(
    candidate: dict[str, Any],
    provider: str,
    html_text: str,
    final_url: str,
) -> list[dict[str, Any]]:
    reports = parse_korean_research_reports(
        html_text,
        source=provider or "supplemental_public_source",
        broker=provider or None,
        base_url=final_url,
        region="domestic",
    )
    ticker = str(candidate.get("ticker") or "").strip()
    if not ticker:
        return []
    latest_date = _iso_date_text(candidate.get("latest_report_date"))
    sources: list[dict[str, Any]] = []
    for report in sorted(reports, key=lambda item: item.report_date, reverse=True):
        if report.ticker != ticker or not report.source_url:
            continue
        if latest_date and report.report_date.isoformat() <= latest_date:
            continue
        if not looks_like_research_report_pdf_url(report.source_url):
            continue
        sources.append(
            _source_result(
                candidate,
                provider=provider,
                source_url=report.source_url,
                source_type="pdf",
                status="provider_list_match",
                report=report,
            )
        )
    return sources


def _iso_date_text(value: Any) -> str:
    text = str(value or "").strip()
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return text[:10]
    return ""


def _embedded_url_date(url: str) -> str:
    parsed = urlparse(url)
    text = f"{parsed.path}/{parsed.query}"
    for match in re.finditer(r"(?<!\d)(20\d{2})[/-]?([01]\d)[/-]?([0-3]\d)(?!\d)", text):
        year, month, day = match.groups()
        if "01" <= month <= "12" and "01" <= day <= "31":
            return f"{year}-{month}-{day}"
    return ""


def _unwrap_search_result_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.path == "/url":
        query = parse_qs(parsed.query)
        for key in ("q", "url"):
            value = query.get(key, [""])[0]
            if value:
                return unquote(value)
    return url


def _read_json(path: Path | str) -> dict[str, Any]:
    json_path = Path(path)
    if not json_path.exists():
        return {}
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Discover usable URLs from supplemental source candidates.")
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATE_PATH)
    parser.add_argument("--discovery-output", type=Path, default=DEFAULT_DISCOVERY_OUTPUT_PATH)
    parser.add_argument("--source-draft-output", type=Path, default=DEFAULT_SOURCE_DRAFT_OUTPUT_PATH)
    parser.add_argument("--max-candidates", type=int, default=MAX_CANDIDATES)
    parser.add_argument("--max-urls-per-candidate", type=int, default=MAX_URLS_PER_CANDIDATE)
    parser.add_argument("--report-date", default=None)
    parser.add_argument("--skip-source-draft", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    discovery = discover_supplemental_research_sources(
        candidate_path=args.candidates,
        output_path=args.discovery_output,
        max_candidates=args.max_candidates,
        max_urls_per_candidate=args.max_urls_per_candidate,
    )
    summary = discovery["summary"]
    print(f"candidate_count={summary.get('candidate_count', 0)}")
    print(f"checked_url_count={summary.get('checked_url_count', 0)}")
    print(f"usable_source_count={summary.get('usable_source_count', 0)}")
    print(f"discovery_output={args.discovery_output}")
    if not args.skip_source_draft:
        rows = convert_discovery_results_to_sources(
            discovery_path=args.discovery_output,
            output_path=args.source_draft_output,
            report_date=args.report_date,
        )
        print(f"source_draft_count={len(rows)}")
        print(f"source_draft_output={args.source_draft_output}")
    print("orders_submitted=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
