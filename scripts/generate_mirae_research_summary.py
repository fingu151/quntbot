from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from pathlib import Path
import sys

from sqlalchemy import Engine, select

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import DATA_DIR
from src.data.database import create_tables, get_engine, session_scope
from src.data.models import ResearchReportAnalysis


EngineFactory = Callable[[str | None], Engine]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a Markdown summary for Mirae Asset research analyses."
    )
    parser.add_argument("--source", default="mirae_asset")
    parser.add_argument("--broker", default="미래에셋증권")
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--output", type=Path, default=DATA_DIR / "mirae_research_summary_latest.md")
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--title", default="Mirae Asset Research Summary")
    return parser.parse_args(argv)


def run(
    args: argparse.Namespace,
    *,
    engine_factory: EngineFactory = get_engine,
) -> int:
    engine = engine_factory(args.database_url)
    create_tables(engine)
    with session_scope(engine) as session:
        rows = _load_rows(
            session,
            source=args.source,
            broker=args.broker,
            limit=args.limit,
        )
    markdown = _format_markdown(
        rows,
        source=args.source,
        broker=args.broker,
        title=args.title,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(markdown, encoding="utf-8")
    print(f"mirae_research_summary_rows={len(rows)}")
    print(f"output_md={args.output}")
    print("orders_submitted=0")
    return 0 if rows else 1


def _load_rows(
    session,
    *,
    source: str,
    broker: str | None,
    limit: int,
) -> list[ResearchReportAnalysis]:
    statement = (
        select(ResearchReportAnalysis)
        .where(ResearchReportAnalysis.source == source)
        .order_by(
            ResearchReportAnalysis.report_date.desc(),
            ResearchReportAnalysis.ticker.asc(),
        )
    )
    if broker:
        statement = statement.where(ResearchReportAnalysis.broker == broker)
    return list(session.scalars(statement.limit(max(1, limit))).all())


def _format_markdown(
    rows: list[ResearchReportAnalysis],
    *,
    source: str,
    broker: str | None,
    title: str = "Mirae Asset Research Summary",
) -> str:
    status_counts: dict[str, int] = {}
    opinion_counts: dict[str, int] = {}
    for row in rows:
        status_counts[row.body_text_status] = status_counts.get(row.body_text_status, 0) + 1
        opinion_counts[row.investment_opinion] = opinion_counts.get(row.investment_opinion, 0) + 1

    lines = [
        f"# {title}",
        "",
        f"- source: `{source}`",
        f"- broker: `{broker or ''}`",
        f"- row_count: `{len(rows)}`",
        f"- body_status: `{_fmt_counts(status_counts)}`",
        f"- investment_opinion: `{_fmt_counts(opinion_counts)}`",
        "- orders_submitted: `0`",
        "",
        "## Reports",
        "",
        "| date | ticker | opinion | body | confidence | key thesis | risk | title |",
        "| --- | --- | --- | --- | ---: | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.report_date),
                    _cell(row.ticker),
                    _cell(row.investment_opinion),
                    _cell(row.body_text_status),
                    f"{row.confidence:.2f}",
                    _cell(_first_text(row.buy_thesis, row.summary)),
                    _cell(_first_text(row.risk_factors, row.sell_or_risk_thesis)),
                    _cell(row.title),
                ]
            )
            + " |"
        )
    if not rows:
        lines.append("| - | - | - | - | 0.00 | - | - | - |")
    lines.append("")
    return "\n".join(lines)


def _fmt_counts(counts: dict[str, int]) -> str:
    if not counts:
        return ""
    return ", ".join(f"{key}={counts[key]}" for key in sorted(counts))


def _first_text(*values: str | None) -> str:
    for value in values:
        if value:
            return value
    return ""


def _cell(value: object) -> str:
    text = str(value or "")
    return text.replace("|", "\\|").replace("\n", " ").strip()


def main(argv: Sequence[str] | None = None) -> int:
    return run(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
