from datetime import date

from src.signals.busanstock_parser import parse_busanstock_report


_HTML = """
<html>
<head><title>트비 주식뉴스 어그리게이터 리포트 · 2026-05-09</title></head>
<body>
<h3>종목 한눈에 · STOCK SNAPSHOT</h3>
<p>총 4종 · 매수 2 / 매도·경고 1 / 관찰 1</p>
<p>매수 (2) 기아 · 현대차</p>
<p>매도·경고 (1) 카카오</p>
<p>관찰 (1) 삼성전자</p>
<h3>컨센서스 변경 · TP 변동률 시각화</h3>
<p>▲ TP 상향 (UPGRADES) · 2건</p>
<p>기아 유진 17만→30만 ▲76%</p>
<p>현대차 유진 60만→100만 ▲67%</p>
<p>▼ TP 하향 (DOWNGRADES) · 1건</p>
<p>카카오게임즈 미래 2.6만→1.9만 ▼27%</p>
</body>
</html>
"""


def test_parse_busanstock_report_extracts_snapshot_and_consensus_signals():
    signals = parse_busanstock_report(
        _HTML,
        ticker_by_name={
            "기아": "000270",
            "현대차": "005380",
            "카카오": "035720",
            "카카오게임즈": "293490",
            "삼성전자": "005930",
        },
    )

    rows = {(signal.ticker, signal.source_section): signal for signal in signals}

    assert rows[("000270", "stock_snapshot")].raw_score == 0.3
    assert rows[("005380", "stock_snapshot")].raw_score == 0.3
    assert rows[("035720", "stock_snapshot")].raw_score == -0.7
    assert rows[("000270", "consensus")].raw_score == 0.7
    assert rows[("005380", "consensus")].raw_score == 0.7
    assert rows[("293490", "consensus")].raw_score == -0.7
    assert "005930" not in {signal.ticker for signal in signals}


def test_parse_busanstock_report_uses_title_date_when_date_not_passed():
    signals = parse_busanstock_report(_HTML, ticker_by_name={"기아": "000270"})

    assert signals
    assert all(signal.signal_date == date(2026, 5, 9) for signal in signals)


def test_parse_busanstock_report_reads_report_html_classes():
    html = """
<html><head><title>리포트 · 2026-05-09</title></head><body>
<div class="snapshot-grid buy">
  <div class="label">매수<br><strong>(2)</strong></div>
  <div class="content"><span class="stock"><strong>기아</strong></span> · <span class="stock"><strong>현대차</strong></span></div>
</div>
<div class="snapshot-grid sell">
  <div class="label">매도·경고<br><strong>(1)</strong></div>
  <div class="content"><span class="stock"><strong>카카오</strong></span></div>
</div>
<div class="tp-bar-row">
  <div class="name">기아</div><div class="house">유진</div>
  <div class="bar-track"><div class="bar-fill up">17만→30만</div></div>
  <div class="pct up">▲76%</div>
</div>
<div class="tp-bar-row">
  <div class="name">카카오게임즈</div><div class="house">미래</div>
  <div class="bar-track"><div class="bar-fill down">2.6만→1.9만</div></div>
  <div class="pct down">▼27%</div>
</div>
</body></html>
"""

    signals = parse_busanstock_report(
        html,
        ticker_by_name={
            "기아": "000270",
            "현대차": "005380",
            "카카오": "035720",
            "카카오게임즈": "293490",
        },
    )

    rows = {(signal.ticker, signal.source_section): signal for signal in signals}
    assert rows[("000270", "stock_snapshot")].raw_score == 0.3
    assert rows[("005380", "stock_snapshot")].raw_score == 0.3
    assert rows[("035720", "stock_snapshot")].raw_score == -0.7
    assert rows[("000270", "consensus")].raw_score == 0.7
    assert rows[("293490", "consensus")].raw_score == -0.7
