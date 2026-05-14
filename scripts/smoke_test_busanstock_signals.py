from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from datetime import date
from pathlib import Path
import sys

from sqlalchemy import Engine

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.smoke_helpers import latest_row_status
from src.data.database import create_tables, get_engine
from src.data.models import BusanstockSignal
from src.signals.busanstock_reader import fetch_and_store_busanstock_signals


EngineFactory = Callable[[str | None], Engine]
SignalFetcher = Callable[[Engine, date], int]
LatestCounter = Callable[[Engine, date], tuple[date | None, int]]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch Busanstock report signals and report stored rows without placing orders."
    )
    parser.add_argument("--as-of-date", type=date.fromisoformat, default=date.today())
    parser.add_argument("--database-url", default=None)
    return parser.parse_args(argv)


def run(
    args: argparse.Namespace,
    *,
    engine_factory: EngineFactory = get_engine,
    signal_fetcher: SignalFetcher = fetch_and_store_busanstock_signals,
    latest_counter: LatestCounter = None,
) -> int:
    engine = engine_factory(args.database_url)
    create_tables(engine)
    stored = signal_fetcher(engine, as_of_date=args.as_of_date)
    counter = latest_counter or _latest_signal_status
    latest_date, latest_count = counter(engine, args.as_of_date)

    print(f"busanstock_signal_rows_stored={stored}")
    print(f"latest_busanstock_signal_date={latest_date.isoformat() if latest_date else 'none'}")
    print(f"latest_busanstock_signal_count={latest_count}")
    print("orders_submitted=0")
    return 0 if stored > 0 and latest_count > 0 else 1


def _latest_signal_status(engine: Engine, as_of_date: date) -> tuple[date | None, int]:
    return latest_row_status(
        engine,
        model=BusanstockSignal,
        date_column=BusanstockSignal.signal_date,
        as_of_date=as_of_date,
    )


def main(argv: Sequence[str] | None = None) -> int:
    return run(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
