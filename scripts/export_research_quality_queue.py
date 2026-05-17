from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from scripts.public_portfolio_dashboard import (
    DEFAULT_TICKER_RESEARCH_BRIEF_PATH,
    build_ticker_research_quality_report,
)


DEFAULT_OUTPUT_PATH = Path("data/research_quality_review_queue.json")
DEFAULT_MARKDOWN_OUTPUT_PATH = Path("data/research_quality_review_queue.md")


ACTION_DESCRIPTIONS = {
    "supplemental_source_needed": "Find or add a better public source/body text first.",
    "latest_report_needed": "Look for a newer report before improving the summary.",
    "latest_report_not_found": "Broad refresh completed, but no newer supported-source report was found.",
    "weak_or_stale_source_only": "Sections are filled, but the source is sparse or stale; review only after section gaps.",
    "parser_section_backfill_candidate": "Existing full/partial text can likely be re-parsed.",
    "low_confidence_review": "Review confidence and source evidence manually.",
    "manual_review": "Keep for manual review after automated queues are cleared.",
}


def classify_quality_issue(issue: dict[str, Any], *, refreshed_through: str | None = None) -> str:
    reasons = {str(reason) for reason in issue.get("reasons", [])}
    source_quality = str(issue.get("source_quality") or "")
    missing_sections = [str(section) for section in issue.get("missing_sections", []) if section]

    if "weak_source_quality" in reasons and missing_sections:
        return "supplemental_source_needed"
    if "weak_source_quality" in reasons and not missing_sections:
        return "weak_or_stale_source_only"
    if "stale_report" in reasons:
        if refreshed_through:
            return "latest_report_not_found"
        return "latest_report_needed"
    if "missing_sections" in reasons and missing_sections and source_quality in {"full_text", "partial_text"}:
        return "parser_section_backfill_candidate"
    if "low_confidence" in reasons:
        return "low_confidence_review"
    return "manual_review"


def export_quality_queue(
    *,
    artifact_path: Path | str = DEFAULT_TICKER_RESEARCH_BRIEF_PATH,
    output_path: Path | str = DEFAULT_OUTPUT_PATH,
    markdown_output_path: Path | str | None = DEFAULT_MARKDOWN_OUTPUT_PATH,
    now_iso: str | None = None,
    stale_days: int = 45,
    refreshed_through: str | None = None,
) -> dict[str, Any]:
    artifact = json.loads(Path(artifact_path).read_text(encoding="utf-8"))
    now = _parse_now(now_iso)
    report = build_ticker_research_quality_report(artifact, now=now, stale_days=stale_days)
    items = [_queue_item(issue, refreshed_through=refreshed_through) for issue in report.get("issues", [])]
    action_counts = Counter(item["primary_action"] for item in items)
    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_artifact": str(artifact_path),
        "stale_days": stale_days,
        "refreshed_through": refreshed_through or "",
        "summary": {
            **report.get("summary", {}),
            "action_counts": dict(sorted(action_counts.items())),
        },
        "actions": ACTION_DESCRIPTIONS,
        "items": items,
    }
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if markdown_output_path is not None:
        markdown = Path(markdown_output_path)
        markdown.parent.mkdir(parents=True, exist_ok=True)
        markdown.write_text(_markdown(payload), encoding="utf-8")
    return payload


def _queue_item(issue: dict[str, Any], *, refreshed_through: str | None = None) -> dict[str, Any]:
    primary_action = classify_quality_issue(issue, refreshed_through=refreshed_through)
    return {
        "ticker": str(issue.get("ticker") or ""),
        "primary_action": primary_action,
        "latest_report_date": str(issue.get("latest_report_date") or ""),
        "reasons": list(issue.get("reasons") or []),
        "missing_sections": list(issue.get("missing_sections") or []),
        "source_quality": str(issue.get("source_quality") or ""),
        "confidence": float(issue.get("confidence") or 0.0),
        "report_count": int(issue.get("report_count") or 0),
        "report_age_days": issue.get("report_age_days"),
        "refreshed_through": refreshed_through or "",
        "next_step": ACTION_DESCRIPTIONS[primary_action],
    }


def _markdown(payload: dict[str, Any]) -> str:
    summary = payload.get("summary", {})
    lines = [
        "# Research Quality Review Queue",
        "",
        f"- Tickers: {summary.get('ticker_count', 0)}",
        f"- Complete: {summary.get('complete_count', 0)}",
        f"- Needs review: {summary.get('issue_count', 0)}",
        f"- Stale days: {payload.get('stale_days', 45)}",
        f"- Refreshed through: {payload.get('refreshed_through') or '-'}",
        "",
        "## Action Counts",
        "",
    ]
    for action, count in (summary.get("action_counts") or {}).items():
        lines.append(f"- {action}: {count}")
    lines.extend(["", "## Top Queue", ""])
    for item in payload.get("items", [])[:50]:
        missing = ", ".join(item.get("missing_sections") or []) or "-"
        reasons = ", ".join(item.get("reasons") or []) or "-"
        lines.append(
            "- "
            f"{item.get('ticker')} | {item.get('primary_action')} | "
            f"latest {item.get('latest_report_date') or '-'} | "
            f"reasons {reasons} | missing {missing}"
        )
    lines.append("")
    return "\n".join(lines)


def _parse_now(now_iso: str | None) -> datetime | None:
    if not now_iso:
        return None
    value = now_iso.strip()
    if value.endswith("Z"):
        value = f"{value[:-1]}+00:00"
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export actionable Ticker Briefs quality review queue.")
    parser.add_argument("--input", type=Path, default=DEFAULT_TICKER_RESEARCH_BRIEF_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--markdown-output", type=Path, default=DEFAULT_MARKDOWN_OUTPUT_PATH)
    parser.add_argument("--no-markdown", action="store_true")
    parser.add_argument("--now", default=None)
    parser.add_argument("--stale-days", type=int, default=45)
    parser.add_argument("--refreshed-through", default=None)
    args = parser.parse_args(argv)

    payload = export_quality_queue(
        artifact_path=args.input,
        output_path=args.output,
        markdown_output_path=None if args.no_markdown else args.markdown_output,
        now_iso=args.now,
        stale_days=args.stale_days,
        refreshed_through=args.refreshed_through,
    )
    summary = payload["summary"]
    print(f"ticker_count={summary.get('ticker_count', 0)}")
    print(f"complete_count={summary.get('complete_count', 0)}")
    print(f"needs_review_count={summary.get('issue_count', 0)}")
    for action, count in summary.get("action_counts", {}).items():
        print(f"action_count.{action}={count}")
    print(f"queue_output={args.output}")
    if not args.no_markdown:
        print(f"markdown_output={args.markdown_output}")
    print("orders_submitted=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
