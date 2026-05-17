from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


DEFAULT_QA_SAMPLE_PATH = Path("data/research_brief_qa_sample.json")
DEFAULT_SOURCE_DISCOVERY_PATH = Path("data/supplemental_source_discovery_results.json")
DEFAULT_JSON_OUTPUT_PATH = Path("data/research_qa_action_queue.json")
DEFAULT_MARKDOWN_OUTPUT_PATH = Path("data/research_qa_action_queue.md")


def export_research_qa_action_queue(
    *,
    qa_sample_path: Path | str = DEFAULT_QA_SAMPLE_PATH,
    source_discovery_path: Path | str | None = DEFAULT_SOURCE_DISCOVERY_PATH,
    json_output_path: Path | str = DEFAULT_JSON_OUTPUT_PATH,
    markdown_output_path: Path | str | None = DEFAULT_MARKDOWN_OUTPUT_PATH,
) -> dict[str, Any]:
    qa_sample = _read_json(qa_sample_path)
    discovery_lookup = _source_refresh_attempt_lookup(source_discovery_path)
    source_items = [item for item in qa_sample.get("items", []) if isinstance(item, dict)]
    source_refresh_attempted_no_new_source_count = 0
    items = []
    for item in source_items:
        actions = _actions_for_item(item)
        if not actions:
            continue
        ticker = str(item.get("ticker") or "")
        if actions == ["source_refresh"] and discovery_lookup.get(ticker):
            source_refresh_attempted_no_new_source_count += 1
            continue
        items.append(_action_item(item, actions=actions))
    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_qa_sample": str(qa_sample_path),
        "source_discovery": str(source_discovery_path) if source_discovery_path else "",
        "summary": {
            "sample_count": len(source_items),
            "action_item_count": len(items),
            "section_rewrite_count": sum(1 for item in items if "section_rewrite" in item["actions"]),
            "source_refresh_count": sum(1 for item in items if "source_refresh" in item["actions"]),
            "source_refresh_attempted_no_new_source_count": source_refresh_attempted_no_new_source_count,
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


def _action_item(item: dict[str, Any], *, actions: list[str] | None = None) -> dict[str, Any]:
    ticker = str(item.get("ticker") or "")
    actions = actions or _actions_for_item(item)
    primary_action = "section_rewrite" if "section_rewrite" in actions else "source_refresh"
    return {
        "ticker": ticker,
        "primary_action": primary_action,
        "actions": actions,
        "qa_bucket": str(item.get("qa_bucket") or ""),
        "issue_category": str(item.get("issue_category") or ""),
        "latest_report_date": str(item.get("latest_report_date") or ""),
        "headline": str(item.get("headline") or ""),
        "auto_issue_reasons": [str(reason) for reason in item.get("auto_issue_reasons", []) if reason],
        "sections": item.get("sections") or {},
        "source_reports": list(item.get("source_reports") or [])[:3],
        "suggested_next_step": _suggested_next_step(actions),
        "suggested_commands": _suggested_commands(ticker=ticker, actions=actions),
    }


def _actions_for_item(item: dict[str, Any]) -> list[str]:
    actions: list[str] = []
    if _truthy(item.get("needs_section_rewrite")):
        actions.append("section_rewrite")
    if _truthy(item.get("needs_source_refresh")):
        actions.append("source_refresh")
    return actions


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def _source_refresh_attempt_lookup(path: Path | str | None) -> dict[str, bool]:
    if path is None:
        return {}
    payload = _read_json(path)
    lookup: dict[str, bool] = {}
    for result in payload.get("results", []):
        if not isinstance(result, dict):
            continue
        ticker = str(result.get("ticker") or "")
        checks = [check for check in result.get("checks", []) if isinstance(check, dict)]
        discovered_sources = [
            source for source in result.get("discovered_sources", []) if isinstance(source, dict)
        ]
        attempted = any(str(check.get("status") or "") != "fetch_failed" for check in checks)
        if ticker and attempted and not discovered_sources:
            lookup[ticker] = True
    return lookup


def _suggested_next_step(actions: list[str]) -> str:
    if actions == ["section_rewrite"]:
        return "Re-run stored report body analysis for this ticker, then regenerate ticker briefs and QA artifacts."
    if actions == ["source_refresh"]:
        return "Run supplemental source discovery for this ticker before another QA pass."
    return "Refresh source coverage first, then re-run body analysis and regenerate QA artifacts."


def _suggested_commands(*, ticker: str, actions: list[str]) -> list[str]:
    commands: list[str] = []
    if "section_rewrite" in actions:
        commands.append(
            f".\\venv\\Scripts\\python.exe -m scripts.reanalyze_research_report_bodies --ticker {ticker}"
        )
    if "source_refresh" in actions:
        commands.append(
            ".\\scripts\\start_public_dashboard_with_refresh.ps1 "
            "-Port 8520 -HostAddress 0.0.0.0 -BrowserAddress localhost "
            "-RefreshIntervalMinutes 30 -RunTimeoutMinutes 10 -IncludeSupplementalDiscovery"
        )
    return commands


def _markdown(payload: dict[str, Any]) -> str:
    summary = payload.get("summary", {})
    lines = [
        "# Research QA Action Queue",
        "",
        f"- Samples: {summary.get('sample_count', 0)}",
        f"- Action items: {summary.get('action_item_count', 0)}",
        f"- Section rewrite: {summary.get('section_rewrite_count', 0)}",
        f"- Source refresh: {summary.get('source_refresh_count', 0)}",
        f"- Source refresh attempted, no new source: {summary.get('source_refresh_attempted_no_new_source_count', 0)}",
        "",
        "| Ticker | Primary action | Actions | Latest | Reasons |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in payload.get("items", []):
        lines.append(
            "| "
            f"{item.get('ticker', '')} | "
            f"{item.get('primary_action', '')} | "
            f"{', '.join(item.get('actions') or [])} | "
            f"{item.get('latest_report_date', '')} | "
            f"{', '.join(item.get('auto_issue_reasons') or [])} |"
        )
    lines.append("")
    return "\n".join(lines)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export action queues from research brief QA auto flags.")
    parser.add_argument("--qa-sample", type=Path, default=DEFAULT_QA_SAMPLE_PATH)
    parser.add_argument("--source-discovery", type=Path, default=DEFAULT_SOURCE_DISCOVERY_PATH)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT_PATH)
    parser.add_argument("--markdown-output", type=Path, default=DEFAULT_MARKDOWN_OUTPUT_PATH)
    parser.add_argument("--no-markdown", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    payload = export_research_qa_action_queue(
        qa_sample_path=args.qa_sample,
        source_discovery_path=args.source_discovery,
        json_output_path=args.json_output,
        markdown_output_path=None if args.no_markdown else args.markdown_output,
    )
    summary = payload["summary"]
    print(f"qa_action_item_count={summary.get('action_item_count', 0)}")
    print(f"qa_section_rewrite_count={summary.get('section_rewrite_count', 0)}")
    print(f"qa_source_refresh_count={summary.get('source_refresh_count', 0)}")
    print(f"json_output={args.json_output}")
    if not args.no_markdown:
        print(f"markdown_output={args.markdown_output}")
    print("orders_submitted=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
