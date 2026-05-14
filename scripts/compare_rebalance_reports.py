from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
import sys
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare two dry-run rebalance JSON reports.")
    parser.add_argument("--before-json", type=Path, required=True)
    parser.add_argument("--after-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, default=None)
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> int:
    try:
        before = _load_json(args.before_json)
        after = _load_json(args.after_json)
    except (OSError, json.JSONDecodeError) as exc:
        print("comparison_status=missing_or_invalid")
        print(f"report_error={exc}")
        return 1

    comparison = _compare_reports(before, after)
    _print_summary(comparison)
    if args.output_md:
        args.output_md.parent.mkdir(parents=True, exist_ok=True)
        args.output_md.write_text(_format_markdown(comparison), encoding="utf-8")
        print(f"output_md={args.output_md}")
    return 0


def _compare_reports(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    before_targets = _targets_by_ticker(before)
    after_targets = _targets_by_ticker(after)
    before_tickers = set(before_targets)
    after_tickers = set(after_targets)

    added = [_target_row("ADDED", after_targets[ticker]) for ticker in sorted(after_tickers - before_tickers)]
    removed = [
        _target_row("REMOVED", before_targets[ticker])
        for ticker in sorted(before_tickers - after_tickers)
    ]
    kept = [
        _kept_row(before_targets[ticker], after_targets[ticker])
        for ticker in sorted(before_tickers & after_tickers)
    ]

    before_buys = _order_tickers(before, side="BUY")
    after_buys = _order_tickers(after, side="BUY")

    return {
        "before_date": before.get("as_of_date", ""),
        "after_date": after.get("as_of_date", ""),
        "before_target_count": len(before_targets),
        "after_target_count": len(after_targets),
        "added": added,
        "removed": removed,
        "kept": kept,
        "buy_added": sorted(after_buys - before_buys),
        "buy_removed": sorted(before_buys - after_buys),
        "buy_kept": sorted(before_buys & after_buys),
    }


def _targets_by_ticker(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = {}
    for item in payload.get("targets") or []:
        ticker = str(item.get("ticker", ""))
        if ticker:
            rows[ticker] = item
    return rows


def _order_tickers(payload: dict[str, Any], *, side: str) -> set[str]:
    return {
        str(order.get("ticker", ""))
        for order in payload.get("orders") or []
        if order.get("side") == side and order.get("ticker")
    }


def _target_row(status: str, item: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": status,
        "ticker": str(item.get("ticker", "")),
        "name": str(item.get("name", "")),
        "rank": int(item.get("rank", 0) or 0),
        "total_score": float(item.get("total_score", 0.0) or 0.0),
    }


def _kept_row(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    before_rank = int(before.get("rank", 0) or 0)
    after_rank = int(after.get("rank", 0) or 0)
    return {
        "status": "KEPT",
        "ticker": str(after.get("ticker", "")),
        "name": str(after.get("name", "")),
        "before_rank": before_rank,
        "after_rank": after_rank,
        "rank_delta": after_rank - before_rank,
        "before_score": float(before.get("total_score", 0.0) or 0.0),
        "after_score": float(after.get("total_score", 0.0) or 0.0),
    }


def _print_summary(comparison: dict[str, Any]) -> None:
    print("comparison_status=clean")
    print(f"before_date={comparison['before_date']}")
    print(f"after_date={comparison['after_date']}")
    print(f"before_target_count={comparison['before_target_count']}")
    print(f"after_target_count={comparison['after_target_count']}")
    print(f"added_count={len(comparison['added'])}")
    print(f"removed_count={len(comparison['removed'])}")
    print(f"kept_count={len(comparison['kept'])}")
    print("status,ticker,name,before_rank,after_rank,rank_delta,before_score,after_score")
    for item in comparison["added"]:
        print(
            f"ADDED,{item['ticker']},{item['name']},"
            f"{item['rank']},{item['total_score']:.4f}"
        )
    for item in comparison["removed"]:
        print(
            f"REMOVED,{item['ticker']},{item['name']},"
            f"{item['rank']},{item['total_score']:.4f}"
        )
    for item in comparison["kept"]:
        print(
            f"KEPT,{item['ticker']},{item['name']},"
            f"{item['before_rank']},{item['after_rank']},{item['rank_delta']},"
            f"{item['before_score']:.4f},{item['after_score']:.4f}"
        )
    print(f"buy_added_count={len(comparison['buy_added'])}")
    print(f"buy_removed_count={len(comparison['buy_removed'])}")
    print(f"buy_kept_count={len(comparison['buy_kept'])}")
    if comparison["buy_added"]:
        print(f"buy_added={','.join(comparison['buy_added'])}")
    if comparison["buy_removed"]:
        print(f"buy_removed={','.join(comparison['buy_removed'])}")


def _format_markdown(comparison: dict[str, Any]) -> str:
    lines = [
        "# Rebalance Report Comparison",
        "",
        f"- before_date: `{comparison['before_date']}`",
        f"- after_date: `{comparison['after_date']}`",
        f"- before_target_count: `{comparison['before_target_count']}`",
        f"- after_target_count: `{comparison['after_target_count']}`",
        f"- added_count: `{len(comparison['added'])}`",
        f"- removed_count: `{len(comparison['removed'])}`",
        f"- kept_count: `{len(comparison['kept'])}`",
        "",
        "## Target Changes",
        "",
        "| status | ticker | name | rank | score |",
        "| --- | --- | --- | ---: | ---: |",
    ]
    for item in comparison["added"] + comparison["removed"]:
        lines.append(
            f"| {item['status']} | {item['ticker']} | {item['name']} | "
            f"{item['rank']} | {item['total_score']:.4f} |"
        )
    if not comparison["added"] and not comparison["removed"]:
        lines.append("| - | - | - | 0 | 0.0000 |")

    lines.extend([
        "",
        "## Kept Targets",
        "",
        "| ticker | name | before_rank | after_rank | rank_delta | before_score | after_score |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ])
    for item in comparison["kept"]:
        lines.append(
            f"| {item['ticker']} | {item['name']} | {item['before_rank']} | "
            f"{item['after_rank']} | {item['rank_delta']} | "
            f"{item['before_score']:.4f} | {item['after_score']:.4f} |"
        )
    if not comparison["kept"]:
        lines.append("| - | - | 0 | 0 | 0 | 0.0000 | 0.0000 |")

    lines.extend([
        "",
        "## Buy Order Changes",
        "",
        f"- buy_added_count: `{len(comparison['buy_added'])}`",
        f"- buy_removed_count: `{len(comparison['buy_removed'])}`",
        f"- buy_kept_count: `{len(comparison['buy_kept'])}`",
        f"- buy_added: `{','.join(comparison['buy_added'])}`",
        f"- buy_removed: `{','.join(comparison['buy_removed'])}`",
        "",
    ])
    return "\n".join(lines)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: Sequence[str] | None = None) -> int:
    return run(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
