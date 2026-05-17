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


def test_analyze_research_report_body_uses_title_context_when_pdf_body_is_sparse():
    report = ParsedResearchReport(
        report_date=date(2026, 5, 14),
        ticker="000120",
        source="mirae_asset",
        region="domestic",
        broker="미래에셋증권",
        rating="Buy",
        rating_score=0.6,
        target_price=None,
        previous_target_price=None,
        target_price_change_pct=None,
        sentiment_score=None,
        raw_score=0.6,
        title="CJ대한통운 (000120/매수)여전히 주목해야 할 시장 지위 확대",
        source_url="https://example.test/report.pdf",
    )

    analysis = analyze_research_report_body(
        report,
        "Mirae Asset Securities Research 2026.5.13 시가총액 발행주식수 외국인 보유비중",
        body_text_status="extracted",
    )

    assert "시장 지위 확대" in analysis.summary
    assert "시장 지위 확대" in analysis.buy_thesis
    assert "000120/매수" not in analysis.buy_thesis
    assert analysis.investment_opinion == "positive"


def test_analyze_research_report_body_does_not_copy_positive_title_into_risk_bucket():
    report = ParsedResearchReport(
        report_date=date(2026, 5, 14),
        ticker="043150",
        source="mirae_asset",
        region="domestic",
        broker="미래에셋증권",
        rating="Buy",
        rating_score=0.6,
        target_price=None,
        previous_target_price=None,
        target_price_change_pct=None,
        sentiment_score=None,
        raw_score=0.6,
        title="바텍 (043150/매수)원가 압박 이겨내는 중",
        source_url="https://example.test/report.pdf",
    )

    analysis = analyze_research_report_body(
        report,
        "",
        body_text_status="extracted",
    )

    assert analysis.buy_thesis == "원가 압박 이겨내는 중"
    assert analysis.risk_factors == ""


def test_analyze_research_report_body_uses_buy_rating_for_title_fallback_when_raw_score_is_zero():
    report = ParsedResearchReport(
        report_date=date(2026, 5, 14),
        ticker="004170",
        source="mirae_asset",
        region="domestic",
        broker="미래에셋증권",
        rating="Buy",
        rating_score=0.6,
        target_price=None,
        previous_target_price=None,
        target_price_change_pct=None,
        sentiment_score=None,
        raw_score=0.0,
        title="신세계 (004170/매수)만점짜리 실적",
        source_url="https://example.test/report.pdf",
    )

    analysis = analyze_research_report_body(report, "", body_text_status="extracted")

    assert analysis.investment_opinion == "positive"
    assert analysis.buy_thesis == "만점짜리 실적"
    assert "만점짜리 실적" in analysis.summary


def test_analyze_research_report_body_ignores_mirae_rating_definition_boilerplate():
    body = """
    투자의견 '매수' 유지, 목표주가 400,000원으로 상향.
    리니지 클래식 매출 호조를 반영한 26F 실적 조정으로 목표주가를 280,000원에서 400,000원으로 상향한다.
    매수 : 향후 12개월 기준 절대수익률 20% 이상의 초과수익 예상 비중확대 : 향후 12개월 기준 업종지수상승률이 시장수익률 대비 높거나 상승.
    지표준수주주행동 매출원가 0 0 0 0 현금 및 현금성자산 504 1,292 1,730 2,146.
    """

    analysis = analyze_research_report_body(
        _report(),
        body,
        body_text_status="extracted",
    )

    assert "절대수익률 20%" not in analysis.buy_thesis
    assert "현금 및 현금성자산" not in analysis.risk_factors
    assert "목표주가 400,000원으로 상향" in analysis.summary
def test_analyze_research_report_body_ignores_display_noise_rows():
    body = """
    Analyst Name 02-1234-5678 E-mail analyst@example.com
    투자등급 매수 중립(보유) 매도 유니버스 투자등급 비율
    매출액 1,000 2,000 3,000 4,000 5,000 영업이익 100 200 300
    AI 서버 수요 확대로 고부가 제품 판매가 증가하고 있다.
    환율 변동과 원가 부담은 단기 리스크로 남아 있다.
    """

    analysis = analyze_research_report_body(
        _report(),
        body,
        body_text_status="extracted",
    )

    combined = " ".join(
        [
            analysis.summary,
            analysis.buy_thesis,
            analysis.growth_drivers,
            analysis.earnings_drivers,
            analysis.risk_factors,
            analysis.sell_or_risk_thesis,
        ]
    )

    assert "analyst@example.com" not in combined
    assert "투자등급 매수 중립" not in combined
    assert "매출액 1,000 2,000" not in combined
    assert "AI 서버 수요" in combined
