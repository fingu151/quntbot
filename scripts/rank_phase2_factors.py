from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from datetime import date
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.data.database import create_tables, get_engine
from src.factors.engine import calculate_factor_scores
from src.factors.models import FactorScore


CalculateFunction = Callable[..., list[FactorScore]]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rank Phase 2 factor scores.")
    parser.add_argument("--as-of-date", type=_parse_date, default=date.today())
    parser.add_argument("--top-n", type=int, default=20)
    parser.add_argument("--lookback-days", type=int, default=None)
    parser.add_argument("--database-url", default=None)
    args = parser.parse_args(argv)
    if args.top_n <= 0:
        parser.error("--top-n must be greater than 0")
    if args.lookback_days is not None and args.lookback_days <= 0:
        parser.error("--lookback-days must be greater than 0")
    return args


def run(
    args: argparse.Namespace,
    *,
    calculate_func: CalculateFunction = calculate_factor_scores,
) -> int:
    engine = get_engine(args.database_url)
    create_tables(engine)
    scores = calculate_func(
        engine,
        as_of_date=args.as_of_date,
        lookback_days=args.lookback_days,
    )
    if scores:
        telegram_scored_count = sum(1 for score in scores if score.telegram_score != 0.0)
        telegram_coverage = telegram_scored_count / len(scores)
        busanstock_scored_count = sum(1 for score in scores if score.busanstock_score != 0.0)
        busanstock_coverage = busanstock_scored_count / len(scores)
        investor_flow_scored_count = sum(1 for score in scores if score.investor_flow_score != 0.0)
        investor_flow_coverage = investor_flow_scored_count / len(scores)
        research_report_scored_count = sum(
            1 for score in scores if score.research_report_score != 0.0
        )
        research_report_coverage = research_report_scored_count / len(scores)
        print(
            f"score_count={len(scores)} "
            f"telegram_scored_count={telegram_scored_count} "
            f"telegram_coverage={telegram_coverage:.1%} "
            f"busanstock_scored_count={busanstock_scored_count} "
            f"busanstock_coverage={busanstock_coverage:.1%} "
            f"investor_flow_scored_count={investor_flow_scored_count} "
            f"investor_flow_coverage={investor_flow_coverage:.1%} "
            f"research_report_scored_count={research_report_scored_count} "
            f"research_report_coverage={research_report_coverage:.1%}"
        )
    for score in scores[: args.top_n]:
        print(
            f"rank={score.rank} "
            f"ticker={score.ticker} "
            f"name={score.name} "
            f"total={score.total_score:.4f} "
            f"value={score.value_score:.4f} "
            f"quality={score.quality_score:.4f} "
            f"momentum={score.momentum_score:.4f} "
            f"yield={score.yield_score:.4f} "
            f"telegram={score.telegram_score:.4f} "
            f"busanstock={score.busanstock_score:.4f} "
            f"investor_flow={score.investor_flow_score:.4f} "
            f"research_report={score.research_report_score:.4f}"
        )
    if not scores:
        print("No factor scores available. Run Phase 1 data sync first.")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    return run(parse_args(argv))


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


if __name__ == "__main__":
    raise SystemExit(main())
