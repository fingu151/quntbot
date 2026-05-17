from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


DEFAULT_QUEUE_PATH = Path("data/research_quality_review_queue.json")
DEFAULT_TICKER_BRIEF_PATH = Path("data/research_report_ticker_briefs.json")
DEFAULT_SNAPSHOT_PATH = Path("data/public_portfolio_snapshot.json")
DEFAULT_JSON_OUTPUT_PATH = Path("data/latest_report_followup_queue.json")
DEFAULT_CSV_OUTPUT_PATH = Path("data/latest_report_followup_queue.csv")
DEFAULT_MARKDOWN_OUTPUT_PATH = Path("data/latest_report_followup_queue.md")

CSV_FIELDS = [
    "priority_rank",
    "ticker",
    "name",
    "priority_bucket",
    "priority_score",
    "latest_report_date",
    "report_age_days",
    "confidence",
    "report_count",
    "latest_broker",
    "latest_title",
    "search_query",
    "next_step",
]


def export_latest_report_followup_queue(
    *,
    queue_path: Path | str = DEFAULT_QUEUE_PATH,
    ticker_brief_path: Path | str = DEFAULT_TICKER_BRIEF_PATH,
    snapshot_path: Path | str = DEFAULT_SNAPSHOT_PATH,
    json_output_path: Path | str = DEFAULT_JSON_OUTPUT_PATH,
    csv_output_path: Path | str | None = DEFAULT_CSV_OUTPUT_PATH,
    markdown_output_path: Path | str | None = DEFAULT_MARKDOWN_OUTPUT_PATH,
) -> dict[str, Any]:
    queue = _read_json(queue_path)
    ticker_briefs = _read_json(ticker_brief_path)
    snapshot = _read_json(snapshot_path)
    portfolio_names = _portfolio_names(snapshot)
    brief_lookup = {
        str(row.get("ticker") or ""): row
        for row in ticker_briefs.get("tickers", [])
        if isinstance(row, dict) and row.get("ticker")
    }
    items = [
        _followup_item(item, brief_lookup.get(str(item.get("ticker") or ""), {}), portfolio_names)
        for item in queue.get("items", [])
        if item.get("primary_action") in {"latest_report_not_found", "latest_report_needed"}
    ]
    items.sort(key=lambda item: (-item["priority_score"], item["ticker"]))
    for index, item in enumerate(items, start=1):
        item["priority_rank"] = index
    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_queue": str(queue_path),
        "source_ticker_briefs": str(ticker_brief_path),
        "source_snapshot": str(snapshot_path),
        "summary": {
            "item_count": len(items),
            "portfolio_item_count": sum(1 for item in items if item["is_portfolio"]),
            "bucket_counts": _bucket_counts(items),
        },
        "items": items,
    }
    output = Path(json_output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if csv_output_path is not None:
        _write_csv(Path(csv_output_path), items)
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


def _portfolio_names(snapshot: dict[str, Any]) -> dict[str, str]:
    return {
        str(row.get("ticker") or ""): str(row.get("name") or "")
        for row in snapshot.get("positions", [])
        if isinstance(row, dict) and row.get("ticker")
    }


def _followup_item(
    queue_item: dict[str, Any],
    brief: dict[str, Any],
    portfolio_names: dict[str, str],
) -> dict[str, Any]:
    ticker = str(queue_item.get("ticker") or "")
    source_reports = list(brief.get("source_reports") or [])
    latest_report = source_reports[0] if source_reports else {}
    latest_title = str(latest_report.get("title") or brief.get("headline") or "")
    name = portfolio_names.get(ticker) or str(brief.get("name") or _name_from_title(latest_title, ticker) or "")
    confidence = float(queue_item.get("confidence") or 0.0)
    age = int(queue_item.get("report_age_days") or 0)
    report_count = int(queue_item.get("report_count") or 0)
    is_portfolio = ticker in portfolio_names
    bucket = _priority_bucket(is_portfolio=is_portfolio, confidence=confidence, age=age, report_count=report_count)
    return {
        "priority_rank": 0,
        "ticker": ticker,
        "name": name,
        "is_portfolio": is_portfolio,
        "priority_bucket": bucket,
        "priority_score": _priority_score(is_portfolio=is_portfolio, confidence=confidence, age=age, report_count=report_count),
        "latest_report_date": str(queue_item.get("latest_report_date") or ""),
        "report_age_days": age,
        "confidence": confidence,
        "report_count": report_count,
        "latest_broker": str(latest_report.get("broker") or ""),
        "latest_title": latest_title,
        "latest_url": str(latest_report.get("url") or latest_report.get("source_url") or ""),
        "primary_action": str(queue_item.get("primary_action") or ""),
        "search_query": _search_query(ticker=ticker, name=name),
        "next_step": "Check another supported/public source for a newer report, or keep as latest-not-found.",
    }


def _priority_bucket(*, is_portfolio: bool, confidence: float, age: int, report_count: int) -> str:
    if is_portfolio:
        return "portfolio"
    if confidence < 0.5 and age >= 60:
        return "stale_low_confidence"
    if age >= 120:
        return "very_stale"
    if report_count <= 1:
        return "single_source_stale"
    return "routine_stale"


def _priority_score(*, is_portfolio: bool, confidence: float, age: int, report_count: int) -> float:
    score = float(age)
    if is_portfolio:
        score += 1000
    if confidence < 0.5:
        score += 120
    elif confidence < 0.65:
        score += 60
    if report_count <= 1:
        score += 40
    return round(score, 3)


def _name_from_title(title: str, ticker: str) -> str:
    marker = f"({ticker}"
    if marker in title:
        return title.split(marker, 1)[0].strip()
    return ""


def _search_query(*, ticker: str, name: str) -> str:
    target = name or ticker
    return " ".join(part for part in [target, ticker if name else "", "최신 증권 리포트"] if part)


def _bucket_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        bucket = str(item.get("priority_bucket") or "")
        counts[bucket] = counts.get(bucket, 0) + 1
    return dict(sorted(counts.items()))


def _write_csv(path: Path, items: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for item in items:
            writer.writerow({field: _csv_value(item.get(field)) for field in CSV_FIELDS})


def _csv_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _markdown(payload: dict[str, Any]) -> str:
    summary = payload.get("summary", {})
    lines = [
        "# Latest Report Follow-up Queue",
        "",
        f"- Items: {summary.get('item_count', 0)}",
        f"- Portfolio items: {summary.get('portfolio_item_count', 0)}",
        f"- Buckets: {summary.get('bucket_counts', {})}",
        "",
        "| Rank | Ticker | Name | Bucket | Age | Confidence | Search |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in payload.get("items", [])[:50]:
        lines.append(
            "| "
            f"{item.get('priority_rank')} | {item.get('ticker')} | {item.get('name')} | "
            f"{item.get('priority_bucket')} | {item.get('report_age_days')} | "
            f"{float(item.get('confidence') or 0):.2f} | {item.get('search_query')} |"
        )
    lines.append("")
    return "\n".join(lines)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export latest-report follow-up queue.")
    parser.add_argument("--queue", type=Path, default=DEFAULT_QUEUE_PATH)
    parser.add_argument("--ticker-briefs", type=Path, default=DEFAULT_TICKER_BRIEF_PATH)
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT_PATH)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT_PATH)
    parser.add_argument("--csv-output", type=Path, default=DEFAULT_CSV_OUTPUT_PATH)
    parser.add_argument("--markdown-output", type=Path, default=DEFAULT_MARKDOWN_OUTPUT_PATH)
    parser.add_argument("--no-csv", action="store_true")
    parser.add_argument("--no-markdown", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    payload = export_latest_report_followup_queue(
        queue_path=args.queue,
        ticker_brief_path=args.ticker_briefs,
        snapshot_path=args.snapshot,
        json_output_path=args.json_output,
        csv_output_path=None if args.no_csv else args.csv_output,
        markdown_output_path=None if args.no_markdown else args.markdown_output,
    )
    summary = payload["summary"]
    print(f"latest_report_followup_count={summary.get('item_count', 0)}")
    print(f"portfolio_followup_count={summary.get('portfolio_item_count', 0)}")
    for bucket, count in summary.get("bucket_counts", {}).items():
        print(f"bucket_count.{bucket}={count}")
    print(f"json_output={args.json_output}")
    if not args.no_csv:
        print(f"csv_output={args.csv_output}")
    if not args.no_markdown:
        print(f"markdown_output={args.markdown_output}")
    print("orders_submitted=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
