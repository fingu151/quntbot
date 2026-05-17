from argparse import Namespace
from datetime import date

from sqlalchemy import select

from scripts.generate_mirae_research_summary import parse_args, run
from src.data.database import create_tables, get_engine, session_scope
from src.data.models import ResearchReportSignal
from src.data.repositories import upsert_research_report_analyses, upsert_research_report_signals


def test_parse_args_uses_mirae_defaults():
    args = parse_args([])

    assert args.source == "mirae_asset"
    assert args.broker == "미래에셋증권"
    assert args.limit == 30
    assert args.title == "Mirae Asset Research Summary"
    assert str(args.output).endswith("mirae_research_summary_latest.md")


def test_run_writes_mirae_research_summary_markdown(tmp_path, capsys):
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    output = tmp_path / "mirae.md"
    with session_scope(engine) as session:
        upsert_research_report_signals(
            session,
            [
                {
                    "report_date": date(2026, 5, 14),
                    "ticker": "011200",
                    "source": "mirae_asset",
                    "region": "domestic",
                    "broker": "미래에셋증권",
                    "rating": "Buy",
                    "rating_score": 0.6,
                    "target_price": None,
                    "previous_target_price": None,
                    "target_price_change_pct": None,
                    "sentiment_score": None,
                    "raw_score": 0.6,
                    "title": "HMM (011200/매수)상승하는 운임, 비용 증가 상쇄 기대",
                    "source_url": "https://example.test/hmm.pdf",
                }
            ],
        )
        signal = session.scalars(select(ResearchReportSignal)).one()
        upsert_research_report_analyses(
            session,
            [
                {
                    "report_signal_id": signal.id,
                    "ticker": "011200",
                    "report_date": date(2026, 5, 14),
                    "source": "mirae_asset",
                    "broker": "미래에셋증권",
                    "title": signal.title,
                    "source_url": signal.source_url,
                    "body_text_status": "extracted",
                    "body_text_chars": 1200,
                    "summary": "011200 리포트는 positive 관점입니다.",
                    "investment_opinion": "positive",
                    "buy_thesis": "상승하는 운임, 비용 증가 상쇄 기대",
                    "sell_or_risk_thesis": "",
                    "growth_drivers": "",
                    "earnings_drivers": "영업이익 개선",
                    "valuation_view": "",
                    "target_price_rationale": "",
                    "risk_factors": "운임 하락",
                    "evidence_terms": "운임, 비용, 영업이익",
                    "analysis_version": "rule-v1",
                    "confidence": 0.8,
                }
            ],
        )

    exit_code = run(
        Namespace(
            source="mirae_asset",
            broker="미래에셋증권",
            database_url=None,
            output=output,
            limit=30,
            title="Mirae Asset Research Summary",
        ),
        engine_factory=lambda database_url: engine,
    )

    captured = capsys.readouterr()
    markdown = output.read_text(encoding="utf-8")

    assert exit_code == 0
    assert "mirae_research_summary_rows=1" in captured.out
    assert "orders_submitted=0" in captured.out
    assert "# Mirae Asset Research Summary" in markdown
    assert "011200" in markdown
    assert "상승하는 운임" in markdown
    assert "운임 하락" in markdown
    assert "extracted" in markdown


def test_run_uses_custom_summary_title(tmp_path):
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    output = tmp_path / "hankyung.md"

    exit_code = run(
        Namespace(
            source="hankyung_consensus",
            broker="한경 컨센서스",
            database_url=None,
            output=output,
            limit=30,
            title="Hankyung Consensus Research Summary",
        ),
        engine_factory=lambda database_url: engine,
    )

    assert exit_code == 1
    assert output.read_text(encoding="utf-8").startswith(
        "# Hankyung Consensus Research Summary"
    )
