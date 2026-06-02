from datetime import date
from types import SimpleNamespace

from src.data.database import create_tables, get_engine, session_scope
from src.data.repositories import get_latest_telegram_signals, upsert_stocks, upsert_telegram_signals
from src.signals import telegram_reader
from src.signals.telegram_parser import ParsedMessage


_MESSAGE = """
주식 요약 · 모닝 · 2026-05-06

수혜 종목
005930 삼성전자 ★★★ - AI 서버 수요 증가

주의 종목
035420 NAVER - 광고 회복 지연
"""


def test_fetch_and_store_signals_persists_parsed_rows(monkeypatch):
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)

    async def fake_fetch_messages(limit):
        assert limit == 3
        return [(77, _MESSAGE)]

    monkeypatch.setattr(
        telegram_reader,
        "TELEGRAM_SIGNAL",
        SimpleNamespace(enabled=True, fetch_limit=3),
    )
    monkeypatch.setattr(telegram_reader, "_fetch_messages", fake_fetch_messages)

    stored = telegram_reader.fetch_and_store_signals(engine, as_of_date=date(2026, 5, 6))

    with session_scope(engine) as session:
        latest = get_latest_telegram_signals(session, date(2026, 5, 6))

    assert stored == 2
    assert latest == {"005930": 3.0, "035420": -1.0}


def test_fetch_and_store_signals_returns_zero_when_disabled(monkeypatch):
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)

    monkeypatch.setattr(
        telegram_reader,
        "TELEGRAM_SIGNAL",
        SimpleNamespace(enabled=False, fetch_limit=3),
    )

    stored = telegram_reader.fetch_and_store_signals(engine, as_of_date=date(2026, 5, 6))

    assert stored == 0


def test_fetch_and_store_signals_resolves_stock_names_from_database(monkeypatch):
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    with session_scope(engine) as session:
        upsert_stocks(
            session,
            [
                {"ticker": "112610", "name": "씨에스윈드", "market": "KOSPI"},
                {"ticker": "278470", "name": "에이피알", "market": "KOSPI"},
            ],
        )

    message = """
주식 요약 · 모닝 · 2026-05-09

▷ 씨에스윈드 — DS 6.5만 → 8.1만 ▲25%
▷ 에이피알 — 한화 45만 → 50만 ▲11%
"""

    async def fake_fetch_messages(limit):
        return [(88, message)]

    monkeypatch.setattr(
        telegram_reader,
        "TELEGRAM_SIGNAL",
        SimpleNamespace(enabled=True, fetch_limit=3),
    )
    monkeypatch.setattr(telegram_reader, "_fetch_messages", fake_fetch_messages)

    stored = telegram_reader.fetch_and_store_signals(engine, as_of_date=date(2026, 5, 9))

    with session_scope(engine) as session:
        latest = get_latest_telegram_signals(session, date(2026, 5, 9))

    assert stored == 2
    assert latest == {"112610": 1.0, "278470": 1.0}


def test_fetch_and_store_signals_replaces_stale_rows_for_same_date(monkeypatch):
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    with session_scope(engine) as session:
        upsert_stocks(session, [{"ticker": "005930", "name": "삼성전자", "market": "KOSPI"}])
        upsert_telegram_signals(
            session,
            [
                {
                    "message_date": date(2026, 5, 9),
                    "ticker": "001510",
                    "signal_type": "positive",
                    "star_rating": 0,
                    "raw_score": 1.0,
                    "target_price": None,
                    "message_id": 1,
                }
            ],
        )

    message = """
주식 요약 · 모닝 · 2026-05-09

1. **삼성전자 5/21 총파업 임박** — 메모리 라인 차질 시 HBM 공급 thesis 직격
"""

    async def fake_fetch_messages(limit):
        return [(88, message)]

    monkeypatch.setattr(
        telegram_reader,
        "TELEGRAM_SIGNAL",
        SimpleNamespace(enabled=True, fetch_limit=3),
    )
    monkeypatch.setattr(telegram_reader, "_fetch_messages", fake_fetch_messages)

    stored = telegram_reader.fetch_and_store_signals(engine, as_of_date=date(2026, 5, 9))

    with session_scope(engine) as session:
        latest = get_latest_telegram_signals(session, date(2026, 5, 9))

    assert stored == 1
    assert latest == {"005930": -1.0}


def test_fetch_and_store_signals_clears_same_day_rows_when_brief_has_no_signals(monkeypatch):
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    with session_scope(engine) as session:
        upsert_telegram_signals(
            session,
            [
                {
                    "message_date": date(2026, 5, 9),
                    "ticker": "005930",
                    "signal_type": "positive",
                    "star_rating": 3,
                    "raw_score": 3.0,
                    "target_price": None,
                    "message_id": 1,
                }
            ],
        )

    async def fake_fetch_messages(limit):
        return [(99, "brief")]

    monkeypatch.setattr(
        telegram_reader,
        "TELEGRAM_SIGNAL",
        SimpleNamespace(enabled=True, fetch_limit=3),
    )
    monkeypatch.setattr(telegram_reader, "_fetch_messages", fake_fetch_messages)
    monkeypatch.setattr(
        telegram_reader,
        "parse_morning_brief",
        lambda text, message_id, ticker_by_name: ParsedMessage(
            message_date=date(2026, 5, 9),
            signals=[],
            message_id=message_id,
        ),
    )

    stored = telegram_reader.fetch_and_store_signals(engine, as_of_date=date(2026, 5, 9))

    with session_scope(engine) as session:
        latest = get_latest_telegram_signals(session, date(2026, 5, 9))

    assert stored == 0
    assert latest == {}
