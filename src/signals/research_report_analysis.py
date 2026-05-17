from __future__ import annotations

import re
from dataclasses import dataclass

from src.signals.research_report_parser import ParsedResearchReport


@dataclass(frozen=True)
class ResearchReportBodyAnalysis:
    body_text_status: str
    body_text_chars: int
    summary: str
    investment_opinion: str
    buy_thesis: str
    sell_or_risk_thesis: str
    growth_drivers: str
    earnings_drivers: str
    valuation_view: str
    target_price_rationale: str
    risk_factors: str
    evidence_terms: str
    analysis_version: str
    confidence: float


_SENTENCE_RE = re.compile(r"(?<=[.!?。])\s+|(?<=다\.)\s+|\n+")
_SPACE_RE = re.compile(r"\s+")

_BUCKET_KEYWORDS: dict[str, tuple[str, ...]] = {
    "buy_thesis": (
        "매수",
        "상향",
        "개선",
        "성장",
        "저평가",
        "수혜",
        "회복",
        "확대",
        "호조",
        "증가",
        "긍정",
    ),
    "sell_or_risk_thesis": (
        "매도",
        "중립",
        "하향",
        "부진",
        "둔화",
        "고평가",
        "부담",
        "리스크",
        "불확실",
        "감소",
        "적자",
        "보수적",
    ),
    "growth_drivers": (
        "수요",
        "수주",
        "신규",
        "시장",
        "점유율",
        "CAPA",
        "증설",
        "출하",
        "해외",
        "고객사",
        "제품",
    ),
    "earnings_drivers": (
        "실적",
        "매출",
        "영업이익",
        "이익",
        "마진",
        "원가",
        "비용",
        "EPS",
        "수익성",
        "흑자",
    ),
    "valuation_view": (
        "밸류에이션",
        "PER",
        "PBR",
        "멀티플",
        "저평가",
        "고평가",
        "상승여력",
        "업사이드",
        "주가",
    ),
    "target_price_rationale": (
        "목표주가",
        "목표가",
        "TP",
        "상향",
        "하향",
        "유지",
        "할인율",
        "추정치",
    ),
    "risk_factors": (
        "risk",
        "uncertainty",
        "execution speed",
        "recovery timing",
        "리스크",
        "위험",
        "불확실",
        "경쟁",
        "환율",
        "금리",
        "규제",
        "원가",
        "지연",
        "둔화",
        "부담",
    ),
}


def analyze_research_report_body(
    report: ParsedResearchReport,
    body_text: str | None,
    *,
    body_text_status: str,
) -> ResearchReportBodyAnalysis:
    raw_text = body_text or ""
    normalized = _normalize(raw_text)
    sentences = _split_sentences(raw_text)
    buckets = {name: _best_sentences(sentences, keywords) for name, keywords in _BUCKET_KEYWORDS.items()}
    buckets = _apply_title_context(report, buckets)
    opinion = _infer_opinion(report, buckets)
    summary = _build_summary(report, buckets, opinion)
    evidence_terms = _evidence_terms(normalized, buckets)
    confidence = _confidence(report, normalized, buckets, body_text_status)
    return ResearchReportBodyAnalysis(
        body_text_status=body_text_status,
        body_text_chars=len(normalized),
        summary=summary,
        investment_opinion=opinion,
        buy_thesis=buckets["buy_thesis"],
        sell_or_risk_thesis=buckets["sell_or_risk_thesis"],
        growth_drivers=buckets["growth_drivers"],
        earnings_drivers=buckets["earnings_drivers"],
        valuation_view=buckets["valuation_view"],
        target_price_rationale=buckets["target_price_rationale"],
        risk_factors=buckets["risk_factors"],
        evidence_terms=evidence_terms,
        analysis_version="rule-v1",
        confidence=confidence,
    )


def _normalize(text: str) -> str:
    return _SPACE_RE.sub(" ", text).strip()


def _split_sentences(text: str) -> list[str]:
    if not text:
        return []
    rough = _SENTENCE_RE.split(text)
    sentences = []
    for sentence in rough:
        cleaned = _normalize(sentence).strip(" -•\t")
        if len(cleaned) < 8 or _is_report_boilerplate(cleaned):
            continue
        sentences.append(_shorten(cleaned, limit=320))
    return sentences


def _best_sentences(sentences: list[str], keywords: tuple[str, ...]) -> str:
    scored: list[tuple[int, int, str]] = []
    for index, sentence in enumerate(sentences):
        lowered = sentence.lower()
        score = sum(1 for keyword in keywords if keyword.lower() in lowered)
        if score:
            scored.append((score, -index, sentence))
    scored.sort(reverse=True)
    selected = [sentence for _, _, sentence in scored[:2]]
    return " / ".join(selected)


def _infer_opinion(report: ParsedResearchReport, buckets: dict[str, str]) -> str:
    if report.raw_score >= 0.35:
        return "positive"
    if report.raw_score <= -0.35:
        return "negative"
    if report.rating_score is not None and report.rating_score > 0:
        return "positive"
    if report.rating_score is not None and report.rating_score < 0:
        return "negative"
    has_positive = bool(buckets["buy_thesis"])
    has_negative = bool(buckets["sell_or_risk_thesis"] or buckets["risk_factors"])
    if has_positive and has_negative:
        return "mixed"
    if has_positive:
        return "positive"
    if has_negative:
        return "negative"
    if report.rating_score == 0.0:
        return "neutral"
    return "unknown"


def _build_summary(
    report: ParsedResearchReport,
    buckets: dict[str, str],
    opinion: str,
) -> str:
    thesis = buckets["buy_thesis"] or buckets["sell_or_risk_thesis"] or buckets["earnings_drivers"]
    if thesis:
        return _shorten(
            f"{report.ticker} 리포트는 {opinion} 관점으로 해석됩니다. 핵심 근거: {thesis}",
            limit=520,
        )
    if report.rating:
        return f"{report.ticker} 리포트는 투자의견 {report.rating}을 제시했지만 본문 근거 추출은 제한적입니다."
    return f"{report.ticker} 리포트의 본문 근거 추출이 제한적입니다."


def _shorten(text: str, *, limit: int) -> str:
    cleaned = _normalize(text)
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"


def _is_report_boilerplate(sentence: str) -> bool:
    lowered = sentence.lower()
    boilerplate_terms = (
        "mirae asset securities research",
        "equity research",
        "향후 12개월 기준",
        "절대수익률 20%",
        "비중확대 :",
        "지표준수주주행동",
        "시가총액",
        "발행주식수",
        "외국인 보유비중",
        "현금 및 현금성자산",
        "자료:",
        "결산기",
    )
    extra_boilerplate_terms = (
        "Company Brief",
        "Issue Comment",
        "투자등급",
        "매수 중립",
        "중립(보유) 매도",
        "Underperform",
        "Neutral(중립)",
        "유니버스 투자등급",
        "본 자료에 수록된",
        "영업이익/금융비용",
        "매출원가율",
        "수정주가",
        "12MF PER",
        "12MF PBR",
        "E-mail",
        "@",
        "\uf06e",
    )
    if any(term in lowered for term in boilerplate_terms) or any(
        term.lower() in lowered for term in extra_boilerplate_terms
    ):
        return True
    numeric_tokens = re.findall(r"\d[\d,]*(?:\.\d+)?", sentence)
    table_terms = ("매출액", "영업이익", "매출원가", "영업이익률", "PER", "PBR")
    if len(numeric_tokens) >= 5 and any(term in sentence for term in table_terms):
        return True
    return len(numeric_tokens) >= 8


def _apply_title_context(
    report: ParsedResearchReport,
    buckets: dict[str, str],
) -> dict[str, str]:
    context = _title_context(report.title)
    if not context:
        return buckets
    updated = dict(buckets)
    positive_view = report.raw_score > 0 or (report.rating_score is not None and report.rating_score > 0)
    negative_view = report.raw_score < 0 or (report.rating_score is not None and report.rating_score < 0)
    if positive_view and not updated["buy_thesis"]:
        updated["buy_thesis"] = context
    elif negative_view and not updated["sell_or_risk_thesis"]:
        updated["sell_or_risk_thesis"] = context
    for bucket_name, keywords in _BUCKET_KEYWORDS.items():
        if updated[bucket_name]:
            continue
        if positive_view and bucket_name in {"sell_or_risk_thesis", "risk_factors"}:
            continue
        if negative_view and bucket_name == "buy_thesis":
            continue
        lowered = context.lower()
        if any(keyword.lower() in lowered for keyword in keywords):
            updated[bucket_name] = context
    return updated


def _title_context(title: str) -> str:
    cleaned = _normalize(title)
    cleaned = re.sub(r"^.*?\(\d{6}/[^)]*\)", "", cleaned).strip()
    cleaned = cleaned.strip(" :-")
    if len(cleaned) < 4:
        return ""
    return _shorten(cleaned, limit=180)


def _evidence_terms(text: str, buckets: dict[str, str]) -> str:
    found = []
    for keywords in _BUCKET_KEYWORDS.values():
        for keyword in keywords:
            if keyword.lower() in text.lower() and keyword not in found:
                found.append(keyword)
    if not found:
        for value in buckets.values():
            if value:
                found.extend(value.split()[:3])
                break
    return ", ".join(found[:12])


def _confidence(
    report: ParsedResearchReport,
    text: str,
    buckets: dict[str, str],
    body_text_status: str,
) -> float:
    score = 0.15
    if body_text_status == "extracted":
        score += 0.35
    if len(text) >= 500:
        score += 0.15
    elif len(text) >= 100:
        score += 0.08
    if report.rating is not None:
        score += 0.1
    if report.target_price is not None or report.target_price_change_pct is not None:
        score += 0.1
    covered_buckets = sum(1 for value in buckets.values() if value)
    score += min(0.15, covered_buckets * 0.03)
    return round(max(0.0, min(1.0, score)), 3)
