from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from datetime import date, timedelta
from pathlib import Path
import sys
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.data.collectors import PykrxMarketDataProvider, sync_phase1_data
from src.data.database import create_tables, get_engine


SyncFunction = Callable[..., dict[str, int]]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync Phase 1 market data into SQLite.")
    parser.add_argument("--start-date", type=_parse_date, default=None)
    parser.add_argument("--end-date", type=_parse_date, default=date.today())
    parser.add_argument("--database-url", default=None)
    args = parser.parse_args(argv)

    if args.start_date is None:
        args.start_date = args.end_date - timedelta(days=30)
    if args.start_date > args.end_date:
        parser.error("--start-date must be on or before --end-date")
    return args


def run(
    args: argparse.Namespace,
    *,
    provider: Any | None = None,
    sync_func: SyncFunction = sync_phase1_data,
) -> int:
    engine = get_engine(args.database_url)
    create_tables(engine)
    provider = provider or PykrxMarketDataProvider()

    result = sync_func(
        engine=engine,
        provider=provider,
        start_date=args.start_date,
        end_date=args.end_date,
    )
    print(
        "Phase 1 sync complete: "
        f"universe_count={result['universe_count']} "
        f"price_count={result['price_count']} "
        f"fundamental_count={result['fundamental_count']}"
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    return run(parse_args(argv))


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


if __name__ == "__main__":
    raise SystemExit(main())
