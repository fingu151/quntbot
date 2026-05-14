from datetime import date

from sqlalchemy import select

from src.data.database import create_tables, get_engine, session_scope
from src.data.models import ResearchReportAnalysis, ResearchReportSignal
from src.signals.research_report_reader import (
    PdfTextTelemetry,
    ResearchReportBodyUnavailable,
    fetch_and_store_korean_research_reports,
)


def test_fetch_and_store_korean_research_reports_parses_and_persists_rows():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    html = """
<html><body>
<tr><td>2026.05.12</td><td><a href="/a.pdf">삼성전자(005930) 매수 목표가 8만→9만 개선</a></td></tr>
<tr><td>2026.05.12</td><td><a href="/b.pdf">카카오(035720) 매도 목표가 5만→4만 부진</a></td></tr>
</body></html>
"""

    stored = fetch_and_store_korean_research_reports(
        engine,
        url="https://example.test/research",
        source="mirae_kr",
        broker="미래에셋증권",
        html_fetcher=lambda url: html,
    )

    with session_scope(engine) as session:
        rows = session.scalars(select(ResearchReportSignal)).all()
        analyses = session.scalars(select(ResearchReportAnalysis)).all()

    assert stored == 2
    assert {row.ticker for row in rows} == {"005930", "035720"}
    assert all(row.report_date == date(2026, 5, 12) for row in rows)
    assert rows[0].source == "mirae_kr"
    assert len(analyses) == 2
    assert {row.body_text_status for row in analyses} == {"not_requested"}


def test_fetch_and_store_korean_research_reports_can_score_pdf_body_text():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    html = """
<html><body>
<tr><td>2026.05.12</td><td><a href="/a.pdf">삼성전자(005930) 매수</a></td></tr>
</body></html>
"""

    fetched_urls = []
    telemetry = PdfTextTelemetry()

    def pdf_text_fetcher(url: str) -> str:
        fetched_urls.append(url)
        return "수요 부진과 비용 부담으로 실적 전망 하향"

    stored = fetch_and_store_korean_research_reports(
        engine,
        url="https://example.test/research",
        source="mirae_kr",
        broker="미래에셋증권",
        html_fetcher=lambda url: html,
        include_pdf_text=True,
        pdf_text_fetcher=pdf_text_fetcher,
        pdf_telemetry=telemetry,
    )

    with session_scope(engine) as session:
        rows = session.scalars(select(ResearchReportSignal)).all()
        analyses = session.scalars(select(ResearchReportAnalysis)).all()

    assert stored == 1
    assert fetched_urls == ["https://example.test/a.pdf"]
    assert telemetry.pdf_text_attempted == 1
    assert telemetry.pdf_text_extracted == 1
    assert telemetry.pdf_text_length > 0
    assert telemetry.body_signal_applied == 1
    assert telemetry.analysis_rows_stored == 1
    assert telemetry.analysis_success_count == 1
    assert rows[0].sentiment_score == -0.1
    assert rows[0].raw_score == 0.5
    assert analyses[0].body_text_status == "extracted"
    assert analyses[0].sell_or_risk_thesis


def test_fetch_and_store_korean_research_reports_treats_hankyung_pdf_path_as_pdf():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    html = """
<html><body>
<tr><td>2026.05.12</td><td><a href="/pdf/2026/05/hash">삼성전자(005930) 매수</a></td></tr>
</body></html>
"""
    fetched_urls = []
    telemetry = PdfTextTelemetry()

    def pdf_text_fetcher(url: str) -> str:
        fetched_urls.append(url)
        return "목표주가 상향과 AI 수요 증가로 실적 개선이 예상된다."

    stored = fetch_and_store_korean_research_reports(
        engine,
        url="https://markets.hankyung.com/consensus",
        source="hankyung_consensus",
        broker="한경 컨센서스",
        html_fetcher=lambda url: html,
        include_pdf_text=True,
        pdf_text_fetcher=pdf_text_fetcher,
        pdf_telemetry=telemetry,
    )

    with session_scope(engine) as session:
        analyses = session.scalars(select(ResearchReportAnalysis)).all()

    assert stored == 1
    assert fetched_urls == ["https://markets.hankyung.com/pdf/2026/05/hash"]
    assert telemetry.pdf_text_attempted == 1
    assert analyses[0].body_text_status == "extracted"
    assert "목표주가" in analyses[0].target_price_rationale


def test_fetch_and_store_korean_research_reports_tracks_empty_pdf_text():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    html = """
<html><body>
<tr><td>2026.05.12</td><td><a href="/a.pdf">?쇱꽦?꾩옄(005930) 留ㅼ닔</a></td></tr>
</body></html>
"""
    telemetry = PdfTextTelemetry()

    stored = fetch_and_store_korean_research_reports(
        engine,
        url="https://example.test/research",
        source="mirae_kr",
        broker="誘몃옒?먯뀑利앷텒",
        html_fetcher=lambda url: html,
        include_pdf_text=True,
        pdf_text_fetcher=lambda url: None,
        pdf_telemetry=telemetry,
    )

    assert stored == 1
    assert telemetry.pdf_text_attempted == 1
    assert telemetry.pdf_text_extracted == 0
    assert telemetry.pdf_text_length == 0
    assert telemetry.body_signal_applied == 0
    assert telemetry.analysis_rows_stored == 1


def test_fetch_and_store_korean_research_reports_does_not_fetch_non_pdf_urls():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    html = """
<html><body>
<tr><td>2026.05.12</td><td><a href="/a.html">?쇱꽦?꾩옄(005930) 留ㅼ닔</a></td></tr>
</body></html>
"""
    fetched_urls = []
    telemetry = PdfTextTelemetry()

    stored = fetch_and_store_korean_research_reports(
        engine,
        url="https://example.test/research",
        source="mirae_kr",
        broker="誘몃옒?먯뀑利앷텒",
        html_fetcher=lambda url: html,
        include_pdf_text=True,
        pdf_text_fetcher=lambda url: fetched_urls.append(url),
        pdf_telemetry=telemetry,
    )

    assert stored == 1
    assert fetched_urls == []
    assert telemetry.pdf_text_attempted == 0
    assert telemetry.pdf_text_extracted == 0
    assert telemetry.pdf_text_length == 0
    assert telemetry.body_signal_applied == 0
    assert telemetry.analysis_rows_stored == 1


def test_fetch_and_store_korean_research_reports_keeps_rows_when_pdf_fetch_fails():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    html = """
<html><body>
<tr><td>2026.05.12</td><td><a href="/a.pdf">삼성전자(005930) 매수</a></td></tr>
</body></html>
"""

    def fail_pdf(url: str) -> str:
        raise TimeoutError("pdf timeout")

    stored = fetch_and_store_korean_research_reports(
        engine,
        url="https://example.test/research",
        source="mirae_kr",
        broker="미래에셋증권",
        html_fetcher=lambda url: html,
        include_pdf_text=True,
        pdf_text_fetcher=fail_pdf,
    )

    with session_scope(engine) as session:
        rows = session.scalars(select(ResearchReportSignal)).all()
        analyses = session.scalars(select(ResearchReportAnalysis)).all()

    assert stored == 1
    assert rows[0].raw_score == 0.6
    assert analyses[0].body_text_status == "fetch_failed"
    assert analyses[0].summary


def test_fetch_and_store_korean_research_reports_tracks_login_required_pdf_body():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    html = """
<html><body>
<tr><td>2026.05.12</td><td><a href="/pdf/locked">삼성전자(005930) 매수</a></td></tr>
</body></html>
"""

    def login_required(url: str) -> str:
        raise ResearchReportBodyUnavailable("login_required", "login required")

    stored = fetch_and_store_korean_research_reports(
        engine,
        url="https://markets.hankyung.com/consensus",
        source="hankyung_consensus",
        broker="한경 컨센서스",
        html_fetcher=lambda url: html,
        include_pdf_text=True,
        pdf_text_fetcher=login_required,
    )

    with session_scope(engine) as session:
        analyses = session.scalars(select(ResearchReportAnalysis)).all()

    assert stored == 1
    assert analyses[0].body_text_status == "login_required"
    assert analyses[0].summary


def test_fetch_and_store_korean_research_reports_returns_zero_on_fetch_failure():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)

    def fail(url: str) -> str:
        raise TimeoutError("timeout")

    stored = fetch_and_store_korean_research_reports(
        engine,
        url="https://example.test/research",
        source="mirae_kr",
        html_fetcher=fail,
    )

    assert stored == 0
