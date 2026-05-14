from __future__ import annotations

from collections.abc import Callable
from datetime import date

import requests
from loguru import logger
from sqlalchemy import Engine, select

from src.data.database import session_scope
from src.data.models import Stock
from src.data.repositories import replace_busanstock_signals_for_date
from src.signals.busanstock_parser import parse_busanstock_report


BUSANSTOCK_REPORT_URL = "https://busanstock.vercel.app/"
HtmlFetcher = Callable[[str], str]


def fetch_html(url: str = BUSANSTOCK_REPORT_URL) -> str:
    response = requests.get(url, timeout=20)
    response.raise_for_status()
    return response.text


def fetch_and_store_busanstock_signals(
    engine: Engine,
    *,
    as_of_date: date | None = None,
    html_fetcher: HtmlFetcher = fetch_html,
    url: str = BUSANSTOCK_REPORT_URL,
) -> int:
    report_date = as_of_date or date.today()
    try:
        html = html_fetcher(url)
    except Exception as exc:
        logger.warning(f"Busanstock fetch failed: {exc}")
        return 0

    ticker_by_name = _load_ticker_by_name(engine)
    parsed = parse_busanstock_report(html, ticker_by_name=ticker_by_name, signal_date=report_date)
    if not parsed:
        logger.debug(f"No Busanstock signals parsed for {report_date}")
        return 0

    rows = [
        {
            "signal_date": signal.signal_date,
            "ticker": signal.ticker,
            "signal_type": signal.signal_type,
            "source_section": signal.source_section,
            "raw_score": signal.raw_score,
            "detail": signal.detail,
        }
        for signal in parsed
    ]
    with session_scope(engine) as session:
        count = replace_busanstock_signals_for_date(session, report_date, rows)
    logger.info(f"Busanstock signals stored: {count} rows for {report_date}")
    return count


def _load_ticker_by_name(engine: Engine) -> dict[str, str]:
    with session_scope(engine) as session:
        stocks = session.scalars(select(Stock).where(Stock.is_active.is_(True))).all()
    return {stock.name: stock.ticker for stock in stocks}
