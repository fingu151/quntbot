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
ValueTransform = Callable[[float | None], float | None]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync market index OHLCV rows.")
    parser.add_argument("--start-date", type=_parse_date, required=True)
    parser.add_argument("--end-date", type=_parse_date, required=True)
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--skip-krx", action="store_true")
    parser.add_argument("--skip-nasdaq", action="store_true")
    parser.add_argument("--skip-bond-yields", action="store_true")
    args = parser.parse_args(argv)
    if args.start_date > args.end_date:
        parser.error("--start-date must be on or before --end-date")
    return args


def run(
    args: argparse.Namespace,
    *,
    krx_fetcher: IndexFetchFunction | None = None,
    us_fetcher: IndexFetchFunction | None = None,
    nasdaq_fetcher: IndexFetchFunction | None = None,
    bond_yield_fetcher: IndexFetchFunction | None = None,
) -> int:
    engine = get_engine(args.database_url)
    create_tables(engine)

    rows: list[dict[str, Any]] = []
    if not args.skip_krx:
        rows.extend((krx_fetcher or fetch_krx_indices)(args.start_date, args.end_date))
    if not args.skip_nasdaq:
        fetcher = us_fetcher or nasdaq_fetcher or fetch_us_indices
        rows.extend(fetcher(args.start_date, args.end_date))
    if not args.skip_bond_yields:
        rows.extend((bond_yield_fetcher or fetch_bond_yields)(args.start_date, args.end_date))

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


def fetch_us_indices(start_date: date, end_date: date) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for symbol, yahoo_symbol in (
        ("NASDAQ", "%5EIXIC"),
        ("SP500", "%5EGSPC"),
        ("DOW", "%5EDJI"),
    ):
        rows.extend(_fetch_yahoo_index(symbol, yahoo_symbol, start_date, end_date))
    return rows


def fetch_nasdaq_index(start_date: date, end_date: date) -> list[dict[str, Any]]:
    return _fetch_yahoo_index("NASDAQ", "%5EIXIC", start_date, end_date)


def fetch_bond_yields(start_date: date, end_date: date) -> list[dict[str, Any]]:
    return fetch_kr_treasury_10y_yield(start_date, end_date) + fetch_us_treasury_10y_yield(
        start_date,
        end_date,
    )


def fetch_kr_treasury_10y_yield(start_date: date, end_date: date) -> list[dict[str, Any]]:
    from pykrx import bond

    frame = bond.get_otc_treasury_yields(
        _format_date(start_date),
        _format_date(end_date),
        "국고채10년",
    )
    if frame.empty:
        return []
    rows = []
    for index_date, row in frame.iterrows():
        close = _float_or_none(row.get("수익률"))
        if close is None:
            continue
        rows.append(
            {
                "symbol": "KR10Y",
                "date": index_date.date() if hasattr(index_date, "date") else date.fromisoformat(str(index_date)),
                "open": None,
                "high": None,
                "low": None,
                "close": close,
                "volume": None,
            }
        )
    return rows


def fetch_us_treasury_10y_yield(start_date: date, end_date: date) -> list[dict[str, Any]]:
    return _fetch_yahoo_index(
        "US10Y",
        "%5ETNX",
        start_date,
        end_date,
        value_transform=_normalize_us_10y_yield,
    )


def _fetch_yahoo_index(
    symbol: str,
    yahoo_symbol: str,
    start_date: date,
    end_date: date,
    *,
    value_transform: ValueTransform | None = None,
) -> list[dict[str, Any]]:
    period1 = int(datetime.combine(start_date, time.min, tzinfo=timezone.utc).timestamp())
    period2 = int(datetime.combine(end_date, time.max, tzinfo=timezone.utc).timestamp())
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}"
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
        close = _sequence_value(quote.get("close"), index, value_transform=value_transform)
        if close is None:
            continue
        rows.append(
            {
                "symbol": symbol,
                "date": datetime.fromtimestamp(int(timestamp), tz=timezone.utc).date(),
                "open": _sequence_value(quote.get("open"), index, value_transform=value_transform),
                "high": _sequence_value(quote.get("high"), index, value_transform=value_transform),
                "low": _sequence_value(quote.get("low"), index, value_transform=value_transform),
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


def _sequence_value(
    values: Any,
    index: int,
    *,
    value_transform: ValueTransform | None = None,
) -> float | None:
    if not isinstance(values, list) or index >= len(values):
        return None
    value = _float_or_none(values[index])
    if value_transform is not None:
        return value_transform(value)
    return value


def _normalize_us_10y_yield(value: float | None) -> float | None:
    if value is None:
        return None
    if value > 20:
        return value / 10.0
    return value


def _format_date(value: date) -> str:
    return value.strftime("%Y%m%d")


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def main(argv: Sequence[str] | None = None) -> int:
    return run(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
