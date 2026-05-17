from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


DEFAULT_TICKER_BRIEF_PATH = Path("data/research_report_ticker_briefs.json")
DEFAULT_QUEUE_PATH = Path("data/research_quality_review_queue.json")
DEFAULT_JSON_OUTPUT_PATH = Path("data/research_brief_qa_sample.json")
DEFAULT_MARKDOWN_OUTPUT_PATH = Path("data/research_brief_qa_sample.md")


def export_research_brief_qa_sample(
    *,
    ticker_brief_path: Path | str = DEFAULT_TICKER_BRIEF_PATH,
    queue_path: Path | str = DEFAULT_QUEUE_PATH,
    json_output_path: Path | str = DEFAULT_JSON_OUTPUT_PATH,
    markdown_output_path: Path | str | None = DEFAULT_MARKDOWN_OUTPUT_PATH,
    sample_size: int = 12,
) -> dict[str, Any]:
    artifact = _read_json(ticker_brief_path)
    queue = _read_json(queue_path)
    queue_lookup = {
        str(item.get("ticker") or ""): item
        for item in queue.get("items", [])
        if isinstance(item, dict) and item.get("ticker")
    }
    ticker_rows = [row for row in artifact.get("tickers", []) if isinstance(row, dict)]
    issue_rows = [
        _qa_item(row, queue_lookup.get(str(row.get("ticker") or ""), {}))
        for row in ticker_rows
        if str(row.get("ticker") or "") in queue_lookup
    ]
    complete_rows = [
        _qa_item(row, {})
        for row in ticker_rows
        if str(row.get("ticker") or "") not in queue_lookup
    ]
    issue_rows.sort(key=lambda item: (-int(item.get("report_age_days") or 0), item["ticker"]))
    complete_rows.sort(key=lambda item: (-int(item.get("report_count") or 0), item["ticker"]))
    issue_count = min(len(issue_rows), max(1, sample_size // 3))
    items = issue_rows[:issue_count] + complete_rows[: max(0, sample_size - issue_count)]
    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_ticker_briefs": str(ticker_brief_path),
        "source_queue": str(queue_path),
        "summary": {
            "sample_count": len(items),
            "issue_sample_count": sum(1 for item in items if item["qa_bucket"] != "complete"),
            "complete_sample_count": sum(1 for item in items if item["qa_bucket"] == "complete"),
            "auto_flag_count": sum(1 for item in items if item.get("issue_category")),
            "needs_source_refresh_count": sum(1 for item in items if item.get("needs_source_refresh")),
            "needs_section_rewrite_count": sum(1 for item in items if item.get("needs_section_rewrite")),
        },
        "items": items,
    }
    output = Path(json_output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if markdown_output_path is not None:
        markdown = Path(markdown_output_path)
        markdown.parent.mkdir(parents=True, exist_ok=True)
        markdown.write_text(_markdown(payload), encoding="utf-8")
    return payload


def _read_json(path: Path | str) -> dict[str, Any]:
    json_path = Path(path)
    if not json_path.exists():
        return {}
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _qa_item(row: dict[str, Any], queue_item: dict[str, Any]) -> dict[str, Any]:
    quality = row.get("quality") or {}
    sections = row.get("sections") or {}
    source_reports = list(row.get("source_reports") or [])
    primary_action = str(queue_item.get("primary_action") or "complete")
    section_values = {
        "stock_view": str(sections.get("stock_view") or ""),
        "growth": str(sections.get("growth") or sections.get("industry") or ""),
        "earnings": str(sections.get("earnings") or ""),
        "valuation": str(sections.get("valuation") or ""),
        "new_business": str(sections.get("new_business") or ""),
        "risk": str(sections.get("risk") or ""),
    }
    auto_qa = _auto_qa_flags(
        headline=str(row.get("headline") or ""),
        sections=section_values,
        source_quality=str(quality.get("source_quality") or ""),
        qa_bucket=primary_action,
    )
    return {
        "ticker": str(row.get("ticker") or ""),
        "qa_bucket": primary_action,
        "latest_report_date": str(row.get("latest_report_date") or ""),
        "opinion": str(row.get("opinion") or ""),
        "headline": str(row.get("headline") or ""),
        "sections": section_values,
        "quality": {
            "source_quality": str(quality.get("source_quality") or ""),
            "confidence": float(quality.get("confidence") or 0.0),
            "report_count": int(quality.get("report_count") or 0),
            "llm_status": str(quality.get("llm_status") or ""),
        },
        "queue": {
            "reasons": list(queue_item.get("reasons") or []),
            "missing_sections": list(queue_item.get("missing_sections") or []),
            "report_age_days": queue_item.get("report_age_days"),
            "next_step": str(queue_item.get("next_step") or ""),
        },
        "source_reports": source_reports[:3],
        "review_status": "",
        "issue_category": auto_qa["issue_category"],
        "needs_source_refresh": auto_qa["needs_source_refresh"],
        "needs_section_rewrite": auto_qa["needs_section_rewrite"],
        "auto_issue_reasons": auto_qa["reasons"],
        "reviewer_notes": auto_qa["reviewer_notes"],
    }


def _auto_qa_flags(
    *,
    headline: str,
    sections: dict[str, str],
    source_quality: str,
    qa_bucket: str,
) -> dict[str, Any]:
    texts = [headline, *sections.values()]
    reasons: list[str] = []
    if source_quality in {"title_or_sparse", "empty", "fetch_failed", "brief_failed"}:
        reasons.append("weak_source_quality")
    if qa_bucket in {"latest_report_needed", "latest_report_not_found"}:
        reasons.append("stale_or_missing_latest_report")
    for label, text in [("headline", headline), *sections.items()]:
        reason = _section_quality_reason(text)
        if reason:
            reasons.append(f"{label}:{reason}")
    unique_reasons = list(dict.fromkeys(reasons))
    needs_source_refresh = any(
        reason in {"weak_source_quality", "stale_or_missing_latest_report"}
        for reason in unique_reasons
    )
    needs_section_rewrite = any(
        ":" in reason
        and not reason.endswith(":explicit_empty_section")
        and not reason.endswith(":empty_section")
        for reason in unique_reasons
    )
    if needs_section_rewrite:
        issue_category = "section_rewrite_candidate"
    elif needs_source_refresh:
        issue_category = "source_refresh_candidate"
    else:
        issue_category = ""
    return {
        "issue_category": issue_category,
        "needs_source_refresh": "true" if needs_source_refresh else "",
        "needs_section_rewrite": "true" if needs_section_rewrite else "",
        "reasons": unique_reasons,
        "reviewer_notes": "auto: " + ", ".join(unique_reasons) if unique_reasons else "",
    }


def _section_quality_reason(text: str) -> str:
    value = str(text or "").strip()
    if not value:
        return "empty_section"
    lowered = value.lower()
    explicit_empty_markers = (
        "no explicit",
        "no stock-view",
        "no growth",
        "no earnings",
        "no valuation",
        "no new-business",
        "추출되지 않았습니다",
        "확인되지 않았습니다",
        "본문 근거 추출이 제한적입니다",
    )
    if any(marker in lowered for marker in explicit_empty_markers):
        return "explicit_empty_section"
    if "\ufffd" in value or "�" in value:
        return "replacement_character"
    question_count = value.count("?")
    if question_count >= 3 and question_count / max(1, len(value)) > 0.04:
        return "many_question_marks"
    if len(value) < 12:
        return "too_short"
    stripped = value.lstrip("0123456789: .,()%+-")
    fragment_prefixes = ("며", "으며", "고 ", "하고", "지만", "또한", "YoY)", "QoQ)")
    if value.startswith(("YoY)", "QoQ)")) or stripped.startswith(fragment_prefixes):
        return "starts_mid_sentence"
    if value.endswith(("하", "되", "며", "고", "를", "을", "의", "로", "에")):
        return "ends_mid_sentence"
    return ""


def _markdown(payload: dict[str, Any]) -> str:
    summary = payload.get("summary", {})
    lines = [
        "# Research Brief QA Sample",
        "",
        f"- Samples: {summary.get('sample_count', 0)}",
        f"- Issue samples: {summary.get('issue_sample_count', 0)}",
        f"- Complete samples: {summary.get('complete_sample_count', 0)}",
        "",
    ]
    for item in payload.get("items", []):
        quality = item.get("quality") or {}
        queue = item.get("queue") or {}
        sections = item.get("sections") or {}
        lines.extend(
            [
                f"## {item.get('ticker')} | {item.get('qa_bucket')}",
                "",
                f"- Latest: {item.get('latest_report_date')}",
                f"- Confidence: {float(quality.get('confidence') or 0):.2f}",
                f"- Source quality: {quality.get('source_quality')}",
                f"- Report count: {quality.get('report_count')}",
                f"- Reasons: {', '.join(queue.get('reasons') or []) or '-'}",
                f"- QA issue category: {item.get('issue_category') or '-'}",
                f"- Auto issue reasons: {', '.join(item.get('auto_issue_reasons') or []) or '-'}",
                f"- Needs source refresh: {item.get('needs_source_refresh') or '-'}",
                f"- Needs section rewrite: {item.get('needs_section_rewrite') or '-'}",
                f"- Headline: {item.get('headline')}",
                f"- Stock view: {sections.get('stock_view') or '-'}",
                f"- Growth: {sections.get('growth') or '-'}",
                f"- Earnings: {sections.get('earnings') or '-'}",
                f"- Risk: {sections.get('risk') or '-'}",
                "",
            ]
        )
    return "\n".join(lines)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export a sample set for manual research brief QA.")
    parser.add_argument("--ticker-briefs", type=Path, default=DEFAULT_TICKER_BRIEF_PATH)
    parser.add_argument("--queue", type=Path, default=DEFAULT_QUEUE_PATH)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT_PATH)
    parser.add_argument("--markdown-output", type=Path, default=DEFAULT_MARKDOWN_OUTPUT_PATH)
    parser.add_argument("--sample-size", type=int, default=12)
    parser.add_argument("--no-markdown", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    payload = export_research_brief_qa_sample(
        ticker_brief_path=args.ticker_briefs,
        queue_path=args.queue,
        json_output_path=args.json_output,
        markdown_output_path=None if args.no_markdown else args.markdown_output,
        sample_size=args.sample_size,
    )
    summary = payload["summary"]
    print(f"qa_sample_count={summary.get('sample_count', 0)}")
    print(f"qa_issue_sample_count={summary.get('issue_sample_count', 0)}")
    print(f"qa_complete_sample_count={summary.get('complete_sample_count', 0)}")
    print(f"json_output={args.json_output}")
    if not args.no_markdown:
        print(f"markdown_output={args.markdown_output}")
    print("orders_submitted=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
