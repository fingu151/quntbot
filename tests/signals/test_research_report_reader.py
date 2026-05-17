from datetime import date

from sqlalchemy import select

from src.data.database import create_tables, get_engine, session_scope
from src.data.models import ResearchReportAnalysis, ResearchReportSignal
from src.signals.research_report_reader import (
    PdfTextTelemetry,
    ResearchReportBodyUnavailable,
    _extract_pdf_text,
    _join_pdf_text_parts,
    build_research_report_page_urls,
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


def test_join_pdf_text_parts_drops_empty_pages_and_preserves_page_breaks():
    assert _join_pdf_text_parts([" first page ", "", "second page"]) == "first page\nsecond page"
    assert _join_pdf_text_parts(["", "   "]) is None


def test_extract_pdf_text_skips_fallback_extractors_when_pypdf_text_is_long(monkeypatch):
    monkeypatch.setattr(
        "src.signals.research_report_reader._extract_pdf_text_with_pypdf",
        lambda content: "x" * 500,
    )

    def fail_fallback(content: bytes) -> str:
        raise AssertionError("fallback should not run for long pypdf text")

    monkeypatch.setattr("src.signals.research_report_reader._extract_pdf_text_with_pymupdf", fail_fallback)
    monkeypatch.setattr("src.signals.research_report_reader._extract_pdf_text_with_pdfplumber", fail_fallback)

    assert _extract_pdf_text(b"%PDF") == "x" * 500


def test_extract_pdf_text_uses_longest_fallback_when_pypdf_text_is_short(monkeypatch):
    monkeypatch.setattr(
        "src.signals.research_report_reader._extract_pdf_text_with_pypdf",
        lambda content: "short",
    )
    monkeypatch.setattr(
        "src.signals.research_report_reader._extract_pdf_text_with_pymupdf",
        lambda content: "medium text",
    )
    monkeypatch.setattr(
        "src.signals.research_report_reader._extract_pdf_text_with_pdfplumber",
        lambda content: "longer fallback text",
    )

    assert _extract_pdf_text(b"%PDF") == "longer fallback text"


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


def test_fetch_and_store_korean_research_reports_treats_hankyung_downpdf_as_pdf():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    html = """
<table>
  <tr>
    <td>2026-05-14</td><td>기업</td>
    <td><a href="/analysis/downpdf?report_idx=649357">HMM(011200) 1Q26 Review</a></td>
    <td>이서연</td><td>상상인증권</td>
    <td><a href="/analysis/downpdf?report_idx=649357">PDF</a></td>
  </tr>
</table>
"""
    fetched_urls = []
    telemetry = PdfTextTelemetry()

    def pdf_text_fetcher(url: str) -> str:
        fetched_urls.append(url)
        return "매수 의견과 운임 상승에 따른 실적 개선을 제시했다."

    stored = fetch_and_store_korean_research_reports(
        engine,
        url="https://consensus.hankyung.com/",
        source="hankyung_consensus",
        broker="한경 컨센서스",
        html_fetcher=lambda url: html,
        include_pdf_text=True,
        pdf_text_fetcher=pdf_text_fetcher,
        pdf_telemetry=telemetry,
    )

    assert stored == 1
    assert fetched_urls == ["https://consensus.hankyung.com/analysis/downpdf?report_idx=649357"]
    assert telemetry.pdf_text_attempted == 1


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


def test_build_research_report_page_urls_expands_miraeasset_cur_pages():
    urls = build_research_report_page_urls(
        "https://securities.miraeasset.com/bbs/board/message/list.do?categoryId=1533",
        pages=3,
    )

    assert len(urls) == 3
    assert "curPage=1" in urls[0]
    assert "curPage=2" in urls[1]
    assert "curPage=3" in urls[2]
    assert "searchType=2" in urls[1]
    assert "startId=zzzzz" in urls[1]


def test_build_research_report_page_urls_uses_requested_date_range():
    urls = build_research_report_page_urls(
        "https://securities.miraeasset.com/bbs/board/message/list.do?categoryId=1533",
        pages=1,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 5, 14),
    )

    assert "searchStartYear=2026" in urls[0]
    assert "searchStartMonth=01" in urls[0]
    assert "searchStartDay=01" in urls[0]
    assert "searchEndYear=2026" in urls[0]
    assert "searchEndMonth=05" in urls[0]
    assert "searchEndDay=14" in urls[0]


def test_build_research_report_page_urls_expands_hankyung_consensus_pages():
    urls = build_research_report_page_urls(
        "https://consensus.hankyung.com/",
        pages=2,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 5, 14),
    )

    assert urls == [
        "https://consensus.hankyung.com/analysis/list?sdate=2026-01-01&edate=2026-05-14&order_type=&pagenum=80&now_page=1",
        "https://consensus.hankyung.com/analysis/list?sdate=2026-01-01&edate=2026-05-14&order_type=&pagenum=80&now_page=2",
    ]


def test_fetch_and_store_korean_research_reports_fetches_multiple_miraeasset_pages():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    fetched_urls = []

    def html_fetcher(url: str) -> str:
        fetched_urls.append(url)
        if "curPage=2" in url:
            return """
<table class="bbs_linetype2"><tbody>
<tr><td>2026-05-13</td><td><a href="javascript:view('2','2')" id="bbsTitle0"><b>덴티움 (145720/매수)</b><br/>중국에서 2차 VBP만 다시 시작된다면!</a></td><td><a href="javascript:downConfirm('https://example.test/2.pdf','2','1024','768','yes','yes');">PDF</a></td></tr>
</tbody></table>
"""
        return """
<table class="bbs_linetype2"><tbody>
<tr><td>2026-05-14</td><td><a href="javascript:view('1','1')" id="bbsTitle0"><b>HMM (011200/매수)</b><br/>상승하는 운임, 비용 증가 상쇄 기대</a></td><td><a href="javascript:downConfirm('https://example.test/1.pdf','1','1024','768','yes','yes');">PDF</a></td></tr>
</tbody></table>
"""

    stored = fetch_and_store_korean_research_reports(
        engine,
        url="https://securities.miraeasset.com/bbs/board/message/list.do?categoryId=1533",
        source="mirae_asset",
        broker="미래에셋증권",
        html_fetcher=html_fetcher,
        pages=2,
    )

    with session_scope(engine) as session:
        rows = session.scalars(select(ResearchReportSignal)).all()

    assert stored == 2
    assert len(fetched_urls) == 2
    assert "curPage=1" in fetched_urls[0]
    assert "curPage=2" in fetched_urls[1]
    assert {row.ticker for row in rows} == {"011200", "145720"}
