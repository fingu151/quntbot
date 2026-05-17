from argparse import Namespace
from datetime import date

from sqlalchemy import select

from scripts.reanalyze_research_report_bodies import parse_args, run
import scripts.reanalyze_research_report_bodies as reanalyze_module
from src.data.database import create_tables, get_engine, session_scope
from src.data.models import ResearchReportAnalysis, ResearchReportBrief, ResearchReportSignal
from src.data.repositories import upsert_research_report_signals
from src.signals.research_report_reader import PdfTextTelemetry
from src.signals.research_report_reader import ResearchReportBodyUnavailable


def test_parse_args_uses_mirae_defaults():
    args = parse_args([])

    assert args.source == "mirae_asset"
    assert args.broker == "미래에셋증권"
    assert args.limit is None
    assert args.ticker == []
    assert args.database_url is None


def test_run_reanalyzes_existing_mirae_rows_without_orders(capsys):
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
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
                },
                {
                    "report_date": date(2026, 5, 14),
                    "ticker": "064260",
                    "source": "mirae_asset",
                    "region": "domestic",
                    "broker": "미래에셋증권",
                    "rating": None,
                    "rating_score": None,
                    "target_price": None,
                    "previous_target_price": None,
                    "target_price_change_pct": None,
                    "sentiment_score": None,
                    "raw_score": 0.0,
                    "title": "다날 (064260/Not Rated)결제는 다 날 통해",
                    "source_url": "https://example.test/danal.pdf",
                },
            ],
        )

    telemetry = PdfTextTelemetry()

    exit_code = run(
        Namespace(
            source="mirae_asset",
            broker="미래에셋증권",
            database_url=None,
            limit=1,
            ticker=[],
        ),
        engine_factory=lambda database_url: engine,
        pdf_text_fetcher=lambda url: "운임 상승과 비용 증가 상쇄로 영업이익 개선이 예상된다.",
        pdf_telemetry=telemetry,
    )

    captured = capsys.readouterr()
    with session_scope(engine) as session:
        analyses = session.scalars(select(ResearchReportAnalysis)).all()
        briefs = session.scalars(select(ResearchReportBrief)).all()
        signals = session.scalars(select(ResearchReportSignal)).all()

    assert exit_code == 0
    assert len(signals) == 2
    assert len(analyses) == 1
    assert len(briefs) == 1
    assert analyses[0].ticker == "011200"
    assert analyses[0].body_text_status == "extracted"
    assert briefs[0].ticker == "011200"
    assert briefs[0].brief_version == "brief-rule-v3"
    assert briefs[0].source_quality in {"title_or_sparse", "partial_text", "full_text"}
    assert "영업이익 개선" in analyses[0].earnings_drivers
    assert "research_report_rows_seen=1" in captured.out
    assert "analysis_rows_stored=1" in captured.out
    assert "brief_rows_stored=1" in captured.out
    assert "orders_submitted=0" in captured.out


def test_run_can_reanalyze_selected_tickers_only(capsys):
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    with session_scope(engine) as session:
        upsert_research_report_signals(
            session,
            [
                {
                    "report_date": date(2026, 5, 14),
                    "ticker": "011200",
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
                    "title": "HMM report",
                    "source_url": "https://example.test/hmm.pdf",
                },
                {
                    "report_date": date(2026, 5, 13),
                    "ticker": "064260",
                    "source": "mirae_asset",
                    "region": "domestic",
                    "broker": "Mirae",
                    "rating": None,
                    "rating_score": None,
                    "target_price": None,
                    "previous_target_price": None,
                    "target_price_change_pct": None,
                    "sentiment_score": None,
                    "raw_score": 0.0,
                    "title": "Danal report",
                    "source_url": "https://example.test/danal.pdf",
                },
            ],
        )

    exit_code = run(
        Namespace(
            source="mirae_asset",
            broker="Mirae",
            database_url=None,
            limit=None,
            ticker=["064260"],
        ),
        engine_factory=lambda database_url: engine,
        pdf_text_fetcher=lambda url: "결제 성장과 비용 리스크가 함께 제시됩니다.",
        pdf_telemetry=PdfTextTelemetry(),
    )

    captured = capsys.readouterr()
    with session_scope(engine) as session:
        analyses = session.scalars(select(ResearchReportAnalysis)).all()

    assert exit_code == 0
    assert [analysis.ticker for analysis in analyses] == ["064260"]
    assert "research_report_rows_seen=1" in captured.out


def test_run_treats_hankyung_pdf_path_as_pdf(capsys):
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    with session_scope(engine) as session:
        upsert_research_report_signals(
            session,
            [
                {
                    "report_date": date(2026, 5, 14),
                    "ticker": "003230",
                    "source": "hankyung_consensus",
                    "region": "domestic",
                    "broker": "한경 컨센서스",
                    "rating": "Buy",
                    "rating_score": 0.6,
                    "target_price": None,
                    "previous_target_price": None,
                    "target_price_change_pct": None,
                    "sentiment_score": None,
                    "raw_score": 0.7,
                    "title": "삼양식품(003230) 분기 매출 7천억원 상회",
                    "source_url": "https://markets.hankyung.com/pdf/2026/05/hash",
                },
            ],
        )

    def login_required(url: str):
        raise ResearchReportBodyUnavailable("login_required", "login required")

    telemetry = PdfTextTelemetry()
    exit_code = run(
        Namespace(
            source="hankyung_consensus",
            broker="한경 컨센서스",
            database_url=None,
            limit=None,
            ticker=[],
        ),
        engine_factory=lambda database_url: engine,
        pdf_text_fetcher=login_required,
        pdf_telemetry=telemetry,
    )

    captured = capsys.readouterr()
    with session_scope(engine) as session:
        analysis = session.scalars(select(ResearchReportAnalysis)).one()
        brief = session.scalars(select(ResearchReportBrief)).one()

    assert exit_code == 0
    assert telemetry.pdf_text_attempted == 1
    assert analysis.body_text_status == "login_required"
    assert brief.source_quality == "login_required"
    assert brief.brief_version == "brief-rule-v3"
    assert "pdf_text_attempted=1" in captured.out
    assert "brief_rows_stored=1" in captured.out


def test_run_preserves_analysis_when_brief_generation_fails(monkeypatch):
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    with session_scope(engine) as session:
        upsert_research_report_signals(
            session,
            [
                {
                    "report_date": date(2026, 5, 14),
                    "ticker": "005930",
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
                    "title": "Samsung memory upcycle",
                    "source_url": "https://example.test/samsung.pdf",
                },
            ],
        )

    def fail_briefing(*args, **kwargs):
        raise RuntimeError("brief failed")

    monkeypatch.setattr(reanalyze_module, "build_research_report_briefing", fail_briefing)
    exit_code = run(
        Namespace(source="mirae_asset", broker="Mirae", database_url=None, limit=None, ticker=[]),
        engine_factory=lambda database_url: engine,
        pdf_text_fetcher=lambda url: "AI server demand improves earnings and valuation.",
        pdf_telemetry=PdfTextTelemetry(),
    )

    with session_scope(engine) as session:
        analysis = session.scalars(select(ResearchReportAnalysis)).one()
        brief = session.scalars(select(ResearchReportBrief)).one()

    assert exit_code == 0
    assert analysis.body_text_status == "extracted"
    assert brief.source_quality == "brief_failed"
    assert brief.brief_version == "brief-rule-v3-fallback"
