from __future__ import annotations

import re
import json
from dataclasses import dataclass, replace
from datetime import date
from html.parser import HTMLParser
from typing import Iterable
from urllib.parse import urljoin


@dataclass(frozen=True)
class ParsedResearchReport:
    report_date: date
    ticker: str
    source: str
    region: str
    broker: str | None
    rating: str | None
    rating_score: float | None
    target_price: float | None
    previous_target_price: float | None
    target_price_change_pct: float | None
    sentiment_score: float | None
    raw_score: float
    title: str
    source_url: str | None


_DATE_RE = re.compile(r"(\d{4})[./-](\d{1,2})[./-](\d{1,2})")
_TICKER_RE = re.compile(r"(?<!\d)(\d{6})(?!\d)")
_TARGET_CHANGE_RE = re.compile(
    r"(?P<before>\d[\d,]*(?:\.\d+)?)\s*(?P<before_unit>만|천|원)?\s*(?:원)?\s*"
    r"(?:→|->|에서)\s*"
    r"(?P<after>\d[\d,]*(?:\.\d+)?)\s*(?P<after_unit>만|천|원)?\s*(?:원)?"
)
_TARGET_RE = re.compile(r"(?:목표가|목표주가|TP)\s*[:：]?\s*(\d[\d,.]*)\s*원?")
_RATING_PATTERNS: tuple[tuple[re.Pattern[str], str, float], ...] = (
    (re.compile(r"적극\s*매수|강력\s*매수|strong\s*buy", re.IGNORECASE), "Strong Buy", 1.0),
    (re.compile(r"매수|buy|outperform", re.IGNORECASE), "Buy", 0.6),
    (re.compile(r"trading\s*buy", re.IGNORECASE), "Trading Buy", 0.4),
    (re.compile(r"중립|보유|hold|neutral|market\s*perform", re.IGNORECASE), "Hold", 0.0),
    (re.compile(r"비중\s*축소|underperform|reduce", re.IGNORECASE), "Underperform", -0.6),
    (re.compile(r"매도|sell|strong\s*sell", re.IGNORECASE), "Sell", -1.0),
)


class _LinkTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.blocks: list[tuple[str, str | None]] = []
        self._parts: list[str] = []
        self._href_stack: list[str | None] = []
        self._active_href: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"tr", "li", "p", "div"}:
            self._flush()
        if tag == "a":
            href = dict(attrs).get("href")
            self._href_stack.append(href)
            self._active_href = href or self._active_href

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href_stack:
            self._href_stack.pop()
        if tag in {"tr", "li", "p", "div"}:
            self._flush()

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if text:
            self._parts.append(text)

    def close(self) -> None:
        super().close()
        self._flush()

    def _flush(self) -> None:
        text = _normalize_space(" ".join(self._parts))
        if text:
            self.blocks.append((text, self._active_href))
        self._parts = []
        self._active_href = None


def parse_korean_research_reports(
    html: str,
    *,
    source: str,
    broker: str | None = None,
    base_url: str | None = None,
    region: str = "domestic",
) -> list[ParsedResearchReport]:
    """Parse Korean broker research-list HTML into normalized report signals."""
    parsed_reports = {
        (report.report_date, report.ticker, report.title): report
        for report in _parse_hankyung_nuxt_reports(
            html,
            source=source,
            broker=broker,
            region=region,
        )
    }
    parsed_reports.update(
        {
            (report.report_date, report.ticker, report.title): report
            for report in _parse_miraeasset_bbsdocs_reports(
                html,
                source=source,
                broker=broker,
                region=region,
            )
        }
    )
    parsed_reports.update(
        {
            (report.report_date, report.ticker, report.title): report
            for report in _parse_miraeasset_table_reports(
                html,
                source=source,
                broker=broker,
                region=region,
            )
        }
    )

    parser = _LinkTextExtractor()
    parser.feed(html)
    parser.close()

    for text, href in parser.blocks:
        href_text = href or ""
        if (
            "window.__NUXT__" in text
            or "REPORT_TITLE" in text
            or "document.write" in text
            or "nv.Popup.open" in text
            or "nv.Popup.open" in href_text
        ):
            continue
        parsed = parse_korean_research_report_text(
            text,
            source=source,
            broker=broker,
            source_url=urljoin(base_url, href) if base_url and href else href,
            region=region,
        )
        if parsed is None:
            continue
        parsed_reports[(parsed.report_date, parsed.ticker, parsed.title)] = parsed
    return list(parsed_reports.values())


def parse_korean_research_report_text(
    text: str,
    *,
    source: str,
    broker: str | None = None,
    source_url: str | None = None,
    region: str = "domestic",
) -> ParsedResearchReport | None:
    normalized = _normalize_space(text)
    report_date = _extract_date(normalized)
    ticker = _extract_ticker(normalized)
    if report_date is None or ticker is None:
        return None

    rating, rating_score = _extract_rating(normalized)
    previous_target, target, target_change_pct = _extract_target_change(normalized)
    if target is None:
        target = _extract_target(normalized)
    sentiment_score = _extract_sentiment_score(normalized)
    raw_score = _combine_report_score(
        rating_score=rating_score,
        target_price_change_pct=target_change_pct,
        sentiment_score=sentiment_score,
    )
    title = _clean_title(normalized)

    return ParsedResearchReport(
        report_date=report_date,
        ticker=ticker,
        source=source,
        region=region,
        broker=broker,
        rating=rating,
        rating_score=rating_score,
        target_price=target,
        previous_target_price=previous_target,
        target_price_change_pct=target_change_pct,
        sentiment_score=sentiment_score,
        raw_score=raw_score,
        title=title,
        source_url=source_url,
    )


def reports_to_rows(reports: Iterable[ParsedResearchReport]) -> list[dict[str, object]]:
    return [
        {
            "report_date": report.report_date,
            "ticker": report.ticker,
            "source": report.source,
            "region": report.region,
            "broker": report.broker,
            "rating": report.rating,
            "rating_score": report.rating_score,
            "target_price": report.target_price,
            "previous_target_price": report.previous_target_price,
            "target_price_change_pct": report.target_price_change_pct,
            "sentiment_score": report.sentiment_score,
            "raw_score": report.raw_score,
            "title": report.title,
            "source_url": report.source_url,
        }
        for report in reports
    ]


def apply_report_body_text_signal(
    report: ParsedResearchReport,
    body_text: str | None,
) -> ParsedResearchReport:
    """Fold PDF body-text sentiment into a parsed report without storing the body."""
    if not body_text:
        return report
    body_rating, body_rating_score = _extract_rating(body_text)
    body_previous_target, body_target, body_target_change_pct = _extract_target_change(body_text)
    if body_target is None:
        body_target = _extract_target(body_text)
    body_sentiment_score = _extract_sentiment_score(body_text)
    if (
        body_rating_score is None
        and body_target is None
        and body_target_change_pct is None
        and body_sentiment_score is None
    ):
        return report
    rating = report.rating or body_rating
    rating_score = report.rating_score if report.rating_score is not None else body_rating_score
    previous_target_price = report.previous_target_price or body_previous_target
    target_price = report.target_price or body_target
    target_price_change_pct = report.target_price_change_pct
    if target_price_change_pct is None:
        target_price_change_pct = body_target_change_pct
    sentiment_score = _clamp(
        (report.sentiment_score or 0.0) + body_sentiment_score,
        lower=-0.3,
        upper=0.3,
    ) if body_sentiment_score is not None else report.sentiment_score
    raw_score = _combine_report_score(
        rating_score=rating_score,
        target_price_change_pct=target_price_change_pct,
        sentiment_score=sentiment_score,
    )
    return replace(
        report,
        rating=rating,
        rating_score=rating_score,
        previous_target_price=previous_target_price,
        target_price=target_price,
        target_price_change_pct=target_price_change_pct,
        sentiment_score=sentiment_score,
        raw_score=raw_score,
    )


def _parse_hankyung_nuxt_reports(
    html: str,
    *,
    source: str,
    broker: str | None,
    region: str,
) -> list[ParsedResearchReport]:
    if "topReports:[" not in html or "window.__NUXT__" not in html:
        return []
    resolver = _nuxt_resolver(html)
    top_reports = _extract_js_array(html, "topReports:[")
    if top_reports is None:
        return []

    reports = []
    for object_text in _iter_js_objects(top_reports):
        item = _parse_js_object_fields(object_text, resolver)
        ticker = item.get("BUSINESS_CODE")
        title = item.get("REPORT_TITLE")
        report_date_text = item.get("REPORT_DATE")
        if not ticker or not title or not report_date_text:
            continue
        report_date = _extract_date(str(report_date_text))
        if report_date is None:
            continue
        rating = item.get("GRADE_VALUE")
        rating_score = _rating_score(str(rating)) if rating else None
        previous_target = _float_or_none(item.get("OLD_TARGET_STOCK_PRICES"))
        target = _float_or_none(item.get("TARGET_STOCK_PRICES"))
        target_change_pct = None
        if previous_target and target:
            target_change_pct = (target / previous_target) - 1.0
        sentiment_score = _extract_sentiment_score(str(title))
        raw_score = _combine_report_score(
            rating_score=rating_score,
            target_price_change_pct=target_change_pct,
            sentiment_score=sentiment_score,
        )
        reports.append(
            ParsedResearchReport(
                report_date=report_date,
                ticker=str(ticker),
                source=source,
                region=region,
                broker=broker or _string_or_none(item.get("OFFICE_NAME")),
                rating=_string_or_none(rating),
                rating_score=rating_score,
                target_price=target,
                previous_target_price=previous_target,
                target_price_change_pct=target_change_pct,
                sentiment_score=sentiment_score,
                raw_score=raw_score,
                title=str(title),
                source_url=_string_or_none(item.get("REPORT_FILEPATH")),
            )
        )
    return reports


def _parse_miraeasset_bbsdocs_reports(
    html: str,
    *,
    source: str,
    broker: str | None,
    region: str,
) -> list[ParsedResearchReport]:
    if "document.write" not in html or "/bbs/board/message/view.do" not in html:
        return []

    reports = []
    row_pattern = re.compile(r"document\.write\('(?P<row><li>.*?</li>)'\);", flags=re.DOTALL)
    title_pattern = re.compile(r'<li><a href="(?P<view>[^"]+)">(?P<title>.*?)</a>', flags=re.DOTALL)
    for row_match in row_pattern.finditer(html):
        row_text = row_match.group("row")
        title_match = title_pattern.search(row_text)
        if title_match is None:
            continue
        view_url = title_match.group("view")
        title = _clean_html_text(title_match.group("title"))
        pdf_url = _extract_pdf_url(row_text)
        if not title:
            continue
        report_date = _extract_date(row_text)
        ticker = _extract_ticker(title)
        if report_date is None or ticker is None:
            continue
        rating, rating_score = _extract_rating(title)
        sentiment_score = _extract_sentiment_score(title)
        raw_score = _combine_report_score(
            rating_score=rating_score,
            target_price_change_pct=None,
            sentiment_score=sentiment_score,
        )
        reports.append(
            ParsedResearchReport(
                report_date=report_date,
                ticker=ticker,
                source=source,
                region=region,
                broker=broker or "미래에셋증권",
                rating=rating,
                rating_score=rating_score,
                target_price=None,
                previous_target_price=None,
                target_price_change_pct=None,
                sentiment_score=sentiment_score,
                raw_score=raw_score,
                title=title,
                source_url=pdf_url or view_url,
            )
        )
    return reports


def _parse_miraeasset_table_reports(
    html: str,
    *,
    source: str,
    broker: str | None,
    region: str,
) -> list[ParsedResearchReport]:
    if "bbs_linetype2" not in html or "javascript:view" not in html:
        return []

    reports = []
    row_pattern = re.compile(r"<tr[^>]*>(?P<row>.*?)</tr>", flags=re.DOTALL | re.IGNORECASE)
    title_pattern = re.compile(
        r'<a\s+href="javascript:view\([^"]+\)"[^>]*>(?P<title>.*?)</a>',
        flags=re.DOTALL | re.IGNORECASE,
    )
    for row_match in row_pattern.finditer(html):
        row_text = row_match.group("row")
        title_match = title_pattern.search(row_text)
        if title_match is None:
            continue
        title = _clean_html_text(title_match.group("title"))
        report_date = _extract_date(row_text)
        ticker = _extract_ticker(title)
        if report_date is None or ticker is None:
            continue
        rating, rating_score = _extract_rating(title)
        sentiment_score = _extract_sentiment_score(title)
        raw_score = _combine_report_score(
            rating_score=rating_score,
            target_price_change_pct=None,
            sentiment_score=sentiment_score,
        )
        reports.append(
            ParsedResearchReport(
                report_date=report_date,
                ticker=ticker,
                source=source,
                region=region,
                broker=broker or "미래에셋증권",
                rating=rating,
                rating_score=rating_score,
                target_price=None,
                previous_target_price=None,
                target_price_change_pct=None,
                sentiment_score=sentiment_score,
                raw_score=raw_score,
                title=title,
                source_url=_extract_pdf_url(row_text),
            )
        )
    return reports


def _nuxt_resolver(html: str) -> dict[str, object]:
    match = re.search(
        r"window\.__NUXT__=\(function\((?P<params>.*?)\)\{return .*?\}\((?P<args>.*?)\)\);</script>",
        html,
        flags=re.DOTALL,
    )
    if not match:
        return {}
    params = [item.strip() for item in match.group("params").split(",") if item.strip()]
    try:
        args = json.loads(f"[{match.group('args')}]")
    except json.JSONDecodeError:
        return {}
    return dict(zip(params, args))


def _extract_js_array(html: str, marker: str) -> str | None:
    start = html.find(marker)
    if start < 0:
        return None
    index = start + len(marker) - 1
    depth = 0
    in_string = False
    escape = False
    for pos in range(index, len(html)):
        char = html[pos]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                return html[index + 1 : pos]
    return None


def _iter_js_objects(array_text: str) -> Iterable[str]:
    depth = 0
    start = None
    in_string = False
    escape = False
    for pos, char in enumerate(array_text):
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            if depth == 0:
                start = pos
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0 and start is not None:
                yield array_text[start + 1 : pos]
                start = None


def _parse_js_object_fields(object_text: str, resolver: dict[str, object]) -> dict[str, object]:
    fields: dict[str, object] = {}
    for match in re.finditer(r"([A-Z_0-9]+):", object_text):
        key = match.group(1)
        value_start = match.end()
        value_end = _find_js_value_end(object_text, value_start)
        token = object_text[value_start:value_end].strip()
        fields[key] = _resolve_js_value(token, resolver)
    return fields


def _find_js_value_end(text: str, start: int) -> int:
    in_string = False
    escape = False
    for pos in range(start, len(text)):
        char = text[pos]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == ",":
            return pos
    return len(text)


def _resolve_js_value(token: str, resolver: dict[str, object]) -> object:
    if not token:
        return None
    if token in resolver:
        return resolver[token]
    if token in {"null", "undefined"}:
        return None
    if token in {"true", "false"}:
        return token == "true"
    if token.startswith('"') and token.endswith('"'):
        try:
            return json.loads(token)
        except json.JSONDecodeError:
            return token.strip('"')
    try:
        return int(token)
    except ValueError:
        pass
    try:
        return float(token)
    except ValueError:
        return token


def _combine_report_score(
    *,
    rating_score: float | None,
    target_price_change_pct: float | None,
    sentiment_score: float | None,
) -> float:
    score = rating_score or 0.0
    if target_price_change_pct is not None:
        if target_price_change_pct >= 0.20:
            score += 0.2
        elif target_price_change_pct > 0:
            score += 0.1
        elif target_price_change_pct <= -0.20:
            score -= 0.2
        elif target_price_change_pct < 0:
            score -= 0.1
    if sentiment_score is not None:
        score += sentiment_score
    return _clamp(score, lower=-1.0, upper=1.0)


def _clamp(value: float, *, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _rating_score(rating: str) -> float | None:
    _, score = _extract_rating(rating)
    return score


def _extract_date(text: str) -> date | None:
    match = _DATE_RE.search(text)
    if not match:
        return None
    year, month, day = (int(value) for value in match.groups())
    return date(year, month, day)


def _extract_ticker(text: str) -> str | None:
    match = _TICKER_RE.search(text)
    return match.group(1) if match else None


def _extract_rating(text: str) -> tuple[str | None, float | None]:
    for pattern, rating, score in _RATING_PATTERNS:
        if pattern.search(text):
            return rating, score
    return None, None


def _extract_target_change(text: str) -> tuple[float | None, float | None, float | None]:
    match = _TARGET_CHANGE_RE.search(text)
    if not match:
        return None, None, None
    before = _parse_korean_price(match.group("before"), match.group("before_unit"))
    after = _parse_korean_price(match.group("after"), match.group("after_unit"))
    if before is None or after is None or before <= 0:
        return before, after, None
    return before, after, (after / before) - 1.0


def _extract_target(text: str) -> float | None:
    match = _TARGET_RE.search(text)
    if not match:
        return None
    return float(match.group(1).replace(",", ""))


def _extract_sentiment_score(text: str) -> float | None:
    score = 0.0
    if re.search(r"상향|올려|인상|개선|호조|저평가|undervalued", text, re.IGNORECASE):
        score += 0.1
    if re.search(r"하향|낮춰|인하|부진|고평가|부담|overvalued|downgrade", text, re.IGNORECASE):
        score -= 0.1
    return score or None


def _parse_korean_price(value: str, unit: str | None) -> float | None:
    try:
        number = float(value.replace(",", ""))
    except ValueError:
        return None
    if unit == "만":
        return number * 10_000
    if unit == "천":
        return number * 1_000
    return number


def _float_or_none(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", ""))
    except ValueError:
        return None


def _string_or_none(value: object) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _extract_pdf_url(text: str) -> str | None:
    match = re.search(r"https://[^'\"\\]+\.pdf\?attachmentId=\d+", text)
    return match.group(0) if match else None


def _clean_title(text: str) -> str:
    cleaned = _DATE_RE.sub("", text)
    cleaned = _normalize_space(cleaned)
    return cleaned[:240]


def _clean_html_text(text: str) -> str:
    return _normalize_space(re.sub(r"<[^>]+>", "", text))


def _normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()
