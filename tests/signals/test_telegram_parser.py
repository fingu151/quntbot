from datetime import date

from src.signals.telegram_parser import parse_morning_brief


_SAMPLE_MESSAGE = """
주식 요약 · 모닝 · 2026-05-06
글로벌 매크로: 미국 증시는 소폭 상승 마감.

수혜 종목
005930 삼성전자 ★★★ - AI 서버 수요 증가
000660 SK하이닉스 ★★ - HBM 생산 확대

주의 종목
035420 NAVER - 광고 회복 지연

| 종목 | 커버 | TP | 코멘트 |
| 005930 삼성전자 | ★★★ | 90,000 | AI 서버 최선호 |
| 000660 SK하이닉스 | ★★ | 200,000 | HBM 수혜 |
"""


def test_parse_morning_brief_extracts_date():
    result = parse_morning_brief(_SAMPLE_MESSAGE)

    assert result is not None
    assert result.message_date == date(2026, 5, 6)


def test_parse_morning_brief_returns_none_for_non_brief():
    result = parse_morning_brief("안녕하세요. 일반 메시지입니다.")

    assert result is None


def test_parse_morning_brief_extracts_table_and_section_signals():
    result = parse_morning_brief(_SAMPLE_MESSAGE)

    assert result is not None
    assert {s.ticker for s in result.signals} == {"005930", "000660", "035420"}


def test_parse_morning_brief_table_signals_take_precedence():
    result = parse_morning_brief(_SAMPLE_MESSAGE)
    by_ticker = {s.ticker: s for s in result.signals}

    assert by_ticker["005930"].signal_type == "positive"
    assert by_ticker["005930"].star_rating == 3
    assert by_ticker["005930"].raw_score == 3.0
    assert by_ticker["005930"].target_price == 90000.0


def test_parse_morning_brief_warning_signal_from_section_only():
    result = parse_morning_brief(_SAMPLE_MESSAGE)
    by_ticker = {s.ticker: s for s in result.signals}

    assert by_ticker["035420"].signal_type == "warning"
    assert by_ticker["035420"].star_rating == 0
    assert by_ticker["035420"].raw_score == -1.0
    assert by_ticker["035420"].target_price is None


def test_parse_morning_brief_target_prices_from_table():
    result = parse_morning_brief(_SAMPLE_MESSAGE)
    by_ticker = {s.ticker: s for s in result.signals}

    assert by_ticker["000660"].target_price == 200000.0


def test_parse_morning_brief_stores_message_id():
    result = parse_morning_brief(_SAMPLE_MESSAGE, message_id=42)

    assert result is not None
    assert result.message_id == 42


def test_parse_morning_brief_resolves_stock_names_to_tickers():
    text = """
주식 요약 · 모닝 · 2026-05-09

▷ 씨에스윈드 — DS 6.5만 → 8.1만 ▲25%
▷ 에이피알 — 한화 45만 → 50만 ▲11%
"""

    result = parse_morning_brief(
        text,
        ticker_by_name={"씨에스윈드": "112610", "에이피알": "278470"},
    )
    by_ticker = {s.ticker: s for s in result.signals}

    assert result is not None
    assert set(by_ticker) == {"112610", "278470"}
    assert by_ticker["112610"].signal_type == "positive"
    assert by_ticker["112610"].raw_score == 1.0


def test_parse_morning_brief_ignores_url_numbers_and_source_link_names():
    text = """
주식 요약 · 모닝 · 2026-05-09

1. **삼성전자 5/21 총파업 임박** — 메모리 라인 차질 시 HBM 공급 thesis 직격
원/달러 박스권 예상 [[신한 FX](https://example.com/file.do?attachmentId=351341)]
*AI 인프라*: NVDA·AVGO — 신규 투자 [[SK증권](https://t.me/skitteam/3861)]
"""

    result = parse_morning_brief(
        text,
        ticker_by_name={"삼성전자": "005930", "SK증권": "001510"},
    )

    assert result is not None
    by_ticker = {s.ticker: s for s in result.signals}
    assert by_ticker == {"005930": by_ticker["005930"]}
    assert by_ticker["005930"].signal_type == "warning"
