from datetime import date, timedelta

from sqlalchemy import func, select

from src.data.database import create_tables, get_engine, session_scope
from src.data.models import DailyPrice, Fundamental, ResearchReportAnalysis, ResearchReportSignal, Stock
from src.data.repositories import (
    count_rows,
    get_latest_busanstock_signals,
    get_recent_research_report_scores,
    get_research_report_signals_by_keys,
    get_recent_investor_flow_scores,
    get_latest_telegram_signals,
    replace_busanstock_signals_for_date,
    replace_telegram_signals_for_date,
    upsert_daily_prices,
    upsert_fundamentals,
    upsert_investor_flows,
    upsert_research_report_analyses,
    upsert_research_report_signals,
    upsert_stocks,
    upsert_telegram_signals,
)


def make_session():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    return engine


def test_upsert_stocks_inserts_and_updates_existing_ticker():
    engine = make_session()

    with session_scope(engine) as session:
        inserted = upsert_stocks(
            session,
            [{"ticker": "005930", "name": "삼성전자", "market": "KOSPI"}],
        )
        updated = upsert_stocks(
            session,
            [{"ticker": "005930", "name": "삼성전자우아님", "market": "KOSPI"}],
        )

    with session_scope(engine) as session:
        rows = session.scalars(select(Stock)).all()

    assert inserted == 1
    assert updated == 1
    assert len(rows) == 1
    assert rows[0].name == "삼성전자우아님"


def test_upsert_daily_prices_uses_ticker_and_date_as_unique_key():
    engine = make_session()
    row = {
        "ticker": "005930",
        "date": date(2026, 5, 1),
        "open": 70000,
        "high": 71000,
        "low": 69000,
        "close": 70500,
        "volume": 1000,
    }

    with session_scope(engine) as session:
        upsert_daily_prices(session, [row])
        upsert_daily_prices(session, [{**row, "close": 70600}])

    with session_scope(engine) as session:
        rows = session.scalars(select(DailyPrice)).all()

    assert len(rows) == 1
    assert rows[0].close == 70600


def test_upsert_daily_prices_batches_large_inputs_under_sqlite_variable_limit():
    engine = make_session()
    start = date(2015, 1, 1)
    rows = [
        {
            "ticker": "005930",
            "date": start + timedelta(days=i),
            "open": 70000 + i,
            "high": 71000 + i,
            "low": 69000 + i,
            "close": 70500 + i,
            "volume": 1000 + i,
            "trading_value": 70_000_000 + i,
            "market_cap": 400_000_000_000_000 + i,
        }
        for i in range(4000)
    ]

    with session_scope(engine) as session:
        inserted = upsert_daily_prices(session, rows)

    with session_scope(engine) as session:
        count = session.scalar(select(func.count()).select_from(DailyPrice))

    assert inserted == 4000
    assert count == 4000


def test_upsert_fundamentals_uses_ticker_and_date_as_unique_key():
    engine = make_session()
    row = {
        "ticker": "005930",
        "date": date(2026, 5, 1),
        "bps": 50000,
        "per": 12.5,
        "pbr": 1.3,
        "eps": 5000,
        "div": 2.0,
        "dps": 1500,
    }

    with session_scope(engine) as session:
        upsert_fundamentals(session, [row])
        upsert_fundamentals(session, [{**row, "per": 13.0}])

    with session_scope(engine) as session:
        rows = session.scalars(select(Fundamental)).all()

    assert len(rows) == 1
    assert rows[0].per == 13.0


def test_count_rows_returns_table_counts():
    engine = make_session()

    with session_scope(engine) as session:
        upsert_stocks(session, [{"ticker": "005930", "name": "삼성전자", "market": "KOSPI"}])
        counts = count_rows(session)

    assert counts["stocks"] == 1
    assert counts["daily_prices"] == 0
    assert counts["fundamentals"] == 0


def test_upsert_telegram_signals_saves_and_updates_rows():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)

    with session_scope(engine) as session:
        inserted = upsert_telegram_signals(
            session,
            [
                {
                    "message_date": date(2026, 5, 11),
                    "ticker": "005930",
                    "signal_type": "positive",
                    "star_rating": 3,
                    "raw_score": 3.0,
                    "target_price": 90000.0,
                    "message_id": 100,
                }
            ],
        )

    with session_scope(engine) as session:
        updated = upsert_telegram_signals(
            session,
            [
                {
                    "message_date": date(2026, 5, 11),
                    "ticker": "005930",
                    "signal_type": "positive",
                    "star_rating": 2,
                    "raw_score": 2.0,
                    "target_price": 88000.0,
                    "message_id": 101,
                }
            ],
        )
        latest = get_latest_telegram_signals(session, date(2026, 5, 11))

    assert inserted == 1
    assert updated == 1
    assert latest == {"005930": 2.0}


def test_replace_telegram_signals_for_date_keeps_existing_rows_when_empty():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)

    with session_scope(engine) as session:
        upsert_telegram_signals(
            session,
            [
                {
                    "message_date": date(2026, 5, 11),
                    "ticker": "005930",
                    "signal_type": "positive",
                    "star_rating": 3,
                    "raw_score": 3.0,
                    "target_price": 90000.0,
                    "message_id": 100,
                }
            ],
        )
        replaced = replace_telegram_signals_for_date(session, date(2026, 5, 11), [])
        latest = get_latest_telegram_signals(session, date(2026, 5, 11))

    assert replaced == 0
    assert latest == {"005930": 3.0}


def test_replace_busanstock_signals_for_date_saves_and_replaces_rows():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)

    with session_scope(engine) as session:
        first = replace_busanstock_signals_for_date(
            session,
            date(2026, 5, 11),
            [
                {
                    "signal_date": date(2026, 5, 11),
                    "ticker": "005930",
                    "signal_type": "buy",
                    "source_section": "stock_snapshot",
                    "raw_score": 0.3,
                    "detail": "매수 분류",
                },
                {
                    "signal_date": date(2026, 5, 11),
                    "ticker": "005930",
                    "signal_type": "tp_up",
                    "source_section": "consensus",
                    "raw_score": 0.5,
                    "detail": "TP 상향",
                },
            ],
        )
        second = replace_busanstock_signals_for_date(
            session,
            date(2026, 5, 11),
            [
                {
                    "signal_date": date(2026, 5, 11),
                    "ticker": "000660",
                    "signal_type": "warning",
                    "source_section": "stock_snapshot",
                    "raw_score": -0.7,
                    "detail": "매도·경고 분류",
                }
            ],
        )
        latest = get_latest_busanstock_signals(session, date(2026, 5, 11))

    assert first == 2
    assert second == 1
    assert latest == {"000660": -0.7}


def test_get_latest_busanstock_signals_does_not_carry_to_later_dates():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)

    with session_scope(engine) as session:
        replace_busanstock_signals_for_date(
            session,
            date(2026, 5, 11),
            [
                {
                    "signal_date": date(2026, 5, 11),
                    "ticker": "005930",
                    "signal_type": "buy",
                    "source_section": "stock_snapshot",
                    "raw_score": 0.3,
                    "detail": "매수 분류",
                }
            ],
        )
        later = get_latest_busanstock_signals(session, date(2026, 5, 12))

    assert later == {}


def test_get_recent_investor_flow_scores_penalizes_retail_only_buying():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)

    with session_scope(engine) as session:
        upsert_daily_prices(
            session,
            [
                {
                    "ticker": "005930",
                    "date": date(2026, 5, 11),
                    "close": 100,
                    "trading_value": 10_000_000_000,
                },
                {
                    "ticker": "000660",
                    "date": date(2026, 5, 11),
                    "close": 100,
                    "trading_value": 10_000_000_000,
                },
            ],
        )
        upsert_investor_flows(
            session,
            [
                {
                    "ticker": "005930",
                    "date": date(2026, 5, 11),
                    "individual_net_buy": 800_000_000,
                    "foreign_net_buy": -400_000_000,
                    "institution_net_buy": -300_000_000,
                },
                {
                    "ticker": "000660",
                    "date": date(2026, 5, 11),
                    "individual_net_buy": -500_000_000,
                    "foreign_net_buy": 300_000_000,
                    "institution_net_buy": 200_000_000,
                },
            ],
        )
        scores = get_recent_investor_flow_scores(session, date(2026, 5, 11), lookback_days=5)

    assert scores["005930"] == -1.0
    assert scores["000660"] == 0.6


def test_upsert_research_report_signals_saves_and_updates_rows():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)

    row = {
        "report_date": date(2026, 5, 11),
        "ticker": "005930",
        "source": "morningstar",
        "region": "global",
        "broker": "Morningstar",
        "rating": "Buy",
        "rating_score": 0.6,
        "target_price": 90000.0,
        "previous_target_price": 85000.0,
        "target_price_change_pct": 0.0588,
        "sentiment_score": 0.2,
        "raw_score": 0.8,
        "title": "Samsung Electronics valuation improving",
        "source_url": "https://example.test/report",
    }

    with session_scope(engine) as session:
        inserted = upsert_research_report_signals(session, [row])
        updated = upsert_research_report_signals(session, [{**row, "rating": "Hold", "raw_score": 0.1}])

    with session_scope(engine) as session:
        rows = session.scalars(select(ResearchReportSignal)).all()

    assert inserted == 1
    assert updated == 1
    assert len(rows) == 1
    assert rows[0].rating == "Hold"
    assert rows[0].raw_score == 0.1


def test_upsert_research_report_analyses_saves_and_updates_by_signal_id():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    signal_row = {
        "report_date": date(2026, 5, 11),
        "ticker": "005930",
        "source": "hankyung_consensus",
        "region": "domestic",
        "broker": "한경 컨센서스",
        "rating": "Buy",
        "rating_score": 0.6,
        "target_price": 90000.0,
        "previous_target_price": 85000.0,
        "target_price_change_pct": 0.0588,
        "sentiment_score": 0.2,
        "raw_score": 0.8,
        "title": "Samsung Electronics valuation improving",
        "source_url": "https://example.test/report.pdf",
    }

    with session_scope(engine) as session:
        upsert_research_report_signals(session, [signal_row])
        signal = get_research_report_signals_by_keys(
            session,
            [(date(2026, 5, 11), "005930", "hankyung_consensus", signal_row["title"])],
        )[0]
        analysis_row = {
            "report_signal_id": signal.id,
            "ticker": signal.ticker,
            "report_date": signal.report_date,
            "source": signal.source,
            "broker": signal.broker,
            "title": signal.title,
            "source_url": signal.source_url,
            "body_text_status": "extracted",
            "body_text_chars": 1200,
            "summary": "실적 개선과 목표가 상향이 핵심입니다.",
            "investment_opinion": "positive",
            "buy_thesis": "매수 근거",
            "sell_or_risk_thesis": "",
            "growth_drivers": "AI 수요",
            "earnings_drivers": "영업이익 개선",
            "valuation_view": "업사이드 존재",
            "target_price_rationale": "목표주가 상향",
            "risk_factors": "환율",
            "evidence_terms": "매수, 목표주가, 영업이익",
            "analysis_version": "rule-v1",
            "confidence": 0.8,
        }
        inserted = upsert_research_report_analyses(session, [analysis_row])
        updated = upsert_research_report_analyses(
            session,
            [{**analysis_row, "summary": "업데이트된 요약", "confidence": 0.6}],
        )

    with session_scope(engine) as session:
        rows = session.scalars(select(ResearchReportAnalysis)).all()

    assert inserted == 1
    assert updated == 1
    assert len(rows) == 1
    assert rows[0].summary == "업데이트된 요약"
    assert rows[0].confidence == 0.6


def test_get_recent_research_report_scores_averages_positive_and_negative_views():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)

    with session_scope(engine) as session:
        upsert_research_report_signals(
            session,
            [
                {
                    "report_date": date(2026, 5, 11),
                    "ticker": "005930",
                    "source": "zacks",
                    "region": "global",
                    "broker": "Zacks",
                    "rating": "Strong Buy",
                    "rating_score": 1.0,
                    "target_price": None,
                    "previous_target_price": None,
                    "target_price_change_pct": None,
                    "sentiment_score": None,
                    "raw_score": 1.0,
                    "title": "Positive earnings revisions",
                    "source_url": None,
                },
                {
                    "report_date": date(2026, 5, 1),
                    "ticker": "005930",
                    "source": "morningstar",
                    "region": "global",
                    "broker": "Morningstar",
                    "rating": "Sell",
                    "rating_score": -1.0,
                    "target_price": None,
                    "previous_target_price": None,
                    "target_price_change_pct": None,
                    "sentiment_score": None,
                    "raw_score": -1.0,
                    "title": "Shares look overvalued",
                    "source_url": None,
                },
                {
                    "report_date": date(2026, 3, 1),
                    "ticker": "000660",
                    "source": "zacks",
                    "region": "global",
                    "broker": "Zacks",
                    "rating": "Strong Sell",
                    "rating_score": -1.0,
                    "target_price": None,
                    "previous_target_price": None,
                    "target_price_change_pct": None,
                    "sentiment_score": None,
                    "raw_score": -1.0,
                    "title": "Stale negative report",
                    "source_url": None,
                },
            ],
        )
        scores = get_recent_research_report_scores(session, date(2026, 5, 11), lookback_days=30)

    assert scores["005930"] > 0.0
    assert "000660" not in scores
