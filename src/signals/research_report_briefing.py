from __future__ import annotations

import re
from dataclasses import dataclass

from src.signals.research_report_analysis import ResearchReportBodyAnalysis
from src.signals.research_report_parser import ParsedResearchReport


@dataclass(frozen=True)
class ResearchReportBriefing:
    report_type: str
    headline: str
    opinion: str
    stock_view: str
    earnings: str
    industry: str
    new_business: str
    valuation: str
    risks: str
    source_quality: str
    brief_version: str
    confidence: float


_SPACE_RE = re.compile(r"\s+")
_SENTENCE_BOUNDARY_RE = re.compile(
    r"\n+|(?<=[.!?。])\s+|(?<=다\.)\s+|(?<=요\.)\s+|(?<=임\.)\s+|(?<=음\.)\s+|(?<=됨\.)\s+|(?<=함\.)\s+"
)
_NOISE_TERMS = (
    "Compliance",
    "Company Brief",
    "Issue Comment",
    "E-mail",
    "@",
    "투자등급",
    "매수 중립",
    "중립(보유) 매도",
    "유니버스 투자등급",
    "본 자료에 수록된",
    "영업이익/금융비용",
    "Mirae Asset Securities Research",
    "Equity Research",
    "절대수익률 기준",
    "기업분석",
    "www.",
    ".com",
    "Underperform",
    "Neutral(중립)",
    "추천일 종가대비",
    "Buy(매수):",
    "Buy (Maintain)",
    "Buy(Maintain)",
    "Sell(매도):",
    "Hold(중립):",
    "Hold(보유) 의견",
    "Sell(매도) 의견",
    "예상되는 종목",
    "당사는 개별 종목",
    "절대수익률이 기대",
    "Buy(매수) 의견",
    "12MF PER",
    "12MF PBR",
    "투자의견 및 목표주가 변동추이",
    "그림",
    "자료:",
    "판매비 및 관리비",
    "계속사업법인세비용",
    "운전자본감소",
    "수익성 (%)",
    "신규추정 기존추정 변동률",
    "투자의견 Buy Buy",
    "투자자별 누적순매수",
    "누적순매수 추이",
    "Strong Buy(매수) 0",
    "컨센서스 비교",
    "좌축",
    "우축",
    "PER 밴드 차트",
    "PBR 밴드 차트",
)
_TABLE_TERMS = ("매출액", "영업이익", "매출원가", "영업이익률", "PER", "PBR", "EPS")
_ACCOUNTING_ROW_TERMS = (
    "판매비",
    "관리비",
    "법인세",
    "운전자본",
    "수익성",
    "감가상각",
    "순차입금",
    "부채비율",
)
_REPORT_TYPE_KEYWORDS = {
    "earnings_review": ("Review", "리뷰", "1Q", "2Q", "3Q", "4Q", "실적", "매출", "영업이익", "마진"),
    "industry_outlook": ("업황", "산업", "수요", "공급", "가격", "시장", "해운", "반도체", "ASP"),
    "new_business": ("신사업", "신규", "수주", "AI", "전기차", "증설", "해외", "CAPA", "패키징"),
    "valuation": ("목표주가", "목표가", "밸류", "valuation", "PER", "PBR", "상향", "하향"),
}
_SECTION_KEYWORDS = {
    "stock_view": (
        "매수",
        "Buy",
        "긍정",
        "유지",
        "상향",
        "호조",
        "개선",
        "성장",
        "경쟁력",
        "판매",
    ),
    "earnings": (
        "실적",
        "매출",
        "영업이익",
        "영업이익률",
        "마진",
        "OPM",
        "EPS",
        "이익",
        "수익성",
        "컨센서스",
    ),
    "industry": (
        "업황",
        "수요",
        "공급",
        "가격",
        "시장",
        "점유율",
        "운임",
        "ASP",
        "재고",
        "판매",
    ),
    "new_business": (
        "신사업",
        "신규",
        "수주",
        "AI",
        "전기차",
        "해외",
        "증설",
        "CAPA",
        "프로젝트",
        "패키징",
        "고객사 확대",
    ),
    "valuation": (
        "목표주가",
        "목표가",
        "PER",
        "PBR",
        "밸류",
        "밸류에이션",
        "상승여력",
        "Multiple",
        "TP",
        "상향",
        "하향",
    ),
    "risks": (
        "risk",
        "uncertainty",
        "execution speed",
        "recovery timing",
        "리스크",
        "우려",
        "부담",
        "불확실",
        "하락",
        "둔화",
        "감소",
        "비용",
        "환율",
        "경쟁",
        "변동성",
        "원가",
    ),
}
_CUT_STARTS = (
    "며,",
    "으며",
    "고 ",
    "하고 ",
    "지만",
    "또한",
    "YoY)",
    "QoQ)",
    "인한 ",
    "따른 ",
    "대비 ",
    "로 ",
    "및 ",
    "은 ",
    "는 ",
    "통해 ",
    "위해 ",
    "성장과 ",
    "직 ",
    "일/",
    "인별 ",
    "스 제품",
)
_CUT_ENDINGS = (
    " 허브",
    " 거",
    " 전년",
    " 매",
    " OPM",
    "억원(",
    "존재하",
    "효과로",
    "성과를",
    "능력으",
    "낮",
    "관세 영향 축소",
    "에서",
    "음식료",
    "수요 둔화 우려가 무색한",
    "해당 레퍼런스를",
    "환율도",
    "제품군",
    "해외 현지",
    "으로",
)
_COVER_DATE_RE = re.compile(r"\b20\d{2}[./-]\d{1,2}[./-]\d{1,2}\b")
_RATING_HISTORY_RE = re.compile(
    r"\b20\d{2}[./-]\d{1,2}[./-]\d{1,2}\b.*\b(?:Buy|Hold|Sell|Neutral)\b.*\d",
    re.IGNORECASE,
)


def build_research_report_briefing(
    report: ParsedResearchReport,
    body_text: str | None,
    analysis: ResearchReportBodyAnalysis,
) -> ResearchReportBriefing:
    cleaned_text = clean_research_report_text(body_text or "")
    filtered_text = _filter_candidate_blocks(cleaned_text)
    candidates = _candidate_sentences(filtered_text)
    fallback_candidates = _candidate_sentences(" ".join(_analysis_values(analysis)))
    if not candidates:
        candidates = fallback_candidates

    sections = _select_sections(candidates)
    sections = _fallback_sections(report, analysis, sections)
    report_type = _report_type(report, candidates, sections)
    headline = _headline(report, sections)
    source_quality = _source_quality(cleaned_text, candidates, analysis.body_text_status)
    confidence = _confidence(analysis.confidence, source_quality, sections, candidates)
    return ResearchReportBriefing(
        report_type=report_type,
        headline=headline,
        opinion=analysis.investment_opinion,
        stock_view=sections["stock_view"],
        earnings=sections["earnings"],
        industry=sections["industry"],
        new_business=sections["new_business"],
        valuation=sections["valuation"],
        risks=sections["risks"],
        source_quality=source_quality,
        brief_version="brief-rule-v3",
        confidence=confidence,
    )


def clean_research_report_text(text: str) -> str:
    lines = []
    for raw_line in str(text or "").replace("\uf06e", " ").splitlines():
        line = _normalize(raw_line)
        if not line:
            if lines and lines[-1]:
                lines.append("")
            continue
        if _is_noise_line(line):
            continue
        lines.append(line)
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


def _filter_candidate_blocks(text: str) -> str:
    blocks = _split_candidate_blocks(text)
    kept = [
        block
        for block in blocks
        if not _is_noise_block(block) and not _looks_cut_block(block)
    ]
    return "\n\n".join(kept)


def _split_candidate_blocks(text: str) -> list[str]:
    blocks: list[str] = []
    current: list[str] = []
    for line in str(text or "").splitlines():
        cleaned = _normalize(line)
        if not cleaned:
            if current:
                blocks.append("\n".join(current))
                current = []
            continue
        current.append(cleaned)
    if current:
        blocks.append("\n".join(current))
    return blocks


def _is_noise_block(block: str) -> bool:
    normalized = _normalize(block)
    lowered = normalized.lower()
    if not normalized:
        return True
    hard_noise_terms = (
        "투자등급 정의",
        "추천일 종가대비",
        "Hold(보유) 의견",
        "Sell(매도) 의견",
        "절대수익률 기준",
        "당사는 개별 종목",
        "유니버스 투자등급",
        "Analyst ",
    )
    if any(term.lower() in lowered for term in hard_noise_terms):
        return True
    lines = [line for line in block.splitlines() if _normalize(line)]
    numeric_tokens = re.findall(r"\d[\d,]*(?:\.\d+)?", normalized)
    table_term_count = sum(1 for term in _TABLE_TERMS if term in normalized)
    if len(lines) >= 2 and len(numeric_tokens) >= 6 and table_term_count >= 2:
        return True
    if len(lines) >= 2 and sum(1 for line in lines if _is_noise_line(line)) >= max(1, len(lines) - 1):
        return True
    return False


def _looks_cut_block(block: str) -> bool:
    lines = [line for line in block.splitlines() if _normalize(line)]
    if not lines:
        return True
    if len(lines) == 1:
        return _looks_broken(lines[0])
    return _looks_broken(lines[0]) and _looks_broken(lines[-1])


def _candidate_sentences(text: str) -> list[str]:
    if not text:
        return []
    candidates: list[str] = []
    for part in _SENTENCE_BOUNDARY_RE.split(text):
        cleaned = _clean_fragment(part)
        if not cleaned:
            continue
        if _is_noise_line(cleaned) or _looks_broken(cleaned):
            continue
        if 12 <= len(cleaned) <= 360 and not _contains_similar(candidates, cleaned):
            candidates.append(_shorten(cleaned, 300))
    return candidates


def _select_sections(sentences: list[str]) -> dict[str, str]:
    selected: dict[str, str] = {key: "" for key in _SECTION_KEYWORDS}
    used: list[str] = []
    for key in ("valuation", "risks", "new_business", "earnings", "industry", "stock_view"):
        picked = _best_sentence(sentences, _SECTION_KEYWORDS[key], used=used)
        selected[key] = picked
        if picked:
            used.append(picked)
    return selected


def _best_sentence(sentences: list[str], keywords: tuple[str, ...], *, used: list[str]) -> str:
    scored: list[tuple[int, int, str]] = []
    for index, sentence in enumerate(sentences):
        lowered = sentence.lower()
        keyword_score = sum(1 for keyword in keywords if keyword.lower() in lowered)
        if not keyword_score:
            continue
        duplicate_penalty = 30 if any(_similar_sentence(sentence, previous) for previous in used) else 0
        quality_score = _sentence_quality_score(sentence)
        scored.append((keyword_score * 20 + quality_score - duplicate_penalty, -index, sentence))
    scored.sort(reverse=True)
    for score, _, sentence in scored:
        if score > 0 and not any(_similar_sentence(sentence, previous) for previous in used):
            return sentence
    return scored[0][2] if scored and scored[0][0] > 0 and not used else ""


def _fallback_sections(
    report: ParsedResearchReport,
    analysis: ResearchReportBodyAnalysis,
    sections: dict[str, str],
) -> dict[str, str]:
    fallback_map = {
        "stock_view": (analysis.buy_thesis, analysis.summary, _title_context(report.title)),
        "earnings": (analysis.earnings_drivers,),
        "industry": (analysis.growth_drivers,),
        "new_business": (analysis.growth_drivers,),
        "valuation": (analysis.valuation_view, analysis.target_price_rationale),
        "risks": (analysis.risk_factors, analysis.sell_or_risk_thesis),
    }
    updated = dict(sections)
    used = [value for value in updated.values() if value]
    for key, values in fallback_map.items():
        if updated[key]:
            continue
        fallback = _first_clean_fragment(*values, used=used)
        if fallback:
            updated[key] = fallback
            used.append(fallback)
    return updated


def _report_type(
    report: ParsedResearchReport,
    sentences: list[str],
    sections: dict[str, str],
) -> str:
    haystack = " ".join([report.title, *sentences[:10], *sections.values()]).lower()
    scores = {
        key: sum(1 for keyword in keywords if keyword.lower() in haystack)
        for key, keywords in _REPORT_TYPE_KEYWORDS.items()
    }
    best = max(scores, key=scores.get)
    return best if scores[best] else "stock_report"


def _headline(report: ParsedResearchReport, sections: dict[str, str]) -> str:
    core = sections.get("stock_view") or sections.get("earnings") or sections.get("industry")
    if core:
        return _shorten(f"{report.ticker}: {core}", 180)
    title = _title_context(report.title)
    return f"{report.ticker}: {title or '핵심 근거 부족'}"


def _source_quality(text: str, sentences: list[str], body_status: str) -> str:
    if body_status != "extracted":
        return body_status
    if len(text) >= 1000 and len(sentences) >= 8:
        return "full_text"
    if len(sentences) >= 3 or (len(text) >= 200 and len(sentences) >= 2):
        return "partial_text"
    return "title_or_sparse"


def _confidence(
    base_confidence: float,
    source_quality: str,
    sections: dict[str, str],
    sentences: list[str],
) -> float:
    section_score = sum(1 for value in sections.values() if value) * 0.04
    diversity_bonus = min(0.08, len({value for value in sections.values() if value}) * 0.015)
    quality_bonus = {"full_text": 0.12, "partial_text": 0.04}.get(source_quality, -0.08)
    sparse_penalty = -0.04 if len(sentences) <= 1 else 0.0
    score = float(base_confidence or 0.0) + section_score + diversity_bonus + quality_bonus + sparse_penalty
    return round(max(0.0, min(1.0, score)), 3)


def _analysis_values(analysis: ResearchReportBodyAnalysis) -> list[str]:
    return [
        analysis.summary,
        analysis.buy_thesis,
        analysis.sell_or_risk_thesis,
        analysis.growth_drivers,
        analysis.earnings_drivers,
        analysis.valuation_view,
        analysis.target_price_rationale,
        analysis.risk_factors,
    ]


def _first_clean_fragment(*values: object, used: list[str] | None = None) -> str:
    used_values = used or []
    for value in values:
        for fragment in str(value or "").split(" / "):
            cleaned = _clean_fragment(_strip_summary_prefix(fragment))
            if (
                cleaned
                and not _is_noise_line(cleaned)
                and not _looks_broken(cleaned)
                and not any(_similar_sentence(cleaned, previous) for previous in used_values)
            ):
                return _shorten(cleaned, 220)
    return ""


def _strip_summary_prefix(text: str) -> str:
    marker = "핵심 근거:"
    if marker in text:
        return text.split(marker, 1)[1].strip()
    return text


def _title_context(title: str) -> str:
    cleaned = _normalize(title)
    cleaned = re.sub(r"^.*?\(\d{6}/[^)]*\)", "", cleaned).strip()
    cleaned = cleaned.strip(" :-")
    return _shorten(cleaned, 180) if len(cleaned) >= 4 else ""


def _clean_fragment(text: str) -> str:
    cleaned = _normalize(str(text or "").replace("\uf06e", " "))
    cleaned = cleaned.strip(" -·ㆍ,;:")
    return cleaned


def _normalize(text: str) -> str:
    normalized = str(text or "").replace("\u118d", " ")
    return _SPACE_RE.sub(" ", normalized).strip()


def _shorten(text: str, limit: int) -> str:
    cleaned = _normalize(text)
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3].rstrip() + "..."


def _is_noise_line(text: str) -> bool:
    lowered = text.lower()
    if any(term.lower() in lowered for term in _NOISE_TERMS):
        return True
    if re.match(r"^\[?표\s*\d+\]?", text, re.IGNORECASE):
        return True
    if re.search(r"(?:PER|PBR|EV/EBITDA|ROE|EPS|BPS)\s*비교", text, re.IGNORECASE):
        metric_terms = re.findall(r"PER|PBR|EV/EBITDA|ROE|EPS|BPS", text, re.IGNORECASE)
        if len(metric_terms) >= 2:
            return True
    if _COVER_DATE_RE.search(text) and len(text) <= 32:
        return True
    if _RATING_HISTORY_RE.search(text):
        return True
    if re.search(r"(?:\bBuy\b\s*){3,}", text, re.IGNORECASE):
        return True
    numeric_tokens = re.findall(r"\d[\d,]*(?:\.\d+)?", text)
    if len(numeric_tokens) >= 6:
        return True
    if len(numeric_tokens) >= 4 and any(term in text for term in _ACCOUNTING_ROW_TERMS):
        return True
    if len(numeric_tokens) >= 4 and any(term in text for term in _TABLE_TERMS):
        return True
    return False


def _looks_broken(text: str) -> bool:
    stripped = text.strip()
    if stripped.count("(") > stripped.count(")"):
        return True
    if stripped.startswith(_CUT_STARTS) or re.match(r"^[가-힣A-Za-z],", stripped):
        return True
    return stripped.endswith(_CUT_ENDINGS)


def _sentence_quality_score(sentence: str) -> int:
    score = 0
    if sentence.endswith(("다.", "다", "요.", "음.", "임.", "됨.", ".")):
        score += 8
    if 25 <= len(sentence) <= 180:
        score += 6
    if any(token in sentence for token in ("했다", "된다", "이다", "있다", "전망", "예상", "유지", "상향", "하향")):
        score += 5
    numeric_tokens = re.findall(r"\d[\d,]*(?:\.\d+)?", sentence)
    if len(numeric_tokens) >= 4:
        score -= 8
    else:
        score -= min(8, max(0, len(numeric_tokens) - 2) * 2)
    return score


def _contains_similar(existing: list[str], sentence: str) -> bool:
    return any(_similar_sentence(sentence, previous) for previous in existing)


def _similar_sentence(left: str, right: str) -> bool:
    if not left or not right:
        return False
    left_norm = _normalize(left)
    right_norm = _normalize(right)
    if left_norm == right_norm:
        return True
    if len(left_norm) >= 20 and len(right_norm) >= 20:
        if left_norm in right_norm or right_norm in left_norm:
            return True
    left_tokens = {token for token in re.split(r"\W+", left_norm.lower()) if len(token) >= 2}
    right_tokens = {token for token in re.split(r"\W+", right_norm.lower()) if len(token) >= 2}
    if not left_tokens or not right_tokens:
        return False
    overlap = len(left_tokens & right_tokens) / min(len(left_tokens), len(right_tokens))
    return overlap >= 0.72
