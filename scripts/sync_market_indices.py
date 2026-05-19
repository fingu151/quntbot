from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from datetime import date, datetime, time, timezone
from pathlib import Path
import sys
from typing import Any

import pandas as pd
import requests

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.data.database import create_tables, get_engine, session_scope
from src.data.repositories import upsert_market_index_prices


IndexFetchFunction = Callable[[date, date], list[dict[str, Any]]]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync market index OHLCV rows.")
    parser.add_argument("--start-date", type=_parse_date, required=True)
    parser.add_argument("--end-date", type=_parse_date, required=True)
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--skip-krx", action="store_true")
    parser.add_argument("--skip-nasdaq", action="store_true")
    args = parser.parse_args(argv)
    if args.start_date > args.end_date:
        parser.error("--start-date must be on or before --end-date")
    return args


def run(
    args: argparse.Namespace,
    *,
    krx_fetcher: IndexFetchFunction | None = None,
    nasdaq_fetcher: IndexFetchFunction | None = None,
) -> int:
    engine = get_engine(args.database_url)
    create_tables(engine)

    rows: list[dict[str, Any]] = []
    if not args.skip_krx:
        rows.extend((krx_fetcher or fetch_krx_indices)(args.start_date, args.end_date))
    if not args.skip_nasdaq:
        rows.extend((nasdaq_fetcher or fetch_nasdaq_index)(args.start_date, args.end_date))

    with session_scope(engine) as session:
        count = upsert_market_index_prices(session, rows)
    print(f"Market index sync complete: row_count={count}")
    return 0


def fetch_krx_indices(start_date: date, end_date: date) -> list[dict[str, Any]]:
    from pykrx import stock

    rows: list[dict[str, Any]] = []
    for symbol, index_code in (("KOSPI", "1001"), ("KOSDAQ", "2001")):
        frame = stock.get_index_ohlcv_by_date(
            _format_date(start_date),
            _format_date(end_date),
            index_code,
        )
        rows.extend(_frame_to_rows(symbol, frame))
    return rows


def fetch_nasdaq_index(start_date: date, end_date: date) -> list[dict[str, Any]]:
    period1 = int(datetime.combine(start_date, time.min, tzinfo=timezone.utc).timestamp())
    period2 = int(datetime.combine(end_date, time.max, tzinfo=timezone.utc).timestamp())
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/%5EIXIC"
        f"?period1={period1}&period2={period2}&interval=1d&events=history"
    )
    response = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    response.raise_for_status()
    payload = response.json()
    result = (payload.get("chart") or {}).get("result") or []
    if not result:
        return []
    item = result[0]
    timestamps = item.get("timestamp") or []
    quote = ((item.get("indicators") or {}).get("quote") or [{}])[0]
    rows = []
    for index, timestamp in enumerate(timestamps):
        close = _sequence_value(quote.get("close"), index)
        if close is None:
            continue
        rows.append(
            {
                "symbol": "NASDAQ",
                "date": datetime.fromtimestamp(int(timestamp), tz=timezone.utc).date(),
                "open": _sequence_value(quote.get("open"), index),
                "high": _sequence_value(quote.get("high"), index),
                "low": _sequence_value(quote.get("low"), index),
                "close": close,
                "volume": _sequence_value(quote.get("volume"), index),
            }
        )
    return rows


def _frame_to_rows(symbol: str, frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    rows = []
    for index_date, row in frame.iterrows():
        values = list(row)
        rows.append(
            {
                "symbol": symbol,
                "date": index_date.date() if hasattr(index_date, "date") else date.fromisoformat(str(index_date)),
                "open": _float_or_none(values[0] if len(values) > 0 else None),
                "high": _float_or_none(values[1] if len(values) > 1 else None),
                "low": _float_or_none(values[2] if len(values) > 2 else None),
                "close": _float_or_none(values[3] if len(values) > 3 else None),
                "volume": _float_or_none(values[4] if len(values) > 4 else None),
            }
        )
    return rows


def _float_or_none(value: Any) -> float | None:
    if pd.isna(value):
        return None
    return float(value)


def _sequence_value(values: Any, index: int) -> float | None:
    if not isinstance(values, list) or index >= len(values):
        return None
    return _float_or_none(values[index])


def _format_date(value: date) -> str:
    return value.strftime("%Y%m%d")


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def main(argv: Sequence[str] | None = None) -> int:
    return run(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
