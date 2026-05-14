"""
Parse daily Korean morning briefing messages from a Telegram channel.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Mapping


@dataclass
class ParsedSignal:
    ticker: str
    signal_type: str
    star_rating: int
    raw_score: float
    target_price: float | None = None


@dataclass
class ParsedMessage:
    message_date: date
    signals: list[ParsedSignal] = field(default_factory=list)
    message_id: int | None = None


_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
_TICKER_RE = re.compile(r"\b(\d{6})\b")
_FILLED_STAR_RE = re.compile(r"★")
_TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?\s*$")
_TARGET_PRICE_RE = re.compile(r"(?:TP|목표가?)\s*[:：]?\s*([0-9][0-9,\s]*)", re.IGNORECASE)
_MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\([^)]+\)")
_URL_RE = re.compile(r"https?://\S+")

_BRIEF_WORDS = ("모닝", "주식 요약", "브리프", "시황")
_POSITIVE_WORDS = ("수혜", "긍정", "매수", "상승", "관심", "호재", "커버", "추천", "▲", "상향", "BUY")
_WARNING_WORDS = ("주의", "부정", "매도", "하락", "리스크", "경고", "악재", "▼", "하향", "SELL", "약세", "차질")


def parse_morning_brief(
    text: str,
    message_id: int | None = None,
    ticker_by_name: Mapping[str, str] | None = None,
) -> ParsedMessage | None:
    """Return a parsed message, or None when the text is not a dated morning brief."""
    msg_date = _extract_message_date(text)
    if msg_date is None:
        return None

    signals: dict[str, ParsedSignal] = {}
    _parse_table(text, signals, ticker_by_name or {})
    _parse_sections(text, signals, ticker_by_name or {})

    return ParsedMessage(
        message_date=msg_date,
        signals=list(signals.values()),
        message_id=message_id,
    )


def _extract_message_date(text: str) -> date | None:
    if not any(word in text for word in _BRIEF_WORDS):
        return None

    for line in text.splitlines():
        if any(word in line for word in _BRIEF_WORDS):
            match = _DATE_RE.search(line)
            if match:
                return date.fromisoformat(match.group(1))

    match = _DATE_RE.search(text)
    return date.fromisoformat(match.group(1)) if match else None


def _parse_table(
    text: str,
    signals: dict[str, ParsedSignal],
    ticker_by_name: Mapping[str, str],
) -> None:
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or _TABLE_SEPARATOR_RE.match(stripped):
            continue

        columns = [col.strip() for col in stripped.strip("|").split("|")]
        if len(columns) < 2:
            continue

        tickers = _find_tickers(columns[0], ticker_by_name)
        if not tickers:
            continue

        row_text = _strip_links(" ".join(columns))
        signal_type = _classify_context(row_text) or "positive"
        stars = _count_stars(row_text)
        target_price = _extract_target_price(columns[2] if len(columns) > 2 else row_text)

        signals[tickers[0]] = ParsedSignal(
            ticker=tickers[0],
            signal_type=signal_type,
            star_rating=stars,
            raw_score=_raw_score(signal_type, stars),
            target_price=target_price,
        )


def _parse_sections(
    text: str,
    signals: dict[str, ParsedSignal],
    ticker_by_name: Mapping[str, str],
) -> None:
    current_type: str | None = None

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("|"):
            continue

        clean_line = _strip_links(stripped)
        line_type = _classify_context(clean_line)
        if line_type and _is_section_heading(clean_line):
            current_type = line_type

        for ticker in _find_tickers(clean_line, ticker_by_name):
            if ticker in signals:
                continue
            signal_type = line_type or current_type
            if signal_type is None:
                continue
            stars = _count_stars(stripped)
            signals[ticker] = ParsedSignal(
                ticker=ticker,
                signal_type=signal_type,
                star_rating=stars,
                raw_score=_raw_score(signal_type, stars),
                target_price=_extract_explicit_target_price(clean_line),
            )


def _classify_context(text: str) -> str | None:
    if any(word in text for word in _WARNING_WORDS):
        return "warning"
    if any(word in text for word in _POSITIVE_WORDS):
        return "positive"
    return None


def _find_tickers(text: str, ticker_by_name: Mapping[str, str]) -> list[str]:
    tickers = list(dict.fromkeys(_TICKER_RE.findall(text)))
    for name, ticker in sorted(ticker_by_name.items(), key=lambda item: len(item[0]), reverse=True):
        if len(name.strip()) < 2:
            continue
        if _contains_stock_name(text, name):
            tickers.append(ticker)
    return list(dict.fromkeys(tickers))


def _is_section_heading(text: str) -> bool:
    return not _find_tickers(text, {}) and "—" not in text and len(text) <= 30


def _strip_links(text: str) -> str:
    return _URL_RE.sub("", _MARKDOWN_LINK_RE.sub("", text))


def _contains_stock_name(text: str, name: str) -> bool:
    pattern = rf"(?<![0-9A-Za-z가-힣]){re.escape(name)}(?![0-9A-Za-z가-힣])"
    return re.search(pattern, text) is not None


def _count_stars(text: str) -> int:
    return len(_FILLED_STAR_RE.findall(text))


def _raw_score(signal_type: str, stars: int) -> float:
    if signal_type == "warning":
        return -float(max(stars, 1))
    return float(max(stars, 1))


def _extract_target_price(text: str) -> float | None:
    explicit_price = _extract_explicit_target_price(text)
    if explicit_price is not None:
        return explicit_price
    return _parse_number(text)


def _extract_explicit_target_price(text: str) -> float | None:
    match = _TARGET_PRICE_RE.search(text)
    return _parse_number(match.group(1)) if match else None


def _parse_number(text: str) -> float | None:
    digits = re.sub(r"[^0-9]", "", text)
    return float(digits) if digits else None
