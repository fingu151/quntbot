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

from config import TELEGRAM_SIGNAL, TelegramSignalConfig
from scripts.smoke_helpers import latest_row_status
from src.data.database import create_tables, get_engine
from src.data.models import TelegramSignal
from src.signals.telegram_reader import fetch_and_store_signals


EngineFactory = Callable[[str | None], Engine]
SignalFetcher = Callable[[Engine, date], int]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch Telegram morning-brief signals and report stored rows without placing orders."
    )
    parser.add_argument("--as-of-date", type=date.fromisoformat, default=date.today())
    parser.add_argument("--database-url", default=None)
    return parser.parse_args(argv)


def run(
    args: argparse.Namespace,
    *,
    config: TelegramSignalConfig = TELEGRAM_SIGNAL,
    engine_factory: EngineFactory = get_engine,
    signal_fetcher: SignalFetcher = fetch_and_store_signals,
) -> int:
    missing = []
    if not config.api_id:
        missing.append("TELEGRAM_API_ID")
    if not config.api_hash:
        missing.append("TELEGRAM_API_HASH")
    if not config.channel:
        missing.append("TELEGRAM_SIGNAL_CHANNEL")

    print(f"telegram_signal_enabled={str(config.enabled).lower()}")
    print(f"api_id_present={str(bool(config.api_id)).lower()}")
    print(f"api_hash_present={str(bool(config.api_hash)).lower()}")
    print(f"channel_present={str(bool(config.channel)).lower()}")
    if missing:
        print(f"missing={','.join(missing)}")
        return 1

    engine = engine_factory(args.database_url)
    create_tables(engine)

    stored = signal_fetcher(engine, args.as_of_date)
    latest_date, latest_count = _latest_signal_status(engine, args.as_of_date)

    print(f"signal_rows_stored={stored}")
    print(f"latest_signal_date={latest_date.isoformat() if latest_date else 'none'}")
    print(f"latest_signal_count={latest_count}")
    print("orders_submitted=0")
    return 0 if stored > 0 and latest_count > 0 else 1


def _latest_signal_status(engine: Engine, as_of_date: date) -> tuple[date | None, int]:
    return latest_row_status(
        engine,
        model=TelegramSignal,
        date_column=TelegramSignal.message_date,
        as_of_date=as_of_date,
    )


def main(argv: Sequence[str] | None = None) -> int:
    return run(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
