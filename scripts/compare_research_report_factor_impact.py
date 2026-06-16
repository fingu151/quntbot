from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
import sys

from sqlalchemy import select

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import DATA_DIR, FACTOR
from src.data.database import create_tables, get_engine, session_scope
from src.data.models import ResearchReportSignal
from src.data.repositories import (
    get_latest_busanstock_signals,
    get_recent_investor_flow_scores,
)
from src.factors import engine as factor_engine
from src.factors.models import FactorScore


DEFAULT_OUTPUT_PATH = DATA_DIR / "mirae_research_factor_impact_latest.md"


@dataclass(frozen=True)
class FactorImpactRow:
    ticker: str
    name: str
    before_rank: int
    after_rank: int
    rank_delta: int
    before_score: float
    after_score: float
    score_delta: float
    research_report_score: float


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare factor rankings with and without research report signals."
    )
    parser.add_argument("--as-of-date", type=_parse_date, default=date.today())
    parser.add_argument("--lookback-days", type=int, default=None)
    parser.add_argument("--research-lookback-days", type=int, default=30)
    parser.add_argument("--research-start-date", type=_parse_date, default=None)
    parser.add_argument("--top-n", type=int, default=20)
    parser.add_argument("--source", default="mirae_asset")
    parser.add_argument("--broker", default=None)
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--title", default="Mirae Research Factor Impact")
    args = parser.parse_args(argv)
    if args.top_n <= 0:
        parser.error("--top-n must be greater than 0")
    if args.research_lookback_days <= 0:
        parser.error("--research-lookback-days must be greater than 0")
    if args.lookback_days is not None and args.lookback_days <= 0:
        parser.error("--lookback-days must be greater than 0")
    return args


def run(args: argparse.Namespace) -> int:
    engine = get_engine(args.database_url)
    create_tables(engine)
    lookback_days = args.lookback_days or FACTOR.momentum_lookback_days
    raw = factor_engine._load_factor_inputs(
        engine,
        as_of_date=args.as_of_date,
        lookback_days=lookback_days,
    )

    with session_scope(engine) as session:
        busanstock_signals = get_latest_busanstock_signals(session, args.as_of_date)
        investor_flow_signals = get_recent_investor_flow_scores(session, args.as_of_date)
        research_report_signals = get_recent_source_research_report_scores(
            session,
            args.as_of_date,
            source=args.source,
            broker=args.broker,
            lookback_days=args.research_lookback_days,
            start_date=args.research_start_date,
        )

    without_research = factor_engine.calculate_factor_scores_from_df(
        raw,
        as_of_date=args.as_of_date,
        busanstock_signals=busanstock_signals,
        investor_flow_signals=investor_flow_signals,
        research_report_signals={},
    )
    with_research = factor_engine.calculate_factor_scores_from_df(
        raw,
        as_of_date=args.as_of_date,
        busanstock_signals=busanstock_signals,
        investor_flow_signals=investor_flow_signals,
        research_report_signals=research_report_signals,
    )

    rows = compare_factor_scores(without_research, with_research)
    output_text = format_factor_impact_markdown(
        rows,
        as_of_date=args.as_of_date,
        source=args.source,
        broker=args.broker,
        research_start_date=args.research_start_date,
        score_count=len(with_research),
        research_signal_count=len(research_report_signals),
        top_n=args.top_n,
        title=args.title,
    )
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.write_text(output_text, encoding="utf-8")

    print(
        f"output={args.output_md} "
        f"score_count={len(with_research)} "
        f"research_signal_count={len(research_report_signals)} "
        f"impacted_count={len(rows)} "
        "orders_submitted=0"
    )
    return 0


def get_recent_source_research_report_scores(
    session,
    as_of_date: date,
    *,
    source: str,
    broker: str | None = None,
    lookback_days: int = 30,
    start_date: date | None = None,
) -> dict[str, float]:
    effective_start_date = start_date or (as_of_date - timedelta(days=lookback_days))
    query = select(ResearchReportSignal).where(
        ResearchReportSignal.report_date >= effective_start_date,
        ResearchReportSignal.report_date <= as_of_date,
        ResearchReportSignal.source == source,
    )
    if broker:
        query = query.where(ResearchReportSignal.broker == broker)
    rows = session.scalars(query).all()
    if not rows:
        return {}

    weighted: dict[str, float] = {}
    weights: dict[str, float] = {}
    for row in rows:
        age_days = max(0, (as_of_date - row.report_date).days)
        if start_date is not None:
            window_days = max(1, (as_of_date - effective_start_date).days)
        else:
            window_days = max(lookback_days, 1)
        recency_weight = max(0.2, 1.0 - (age_days / window_days))
        raw_score = max(-1.0, min(1.0, float(row.raw_score)))
        weighted[row.ticker] = weighted.get(row.ticker, 0.0) + raw_score * recency_weight
        weights[row.ticker] = weights.get(row.ticker, 0.0) + recency_weight

    scores = {}
    for ticker, weighted_score in weighted.items():
        weight = weights.get(ticker, 0.0)
        if weight <= 0:
            continue
        score = weighted_score / weight
        if score != 0.0:
            scores[ticker] = score
    return scores


def compare_factor_scores(
    without_research: Sequence[FactorScore],
    with_research: Sequence[FactorScore],
) -> list[FactorImpactRow]:
    before_by_ticker = {score.ticker: score for score in without_research}
    rows: list[FactorImpactRow] = []
    for after in with_research:
        if after.research_report_score == 0.0:
            continue
        before = before_by_ticker.get(after.ticker)
        if before is None:
            continue
        rows.append(
            FactorImpactRow(
                ticker=after.ticker,
                name=after.name,
                before_rank=before.rank,
                after_rank=after.rank,
                rank_delta=before.rank - after.rank,
                before_score=before.total_score,
                after_score=after.total_score,
                score_delta=after.total_score - before.total_score,
                research_report_score=after.research_report_score,
            )
        )
    return sorted(rows, key=lambda row: (abs(row.score_delta), abs(row.rank_delta)), reverse=True)


def format_factor_impact_markdown(
    rows: Sequence[FactorImpactRow],
    *,
    as_of_date: date,
    source: str,
    broker: str | None,
    research_start_date: date | None = None,
    score_count: int,
    research_signal_count: int,
    top_n: int,
    title: str = "Mirae Research Factor Impact",
) -> str:
    lines = [
        f"# {title}",
        "",
        f"- 기준일: `{as_of_date.isoformat()}`",
        f"- research_start_date: `{research_start_date.isoformat() if research_start_date else ''}`",
        f"- source: `{source}`",
        f"- broker: `{broker or 'all'}`",
        f"- factor_score_count: `{score_count}`",
        f"- research_signal_count: `{research_signal_count}`",
        f"- impacted_count: `{len(rows)}`",
        "- orders_submitted: `0`",
        "",
        "## 영향 상위 종목",
        "",
        "| ticker | name | rank_before | rank_after | rank_delta | score_before | score_after | score_delta | research_score |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows[:top_n]:
        lines.append(
            "| "
            f"{row.ticker} | "
            f"{_escape_table_cell(row.name)} | "
            f"{row.before_rank} | "
            f"{row.after_rank} | "
            f"{row.rank_delta:+d} | "
            f"{row.before_score:.4f} | "
            f"{row.after_score:.4f} | "
            f"{row.score_delta:+.4f} | "
            f"{row.research_report_score:+.4f} |"
        )
    if not rows:
        lines.append("| - | - | - | - | - | - | - | - | - |")
    lines.extend(["", "리서치 신호만 켜고 끈 차이를 비교했으며, 주문 실행은 하지 않았습니다."])
    return "\n".join(lines) + "\n"


def _escape_table_cell(value: str) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ").strip()


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def main(argv: Sequence[str] | None = None) -> int:
    return run(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
