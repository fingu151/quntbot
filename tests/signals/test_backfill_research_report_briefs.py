from argparse import Namespace
from datetime import date

from sqlalchemy import select

from scripts.backfill_research_report_briefs import run
from src.data.database import create_tables, get_engine, session_scope
from src.data.models import ResearchReportBrief
from src.data.repositories import upsert_research_report_analyses, upsert_research_report_signals


def test_run_backfills_missing_brief_from_existing_analysis(capsys):
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
                }
            ],
        )
        signal_id = session.scalar(select(ResearchReportBrief.report_signal_id))
        assert signal_id is None
        signal = session.execute(select(__import__("src.data.models", fromlist=["ResearchReportSignal"]).ResearchReportSignal)).scalar_one()
        upsert_research_report_analyses(
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
                    "body_text_status": "title_or_sparse",
                    "body_text_chars": 0,
                    "summary": "Memory recovery supports earnings.",
                    "investment_opinion": "positive",
                    "buy_thesis": "Memory 업황 회복이 투자 포인트다.",
                    "sell_or_risk_thesis": "가격 조정은 리스크다.",
                    "growth_drivers": "AI 수요가 성장 동력이다.",
                    "earnings_drivers": "DRAM 가격 상승이 실적을 견인한다.",
                    "valuation_view": "Peer 대비 저평가다.",
                    "target_price_rationale": "이익 추정치 상향 기준이다.",
                    "risk_factors": "수요 회복 지연이 주요 리스크다.",
                    "evidence_terms": "memory, earnings",
                    "analysis_version": "test",
                    "confidence": 0.7,
                }
            ],
        )

    exit_code = run(
        Namespace(database_url=None, limit=None, dry_run=False),
        engine_factory=lambda database_url: engine,
    )

    captured = capsys.readouterr()
    with session_scope(engine) as session:
        briefs = session.scalars(select(ResearchReportBrief)).all()

    assert exit_code == 0
    assert len(briefs) == 1
    assert briefs[0].ticker == "005930"
    assert briefs[0].stock_view
    assert "missing_brief_rows_seen=1" in captured.out
    assert "brief_rows_stored=1" in captured.out
    assert "orders_submitted=0" in captured.out
