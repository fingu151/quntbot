from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from scripts.public_portfolio_dashboard import (
    DEFAULT_TICKER_RESEARCH_BRIEF_PATH,
    save_ticker_research_briefs,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate ticker-level consolidated research report briefs.",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_TICKER_RESEARCH_BRIEF_PATH),
        help="Output JSON path.",
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="Optional SQLAlchemy database URL. Defaults to config.DATABASE_URL.",
    )
    parser.add_argument(
        "--sample-row",
        action="append",
        default=[],
        help="JSON row used for tests or dry local generation. Repeatable.",
    )
    parser.add_argument(
        "--llm-status",
        choices=["disabled", "ready", "generated"],
        default="disabled",
        help="Metadata status for the optional LLM summary layer.",
    )
    args = parser.parse_args(argv)

    rows = [json.loads(row) for row in args.sample_row] if args.sample_row else None
    result = save_ticker_research_briefs(
        Path(args.output),
        rows=rows,
        database_url=args.database_url,
        llm_status=args.llm_status,
    )
    if result.get("status") != "ok":
        print(f"failed: {result.get('error')}")
        return 1

    artifact = result["artifact"]
    summary = artifact.get("summary", {})
    print(
        "wrote "
        f"{result['path']} "
        f"(tickers={summary.get('ticker_count', 0)}, "
        f"reports={summary.get('source_report_count', 0)})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
