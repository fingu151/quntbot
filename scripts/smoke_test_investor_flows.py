from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from datetime import date
from pathlib import Path
import sys

from sqlalchemy import Engine, func, select

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.smoke_helpers import latest_row_status
from src.data.database import create_tables, get_engine, session_scope
from src.data.models import InvestorFlow
from src.data.repositories import get_recent_investor_flow_scores


EngineFactory = Callable[[str | None], Engine]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Report investor flow readiness from stored DB rows without placing orders."
    )
    parser.add_argument("--as-of-date", type=date.fromisoformat, default=date.today())
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--lookback-days", type=int, default=5)
    return parser.parse_args(argv)


def run(
    args: argparse.Namespace,
    *,
    engine_factory: EngineFactory = get_engine,
) -> int:
    engine = engine_factory(args.database_url)
    create_tables(engine)
    status = _investor_flow_status(engine, args.as_of_date, args.lookback_days)

    latest_date = status["latest_date"]
    print(f"investor_flow_rows_total={status['total_count']}")
    print(f"latest_investor_flow_date={latest_date.isoformat() if latest_date else 'none'}")
    print(f"latest_investor_flow_count={status['latest_count']}")
    print(f"investor_flow_scored_count={status['scored_count']}")
    print(f"retail_only_penalty_count={status['negative_count']}")
    print(f"smart_money_positive_count={status['positive_count']}")
    print("orders_submitted=0")

    return 0 if latest_date == args.as_of_date and status["scored_count"] > 0 else 1


def _investor_flow_status(engine: Engine, as_of_date: date, lookback_days: int) -> dict[str, object]:
    with session_scope(engine) as session:
        total_count = session.scalar(select(func.count()).select_from(InvestorFlow)) or 0
        scores = get_recent_investor_flow_scores(
            session,
            as_of_date,
            lookback_days=lookback_days,
        )
    latest_date, latest_count = latest_row_status(
        engine,
        model=InvestorFlow,
        date_column=InvestorFlow.date,
        as_of_date=as_of_date,
    )

    return {
        "total_count": int(total_count),
        "latest_date": latest_date,
        "latest_count": int(latest_count),
        "scored_count": len(scores),
        "negative_count": sum(1 for score in scores.values() if score < 0),
        "positive_count": sum(1 for score in scores.values() if score > 0),
    }


def main(argv: Sequence[str] | None = None) -> int:
    return run(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
