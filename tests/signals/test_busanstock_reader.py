from datetime import date

from src.data.database import create_tables, get_engine, session_scope
from src.data.repositories import get_latest_busanstock_signals, upsert_stocks
from src.signals.busanstock_reader import fetch_and_store_busanstock_signals


_HTML = """
<html>
<head><title>트비 주식뉴스 어그리게이터 리포트 · 2026-05-09</title></head>
<body>
<h3>종목 한눈에 · STOCK SNAPSHOT</h3>
<p>매수 (1) 기아</p>
<p>매도·경고 (1) 카카오</p>
<h3>컨센서스 변경 · TP 변동률 시각화</h3>
<p>기아 유진 17만→30만 ▲76%</p>
</body>
</html>
"""


def test_fetch_and_store_busanstock_signals_persists_parsed_rows():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    with session_scope(engine) as session:
        upsert_stocks(
            session,
            [
                {"ticker": "000270", "name": "기아", "market": "KOSPI"},
                {"ticker": "035720", "name": "카카오", "market": "KOSPI"},
            ],
        )

    stored = fetch_and_store_busanstock_signals(
        engine,
        as_of_date=date(2026, 5, 9),
        html_fetcher=lambda url: _HTML,
    )

    with session_scope(engine) as session:
        latest = get_latest_busanstock_signals(session, date(2026, 5, 9))

    assert stored == 3
    assert latest == {"000270": 1.0, "035720": -0.7}
