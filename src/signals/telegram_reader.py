"""
Fetch morning briefing messages from a Telegram channel using the MTProto user API.

Requires TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_SIGNAL_CHANNEL in .env.
On first run, telethon prompts for a phone number + OTP to create a session file
at data/telegram_signal.session (excluded from git).

Usage (one-shot, called from APScheduler):
    from src.signals.telegram_reader import fetch_and_store_signals
    fetch_and_store_signals(db_engine)
"""
from __future__ import annotations

import asyncio
from datetime import date

from loguru import logger
from sqlalchemy import Engine, select

from config import TELEGRAM_SIGNAL
from src.data.database import session_scope
from src.data.models import Stock
from src.data.repositories import replace_telegram_signals_for_date
from src.signals.telegram_parser import ParsedMessage, parse_morning_brief

_SESSION_NAME = "data/telegram_signal"


async def _fetch_messages(limit: int) -> list[tuple[int, str]]:
    """Return [(message_id, text), ...] from the configured channel."""
    from telethon import TelegramClient  # deferred import so module loads without telethon

    client = TelegramClient(_SESSION_NAME, TELEGRAM_SIGNAL.api_id, TELEGRAM_SIGNAL.api_hash)
    results: list[tuple[int, str]] = []
    async with client:
        async for msg in client.iter_messages(TELEGRAM_SIGNAL.channel, limit=limit):
            if msg.text:
                results.append((msg.id, msg.text))
    return results


def fetch_and_store_signals(engine: Engine, as_of_date: date | None = None) -> int:
    """
    Fetch recent channel messages, parse morning briefs, store to DB.
    Returns the number of signal rows stored.
    """
    if not TELEGRAM_SIGNAL.enabled:
        logger.debug("Telegram signal reader disabled (missing credentials)")
        return 0

    today = as_of_date or date.today()
    try:
        raw_messages = asyncio.run(_fetch_messages(TELEGRAM_SIGNAL.fetch_limit))
    except Exception as exc:
        logger.warning(f"Telegram fetch failed: {exc}")
        return 0

    ticker_by_name = _load_ticker_by_name(engine)
    parsed_today: list[ParsedMessage] = []
    for msg_id, text in raw_messages:
        parsed = parse_morning_brief(text, message_id=msg_id, ticker_by_name=ticker_by_name)
        if parsed and parsed.message_date == today:
            parsed_today.append(parsed)

    if not parsed_today:
        logger.debug(f"No morning brief found for {today}")
        return 0

    # Use the first (most recent) matching message
    brief = parsed_today[0]
    if not brief.signals:
        logger.debug(f"Morning brief for {today} parsed but contained no ticker signals")
        return 0

    rows = [
        {
            "message_date": brief.message_date,
            "ticker": sig.ticker,
            "signal_type": sig.signal_type,
            "star_rating": sig.star_rating,
            "raw_score": sig.raw_score,
            "target_price": sig.target_price,
            "message_id": brief.message_id,
        }
        for sig in brief.signals
    ]

    with session_scope(engine) as session:
        count = replace_telegram_signals_for_date(session, brief.message_date, rows)

    logger.info(f"Telegram signals stored: {count} rows for {today}")
    return count


def _load_ticker_by_name(engine: Engine) -> dict[str, str]:
    with session_scope(engine) as session:
        stocks = session.scalars(select(Stock).where(Stock.is_active.is_(True))).all()
    return {stock.name: stock.ticker for stock in stocks}
