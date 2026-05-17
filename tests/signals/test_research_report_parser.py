from datetime import date

import pytest

from src.signals.research_report_parser import (
    apply_report_body_text_signal,
    parse_korean_research_report_text,
    parse_korean_research_reports,
    reports_to_rows,
)


_HTML = """
<html><body>
<table>
  <tr>
    <td>2026.05.12</td>
    <td><a href="/report/005930.pdf">삼성전자(005930) 매수 목표주가 85,000원→95,000원 실적 개선</a></td>
    <td>미래에셋증권</td>
  </tr>
  <tr>
    <td>2026.05.12</td>
    <td><a href="/report/000660.pdf">SK하이닉스(000660) 중립 고평가 부담</a></td>
    <td>미래에셋증권</td>
  </tr>
  <tr>
    <td>2026.05.12</td>
    <td><a href="/report/035720.pdf">카카오(035720) 매도 목표가 5만→4만 부진</a></td>
    <td>미래에셋증권</td>
  </tr>
</table>
</body></html>
"""


def test_parse_korean_research_reports_extracts_domestic_report_signals():
    reports = parse_korean_research_reports(
        _HTML,
        source="mirae_kr",
        broker="미래에셋증권",
        base_url="https://example.test/research/list",
    )

    by_ticker = {report.ticker: report for report in reports}

    assert set(by_ticker) == {"005930", "000660", "035720"}
    samsung = by_ticker["005930"]
    assert samsung.report_date == date(2026, 5, 12)
    assert samsung.rating == "Buy"
    assert samsung.rating_score == 0.6
    assert samsung.previous_target_price == 85000
    assert samsung.target_price == 95000
    assert samsung.target_price_change_pct == pytest.approx((95000 / 85000) - 1.0)
    assert samsung.raw_score > 0.6
    assert samsung.source_url == "https://example.test/report/005930.pdf"

    hynix = by_ticker["000660"]
    assert hynix.rating == "Hold"
    assert hynix.raw_score < 0

    kakao = by_ticker["035720"]
    assert kakao.rating == "Sell"
    assert kakao.raw_score == -1.0


def test_parse_korean_research_report_text_handles_manwon_target_prices():
    report = parse_korean_research_report_text(
        "2026-05-12 기아 000270 매수 목표주가 17만→30만 저평가",
        source="mirae_kr",
        broker="미래에셋증권",
    )

    assert report is not None
    assert report.ticker == "000270"
    assert report.previous_target_price == 170000
    assert report.target_price == 300000
    assert report.target_price_change_pct == pytest.approx((300000 / 170000) - 1.0)
    assert report.raw_score == pytest.approx(0.9)


def test_reports_to_rows_returns_repository_ready_payloads():
    reports = parse_korean_research_reports(
        _HTML,
        source="mirae_kr",
        broker="미래에셋증권",
    )

    rows = reports_to_rows(reports)

    assert rows
    assert {"report_date", "ticker", "source", "raw_score", "title"} <= set(rows[0])


def test_apply_report_body_text_signal_updates_score_without_storing_body():
    report = parse_korean_research_report_text(
        "2026-05-12 삼성전자 005930 매수",
        source="mirae_kr",
        broker="미래에셋증권",
    )

    assert report is not None
    enriched = apply_report_body_text_signal(report, "수요 부진과 비용 부담으로 실적 전망 하향")

    assert enriched.title == report.title
    assert enriched.source_url == report.source_url
    assert enriched.sentiment_score == pytest.approx(-0.1)
    assert enriched.raw_score == pytest.approx(0.5)


def test_apply_report_body_text_signal_fills_missing_target_from_body():
    report = parse_korean_research_report_text(
        "2026-05-12 삼성전자 005930",
        source="mirae_kr",
        broker="미래에셋증권",
    )

    assert report is not None
    enriched = apply_report_body_text_signal(
        report,
        "투자의견 매수 유지. 목표주가 85,000원→95,000원 실적 개선",
    )

    assert enriched.rating == "Buy"
    assert enriched.previous_target_price == 85000
    assert enriched.target_price == 95000
    assert enriched.target_price_change_pct == pytest.approx((95000 / 85000) - 1.0)
    assert enriched.raw_score == pytest.approx(0.8)


def test_apply_report_body_text_signal_clamps_combined_sentiment():
    report = parse_korean_research_report_text(
        "2026-05-12 카카오 035720 매도 부진",
        source="mirae_kr",
        broker="미래에셋증권",
    )

    assert report is not None
    enriched = apply_report_body_text_signal(report, "목표주가 하향, 비용 부담, 고평가")

    assert enriched.sentiment_score == pytest.approx(-0.2)
    assert enriched.raw_score == -1.0


def test_parse_korean_research_reports_reads_miraeasset_public_js_rows():
    html = r"""
document.write('<ul class="list">');
document.write('<li><a href="/bbs/board/message/view.do?categoryId=1533&messageId=2339804">티앤알바이오팹 (145720/매수)중국에서 2차 VBP가 다시 시작된다면!</a><a href="javascript:nv.Popup.open(\'https://securities.miraeasset.com/bbs/download/2144592.pdf?attachmentId=2144592\',\'2144592\',\'1024\',\'768\',\'yes\',\'yes\');" title="새창"><img alt="pdf 첨부파일"/></a><span style="float:right;">2026.05.13</span></li>');
document.write('<li><a href="/bbs/board/message/view.do?categoryId=1533&messageId=2339797">NC (036570/중립)신작 타이밍. 기다림 필요</a><a href="javascript:nv.Popup.open(\'https://securities.miraeasset.com/bbs/download/2144582.pdf?attachmentId=2144582\',\'2144582\',\'1024\',\'768\',\'yes\',\'yes\');" title="새창"><img alt="pdf 첨부파일"/></a><span style="float:right;">2026.05.13</span></li>');
document.write('</ul>');
"""

    reports = parse_korean_research_reports(
        html,
        source="mirae_kr",
        broker="미래에셋증권",
    )

    by_ticker = {report.ticker: report for report in reports}

    assert set(by_ticker) == {"145720", "036570"}
    assert by_ticker["145720"].report_date == date(2026, 5, 13)
    assert by_ticker["145720"].rating == "Buy"
    assert by_ticker["145720"].raw_score == 0.6
    assert by_ticker["145720"].source_url == (
        "https://securities.miraeasset.com/bbs/download/2144592.pdf?attachmentId=2144592"
    )
    assert by_ticker["036570"].rating == "Hold"


def test_parse_korean_research_reports_reads_miraeasset_current_table_rows():
    html = """
<table class="bbs_linetype2">
  <tbody>
    <tr class="first">
      <td>2026-05-13</td>
      <td class="left">
        <div class="subject">
          <a href="javascript:view('2339809','803')" id="bbsTitle0">
            <b>CJ대한통운 (000120/매수)</b><br/>여전히 주목해야 할 시장 지위 확대
          </a>
        </div>
      </td>
      <td>
        <a href="javascript:downConfirm('https://securities.miraeasset.com/bbs/download/2144597.pdf?attachmentId=2144597','2144597','1024','768','yes','yes');">PDF</a>
      </td>
      <td>류제현</td>
    </tr>
  </tbody>
</table>
"""

    reports = parse_korean_research_reports(
        html,
        source="mirae_asset",
        broker="미래에셋증권",
    )

    assert len(reports) == 1
    report = reports[0]
    assert report.report_date == date(2026, 5, 13)
    assert report.ticker == "000120"
    assert report.rating == "Buy"
    assert "시장 지위 확대" in report.title
    assert report.source_url == (
        "https://securities.miraeasset.com/bbs/download/2144597.pdf?attachmentId=2144597"
    )


def test_parse_korean_research_reports_reads_hankyung_consensus_downpdf_rows():
    html = """
<table>
  <tr class="first">
    <td class="first txt_number">2026-05-14</td>
    <td>기업</td>
    <td class="text_l">
      <a href="/analysis/downpdf?report_idx=649357" target="_blank">
        HMM(011200) 1Q26 Review: 전쟁 효과는 2Q부터
      </a>
      <div class="layerPop"><strong>HMM(011200) 1Q26 Review: 전쟁 효과는 2Q부터</strong></div>
    </td>
    <td>이서연</td>
    <td>상상인증권</td>
    <td><a href="/analysis/downpdf?report_idx=649357" title="CM0079_4434_1.pdf">PDF</a></td>
  </tr>
</table>
"""

    reports = parse_korean_research_reports(
        html,
        source="hankyung_consensus",
        broker="한경 컨센서스",
        base_url="https://consensus.hankyung.com/",
    )

    assert len(reports) == 1
    report = reports[0]
    assert report.report_date == date(2026, 5, 14)
    assert report.ticker == "011200"
    assert report.broker == "상상인증권"
    assert report.title == "HMM(011200) 1Q26 Review: 전쟁 효과는 2Q부터"
    assert report.source_url == (
        "https://consensus.hankyung.com/analysis/downpdf?report_idx=649357"
    )
