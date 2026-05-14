from datetime import date

from src.signals.research_report_analysis import analyze_research_report_body
from src.signals.research_report_parser import ParsedResearchReport


def _report(raw_score: float = 0.8, rating: str = "Buy") -> ParsedResearchReport:
    return ParsedResearchReport(
        report_date=date(2026, 5, 14),
        ticker="005930",
        source="hankyung_consensus",
        region="domestic",
        broker="한경 컨센서스",
        rating=rating,
        rating_score=0.6 if rating == "Buy" else 0.0,
        target_price=95000,
        previous_target_price=85000,
        target_price_change_pct=(95000 / 85000) - 1.0,
        sentiment_score=0.2,
        raw_score=raw_score,
        title="삼성전자(005930) 실적 개선",
        source_url="https://example.test/report.pdf",
    )


def test_analyze_research_report_body_extracts_buy_and_valuation_context():
    body = """
    투자의견 매수를 유지하고 목표주가를 85,000원에서 95,000원으로 상향한다.
    AI 서버 수요 증가와 신규 고객사 확대가 성장 동력이다.
    메모리 가격 상승으로 매출과 영업이익 개선이 예상된다.
    현재 주가는 업사이드가 남아 있어 밸류에이션 부담이 낮다.
    리스크는 환율 변동과 고객사 투자 지연이다.
    """

    analysis = analyze_research_report_body(_report(), body, body_text_status="extracted")

    assert analysis.investment_opinion == "positive"
    assert "매수" in analysis.buy_thesis
    assert "수요" in analysis.growth_drivers
    assert "영업이익" in analysis.earnings_drivers
    assert "업사이드" in analysis.valuation_view
    assert "목표주가" in analysis.target_price_rationale
    assert "환율" in analysis.risk_factors
    assert analysis.confidence >= 0.7
    assert analysis.analysis_version == "rule-v1"


def test_analyze_research_report_body_extracts_negative_context():
    body = """
    투자의견 중립을 유지한다. 수요 둔화와 원가 부담이 이어지고 있다.
    목표주가를 50,000원에서 40,000원으로 하향한다.
    실적 부진과 경쟁 심화로 영업이익 회복 시점이 불확실하다.
    """

    analysis = analyze_research_report_body(
        _report(raw_score=-0.7, rating="Hold"),
        body,
        body_text_status="extracted",
    )

    assert analysis.investment_opinion == "negative"
    assert "둔화" in analysis.sell_or_risk_thesis
    assert "하향" in analysis.target_price_rationale
    assert "불확실" in analysis.risk_factors


def test_analyze_research_report_body_handles_missing_body_as_low_confidence():
    analysis = analyze_research_report_body(_report(), None, body_text_status="fetch_failed")

    assert analysis.body_text_chars == 0
    assert analysis.summary
    assert analysis.confidence < 0.5
    assert analysis.body_text_status == "fetch_failed"

