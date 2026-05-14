from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from html.parser import HTMLParser
from typing import Mapping


@dataclass(frozen=True)
class BusanstockParsedSignal:
    signal_date: date
    ticker: str
    signal_type: str
    source_section: str
    raw_score: float
    detail: str


_TITLE_DATE_RE = re.compile(r"(\d{4})[.-](\d{2})[.-](\d{2})")
_PERCENT_RE = re.compile(r"([▲▼])\s*(\d+(?:\.\d+)?)%")


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"p", "div", "h1", "h2", "h3", "li", "tr"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if text:
            self.parts.append(text)

    def text(self) -> str:
        return "\n".join(part for part in self.parts if part.strip())


def parse_busanstock_report(
    html: str,
    *,
    ticker_by_name: Mapping[str, str],
    signal_date: date | None = None,
) -> list[BusanstockParsedSignal]:
    report_date = signal_date or _extract_date(html)
    if report_date is None:
        return []

    text = _html_to_text(html)
    signals: dict[tuple[str, str], BusanstockParsedSignal] = {}
    _parse_snapshot_grid_html(html, report_date, ticker_by_name, signals)
    _parse_tp_bar_rows_html(html, report_date, ticker_by_name, signals)
    _parse_stock_snapshot(text, report_date, ticker_by_name, signals)
    _parse_consensus(text, report_date, ticker_by_name, signals)
    return list(signals.values())


def _html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    return parser.text()


def _extract_date(html: str) -> date | None:
    match = _TITLE_DATE_RE.search(html)
    if not match:
        return None
    year, month, day = (int(value) for value in match.groups())
    return date(year, month, day)


def _parse_stock_snapshot(
    text: str,
    signal_date: date,
    ticker_by_name: Mapping[str, str],
    signals: dict[tuple[str, str], BusanstockParsedSignal],
) -> None:
    for label, signal_type, raw_score in (
        ("매수", "buy", 0.3),
        ("매도·경고", "warning", -0.7),
    ):
        match = re.search(rf"{re.escape(label)}\s*\(\d+\)\s*([^\n]+)", text)
        if not match:
            continue
        for name in _split_names(match.group(1)):
            ticker = ticker_by_name.get(name)
            if not ticker:
                continue
            signals[(ticker, "stock_snapshot")] = BusanstockParsedSignal(
                signal_date=signal_date,
                ticker=ticker,
                signal_type=signal_type,
                source_section="stock_snapshot",
                raw_score=raw_score,
                detail=f"{label}: {name}",
            )


def _parse_snapshot_grid_html(
    html: str,
    signal_date: date,
    ticker_by_name: Mapping[str, str],
    signals: dict[tuple[str, str], BusanstockParsedSignal],
) -> None:
    for css_class, label, signal_type, raw_score in (
        ("buy", "매수", "buy", 0.3),
        ("sell", "매도·경고", "warning", -0.7),
    ):
        for block in re.findall(
            rf'<div class="snapshot-grid {css_class}">(.*?)</div>\s*</div>',
            html,
            flags=re.DOTALL,
        ):
            for name in re.findall(r'<span class="stock"><strong>(.*?)</strong></span>', block):
                ticker = ticker_by_name.get(_clean_html_text(name))
                if not ticker:
                    continue
                signals[(ticker, "stock_snapshot")] = BusanstockParsedSignal(
                    signal_date=signal_date,
                    ticker=ticker,
                    signal_type=signal_type,
                    source_section="stock_snapshot",
                    raw_score=raw_score,
                    detail=f"{label}: {_clean_html_text(name)}",
                )


def _parse_tp_bar_rows_html(
    html: str,
    signal_date: date,
    ticker_by_name: Mapping[str, str],
    signals: dict[tuple[str, str], BusanstockParsedSignal],
) -> None:
    pattern = re.compile(
        r'<div class="tp-bar-row">.*?'
        r'<div class="name">(.*?)</div>.*?'
        r'<div class="pct [^"]*">([▲▼]\s*\d+(?:\.\d+)?%)</div>',
        flags=re.DOTALL,
    )
    for name_raw, pct_raw in pattern.findall(html):
        name = _clean_html_text(name_raw)
        ticker = ticker_by_name.get(name)
        if not ticker:
            continue
        percent = _PERCENT_RE.search(pct_raw)
        if not percent:
            continue
        direction, value = percent.group(1), float(percent.group(2))
        if direction == "▲":
            raw_score = 0.7 if value >= 30 else 0.5
            signal_type = "tp_up"
        else:
            raw_score = -0.7
            signal_type = "tp_down"
        signals[(ticker, "consensus")] = BusanstockParsedSignal(
            signal_date=signal_date,
            ticker=ticker,
            signal_type=signal_type,
            source_section="consensus",
            raw_score=raw_score,
            detail=f"{name} {pct_raw}",
        )


def _parse_consensus(
    text: str,
    signal_date: date,
    ticker_by_name: Mapping[str, str],
    signals: dict[tuple[str, str], BusanstockParsedSignal],
) -> None:
    for line in text.splitlines():
        percent = _PERCENT_RE.search(line)
        if not percent:
            continue
        direction, value = percent.group(1), float(percent.group(2))
        name, ticker = _first_stock_name(line, ticker_by_name)
        if not ticker:
            continue
        if direction == "▲":
            raw_score = 0.7 if value >= 30 else 0.5
            signal_type = "tp_up"
        else:
            raw_score = -0.7
            signal_type = "tp_down"
        signals[(ticker, "consensus")] = BusanstockParsedSignal(
            signal_date=signal_date,
            ticker=ticker,
            signal_type=signal_type,
            source_section="consensus",
            raw_score=raw_score,
            detail=line.strip(),
        )


def _first_stock_name(line: str, ticker_by_name: Mapping[str, str]) -> tuple[str | None, str | None]:
    for name, ticker in sorted(ticker_by_name.items(), key=lambda item: len(item[0]), reverse=True):
        if re.search(rf"^\s*{re.escape(name)}(?![0-9A-Za-z가-힣])", line):
            return name, ticker
    return None, None


def _split_names(text: str) -> list[str]:
    return [
        token.strip()
        for token in re.split(r"\s*[·,]\s*", text)
        if token.strip() and not token.strip().startswith("(")
    ]


def _clean_html_text(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", text)).strip()
