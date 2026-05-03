from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Protocol

import pandas as pd
from sqlalchemy import Engine

from src.data.database import session_scope
from src.data.models import SyncRun, utc_now
from src.data.repositories import upsert_daily_prices, upsert_fundamentals, upsert_stocks


KOSPI200_INDEX_TICKER = "1028"
KOSDAQ150_INDEX_TICKER = "2203"


class MarketDataProvider(Protocol):
    def get_universe(self) -> list[dict[str, Any]]:
        ...

    def get_daily_prices(self, ticker: str, start_date: date, end_date: date) -> list[dict[str, Any]]:
        ...

    def get_fundamentals(self, ticker: str, start_date: date, end_date: date) -> list[dict[str, Any]]:
        ...


class PykrxMarketDataProvider:
    def __init__(self) -> None:
        from pykrx import stock

        self.stock = stock

    def _resolve_recent_business_date(self) -> str:
        # When date=None, some pykrx versions fail to find a business day if the
        # KRX site response shape changes (IndexError on empty dataframe).
        # Walk back from yesterday up to 14 days, skipping weekends.
        today = date.today()
        for offset in range(1, 15):
            candidate = today - timedelta(days=offset)
            if candidate.weekday() >= 5:  # Saturday=5, Sunday=6
                continue
            return candidate.strftime("%Y%m%d")
        # Fallback: 14 days ago
        return (today - timedelta(days=14)).strftime("%Y%m%d")

    def get_universe(self) -> list[dict[str, Any]]:
        target_date = self._resolve_recent_business_date()
        rows: list[dict[str, Any]] = []
        for market, index_ticker in (
            ("KOSPI200", KOSPI200_INDEX_TICKER),
            ("KOSDAQ150", KOSDAQ150_INDEX_TICKER),
        ):
            # Pass explicit date + alternative=True so pykrx falls back to the
            # most recent business day even if target_date is a holiday.
            tickers = self.stock.get_index_portfolio_deposit_file(
                index_ticker, target_date, alternative=True
            )
            for ticker in tickers:
                rows.append(
                    {
                        "ticker": ticker,
                        "name": self.stock.get_market_ticker_name(ticker),
                        "market": market,
                        "is_active": True,
                    }
                )
        return rows

    def get_daily_prices(self, ticker: str, start_date: date, end_date: date) -> list[dict[str, Any]]:
        frame = self.stock.get_market_ohlcv_by_date(
            _format_date(start_date),
            _format_date(end_date),
            ticker,
            adjusted=True,
        )
        return _price_frame_to_rows(ticker, frame)

    def get_fundamentals(self, ticker: str, start_date: date, end_date: date) -> list[dict[str, Any]]:
        frame = self.stock.get_market_fundamental_by_date(
            _format_date(start_date),
            _format_date(end_date),
            ticker,
        )
        return _fundamental_frame_to_rows(ticker, frame)


def sync_phase1_data(
    *,
    engine: Engine,
    provider: MarketDataProvider,
    start_date: date,
    end_date: date,
) -> dict[str, int]:
    error: Exception | None = None
    result: dict[str, int] | None = None
    with session_scope(engine) as session:
        sync_run = SyncRun(status="running")
        session.add(sync_run)
        session.flush()

        try:
            universe = provider.get_universe()
            universe_count = upsert_stocks(session, universe)

            price_rows: list[dict[str, Any]] = []
            fundamental_rows: list[dict[str, Any]] = []
            for stock_row in universe:
                ticker = stock_row["ticker"]
                price_rows.extend(provider.get_daily_prices(ticker, start_date, end_date))
                fundamental_rows.extend(provider.get_fundamentals(ticker, start_date, end_date))

            price_count = upsert_daily_prices(session, price_rows)
            fundamental_count = upsert_fundamentals(session, fundamental_rows)

            sync_run.status = "success"
            sync_run.finished_at = utc_now()
            sync_run.universe_count = universe_count
            sync_run.price_count = price_count
            sync_run.fundamental_count = fundamental_count
            result = {
                "universe_count": universe_count,
                "price_count": price_count,
                "fundamental_count": fundamental_count,
            }
        except Exception as exc:
            sync_run.status = "failed"
            sync_run.finished_at = utc_now()
            sync_run.error_message = str(exc)
            error = exc

    if error is not None:
        raise error
    if result is None:
        raise RuntimeError("sync finished without a result")
    return result


def _format_date(value: date) -> str:
    return value.strftime("%Y%m%d")


def _price_frame_to_rows(ticker: str, frame: pd.DataFrame) -> list[dict[str, Any]]:
    rows = []
    for index, row in frame.iterrows():
        rows.append(
            {
                "ticker": ticker,
                "date": _index_to_date(index),
                "open": _get_optional(row, "시가"),
                "high": _get_optional(row, "고가"),
                "low": _get_optional(row, "저가"),
                "close": _get_optional(row, "종가"),
                "volume": _get_optional(row, "거래량"),
                "trading_value": _get_optional(row, "거래대금"),
                "market_cap": _get_optional(row, "시가총액"),
            }
        )
    return rows


def _fundamental_frame_to_rows(ticker: str, frame: pd.DataFrame) -> list[dict[str, Any]]:
    rows = []
    for index, row in frame.iterrows():
        rows.append(
            {
                "ticker": ticker,
                "date": _index_to_date(index),
                "bps": _get_optional(row, "BPS"),
                "per": _get_optional(row, "PER"),
                "pbr": _get_optional(row, "PBR"),
                "eps": _get_optional(row, "EPS"),
                "div": _get_optional(row, "DIV"),
                "dps": _get_optional(row, "DPS"),
            }
        )
    return rows


def _index_to_date(value: Any) -> date:
    if hasattr(value, "date"):
        return value.date()
    return date.fromisoformat(str(value)[:10])


def _get_optional(row: pd.Series, key: str) -> float | None:
    if key not in row or pd.isna(row[key]):
        return None
    return float(row[key])
