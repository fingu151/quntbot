from datetime import date

from src.signals.research_report_analysis import analyze_research_report_body
from src.signals.research_report_briefing import (
    build_research_report_briefing,
    clean_research_report_text,
)
from src.signals.research_report_parser import ParsedResearchReport


def _report() -> ParsedResearchReport:
    return ParsedResearchReport(
        report_date=date(2026, 5, 14),
        ticker="005930",
        source="hankyung_consensus",
        region="domestic",
        broker="Hankyung",
        rating="Buy",
        rating_score=0.6,
        target_price=95000,
        previous_target_price=90000,
        target_price_change_pct=0.055,
        sentiment_score=0.2,
        raw_score=0.8,
        title="Samsung Electronics AI memory upcycle",
        source_url="https://example.test/report.pdf",
    )


def test_build_research_report_briefing_extracts_sections_from_body_text():
    body = """
    Analyst E-mail analyst@example.com
    삼성전자는 AI 서버 수요 확대로 HBM 판매가 증가하고 있다.
    1Q26 매출액은 증가했고 영업이익률은 개선됐다.
    신규 패키징 증설과 고객사 확대가 중장기 성장 동력이다.
    목표주가 95,000원을 유지하며 밸류에이션 부담은 제한적이다.
    환율 변동과 메모리 가격 하락은 리스크다.
    """
    report = _report()
    analysis = analyze_research_report_body(report, body, body_text_status="extracted")

    brief = build_research_report_briefing(report, body, analysis)

    assert brief.brief_version == "brief-rule-v3"
    assert brief.source_quality in {"partial_text", "full_text"}
    assert brief.headline.startswith("005930:")
    assert "AI" in (brief.stock_view + brief.industry + brief.new_business)
    assert "매출액" in brief.earnings
    assert "목표주가" in brief.valuation
    assert "리스크" in brief.risks
    assert "E-mail" not in brief.headline


def test_clean_research_report_text_removes_common_disclaimer_noise():
    cleaned = clean_research_report_text(
        "Compliance Notice\n"
        "Analyst E-mail analyst@example.com\n"
        "핵심 문장은 남아야 한다."
    )

    assert "Compliance" not in cleaned
    assert "E-mail" not in cleaned
    assert "핵심 문장" in cleaned


def test_clean_research_report_text_normalizes_pdf_hangul_separator_artifact():
    cleaned = clean_research_report_text("판매ᆍ공급지역 확대와 수익성 개선이 기대된다.")

    assert "ᆍ" not in cleaned
    assert "판매 공급지역 확대" in cleaned


def test_build_research_report_briefing_v2_uses_distinct_section_sentences():
    body = """
    투자등급 매수 중립(보유) 매도
    삼성전자는 AI 서버 수요 확대로 HBM 판매가 증가하고 있다.
    1Q26 매출액은 전년 대비 증가했고 영업이익률도 개선됐다.
    신규 패키징 증설과 고객사 확대가 중장기 성장 동력이다.
    목표주가 95,000원을 유지하며 밸류에이션 부담은 제한적이다.
    환율 변동과 메모리 가격 하락은 단기 리스크다.
    """
    report = _report()
    analysis = analyze_research_report_body(report, body, body_text_status="extracted")

    brief = build_research_report_briefing(report, body, analysis)

    assert brief.brief_version == "brief-rule-v3"
    assert "HBM 판매" in brief.industry or "HBM 판매" in brief.stock_view
    assert "신규 패키징" in brief.new_business
    assert "매출액" in brief.earnings
    assert "목표주가 95,000원" in brief.valuation
    assert "리스크" in brief.risks
    assert len(
        {
            brief.stock_view,
            brief.earnings,
            brief.industry,
            brief.new_business,
            brief.valuation,
            brief.risks,
        }
        - {""}
    ) >= 5


def test_build_research_report_briefing_v2_rejects_tables_disclaimers_and_cut_fragments():
    body = """
    Company Brief Analyst E-mail analyst@example.com
    투자등급 매수 중립(보유) 매도 유니버스 투자등급 비율
    매출액 1,000 2,000 3,000 4,000 5,000 영업이익 100 200 300
    인한 비용 증가가 단기적으로 부담으로 작용
    AI 서버 수요 확대로 고부가 제품 판매가 증가하고 있다.
    원가 부담과 환율 변동은 실적 변동성을 키울 수 있다.
    """
    report = _report()
    analysis = analyze_research_report_body(report, body, body_text_status="extracted")

    brief = build_research_report_briefing(report, body, analysis)
    combined = " ".join(
        [
            brief.headline,
            brief.stock_view,
            brief.earnings,
            brief.industry,
            brief.new_business,
            brief.valuation,
            brief.risks,
        ]
    )

    assert "analyst@example.com" not in combined
    assert "투자등급 매수" not in combined
    assert "매출액 1,000 2,000" not in combined
    assert "인한 비용 증가" not in combined
    assert "AI 서버 수요" in combined
    assert "환율 변동" in combined


def test_build_research_report_briefing_v2_rejects_web_headers_and_rating_policy_rows():
    body = """
    Company 절대수익률 기준 Buy (매수) +15% 이상 기대 89.3%
    기업분석 2026.05.14 www.daishin.com
    주요 차종 판매 호조로 외형 성장과 Mix 개선이 지속되고 있다.
    미국 현지생산 확대에 따른 관세 영향 축소가 기대된다.
    타이트한 비용관리 능력으
    """
    report = _report()
    analysis = analyze_research_report_body(report, body, body_text_status="extracted")

    brief = build_research_report_briefing(report, body, analysis)
    combined = " ".join(
        [
            brief.headline,
            brief.stock_view,
            brief.industry,
            brief.new_business,
            brief.risks,
        ]
    )

    assert "절대수익률 기준" not in combined
    assert "www.daishin.com" not in combined
    assert "기업분석" not in combined
    assert "능력으" not in combined
    assert "주요 차종 판매 호조" in combined


def test_build_research_report_briefing_v2_rejects_cover_date_author_and_tail_particles():
    body = """
    2024.01.09 신규 이재혁
    투자의견 Buy를 유지하고 목표주가를 기존 190,000원에서
    고, 높은 광고성 비용이 인식될 전망이나 이는 매출 증가를 통해 상쇄 가능한 수준.
    밀양2공장은 증설 효과가 점진적으로 반영되고 있다.
    공장 채용 확대에 따른 제조 인건비 증가도 원가 부담 요인으로 작용한다.
    """
    report = _report()
    analysis = analyze_research_report_body(report, body, body_text_status="extracted")

    brief = build_research_report_briefing(report, body, analysis)
    combined = " ".join(
        [
            brief.headline,
            brief.stock_view,
            brief.earnings,
            brief.industry,
            brief.new_business,
            brief.valuation,
            brief.risks,
        ]
    )

    assert "신규 이재혁" not in combined
    assert "기존 190,000원에서" not in combined
    assert "고, 높은" not in combined
    assert "밀양2공장" in combined
    assert "원가 부담" in combined


def test_build_research_report_briefing_v2_rejects_rating_definition_headlines():
    body = """
    Buy(매수): 추천일 종가대비 +15% 이상
    W&D 견조한 신규 수주(+34% YoY)에도 음식료
    CJ대한통운은 택배 물동량 증가와 글로벌 신규 수주로 이익 개선이 기대된다.
    배송 고도화를 위해 초기 비용이 집행 중이나 중장기 효율화가 예상된다.
    """
    report = _report()
    analysis = analyze_research_report_body(report, body, body_text_status="extracted")

    brief = build_research_report_briefing(report, body, analysis)
    combined = " ".join(
        [
            brief.headline,
            brief.stock_view,
            brief.earnings,
            brief.industry,
            brief.new_business,
            brief.risks,
        ]
    )

    assert "추천일 종가대비" not in combined
    assert "W&D 견조한 신규 수주" not in combined
    assert "택배 물동량 증가" in combined
    assert "초기 비용" in combined


def test_build_research_report_briefing_v2_rejects_policy_paragraphs_and_pdf_shards():
    body = """
    당사는 개별 종목에 대해 향후 1 년간 +15% 이상의 절대수익률이 기대되는 종목에 대해 Buy(매수) 의견을 제시합니다.
    일/폴란드 중심의 큰 폭 성장과 프랑스 채널 입점 확대
    스 제품은 글로벌 AI 반도체 기업의 가속기용 반도체패키지다.
    경쟁 빅테크 기업들의 패키지 기술도 해당 레퍼런스를
    해외 매출 비중 확대와 증설 효과가 실적 개선을 이끌 전망이다.
    원가 부담은 남아 있으나 가격 전가력으로 방어 가능하다.
    """
    report = _report()
    analysis = analyze_research_report_body(report, body, body_text_status="extracted")

    brief = build_research_report_briefing(report, body, analysis)
    combined = " ".join(
        [
            brief.headline,
            brief.stock_view,
            brief.earnings,
            brief.industry,
            brief.new_business,
            brief.risks,
        ]
    )

    assert "당사는 개별 종목" not in combined
    assert "일/폴란드" not in combined
    assert "스 제품은" not in combined
    assert "해당 레퍼런스를" not in combined
    assert "해외 매출 비중 확대" in combined
    assert "원가 부담" in combined


def test_build_research_report_briefing_v2_rejects_rating_labels_and_short_tails():
    body = """
    Buy (Maintain)
    익률 -15~+15%가 예상되는 종목에 대해 Hold(보유) 의견을, -15% 이하가 예상되는 종목에 대해 Sell(매도) 의견을 제시합니다.
    불확실성이 낮아졌고, 동사의 제품군
    AI 고객의 대규모 투자지원과 기판 확보 수요가 확대되고 있다.
    경쟁 불확실성은 낮아졌으나 고객사 투자 속도는 리스크다.
    """
    report = _report()
    analysis = analyze_research_report_body(report, body, body_text_status="extracted")

    brief = build_research_report_briefing(report, body, analysis)
    combined = " ".join(
        [
            brief.headline,
            brief.stock_view,
            brief.earnings,
            brief.industry,
            brief.new_business,
            brief.risks,
        ]
    )

    assert "Buy (Maintain)" not in combined
    assert "Hold(보유) 의견" not in combined
    assert "Sell(매도) 의견" not in combined
    assert "동사의 제품군" not in combined
    assert "기판 확보 수요" in combined
    assert "리스크" in combined


def test_build_research_report_briefing_v3_filters_entire_rating_policy_block():
    body = """
    투자등급 정의
    Buy(매수): 추천일 종가대비 +15% 이상
    Hold(보유) 의견은 -15~+15%가 예상되는 종목에 대해 제시합니다.
    Sell(매도) 의견은 -15% 이하가 예상되는 종목에 대해 제시합니다.

    투자포인트
    AI 서버 수요 확대와 HBM 고객사 확대가 핵심 성장 동력이다.
    """
    report = _report()
    analysis = analyze_research_report_body(report, body, body_text_status="extracted")

    brief = build_research_report_briefing(report, body, analysis)
    combined = " ".join(
        [
            brief.headline,
            brief.stock_view,
            brief.industry,
            brief.new_business,
            brief.risks,
        ]
    )

    assert brief.brief_version == "brief-rule-v3"
    assert "추천일 종가대비" not in combined
    assert "Hold(보유) 의견" not in combined
    assert "Sell(매도) 의견" not in combined
    assert "AI 서버 수요 확대" in combined


def test_build_research_report_briefing_v3_filters_multi_line_financial_table_block():
    body = """
    실적표
    매출액 1,000 2,000 3,000
    영업이익 100 200 300
    EPS 10 20 30

    실적 전망
    고부가 제품 비중 상승으로 수익성 개선이 예상된다.
    """
    report = _report()
    analysis = analyze_research_report_body(report, body, body_text_status="extracted")

    brief = build_research_report_briefing(report, body, analysis)
    combined = " ".join(
        [
            brief.headline,
            brief.earnings,
            brief.industry,
            brief.new_business,
        ]
    )

    assert "매출액 1,000" not in combined
    assert "영업이익 100" not in combined
    assert "EPS 10" not in combined
    assert "수익성 개선" in combined


def test_build_research_report_briefing_v3_keeps_valid_multi_sentence_business_block():
    body = """
    투자포인트
    신규 패키징 증설과 AI 고객사 확대가 중장기 성장 동력이다.
    원가 부담과 고객사 투자 지연은 리스크로 남아 있다.
    """
    report = _report()
    analysis = analyze_research_report_body(report, body, body_text_status="extracted")

    brief = build_research_report_briefing(report, body, analysis)

    assert "신규 패키징 증설" in brief.new_business
    assert "투자 지연" in brief.risks


def test_build_research_report_briefing_v3_rejects_real_financial_table_and_chart_noise():
    body = """
    판매비 및 관리비 856 844 862 889 922
    계속사업법인세비용 110 71 86 98 109
    운전자본감소(증가) -319 -707 -445 -309 -291 수익성 (%)
    삼성전기 투자자별 누적순매수 추이 (23.01.02~)

    택배 물동량 증가와 글로벌 신규 수주로 이익 개선이 기대된다.
    고객사 투자 확대와 기판 수요 증가가 성장 동력이다.
    원가 부담은 리스크다.
    """
    report = _report()
    analysis = analyze_research_report_body(report, body, body_text_status="extracted")

    brief = build_research_report_briefing(report, body, analysis)
    combined = " ".join(
        [
            brief.headline,
            brief.stock_view,
            brief.earnings,
            brief.industry,
            brief.new_business,
            brief.valuation,
            brief.risks,
        ]
    )

    assert "판매비 및 관리비" not in combined
    assert "계속사업법인세비용" not in combined
    assert "운전자본감소" not in combined
    assert "누적순매수 추이" not in combined
    assert "이익 개선" in combined
    assert "성장 동력" in combined
    assert "리스크" in combined


def test_build_research_report_briefing_v3_rejects_real_rating_history_and_short_tails():
    body = """
    Strong Buy(매수) 0
    2024.07.26 Buy 800,000 -20.3 -33.1
    투자의견 Buy Buy Buy Buy Buy Buy
    신규추정 기존추정 변동률
    견조한 수요를 바탕으로 해외 현지

    고부가 제품 비중 확대와 해외 고객 수요 증가로 실적 개선이 예상된다.
    단기 비용 증가는 수익성 부담으로 작용할 수 있다.
    """
    report = _report()
    analysis = analyze_research_report_body(report, body, body_text_status="extracted")

    brief = build_research_report_briefing(report, body, analysis)
    combined = " ".join(
        [
            brief.headline,
            brief.stock_view,
            brief.earnings,
            brief.industry,
            brief.new_business,
            brief.valuation,
            brief.risks,
        ]
    )

    assert "Strong Buy(매수) 0" not in combined
    assert "2024.07.26 Buy" not in combined
    assert "투자의견 Buy Buy" not in combined
    assert "신규추정 기존추정 변동률" not in combined
    assert "해외 현지" not in combined
    assert "실적 개선" in combined
    assert "수익성 부담" in combined


def test_build_research_report_briefing_v3_rejects_chart_table_titles_and_metric_lists():
    body = """
    [표1] 삼양식품 분기 및 연간 실적 추정 (단위: 십억원)
    CJ대한통운 1Q26P 영업실적 및 컨센서스 비교
    LG전자운반비(물류비)(좌축) 운임지수(SCFI)(우축)(십억원)
    PER 비교 EV/EBITDA 비교 PBR 비교
    호텔신라 PER 밴드 차트 호텔신라 PBR 밴드 차트

    라면 수출 증가와 고마진 제품 비중 확대로 영업이익 개선이 예상된다.
    물류비 부담은 단기 수익성 리스크로 남아 있다.
    """
    report = _report()
    analysis = analyze_research_report_body(report, body, body_text_status="extracted")

    brief = build_research_report_briefing(report, body, analysis)
    combined = " ".join(
        [
            brief.headline,
            brief.stock_view,
            brief.earnings,
            brief.industry,
            brief.new_business,
            brief.valuation,
            brief.risks,
        ]
    )

    assert "[표1]" not in combined
    assert "컨센서스 비교" not in combined
    assert "좌축" not in combined
    assert "PER 비교 EV/EBITDA" not in combined
    assert "밴드 차트" not in combined
    assert "영업이익 개선" in combined
    assert "수익성 리스크" in combined
def test_build_research_report_briefing_rejects_korean_mid_sentence_fragments():
    body = """
    으며, 3년 누적 기준 JSW가 플라시보 대비 -0.15mm 개선되었다.
    삼일제약은 안과 치료제 매출 확대와 신규 수주 논의로 실적 정상화가 기대된다.
    목표주가 상향은 수익성 개선과 파이프라인 가치 재평가를 반영한다.
    원가 상승과 임상 일정 지연은 단기 리스크로 점검할 필요가 있다.
    """
    base = _report()
    report = ParsedResearchReport(
        report_date=base.report_date,
        ticker="000520",
        source=base.source,
        region=base.region,
        broker=base.broker,
        rating=base.rating,
        rating_score=base.rating_score,
        target_price=base.target_price,
        previous_target_price=base.previous_target_price,
        target_price_change_pct=base.target_price_change_pct,
        sentiment_score=base.sentiment_score,
        raw_score=base.raw_score,
        title="삼일제약 실적 정상화",
        source_url=base.source_url,
    )
    analysis = analyze_research_report_body(report, body, body_text_status="extracted")

    brief = build_research_report_briefing(report, body, analysis)
    combined = " ".join([brief.headline, brief.stock_view, brief.valuation])

    assert "으며, 3년 누적" not in combined
    assert "실적 정상화" in combined


def test_build_research_report_briefing_rejects_yoy_fragments_table_titles_and_tail_particles():
    body = """
    YoY)가 고르게 성장하며 전년 대비 전체 매출이 7.2% 성장했다.
    동아쏘시오홀딩스 투자의견 및 목표주가 변동추이
    속된 가운데, 올해 3월 긍정적인 래깅 효과가 발생한 점이 실적 개선의 주요 배경으로
    에스티젠바이오는 글로벌 상업화 물량과 신규 수주 매출로 실적 성장이 기대된다.
    Kraton의 EBITDA 개선을 고려하여 목표주가를 상향 조정한다.
    원재료 가격과 환율 변동은 단기 수익성 리스크로 점검할 필요가 있다.
    """
    base = _report()
    report = ParsedResearchReport(
        report_date=base.report_date,
        ticker="000640",
        source=base.source,
        region=base.region,
        broker=base.broker,
        rating=base.rating,
        rating_score=base.rating_score,
        target_price=base.target_price,
        previous_target_price=base.previous_target_price,
        target_price_change_pct=base.target_price_change_pct,
        sentiment_score=base.sentiment_score,
        raw_score=base.raw_score,
        title="동아쏘시오홀딩스 자회사 성장 기대",
        source_url=base.source_url,
    )
    analysis = analyze_research_report_body(report, body, body_text_status="extracted")

    brief = build_research_report_briefing(report, body, analysis)
    combined = " ".join(
        [
            brief.headline,
            brief.stock_view,
            brief.earnings,
            brief.industry,
            brief.new_business,
            brief.valuation,
            brief.risks,
        ]
    )

    assert "YoY)가 고르게" not in combined
    assert "투자의견 및 목표주가 변동추이" not in combined
    assert "주요 배경으로" not in combined
    assert "실적 성장이 기대된다" in combined
    assert "목표주가를 상향 조정한다" in combined
