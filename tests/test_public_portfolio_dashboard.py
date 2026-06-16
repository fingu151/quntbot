from __future__ import annotations

import ast
import json
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from scripts.public_portfolio_dashboard import (
    FACTOR_LABELS,
    DEFAULT_RESEARCH_LIMIT,
    DEFAULT_VISIBLE_RESEARCH_CARDS,
    _actionable_quality_issues,
    _body_text_available_count,
    _build_css,
    _detail_html,
    _highlight_cards_html,
    _hero_html,
    _holdings_table_html,
    _latest_not_found_quality_issues,
    _quality_dashboard_summary,
    _holdings_rows,
    _research_qa_summary_html,
    _research_qa_action_queue_html,
    _research_operator_next_action_html,
    _research_report_card_html,
    _research_freshness_html,
    _research_supplement_need_html,
    _research_quality_issue_html,
    _source_quality_label,
    _ticker_research_brief_card_html,
    build_research_supplement_needs,
    build_research_qa_action_summary,
    build_research_qa_sample_summary,
    build_ticker_research_briefs,
    build_ticker_research_quality_report,
    filter_research_report_briefs,
    format_krw,
    format_pct,
    load_research_report_briefs,
    load_research_quality_queue,
    load_research_qa_action_queue,
    load_research_brief_qa_sample,
    load_snapshot,
    load_ticker_research_briefs,
    render_dashboard,
    research_report_display_limit,
    snapshot_is_stale,
)
from src.data.database import create_tables, get_engine, session_scope
from src.data.models import ResearchReportSignal
from src.data.repositories import upsert_research_report_briefs, upsert_research_report_signals


KST = ZoneInfo("Asia/Seoul")


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _sample_snapshot() -> dict:
    return {
        "schema_version": 1,
        "generated_at": "2026-05-12T09:00:00+09:00",
        "source": {"dashboard_calls_kis": False},
        "summary": {
            "holding_count": 1,
            "total_market_value": 720000,
            "stock_market_value": 720000,
            "cash_balance": 280000,
            "total_asset_value": 1000000,
            "total_cost": 700000,
            "total_profit_loss": 20000,
            "total_profit_loss_rate": 2.86,
            "realized_profit_loss": 12000,
        },
        "cash": {"available": 280000, "withdrawable": 270000, "source": "kis_balance"},
        "realized": {"profit_loss": 12000, "source": "kis_balance"},
        "market": {
            "generated_at": "2026-05-12T09:00:00+09:00",
            "source": "yahoo_chart",
            "status": "OPEN",
            "session_label": "정규장",
            "kospi": {"value": 2780.5, "chg_pct": 0.5},
            "kosdaq": {"value": 900.2, "chg_pct": -0.1},
            "usdkrw": {"value": 1365.4, "chg_pct": 0.2},
        },
        "positions": [
            {
                "ticker": "005930",
                "name": "Samsung Electronics",
                "qty": 10,
                "avg_price": 70000,
                "current_price": 72000,
                "market_value": 720000,
                "profit_loss": 20000,
                "profit_loss_rate": 2.86,
                "rationale": {
                    "order_reason": "target allocation buy",
                    "rank": 1,
                    "total_score": 1.2345,
                    "factor_scores": {"quality": 0.2, "momentum": 0.3},
                    "market_context": {
                        "quality": {"roe": 0.12},
                        "investor_flow": {"foreign_net_buy": 1000000.0},
                    },
                    "signals": [
                        {
                            "source": "busanstock",
                            "detail": "TP up",
                            "raw_score": 1.0,
                        }
                    ],
                },
            }
        ],
        "warnings": ["missing_rationale:000660"],
    }


def test_format_helpers_render_public_values() -> None:
    assert format_krw(1234567) == "1,234,567 KRW"
    assert format_krw(None) == "-"
    assert format_pct(2.864) == "2.86%"
    assert format_pct(None) == "-"


def test_public_dashboard_korean_labels_are_valid_utf8_text() -> None:
    assert FACTOR_LABELS == {
        "value": "Value · 가치",
        "quality": "Quality · 품질",
        "momentum": "Momentum · 모멘텀",
        "yield": "Yield · 배당",
        "telegram": "Telegram",
        "busanstock": "Busanstock",
        "investor_flow": "Flow · 수급",
        "research_report": "Research",
    }

    row = _holdings_rows(_sample_snapshot()["positions"])[0]

    assert list(row) == [
        "종목코드",
        "종목명",
        "수량",
        "평균단가",
        "현재가",
        "평가액",
        "평가손익",
        "수익률",
    ]


def test_load_snapshot_reports_missing_file(tmp_path: Path) -> None:
    result = load_snapshot(tmp_path / "missing.json")

    assert result["status"] == "missing"
    assert "snapshot" not in result


def test_load_snapshot_reports_malformed_json(tmp_path: Path) -> None:
    path = tmp_path / "public_portfolio_snapshot.json"
    path.write_text("{", encoding="utf-8")

    result = load_snapshot(path)

    assert result["status"] == "invalid"
    assert result["error"]


def test_load_snapshot_returns_valid_payload(tmp_path: Path) -> None:
    path = tmp_path / "public_portfolio_snapshot.json"
    payload = _sample_snapshot()
    _write_json(path, payload)

    result = load_snapshot(path)

    assert result == {"status": "ok", "snapshot": payload}


def test_snapshot_is_stale_uses_generated_timestamp_age() -> None:
    snapshot = {"generated_at": "2026-05-12T09:00:00+09:00"}

    assert (
        snapshot_is_stale(
            snapshot,
            now=datetime(2026, 5, 13, 8, 0, tzinfo=KST),
            max_age_hours=24,
        )
        is False
    )
    assert (
        snapshot_is_stale(
            snapshot,
            now=datetime(2026, 5, 13, 10, 0, tzinfo=KST),
            max_age_hours=24,
        )
        is True
    )


@pytest.mark.parametrize("snapshot", [{}, {"generated_at": "not-a-date"}])
def test_snapshot_is_stale_treats_missing_or_invalid_timestamp_as_stale(
    snapshot: dict,
) -> None:
    assert snapshot_is_stale(snapshot, now=datetime(2026, 5, 12, tzinfo=KST)) is True


def test_dashboard_module_does_not_import_trading_or_kis_helpers() -> None:
    source = Path("scripts/public_portfolio_dashboard.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden = {"KisClient", "TradingEngine", "execute_rebalance"}

    imported_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported_names.update(alias.name for alias in node.names)
            if node.module:
                imported_names.add(node.module)
        elif isinstance(node, ast.Import):
            imported_names.update(alias.name for alias in node.names)

    assert forbidden.isdisjoint(imported_names)


def test_load_research_report_briefs_reads_brief_rows_without_trading_calls():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    with session_scope(engine) as session:
        upsert_research_report_signals(
            session,
            [
                {
                    "report_date": datetime(2026, 5, 14).date(),
                    "ticker": "005930",
                    "source": "hankyung_consensus",
                    "region": "domestic",
                    "broker": "Hankyung",
                    "rating": "Buy",
                    "rating_score": 0.6,
                    "target_price": 90000,
                    "previous_target_price": 80000,
                    "target_price_change_pct": 0.125,
                    "sentiment_score": 0.2,
                    "raw_score": 0.8,
                    "title": "Samsung memory upcycle",
                    "source_url": "https://example.test/report.pdf",
                }
            ],
        )
        signal = session.scalars(select(ResearchReportSignal)).one()
        upsert_research_report_briefs(
            session,
            [
                {
                    "report_signal_id": signal.id,
                    "ticker": "005930",
                    "report_date": datetime(2026, 5, 14).date(),
                    "source": "hankyung_consensus",
                    "broker": "Hankyung",
                    "title": "Samsung memory upcycle",
                    "source_url": "https://example.test/report.pdf",
                    "report_type": "industry_outlook",
                    "headline": "Memory demand improves.",
                    "opinion": "positive",
                    "stock_view": "AI server demand.",
                    "earnings": "Margin recovery.",
                    "industry": "HBM demand.",
                    "new_business": "Advanced packaging expansion.",
                    "valuation": "Upside remains.",
                    "risks": "FX volatility.",
                    "source_quality": "full_text",
                    "brief_version": "brief-rule-v1",
                    "confidence": 0.8,
                }
            ],
        )

    result = load_research_report_briefs(engine_factory=lambda _: engine)

    assert result["status"] == "ok"
    assert result["rows"][0]["ticker"] == "005930"
    assert result["rows"][0]["summary"] == "Memory demand improves."
    assert result["rows"][0]["new_business"] == "Advanced packaging expansion."


def test_load_research_report_briefs_enriches_sparse_latest_row_from_full_text_same_ticker():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    with session_scope(engine) as session:
        upsert_research_report_signals(
            session,
            [
                {
                    "report_date": datetime(2026, 5, 13).date(),
                    "ticker": "004170",
                    "source": "mirae_asset",
                    "region": "domestic",
                    "broker": "Mirae",
                    "rating": "Buy",
                    "rating_score": 0.6,
                    "target_price": None,
                    "previous_target_price": None,
                    "target_price_change_pct": None,
                    "sentiment_score": None,
                    "raw_score": 0.6,
                    "title": "신세계 만점짜리 실적",
                    "source_url": "https://example.test/sparse.pdf",
                },
                {
                    "report_date": datetime(2026, 5, 10).date(),
                    "ticker": "004170",
                    "source": "hankyung_consensus",
                    "region": "domestic",
                    "broker": "Hankyung",
                    "rating": "Buy",
                    "rating_score": 0.6,
                    "target_price": None,
                    "previous_target_price": None,
                    "target_price_change_pct": None,
                    "sentiment_score": None,
                    "raw_score": 0.7,
                    "title": "신세계 백화점과 면세점 회복",
                    "source_url": "https://example.test/full.pdf",
                },
            ],
        )
        signals = session.scalars(select(ResearchReportSignal).order_by(ResearchReportSignal.report_date.desc())).all()
        sparse_signal, full_signal = signals
        upsert_research_report_briefs(
            session,
            [
                {
                    "report_signal_id": sparse_signal.id,
                    "ticker": "004170",
                    "report_date": datetime(2026, 5, 13).date(),
                    "source": "mirae_asset",
                    "broker": "Mirae",
                    "title": "신세계 만점짜리 실적",
                    "source_url": "https://example.test/sparse.pdf",
                    "report_type": "earnings_review",
                    "headline": "004170: 만점짜리 실적",
                    "opinion": "positive",
                    "stock_view": "만점짜리 실적",
                    "earnings": "",
                    "industry": "",
                    "new_business": "",
                    "valuation": "",
                    "risks": "",
                    "source_quality": "title_or_sparse",
                    "brief_version": "brief-rule-v3",
                    "confidence": 0.7,
                },
                {
                    "report_signal_id": full_signal.id,
                    "ticker": "004170",
                    "report_date": datetime(2026, 5, 10).date(),
                    "source": "hankyung_consensus",
                    "broker": "Hankyung",
                    "title": "신세계 백화점과 면세점 회복",
                    "source_url": "https://example.test/full.pdf",
                    "report_type": "earnings_review",
                    "headline": "004170: 백화점과 면세점 실적 개선",
                    "opinion": "positive",
                    "stock_view": "백화점과 면세점 실적 개선",
                    "earnings": "영업이익 개선이 예상된다.",
                    "industry": "외국인 매출 증가와 백화점 업황 회복이 이어진다.",
                    "new_business": "면세점 정규 매장 확대가 모멘텀이다.",
                    "valuation": "목표주가 상향 여력이 있다.",
                    "risks": "환율 변동은 리스크다.",
                    "source_quality": "full_text",
                    "brief_version": "brief-rule-v3",
                    "confidence": 0.95,
                },
            ],
        )

    result = load_research_report_briefs(engine_factory=lambda _: engine)

    assert result["status"] == "ok"
    latest = result["rows"][0]
    assert latest["ticker"] == "004170"
    assert latest["title"] == "신세계 만점짜리 실적"
    assert latest["body_text_status"] == "title_or_sparse"
    assert latest["growth_drivers"] == "외국인 매출 증가와 백화점 업황 회복이 이어진다."
    assert latest["earnings_drivers"] == "영업이익 개선이 예상된다."
    assert latest["new_business"] == "면세점 정규 매장 확대가 모멘텀이다."
    assert latest["risk_factors"] == "환율 변동은 리스크다."
    assert "enriched_from:004170/full_text" in latest["evidence_terms"]


def test_load_research_report_briefs_skips_noisy_full_text_donor_fragments():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    with session_scope(engine) as session:
        signal_rows = [
            {
                "report_date": datetime(2026, 5, 13).date(),
                "ticker": "004170",
                "source": "mirae_asset",
                "region": "domestic",
                "broker": "Mirae",
                "rating": "Buy",
                "rating_score": 0.6,
                "target_price": None,
                "previous_target_price": None,
                "target_price_change_pct": None,
                "sentiment_score": None,
                "raw_score": 0.6,
                "title": "신세계 만점짜리 실적",
                "source_url": "https://example.test/sparse.pdf",
            },
            {
                "report_date": datetime(2026, 5, 13).date(),
                "ticker": "004170",
                "source": "hankyung_consensus",
                "region": "domestic",
                "broker": "Noisy",
                "rating": "Buy",
                "rating_score": 0.6,
                "target_price": None,
                "previous_target_price": None,
                "target_price_change_pct": None,
                "sentiment_score": None,
                "raw_score": 0.7,
                "title": "신세계 표 조각",
                "source_url": "https://example.test/noisy.pdf",
            },
            {
                "report_date": datetime(2026, 5, 10).date(),
                "ticker": "004170",
                "source": "hankyung_consensus",
                "region": "domestic",
                "broker": "Clean",
                "rating": "Buy",
                "rating_score": 0.6,
                "target_price": None,
                "previous_target_price": None,
                "target_price_change_pct": None,
                "sentiment_score": None,
                "raw_score": 0.7,
                "title": "신세계 업황 회복",
                "source_url": "https://example.test/clean.pdf",
            },
        ]
        upsert_research_report_signals(session, signal_rows)
        signals = session.scalars(select(ResearchReportSignal).order_by(ResearchReportSignal.report_date.desc())).all()
        sparse_signal, noisy_signal, clean_signal = signals
        upsert_research_report_briefs(
            session,
            [
                {
                    "report_signal_id": sparse_signal.id,
                    "ticker": "004170",
                    "report_date": datetime(2026, 5, 13).date(),
                    "source": "mirae_asset",
                    "broker": "Mirae",
                    "title": "신세계 만점짜리 실적",
                    "source_url": "https://example.test/sparse.pdf",
                    "report_type": "earnings_review",
                    "headline": "004170: 만점짜리 실적",
                    "opinion": "positive",
                    "stock_view": "만점짜리 실적",
                    "earnings": "",
                    "industry": "",
                    "new_business": "",
                    "valuation": "",
                    "risks": "",
                    "source_quality": "title_or_sparse",
                    "brief_version": "brief-rule-v3",
                    "confidence": 0.7,
                },
                {
                    "report_signal_id": noisy_signal.id,
                    "ticker": "004170",
                    "report_date": datetime(2026, 5, 13).date(),
                    "source": "hankyung_consensus",
                    "broker": "Noisy",
                    "title": "신세계 표 조각",
                    "source_url": "https://example.test/noisy.pdf",
                    "report_type": "earnings_review",
                    "headline": "004170: 표 조각",
                    "opinion": "positive",
                    "stock_view": "표 조각",
                    "earnings": "백화점부문 순이익 3,181 각 법인 지분율 고려",
                    "industry": "목표가격 660,000",
                    "new_business": "억원(+49.5% YoY)을 기록해 영업이익 기준 시장 기대치(1,682억원)를",
                    "valuation": "목표주가(상향): 660,000원",
                    "risks": "단기투자자산감소 (7) (19) (13) (14) (14) 수익성(%)",
                    "source_quality": "full_text",
                    "brief_version": "brief-rule-v3",
                    "confidence": 1.0,
                },
                {
                    "report_signal_id": clean_signal.id,
                    "ticker": "004170",
                    "report_date": datetime(2026, 5, 10).date(),
                    "source": "hankyung_consensus",
                    "broker": "Clean",
                    "title": "신세계 업황 회복",
                    "source_url": "https://example.test/clean.pdf",
                    "report_type": "earnings_review",
                    "headline": "004170: 업황 회복",
                    "opinion": "positive",
                    "stock_view": "백화점과 면세점 실적 개선",
                    "earnings": "백화점과 면세점 영업이익 개선이 예상된다.",
                    "industry": "외국인 매출 증가와 백화점 업황 회복이 이어진다.",
                    "new_business": "면세점 정규 매장 확대가 모멘텀이다.",
                    "valuation": "목표주가 상향 여력이 있다.",
                    "risks": "환율 변동은 리스크다.",
                    "source_quality": "full_text",
                    "brief_version": "brief-rule-v3",
                    "confidence": 0.9,
                },
            ],
        )

    result = load_research_report_briefs(engine_factory=lambda _: engine)

    latest = result["rows"][0]
    assert latest["growth_drivers"] == "외국인 매출 증가와 백화점 업황 회복이 이어진다."
    assert latest["earnings_drivers"] == "백화점과 면세점 영업이익 개선이 예상된다."
    assert latest["new_business"] == "면세점 정규 매장 확대가 모멘텀이다."
    assert latest["risk_factors"] == "환율 변동은 리스크다."


def test_load_research_report_briefs_replaces_low_quality_existing_sections():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    with session_scope(engine) as session:
        signal_rows = [
            {
                "report_date": datetime(2026, 5, 13).date(),
                "ticker": "004170",
                "source": "hankyung_consensus",
                "region": "domestic",
                "broker": "Noisy",
                "rating": "Buy",
                "rating_score": 0.6,
                "target_price": None,
                "previous_target_price": None,
                "target_price_change_pct": None,
                "sentiment_score": None,
                "raw_score": 0.7,
                "title": "신세계 최신 리포트",
                "source_url": "https://example.test/noisy.pdf",
            },
            {
                "report_date": datetime(2026, 5, 10).date(),
                "ticker": "004170",
                "source": "hankyung_consensus",
                "region": "domestic",
                "broker": "Clean",
                "rating": "Buy",
                "rating_score": 0.6,
                "target_price": None,
                "previous_target_price": None,
                "target_price_change_pct": None,
                "sentiment_score": None,
                "raw_score": 0.7,
                "title": "신세계 클린 리포트",
                "source_url": "https://example.test/clean.pdf",
            },
        ]
        upsert_research_report_signals(session, signal_rows)
        signals = session.scalars(select(ResearchReportSignal).order_by(ResearchReportSignal.report_date.desc())).all()
        noisy_signal, clean_signal = signals
        upsert_research_report_briefs(
            session,
            [
                {
                    "report_signal_id": noisy_signal.id,
                    "ticker": "004170",
                    "report_date": datetime(2026, 5, 13).date(),
                    "source": "hankyung_consensus",
                    "broker": "Noisy",
                    "title": "신세계 최신 리포트",
                    "source_url": "https://example.test/noisy.pdf",
                    "report_type": "earnings_review",
                    "headline": "004170: 최신 리포트",
                    "opinion": "positive",
                    "stock_view": "백화점과 면세점 회복 기대",
                    "earnings": "매출총이익 3,855 4,053 5,077 5,364 5,733",
                    "industry": "2018년 6월부로 인천공항 사업자로 선정, 면세시장 점유율 확대해 나가고",
                    "new_business": "또한 코로나 시기 준내구재 수요",
                    "valuation": "목표주가(상향): 660,000원",
                    "risks": "달러 대비 위안화 환율",
                    "source_quality": "full_text",
                    "brief_version": "brief-rule-v3",
                    "confidence": 1.0,
                },
                {
                    "report_signal_id": clean_signal.id,
                    "ticker": "004170",
                    "report_date": datetime(2026, 5, 10).date(),
                    "source": "hankyung_consensus",
                    "broker": "Clean",
                    "title": "신세계 클린 리포트",
                    "source_url": "https://example.test/clean.pdf",
                    "report_type": "earnings_review",
                    "headline": "004170: 클린 리포트",
                    "opinion": "positive",
                    "stock_view": "백화점과 면세점 실적 개선이 기대된다.",
                    "earnings": "외국인 매출 비중 상승과 할인율 개선으로 영업이익 개선이 예상된다.",
                    "industry": "외국인 관광객 회복과 럭셔리 소비 증가가 백화점 업황을 견인한다.",
                    "new_business": "면세점 정규 매장 확대와 온라인 채널 강화가 모멘텀이다.",
                    "valuation": "실적 추정치 상향으로 밸류에이션 부담이 완화된다.",
                    "risks": "환율 변동과 소비 둔화는 단기 리스크다.",
                    "source_quality": "full_text",
                    "brief_version": "brief-rule-v3",
                    "confidence": 0.9,
                },
            ],
        )

    result = load_research_report_briefs(engine_factory=lambda _: engine)

    latest = result["rows"][0]
    assert latest["earnings_drivers"] == "외국인 매출 비중 상승과 할인율 개선으로 영업이익 개선이 예상된다."
    assert latest["growth_drivers"] == "외국인 관광객 회복과 럭셔리 소비 증가가 백화점 업황을 견인한다."
    assert latest["new_business"] == "면세점 정규 매장 확대와 온라인 채널 강화가 모멘텀이다."
    assert latest["risk_factors"] == "환율 변동과 소비 둔화는 단기 리스크다."


def test_load_research_report_briefs_uses_title_and_thesis_when_section_fields_are_sparse():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    with session_scope(engine) as session:
        upsert_research_report_signals(
            session,
            [
                {
                    "report_date": datetime(2026, 5, 13).date(),
                    "ticker": "004170",
                    "source": "mirae_asset",
                    "region": "domestic",
                    "broker": "Mirae",
                    "rating": "Buy",
                    "rating_score": 0.6,
                    "target_price": None,
                    "previous_target_price": None,
                    "target_price_change_pct": None,
                    "sentiment_score": None,
                    "raw_score": 0.6,
                    "title": "신세계 만점짜리 실적",
                    "source_url": "https://example.test/sparse.pdf",
                },
                {
                    "report_date": datetime(2026, 5, 10).date(),
                    "ticker": "004170",
                    "source": "hankyung_consensus",
                    "region": "domestic",
                    "broker": "Clean",
                    "rating": "Buy",
                    "rating_score": 0.6,
                    "target_price": None,
                    "previous_target_price": None,
                    "target_price_change_pct": None,
                    "sentiment_score": None,
                    "raw_score": 0.7,
                    "title": "신세계 자산 효과와 인바운드 소비가 성장의 축",
                    "source_url": "https://example.test/title.pdf",
                },
            ],
        )
        signals = session.scalars(select(ResearchReportSignal).order_by(ResearchReportSignal.report_date.desc())).all()
        sparse_signal, title_signal = signals
        upsert_research_report_briefs(
            session,
            [
                {
                    "report_signal_id": sparse_signal.id,
                    "ticker": "004170",
                    "report_date": datetime(2026, 5, 13).date(),
                    "source": "mirae_asset",
                    "broker": "Mirae",
                    "title": "신세계 만점짜리 실적",
                    "source_url": "https://example.test/sparse.pdf",
                    "report_type": "earnings_review",
                    "headline": "004170: 만점짜리 실적",
                    "opinion": "positive",
                    "stock_view": "만점짜리 실적",
                    "earnings": "",
                    "industry": "",
                    "new_business": "",
                    "valuation": "",
                    "risks": "",
                    "source_quality": "title_or_sparse",
                    "brief_version": "brief-rule-v3",
                    "confidence": 0.7,
                },
                {
                    "report_signal_id": title_signal.id,
                    "ticker": "004170",
                    "report_date": datetime(2026, 5, 10).date(),
                    "source": "hankyung_consensus",
                    "broker": "Clean",
                    "title": "신세계 자산 효과와 인바운드 소비가 성장의 축",
                    "source_url": "https://example.test/title.pdf",
                    "report_type": "industry_outlook",
                    "headline": "004170: 자산 효과와 인바운드 소비가 성장의 축",
                    "opinion": "positive",
                    "stock_view": "리뉴얼 효과와 내수소비 회복에 더해 외국인 매출 증가가 기대된다.",
                    "earnings": "",
                    "industry": "",
                    "new_business": "",
                    "valuation": "",
                    "risks": "환율 변동은 단기 리스크다.",
                    "source_quality": "full_text",
                    "brief_version": "brief-rule-v3",
                    "confidence": 0.9,
                },
            ],
        )

    result = load_research_report_briefs(engine_factory=lambda _: engine)

    latest = result["rows"][0]
    assert latest["growth_drivers"] == "리뉴얼 효과와 내수소비 회복에 더해 외국인 매출 증가가 기대된다."
    assert latest["earnings_drivers"] == "리뉴얼 효과와 내수소비 회복에 더해 외국인 매출 증가가 기대된다."
    assert latest["risk_factors"] == "환율 변동은 단기 리스크다."


def test_build_ticker_research_briefs_consolidates_rows_without_llm_by_default():
    rows = [
        {
            "ticker": "005930",
            "report_date": "2026-05-14",
            "source": "hankyung_consensus",
            "broker": "Broker A",
            "title": "Samsung memory upcycle",
            "summary": "Memory demand improves.",
            "investment_opinion": "positive",
            "buy_thesis": "AI server demand supports HBM shipments.",
            "growth_drivers": "HBM demand and foundry utilization improve.",
            "earnings_drivers": "DRAM margin recovery continues.",
            "valuation_view": "Upside remains versus peer multiples.",
            "risk_factors": "FX volatility can pressure margins.",
            "new_business": "Advanced packaging expansion adds momentum.",
            "confidence": 0.82,
            "body_text_status": "full_text",
            "evidence_terms": "industry_outlook, full_text, brief-rule-v3",
            "source_url": "https://example.test/new.pdf",
        },
        {
            "ticker": "005930",
            "report_date": "2026-05-10",
            "source": "mirae_research",
            "broker": "Broker B",
            "title": "Legacy memory note",
            "summary": "Older memory view.",
            "investment_opinion": "neutral",
            "buy_thesis": "Older view.",
            "growth_drivers": "",
            "earnings_drivers": "",
            "valuation_view": "",
            "risk_factors": "",
            "new_business": "",
            "confidence": 0.4,
            "body_text_status": "title_or_sparse",
            "evidence_terms": "company_update, title_or_sparse, brief-rule-v3",
            "source_url": "https://example.test/old.pdf",
        },
        {
            "ticker": "000660",
            "report_date": "2026-05-13",
            "source": "hankyung_consensus",
            "broker": "Broker A",
            "title": "SK Hynix HBM",
            "summary": "HBM mix improves.",
            "investment_opinion": "positive",
            "buy_thesis": "HBM mix improves profitability.",
            "growth_drivers": "AI accelerator demand remains firm.",
            "earnings_drivers": "Product mix lifts margins.",
            "valuation_view": "",
            "risk_factors": "",
            "new_business": "",
            "confidence": 0.7,
            "body_text_status": "partial_text",
            "evidence_terms": "industry_outlook, partial_text, brief-rule-v3",
            "source_url": "",
        },
    ]

    briefs = build_ticker_research_briefs(rows, generated_at="2026-05-15T09:00:00+09:00")

    assert briefs["schema_version"] == 1
    assert briefs["brief_version"] == "ticker-brief-rule-v1"
    assert briefs["llm"]["status"] == "disabled"
    assert briefs["summary"]["ticker_count"] == 2
    assert briefs["summary"]["source_report_count"] == 3
    assert [item["ticker"] for item in briefs["tickers"]] == ["005930", "000660"]
    samsung = briefs["tickers"][0]
    assert samsung["latest_report_date"] == "2026-05-14"
    assert samsung["opinion"] == "positive"
    assert samsung["sections"]["growth"] == "HBM demand and foundry utilization improve."
    assert samsung["sections"]["risk"] == "FX volatility can pressure margins."
    assert samsung["quality"]["source_quality"] == "full_text"
    assert samsung["quality"]["report_count"] == 2
    assert samsung["source_reports"][0]["title"] == "Samsung memory upcycle"


def test_build_ticker_research_briefs_prefers_full_text_primary_and_rejects_fragments():
    rows = [
        {
            "ticker": "012345",
            "report_date": "2026-05-15",
            "source": "hankyung_consensus",
            "broker": "Broker Sparse",
            "title": "Sparse latest note",
            "summary": "and operating margins improved.",
            "investment_opinion": "positive",
            "buy_thesis": "and operating margins improved.",
            "growth_drivers": "",
            "earnings_drivers": "",
            "valuation_view": "",
            "risk_factors": "",
            "new_business": "",
            "confidence": 0.95,
            "body_text_status": "title_or_sparse",
            "evidence_terms": "company_update, title_or_sparse, brief-rule-v3",
            "source_url": "https://example.test/sparse",
        },
        {
            "ticker": "012345",
            "report_date": "2026-05-14",
            "source": "mirae_asset",
            "broker": "Broker Full",
            "title": "Full text primary report",
            "summary": "Full text thesis stays coherent.",
            "investment_opinion": "positive",
            "buy_thesis": "Customer demand is recovering across core products.",
            "growth_drivers": "New customer wins support revenue growth.",
            "earnings_drivers": "Margin recovery continues as utilization improves.",
            "valuation_view": "Peer multiples leave room for upside.",
            "risk_factors": "Execution delays are the main risk.",
            "new_business": "",
            "confidence": 0.8,
            "body_text_status": "full_text",
            "evidence_terms": "earnings_review, full_text, brief-rule-v3",
            "source_url": "https://example.test/full.pdf",
        },
    ]

    artifact = build_ticker_research_briefs(rows, generated_at="2026-05-15T09:00:00+09:00")
    brief = artifact["tickers"][0]

    assert brief["latest_report_date"] == "2026-05-15"
    assert brief["headline"] == "Full text thesis stays coherent."
    assert brief["sections"]["stock_view"] == "Customer demand is recovering across core products."
    assert "and operating margins improved" not in json.dumps(brief, ensure_ascii=False)
    assert brief["quality"]["source_quality"] == "full_text"


def test_build_ticker_research_briefs_uses_explicit_low_score_sections_but_skips_rating_noise():
    rows = [
        {
            "ticker": "078930",
            "report_date": "2026-05-14",
            "source": "hankyung_consensus",
            "broker": "Broker A",
            "title": "GS earnings surprise",
            "summary": "GS earnings surprise.",
            "investment_opinion": "positive",
            "buy_thesis": "실적 개선 시 현재 배당정책 유지 가능할 것으로 판단된다.",
            "growth_drivers": "현재 두바이유 100달러 수준 유지 시 재고평가이익 소폭 플러스 가능성 존재.",
            "earnings_drivers": "정제마진 유지 시 분기 영업이익 4,000억원 수준 예상.",
            "valuation_view": "목표주가 상향.",
            "risk_factors": "가동률 하락 영향으로 재고 규모는 평상시 대비 약 10% 감소했다.",
            "new_business": "",
            "confidence": 1.0,
            "body_text_status": "full_text",
            "evidence_terms": "earnings_review, full_text, brief-rule-v3",
            "source_url": "",
        },
        {
            "ticker": "095610",
            "report_date": "2026-05-14",
            "source": "hankyung_consensus",
            "broker": "Broker B",
            "title": "TES equipment",
            "summary": "TES equipment line-up.",
            "investment_opinion": "positive",
            "buy_thesis": "빅테크 업체의 CAPEX 상향은 기대 이상이다.",
            "growth_drivers": "DRAM 증설과 신규 장비 모멘텀이 이어진다.",
            "earnings_drivers": "고가 증착 장비로 수익성 개선이 기대된다.",
            "valuation_view": "밸류에이션 팽창 전망.",
            "risk_factors": "Hold 추천기준일 직전 1개월 평균종가대비 -20% 이상 중립 10.3%",
            "new_business": "",
            "confidence": 1.0,
            "body_text_status": "full_text",
            "evidence_terms": "earnings_review, full_text, brief-rule-v3",
            "source_url": "",
        },
    ]

    artifact = build_ticker_research_briefs(rows, generated_at="2026-05-15T09:00:00+09:00")
    by_ticker = {row["ticker"]: row for row in artifact["tickers"]}

    assert by_ticker["078930"]["sections"]["growth"] == "현재 두바이유 100달러 수준 유지 시 재고평가이익 소폭 플러스 가능성 존재."
    assert by_ticker["078930"]["sections"]["risk"] == "가동률 하락 영향으로 재고 규모는 평상시 대비 약 10% 감소했다."
    assert by_ticker["095610"]["sections"]["risk"] == "리포트에서 명시적인 리스크 요인은 확인되지 않았습니다."
    assert "Hold 추천기준일" not in by_ticker["095610"]["sections"]["risk"]


def test_build_ticker_research_briefs_falls_back_to_growth_for_missing_stock_view():
    rows = [
        {
            "ticker": "007340",
            "report_date": "2026-04-21",
            "source": "kiwoom_public_research",
            "broker": "Kiwoom",
            "title": "DN Automotive target price raised",
            "summary": "Target price raised on undervalued auto-parts portfolio.",
            "investment_opinion": "positive",
            "buy_thesis": "",
            "growth_drivers": "DN Automotive is viewed as an undervalued mid-cap auto-parts stock.",
            "earnings_drivers": "Heller acquisition starts contributing to earnings.",
            "valuation_view": "Target P/E supports upside.",
            "risk_factors": "Rating table says market-relative downside threshold.",
            "new_business": "New order backlog supports MTB sales conversion.",
            "confidence": 1.0,
            "body_text_status": "full_text",
            "evidence_terms": "stock_report, full_text, brief-rule-v3",
            "source_url": "",
        }
    ]

    artifact = build_ticker_research_briefs(rows, generated_at="2026-05-15T09:00:00+09:00")
    brief = artifact["tickers"][0]

    assert brief["sections"]["stock_view"] == "DN Automotive is viewed as an undervalued mid-cap auto-parts stock."


def test_build_ticker_research_briefs_marks_missing_full_text_risk_as_not_explicit():
    rows = [
        {
            "ticker": "092130",
            "report_date": "2026-05-15",
            "source": "hankyung_consensus",
            "broker": "Broker A",
            "title": "Credit data stable growth",
            "summary": "Credit data revenue grows steadily.",
            "investment_opinion": "positive",
            "buy_thesis": "Credit data demand supports stable growth.",
            "growth_drivers": "Enterprise data usage expands.",
            "earnings_drivers": "Recurring revenue improves margins.",
            "valuation_view": "Valuation remains reasonable.",
            "risk_factors": "",
            "new_business": "",
            "confidence": 1.0,
            "body_text_status": "full_text",
            "evidence_terms": "earnings_review, full_text, brief-rule-v3",
            "source_url": "",
        }
    ]

    artifact = build_ticker_research_briefs(rows, generated_at="2026-05-15T09:00:00+09:00")
    brief = artifact["tickers"][0]

    assert brief["sections"]["risk"] == "리포트에서 명시적인 리스크 요인은 확인되지 않았습니다."


def test_build_ticker_research_briefs_marks_missing_full_text_required_sections_as_not_explicit():
    rows = [
        {
            "ticker": "053690",
            "report_date": "2026-04-10",
            "source": "hankyung_consensus",
            "broker": "Broker A",
            "title": "A",
            "summary": "",
            "investment_opinion": "positive",
            "buy_thesis": "",
            "growth_drivers": "",
            "earnings_drivers": "",
            "valuation_view": "Valuation re-rating can follow nuclear expansion.",
            "risk_factors": "Execution risk should be minimized.",
            "new_business": "Overseas nuclear project pipeline expands.",
            "confidence": 1.0,
            "body_text_status": "full_text",
            "evidence_terms": "new_business, full_text, brief-rule-v3",
            "source_url": "",
        }
    ]

    artifact = build_ticker_research_briefs(rows, generated_at="2026-05-15T09:00:00+09:00")
    brief = artifact["tickers"][0]

    assert brief["sections"]["stock_view"] == "리포트에서 명시적인 종목 관점은 확인되지 않았습니다."
    assert brief["sections"]["growth"] == "리포트에서 명시적인 성장/업황 내용은 확인되지 않았습니다."
    assert brief["sections"]["earnings"] == "리포트에서 명시적인 실적 내용은 확인되지 않았습니다."


def test_load_ticker_research_briefs_reads_generated_artifact(tmp_path: Path):
    artifact = {
        "schema_version": 1,
        "brief_version": "ticker-brief-rule-v1",
        "summary": {"ticker_count": 1, "source_report_count": 2},
        "llm": {"status": "disabled"},
        "tickers": [
            {
                "ticker": "005930",
                "latest_report_date": "2026-05-14",
                "headline": "Memory demand improves.",
                "opinion": "positive",
                "sections": {"growth": "HBM demand improves."},
                "quality": {"source_quality": "full_text", "report_count": 2},
                "source_reports": [],
            }
        ],
    }
    path = tmp_path / "research_report_ticker_briefs.json"
    path.write_text(json.dumps(artifact), encoding="utf-8")

    result = load_ticker_research_briefs(path)

    assert result["status"] == "ok"
    assert result["artifact"]["summary"]["ticker_count"] == 1
    assert result["by_ticker"]["005930"]["sections"]["growth"] == "HBM demand improves."


def test_ticker_research_brief_card_shows_sections_sources_and_llm_status():
    html = _ticker_research_brief_card_html(
        {
            "ticker": "005930",
            "latest_report_date": "2026-05-14",
            "headline": "Memory demand improves.",
            "opinion": "positive",
            "sections": {
                "stock_view": "AI server demand supports HBM shipments.",
                "growth": "HBM demand and foundry utilization improve.",
                "earnings": "DRAM margin recovery continues.",
                "valuation": "Upside remains versus peer multiples.",
                "new_business": "Advanced packaging expansion adds momentum.",
                "risk": "FX volatility can pressure margins.",
            },
            "quality": {
                "source_quality": "full_text",
                "confidence": 0.82,
                "report_count": 2,
                "llm_status": "disabled",
            },
            "source_reports": [
                {
                    "report_date": "2026-05-14",
                    "source": "hankyung_consensus",
                    "broker": "Broker A",
                    "title": "Samsung memory upcycle",
                    "url": "https://example.test/new.pdf",
                    "source_quality": "full_text",
                }
            ],
        }
    )

    assert "Ticker Integrated Brief" in html
    assert "005930" in html
    assert "HBM demand and foundry utilization improve." in html
    assert "FX volatility can pressure margins." in html
    assert "LLM disabled" in html
    assert "Samsung memory upcycle" in html


def test_source_quality_label_translates_storage_codes_for_dashboard():
    assert _source_quality_label("full_text") == "Full text · 원문 기반"
    assert _source_quality_label("partial_text") == "Partial text · 일부 본문"
    assert _source_quality_label("supplemental_summary") == "Supplemental · 수동 보충"
    assert _source_quality_label("title_or_sparse") == "Sparse · 제목/요약 중심"
    assert _source_quality_label("unknown_source") == "unknown_source"


def test_research_quality_issue_card_shows_action_and_next_step():
    html = _research_quality_issue_html(
        {
            "ticker": "000660",
            "latest_report_date": "2026-01-01",
            "reasons": ["stale_report"],
            "missing_sections": [],
            "source_quality": "full_text",
            "confidence": 0.8,
            "report_count": 2,
        }
    )

    assert "Action" in html
    assert "Latest report check" in html
    assert "Find a newer report" in html


def test_ticker_research_brief_card_shows_human_source_quality_label():
    html = _ticker_research_brief_card_html(
        {
            "ticker": "007340",
            "latest_report_date": "2026-05-14",
            "headline": "Supplemental report added.",
            "opinion": "neutral",
            "sections": {},
            "quality": {
                "source_quality": "supplemental_summary",
                "confidence": 0.55,
                "report_count": 1,
                "llm_status": "disabled",
            },
            "source_reports": [],
        }
    )

    assert "Supplemental · 수동 보충" in html
    assert "supplemental_summary" not in html


def test_detail_html_attaches_matching_ticker_research_brief():
    position = _sample_snapshot()["positions"][0]
    brief_by_ticker = {
        "005930": {
            "ticker": "005930",
            "latest_report_date": "2026-05-14",
            "headline": "Memory demand improves.",
            "opinion": "positive",
            "sections": {
                "stock_view": "AI server demand supports HBM shipments.",
                "growth": "HBM demand improves.",
                "risk": "FX volatility can pressure margins.",
            },
            "quality": {
                "source_quality": "full_text",
                "report_count": 2,
                "llm_status": "disabled",
            },
            "source_reports": [],
        }
    }

    html = _detail_html(position, brief_by_ticker=brief_by_ticker)

    assert "Research Brief" in html
    assert "Memory demand improves." in html
    assert "FX volatility can pressure margins." in html
    assert "\n        <div>\n          <div class='subhead'>Research Brief</div>" not in html


def test_build_ticker_research_quality_report_flags_sparse_low_quality_and_stale_items():
    artifact = {
        "generated_at": "2026-05-15T09:00:00+09:00",
        "tickers": [
            {
                "ticker": "005930",
                "latest_report_date": "2026-05-14",
                "sections": {
                    "stock_view": "AI server demand supports HBM shipments.",
                    "growth": "HBM demand improves.",
                    "earnings": "DRAM margin recovery continues.",
                    "valuation": "Upside remains.",
                    "new_business": "Advanced packaging expands.",
                    "risk": "FX volatility can pressure margins.",
                },
                "quality": {"source_quality": "full_text", "confidence": 0.82, "report_count": 3},
            },
            {
                "ticker": "000660",
                "latest_report_date": "2026-03-01",
                "sections": {"stock_view": "HBM mix improves."},
                "quality": {"source_quality": "title_or_sparse", "confidence": 0.41, "report_count": 1},
            },
        ],
    }

    report = build_ticker_research_quality_report(
        artifact,
        portfolio_tickers={"005930", "000660", "035720"},
        now=datetime(2026, 5, 15, tzinfo=KST),
        stale_days=45,
    )

    assert report["summary"]["ticker_count"] == 2
    assert report["summary"]["portfolio_missing_count"] == 1
    assert report["summary"]["complete_count"] == 1
    assert report["summary"]["issue_count"] == 1
    issue = report["issues"][0]
    assert issue["ticker"] == "000660"
    assert "missing_sections" in issue["reasons"]
    assert "stale_report" in issue["reasons"]
    assert "low_confidence" in issue["reasons"]
    assert "weak_source_quality" in issue["reasons"]
    assert report["portfolio_missing"] == ["035720"]


def test_quality_dashboard_summary_separates_latest_report_not_found_items(tmp_path: Path):
    queue_path = tmp_path / "research_quality_review_queue.json"
    queue_path.write_text(
        json.dumps(
            {
                "items": [
                    {"ticker": "000660", "primary_action": "latest_report_not_found"},
                    {"ticker": "035720", "primary_action": "parser_section_backfill_candidate"},
                ]
            }
        ),
        encoding="utf-8",
    )
    queue = load_research_quality_queue(queue_path)
    quality_report = {
        "summary": {"complete_count": 10, "issue_count": 2, "portfolio_missing_count": 0},
        "issues": [
            {"ticker": "000660", "reasons": ["stale_report"]},
            {"ticker": "035720", "reasons": ["missing_sections"]},
        ],
    }

    summary = _quality_dashboard_summary(quality_report, queue)
    actionable = _actionable_quality_issues(quality_report, queue)
    latest_not_found = _latest_not_found_quality_issues(quality_report, queue)

    assert summary["issue_count"] == 2
    assert summary["actionable_issue_count"] == 1
    assert summary["latest_report_not_found_count"] == 1
    assert [item["ticker"] for item in actionable] == ["035720"]
    assert [item["ticker"] for item in latest_not_found] == ["000660"]


def test_research_operator_next_action_prefers_automation_before_manual_review():
    html = _research_operator_next_action_html(
        {
            "complete_count": 407,
            "actionable_issue_count": 111,
            "latest_report_not_found_count": 8,
            "portfolio_missing_count": 0,
        }
    )

    assert "Operator Next Action" in html
    assert "Automated quality pass" in html
    assert "-IncludeSupplementalDiscovery" in html


def test_research_qa_sample_summary_counts_pending_and_review_flags(tmp_path: Path):
    sample_path = tmp_path / "qa.json"
    sample_path.write_text(
        json.dumps(
            {
                "items": [
                    {"ticker": "005930", "review_status": "approved"},
                    {
                        "ticker": "000660",
                        "review_status": "",
                        "needs_source_refresh": "true",
                        "needs_section_rewrite": "yes",
                        "issue_category": "stale_source",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    result = load_research_brief_qa_sample(sample_path)
    summary = build_research_qa_sample_summary(result)
    html = _research_qa_summary_html(result)

    assert result["status"] == "ok"
    assert summary["sample_count"] == 2
    assert summary["reviewed_count"] == 1
    assert summary["pending_count"] == 1
    assert summary["source_refresh_count"] == 1
    assert summary["section_rewrite_count"] == 1
    assert "QA Sample Trust" in html
    assert "pending 1" in html


def test_research_qa_action_queue_summary_and_html(tmp_path: Path):
    queue_path = tmp_path / "research_qa_action_queue.json"
    queue_path.write_text(
        json.dumps(
            {
                "summary": {
                    "sample_count": 3,
                    "action_item_count": 2,
                    "section_rewrite_count": 1,
                    "source_refresh_count": 2,
                    "source_refresh_attempted_no_new_source_count": 4,
                },
                "items": [
                    {
                        "ticker": "005930",
                        "primary_action": "section_rewrite",
                        "actions": ["section_rewrite", "source_refresh"],
                        "latest_report_date": "2026-05-14",
                        "auto_issue_reasons": ["headline:starts_mid_sentence"],
                        "suggested_next_step": "Refresh then rewrite.",
                    },
                    {
                        "ticker": "000660",
                        "primary_action": "source_refresh",
                        "actions": ["source_refresh"],
                        "latest_report_date": "2026-01-01",
                        "auto_issue_reasons": ["stale_or_missing_latest_report"],
                        "suggested_next_step": "Find newer source.",
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = load_research_qa_action_queue(queue_path)
    summary = build_research_qa_action_summary(result)
    html = _research_qa_action_queue_html(result)

    assert result["status"] == "ok"
    assert summary["action_item_count"] == 2
    assert summary["section_rewrite_count"] == 1
    assert summary["source_refresh_count"] == 2
    assert summary["source_refresh_attempted_no_new_source_count"] == 4
    assert "해야 할 작업" in html
    assert "005930" in html
    assert "000660" in html
    assert "섹션 재작성" in html
    assert "탐색 완료" in html


def test_render_dashboard_uses_separate_korean_task_tab(monkeypatch):
    calls: list[tuple[str, tuple, dict]] = []

    class FakeTab:
        def __enter__(self):
            calls.append(("tab_enter", (), {}))
            return self

        def __exit__(self, exc_type, exc, tb):
            calls.append(("tab_exit", (), {}))
            return False

    class FakeColumn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def __getattr__(self, name):
            def _inner(*args, **kwargs):
                calls.append((name, args, kwargs))
            return _inner

    def record(name):
        def _inner(*args, **kwargs):
            calls.append((name, args, kwargs))
            if name == "tabs":
                return [FakeTab() for _ in args[0]]
            if name == "columns":
                count = len(args[0]) if isinstance(args[0], list) else args[0]
                return [FakeColumn() for _ in range(count)]
            return None

        return _inner

    fake_streamlit = SimpleNamespace(
        set_page_config=record("set_page_config"),
        sidebar=SimpleNamespace(
            markdown=record("sidebar_markdown"),
            radio=lambda *args, **kwargs: args[1][kwargs.get("index", 0)],
            selectbox=lambda *args, **kwargs: args[1][kwargs.get("index", 0)],
            toggle=lambda *args, **kwargs: kwargs.get("value", False),
        ),
        tabs=record("tabs"),
        columns=record("columns"),
        markdown=record("markdown"),
        metric=record("metric"),
        info=record("info"),
        warning=record("warning"),
        caption=record("caption"),
        checkbox=lambda *args, **kwargs: kwargs.get("value", False),
        text_input=lambda *args, **kwargs: kwargs.get("value", ""),
        selectbox=lambda *args, **kwargs: args[1][kwargs.get("index", 0)],
        radio=lambda *args, **kwargs: args[1][kwargs.get("index", 0)],
    )
    monkeypatch.setitem(__import__("sys").modules, "streamlit", fake_streamlit)

    render_dashboard(_sample_snapshot())

    tab_call = next(call for call in calls if call[0] == "tabs")
    assert tab_call[1][0] == ["Portfolio", "Supplement Needs", "Ticker Briefs", "Research Reports"]


def test_dashboard_css_wraps_long_operational_text():
    css = _build_css("regular", "kr", "#f2c94c", "Arial", "Consolas")

    assert ".sig .detail" in css
    assert "overflow-wrap: anywhere" in css
    assert ".pill" in css
    assert "white-space: normal" in css
    assert ".htable .ticker-cell" in css


def test_dashboard_html_escapes_external_rank_and_report_count_values():
    position = _sample_snapshot()["positions"][0]
    position["rationale"]["rank"] = "<script>alert(1)</script>"
    table_html = _holdings_table_html([position], total_mv=1, selected="", show_spark=False, show_stripe=False)
    highlight_html = _highlight_cards_html([position])
    brief_html = _ticker_research_brief_card_html(
        {
            "ticker": "005930",
            "latest_report_date": "2026-05-14",
            "headline": "Safe headline",
            "opinion": "positive",
            "sections": {},
            "quality": {"report_count": "<script>alert(1)</script>"},
            "source_reports": [],
        }
    )

    combined = table_html + highlight_html + brief_html
    assert "<script>" not in combined
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in combined
    assert "reports 0" in brief_html


def test_hero_uses_total_assets_cash_and_realized_values():
    html_text = _hero_html(_sample_snapshot())

    assert "1,000,000" in html_text
    assert "Cash · 현금" in html_text
    assert "₩280,000" in html_text
    assert "Realized · 실현" in html_text
    assert "+₩12,000" in html_text


def test_build_research_supplement_needs_prioritizes_portfolio_missing_and_issues():
    artifact = {
        "tickers": [
            {
                "ticker": "000990",
                "latest_report_date": "2026-01-21",
                "sections": {"stock_view": "Foundry view."},
                "quality": {"source_quality": "full_text", "confidence": 0.6, "report_count": 1},
            },
            {
                "ticker": "005930",
                "latest_report_date": "2026-05-14",
                "sections": {
                    "stock_view": "HBM view.",
                    "growth": "HBM demand improves.",
                    "earnings": "Margins recover.",
                    "risk": "Supply risk.",
                },
                "quality": {"source_quality": "full_text", "confidence": 0.9, "report_count": 4},
            },
        ]
    }
    positions = [
        {"ticker": "007340", "name": "DN Automotive"},
        {"ticker": "000990", "name": "DB HiTek"},
        {"ticker": "005930", "name": "Samsung Electronics"},
    ]

    needs = build_research_supplement_needs(
        artifact,
        positions,
        now=datetime(2026, 5, 15, tzinfo=KST),
        stale_days=45,
    )

    assert [row["ticker"] for row in needs] == ["007340", "000990"]
    assert needs[0]["status"] == "missing_brief"
    assert needs[0]["name"] == "DN Automotive"
    assert needs[1]["status"] == "needs_review"
    assert "stale_report" in needs[1]["reasons"]


def test_build_research_supplement_needs_excludes_latest_not_found_backlog():
    artifact = {
        "tickers": [
            {
                "ticker": "000990",
                "latest_report_date": "2026-01-21",
                "sections": {
                    "stock_view": "Foundry view.",
                    "growth": "Foundry demand.",
                    "earnings": "Margins recover.",
                    "risk": "Cycle risk.",
                },
                "quality": {"source_quality": "full_text", "confidence": 0.9, "report_count": 1},
            },
            {
                "ticker": "000520",
                "latest_report_date": "2026-02-20",
                "sections": {"stock_view": ""},
                "quality": {"source_quality": "title_or_sparse", "confidence": 0.2, "report_count": 1},
            },
        ]
    }
    positions = [
        {"ticker": "000990", "name": "DB HiTek"},
        {"ticker": "000520", "name": "Samick THK"},
    ]
    queue_result = {
        "status": "ok",
        "action_by_ticker": {
            "000990": "latest_report_not_found",
            "000520": "supplemental_source_needed",
        },
    }

    needs = build_research_supplement_needs(
        artifact,
        positions,
        queue_result=queue_result,
        now=datetime(2026, 5, 15, tzinfo=KST),
        stale_days=45,
    )

    assert [row["ticker"] for row in needs] == ["000520"]
    assert needs[0]["status"] == "needs_review"
    assert "weak_source_quality" in needs[0]["reasons"]


def test_research_supplement_need_html_renders_actionable_dashboard_card():
    html = _research_supplement_need_html(
        {
            "ticker": "007340",
            "name": "DN Automotive",
            "status": "missing_brief",
            "latest_report_date": "",
            "reasons": ["missing_brief"],
            "missing_sections": ["stock_view", "earnings"],
            "source_quality": "",
            "confidence": 0.0,
        }
    )

    assert "007340" in html
    assert "DN Automotive" in html
    assert "missing_brief" in html
    assert "stock_view, earnings" in html


def test_research_quality_issue_html_renders_actionable_issue_summary():
    html = _research_quality_issue_html(
        {
            "ticker": "000660",
            "latest_report_date": "2026-03-01",
            "missing_sections": ["earnings", "risk"],
            "reasons": ["missing_sections", "stale_report"],
            "confidence": 0.41,
            "source_quality": "title_or_sparse",
            "report_count": 1,
        }
    )

    assert "000660" in html
    assert "missing_sections" in html
    assert "earnings, risk" in html
    assert "Sparse · 제목/요약 중심" in html


def test_load_research_report_briefs_reports_signal_freshness_metadata():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    with session_scope(engine) as session:
        upsert_research_report_signals(
            session,
            [
                {
                    "report_date": date(2026, 5, 15),
                    "ticker": "005930",
                    "source": "hankyung_consensus",
                    "region": "domestic",
                    "broker": "Test",
                    "rating": "Buy",
                    "rating_score": 0.6,
                    "target_price": 100000,
                    "previous_target_price": 90000,
                    "target_price_change_pct": 11.1,
                    "sentiment_score": 0.7,
                    "raw_score": 0.7,
                    "title": "Samsung earnings recovery",
                    "source_url": "https://example.test/report.pdf",
                },
                {
                    "report_date": date(2026, 5, 18),
                    "ticker": "042510",
                    "source": "hankyung_consensus",
                    "region": "domestic",
                    "broker": "Test",
                    "rating": "Buy",
                    "rating_score": 0.6,
                    "target_price": 20000,
                    "previous_target_price": 18000,
                    "target_price_change_pct": 11.1,
                    "sentiment_score": 0.7,
                    "raw_score": 0.7,
                    "title": "Raonsecure new report",
                    "source_url": "https://example.test/raon.pdf",
                },
            ],
        )
        signal = session.scalars(
            select(ResearchReportSignal).where(ResearchReportSignal.ticker == "005930")
        ).one()
        upsert_research_report_briefs(
            session,
            [
                {
                    "report_signal_id": signal.id,
                    "ticker": "005930",
                    "report_date": date(2026, 5, 15),
                    "source": "hankyung_consensus",
                    "broker": "Test",
                    "title": "Samsung earnings recovery",
                    "source_url": "https://example.test/report.pdf",
                    "report_type": "earnings_review",
                    "headline": "Memory recovery supports earnings.",
                    "opinion": "positive",
                    "stock_view": "Memory recovery supports the stock view.",
                    "earnings": "Margins recover.",
                    "industry": "AI demand improves.",
                    "new_business": "",
                    "valuation": "Target price rises.",
                    "risks": "Demand volatility is the main risk.",
                    "source_quality": "full_text",
                    "brief_version": "brief-rule-v3",
                    "confidence": 0.9,
                }
            ],
        )

    result = load_research_report_briefs(engine_factory=lambda _: engine)
    freshness_html = _research_freshness_html(result.get("freshness", {}))

    assert result["freshness"] == {
        "latest_brief_date": "2026-05-15",
        "latest_signal_date": "2026-05-18",
        "missing_brief_count": 1,
    }
    assert "Latest brief" in freshness_html
    assert "2026-05-15" in freshness_html
    assert "Latest signal" in freshness_html
    assert "2026-05-18" in freshness_html
    assert "Missing briefs" in freshness_html
    assert "1" in freshness_html


def test_filter_research_report_briefs_supports_portfolio_opinion_source_and_query():
    rows = [
        {
            "ticker": "005930",
            "source": "hankyung_consensus",
            "investment_opinion": "positive",
            "summary": "HBM demand improves.",
            "growth_drivers": "AI server",
        },
        {
            "ticker": "000660",
            "source": "mirae_asset",
            "investment_opinion": "mixed",
            "summary": "Demand risk remains.",
            "growth_drivers": "",
        },
    ]

    filtered = filter_research_report_briefs(
        rows,
        portfolio_tickers={"005930"},
        portfolio_only=True,
        opinion="positive",
        source="hankyung_consensus",
        query="HBM",
    )

    assert filtered == [rows[0]]


def test_filter_research_report_briefs_returns_empty_when_portfolio_only_has_no_tickers():
    rows = [{"ticker": "005930"}, {"ticker": "000660"}]

    filtered = filter_research_report_briefs(
        rows,
        portfolio_tickers=set(),
        portfolio_only=True,
    )

    assert filtered == []


def test_body_text_available_count_includes_brief_source_quality_values():
    assert _body_text_available_count(
        {"extracted": 1, "full_text": 2, "partial_text": 3, "title_or_sparse": 4}
    ) == 6


def test_research_report_default_limit_covers_current_local_history():
    assert DEFAULT_RESEARCH_LIMIT >= 2335
    assert DEFAULT_VISIBLE_RESEARCH_CARDS == 100


def test_research_report_display_limit_supports_large_filtered_sets():
    assert research_report_display_limit("30", 2335) == 30
    assert research_report_display_limit("300", 2335) == 300
    assert research_report_display_limit("all", 2335) == 2335
    assert research_report_display_limit("bad", 2335) == DEFAULT_VISIBLE_RESEARCH_CARDS


def test_research_report_card_shows_explicit_empty_category_states():
    html = _research_report_card_html(
        {
            "report_date": "2026-05-14",
            "ticker": "005930",
            "source": "mirae_asset",
            "title": "Samsung title fallback",
            "summary": "Title-based positive summary.",
            "investment_opinion": "positive",
            "confidence": 0.6,
            "buy_thesis": "Title thesis.",
            "growth_drivers": "",
            "earnings_drivers": "",
            "valuation_view": "",
            "target_price_rationale": "",
            "risk_factors": "",
            "sell_or_risk_thesis": "",
            "evidence_terms": "",
        }
    )

    assert "Title thesis." in html
    assert "업황/성장 문장은 추출되지 않았습니다." in html
    assert "실적/밸류 문장은 추출되지 않았습니다." in html
    assert "명시 리스크 문장은 추출되지 않았습니다." in html


def test_research_report_card_cleans_noisy_fragments_and_preserves_full_details():
    html = _research_report_card_html(
        {
            "report_date": "2026-05-14",
            "ticker": "000270",
            "source": "hankyung_consensus",
            "title": "Kia report",
            "summary": "000270 리포트는 positive 관점으로 해석됩니다. 핵심 근거: 매수 중립(보유) 매도 / 주요 차종 판매 호조와 Mix 개선",
            "investment_opinion": "positive",
            "confidence": 0.9,
            "buy_thesis": "매수 중립(보유) 매도 / 주요 차종 판매 호조와 Mix 개선",
            "growth_drivers": "향후 6개월간 업종지수상승률이 시장수익률과 유사한 수준 예상 / 신차 판매 확대",
            "earnings_drivers": "영업이익 12,667 9,078 10,031 10,926 13,319 / Mix 개선으로 수익성 방어",
            "valuation_view": "목표주가 240,000원 유지",
            "target_price_rationale": "",
            "risk_factors": "Issue Comment / 환율 변동",
            "sell_or_risk_thesis": "",
            "evidence_terms": "판매, Mix, 환율",
        }
    )

    assert "주요 차종 판매 호조와 Mix 개선" in html
    assert "신차 판매 확대" in html
    assert "Mix 개선으로 수익성 방어" in html
    assert "환율 변동" in html
    assert "분석 문장 전체 보기" in html
    assert "매수 중립(보유) 매도" not in html
    assert "영업이익 12,667" not in html
    assert "Issue Comment" not in html


def test_research_report_card_hides_obviously_cut_sentence_fragments():
    html = _research_report_card_html(
        {
            "report_date": "2026-05-14",
            "ticker": "000120",
            "source": "hankyung_consensus",
            "title": "CJ Logistics",
            "summary": "000120 리포트는 positive 관점으로 해석됩니다. 핵심 근거: 물량 확대에 따른 실적 증가 요인이 컸으나, 허브 / 택배 시장 점유율 확대",
            "investment_opinion": "positive",
            "confidence": 0.8,
            "buy_thesis": "물량 확대에 따른 실적 증가 요인이 컸으나, 허브 / 택배 시장 점유율 확대",
            "growth_drivers": "전방 고객사 물량 감소와 비용확대 영향으로 전년 / 신규수주 확대",
            "earnings_drivers": "영업이익은 921억원(+7.9% / 실적 기대치 하회",
            "valuation_view": "",
            "target_price_rationale": "",
            "risk_factors": "환율 변동",
            "sell_or_risk_thesis": "",
            "evidence_terms": "",
        }
    )

    assert "택배 시장 점유율 확대" in html
    assert "신규수주 확대" in html
    assert "실적 기대치 하회" in html
    assert "허브" not in html
    assert "영업이익은 921억원(+7.9%" not in html


def test_build_ticker_research_quality_report_treats_limited_body_placeholder_as_missing():
    artifact = build_ticker_research_briefs(
        [
            {
                "ticker": "358570",
                "report_date": "2026-03-27",
                "source": "mirae_asset",
                "broker": "Mirae",
                "title": "GI Innovation",
                "summary": "358570 리포트의 본문 근거 추출이 제한적입니다.",
                "investment_opinion": "positive",
                "buy_thesis": "358570 리포트의 본문 근거 추출이 제한적입니다.",
                "growth_drivers": "358570 리포트의 본문 근거 추출이 제한적입니다.",
                "earnings_drivers": "358570 리포트의 본문 근거 추출이 제한적입니다.",
                "valuation_view": "",
                "risk_factors": "임상 데이터로 입증하는 파이프라인 경쟁력",
                "new_business": "",
                "confidence": 0.56,
                "body_text_status": "title_or_sparse",
                "evidence_terms": "stock_report, title_or_sparse, brief-rule-v3",
                "source_url": "",
            }
        ],
        generated_at="2026-05-15T09:00:00+09:00",
    )

    report = build_ticker_research_quality_report(
        artifact,
        now=datetime(2026, 5, 15, tzinfo=KST),
        stale_days=45,
    )

    issue = report["issues"][0]
    assert issue["ticker"] == "358570"
    assert issue["missing_sections"] == ["stock_view", "growth", "earnings"]


def test_research_report_card_hides_additional_incomplete_report_tails():
    html = _research_report_card_html(
        {
            "report_date": "2026-05-14",
            "ticker": "004170",
            "source": "hankyung_consensus",
            "title": "Shinsegae",
            "summary": "정상 요약입니다.",
            "investment_opinion": "positive",
            "confidence": 0.8,
            "buy_thesis": "투자포인트는 / 백화점과 면세점 실적 개선이 기대된다.",
            "growth_drivers": "(Y oY +66.5%)을 기록하며, 당사 추정치 및 시장 기대치를 상회하는 실적을 달성하 / 외국인 관광객 회복과 럭셔리 소비 증가가 업황을 견인한다.",
            "earnings_drivers": "1Q26 매출과 영업이익은 MLCC 믹스 개선에 힘입어 각각 3조 / 외국인 매출 비중 상승으로 영업이익 개선이 예상된다.",
            "valuation_view": "",
            "target_price_rationale": "",
            "risk_factors": "비 부담이 확대된 한편 전방 고객사 발주가 동반 부진한 영향이다. / 환율 변동과 소비 둔화는 단기 리스크다.",
            "sell_or_risk_thesis": "",
            "evidence_terms": "",
        }
    )

    assert "투자포인트는" not in html
    assert "실적을 달성하" not in html
    assert "각각 3조" not in html
    assert "비 부담이 확대된" not in html
    assert "업황을 견인한다" in html
    assert "영업이익 개선이 예상된다" in html
    assert "단기 리스크" in html


def test_research_report_card_hides_broken_leading_and_trailing_fragments():
    html = _research_report_card_html(
        {
            "report_date": "2026-05-14",
            "ticker": "003230",
            "source": "hankyung_consensus",
            "title": "Samyang Foods",
            "summary": "인의 원활한 재고 소진과 수출 증가에 따른 ASP 상승에 / 공급 병목 완화",
            "investment_opinion": "positive",
            "confidence": 0.8,
            "buy_thesis": "인의 원활한 재고 소진과 수출 증가에 따른 ASP 상승에 / 공급 병목 완화",
            "growth_drivers": "신규로 편입되면서 151억원의 매출 증가 효과 반영",
            "earnings_drivers": "매출총이익률 감소했으나 영업이익률에는 영향 없음",
            "valuation_view": "",
            "target_price_rationale": "",
            "risk_factors": "중동 사태로 인해 물류비와 포장재 원가 부담이 상승할 우려가 존재하 / 원가 부담",
            "sell_or_risk_thesis": "",
            "evidence_terms": "",
        }
    )

    assert "공급 병목 완화" in html
    assert "원가 부담" in html
    assert "인의 원활한" not in html
    assert "우려가 존재하" not in html


def test_render_dashboard_shows_read_only_summary_positions_and_warnings(monkeypatch):
    calls: list[tuple[str, tuple, dict]] = []

    class FakeColumn:
        def __enter__(self):
            calls.append(("column_enter", (), {}))
            return self

        def __exit__(self, exc_type, exc, tb):
            calls.append(("column_exit", (), {}))
            return False

        def __getattr__(self, name):
            def _inner(*args, **kwargs):
                calls.append((name, args, kwargs))
            return _inner

    class FakeExpander:
        def __enter__(self):
            calls.append(("expander_enter", (), {}))
            return self

        def __exit__(self, exc_type, exc, tb):
            calls.append(("expander_exit", (), {}))
            return False

    def record(name):
        def _inner(*args, **kwargs):
            calls.append((name, args, kwargs))
            if name == "columns":
                count = len(args[0]) if isinstance(args[0], list) else args[0]
                return [FakeColumn() for _ in range(count)]
            if name == "expander":
                return FakeExpander()
            return None

        return _inner

    fake_streamlit = SimpleNamespace(
        set_page_config=record("set_page_config"),
        title=record("title"),
        caption=record("caption"),
        success=record("success"),
        warning=record("warning"),
        metric=record("metric"),
        columns=record("columns"),
        subheader=record("subheader"),
        dataframe=record("dataframe"),
        expander=record("expander"),
        markdown=record("markdown"),
        json=record("json"),
        plotly_chart=record("plotly_chart"),
    )
    monkeypatch.setitem(__import__("sys").modules, "streamlit", fake_streamlit)

    render_dashboard(_sample_snapshot())

    rendered_text = "\n".join(str(arg) for _, args, _ in calls for arg in args)
    assert "Public Portfolio Dashboard" in rendered_text
    assert "Read-only snapshot" in rendered_text
    assert "2026-05-12T09:00:00+09:00" in rendered_text
    assert "missing_rationale:000660" in rendered_text
    assert "htable" in rendered_text
    assert "Equity Curve" in rendered_text
    assert any("target allocation buy" in str(args) for _, args, _ in calls)
    assert "ROE" in rendered_text
    assert "Investor Flow" in rendered_text
