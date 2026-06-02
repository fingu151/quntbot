"""
Public Portfolio Dashboard — Streamlit
=======================================

Bloomberg-density + Toss-readable redesign.

Drop-in replacement for the original `scripts/public_portfolio_dashboard.py`.
Preserves the public API surface used by tests:
    - load_snapshot(path) -> {"status": "ok"|"missing"|"invalid", "snapshot": ...}
    - format_krw(value), format_pct(value)
    - snapshot_is_stale(snapshot, now=None, max_age_hours=24) -> bool
    - render_dashboard(snapshot)
    - main()

Design tokens are CSS variables on :root — Streamlit "Tweaks" controls in the
sidebar rewrite them at runtime.

SAFETY: This module is READ-ONLY. It must NOT import KisClient, submit orders,
mutate the DB, or call any external broker API.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_SNAPSHOT_PATH = ROOT_DIR / "data" / "public_portfolio_snapshot.json"
AUTO_REFRESH_SECONDS = 30 * 60
DEFAULT_RESEARCH_LIMIT = 5000
DEFAULT_VISIBLE_RESEARCH_CARDS = 100
DEFAULT_TICKER_RESEARCH_BRIEF_PATH = ROOT_DIR / "data" / "research_report_ticker_briefs.json"
DEFAULT_RESEARCH_QUALITY_QUEUE_PATH = ROOT_DIR / "data" / "research_quality_review_queue.json"
DEFAULT_RESEARCH_BRIEF_QA_SAMPLE_PATH = ROOT_DIR / "data" / "research_brief_qa_sample.json"
DEFAULT_RESEARCH_QA_ACTION_QUEUE_PATH = ROOT_DIR / "data" / "research_qa_action_queue.json"


# ─────────────────────────── Factor metadata ────────────────────────────────
FACTOR_KEYS: list[str] = [
    "value", "quality", "momentum", "yield",
    "telegram", "busanstock", "investor_flow", "research_report",
]
FACTOR_LABELS: dict[str, str] = {
    "value": "Value · 가치",
    "quality": "Quality · 품질",
    "momentum": "Momentum · 모멘텀",
    "yield": "Yield · 배당",
    "telegram": "Telegram",
    "busanstock": "Busanstock",
    "investor_flow": "Flow · 수급",
    "research_report": "Research",
}

DENSITY_OPTS = {
    "compact": "꽉 차게 (compact)",
    "regular": "보통 (regular)",
    "comfy":   "여유 (comfy)",
}
CC_OPTS = {
    "kr":      "한국식 (수익=빨강, 손실=파랑)",
    "us":      "미국식 (수익=초록, 손실=빨강)",
    "neutral": "중립 (수익=골드, 손실=회색)",
}
ACCENT_OPTS = {
    "gold":   "#f2c94c",
    "cyan":   "#5ee2dd",
    "violet": "#a78bfa",
    "orange": "#f97316",
}
TYPO_OPTS = {
    "plex":       ("IBM Plex Sans + Plex Mono", "'IBM Plex Sans', 'Pretendard', -apple-system, sans-serif",
                   "'IBM Plex Mono', 'JetBrains Mono', 'Consolas', monospace"),
    "pretendard": ("Pretendard + JetBrains Mono", "'Pretendard', -apple-system, 'Malgun Gothic', sans-serif",
                   "'JetBrains Mono', 'IBM Plex Mono', 'Consolas', monospace"),
    "inter":      ("Inter + JetBrains Mono", "'Inter', -apple-system, 'Malgun Gothic', sans-serif",
                   "'JetBrains Mono', 'Consolas', monospace"),
}


# ─────────────────────────── Snapshot I/O ──────────────────────────────────
def load_snapshot(path: Path | str) -> dict[str, Any]:
    snapshot_path = Path(path)
    if not snapshot_path.exists():
        return {"status": "missing"}
    try:
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": "invalid", "error": str(exc)}
    if not isinstance(snapshot, dict):
        return {"status": "invalid", "error": "snapshot root must be a JSON object"}
    return {"status": "ok", "snapshot": snapshot}


def load_research_report_briefs(
    database_url: str | None = None,
    *,
    limit: int = DEFAULT_RESEARCH_LIMIT,
    engine_factory=None,
) -> dict[str, Any]:
    """Load read-only research report analysis rows for the public dashboard."""
    try:
        from sqlalchemy import select

        from config import DATABASE_URL
        from src.data.database import get_engine, session_scope
        from src.data.models import ResearchReportBrief

        engine = (engine_factory or get_engine)(database_url or DATABASE_URL)
        with session_scope(engine) as session:
            statement = (
                select(ResearchReportBrief)
                .order_by(
                    ResearchReportBrief.report_date.desc(),
                    ResearchReportBrief.ticker.asc(),
                )
                .limit(max(1, int(limit)))
            )
            rows = list(session.scalars(statement).all())
    except Exception as exc:
        return {"status": "invalid", "error": str(exc), "rows": []}

    dashboard_rows = [_brief_row_to_dashboard_row(row) for row in rows]
    dashboard_rows = _enrich_sparse_research_rows(dashboard_rows)

    return {
        "status": "ok",
        "rows": dashboard_rows,
    }


def load_ticker_research_briefs(
    path: Path | str = DEFAULT_TICKER_RESEARCH_BRIEF_PATH,
) -> dict[str, Any]:
    artifact_path = Path(path)
    if not artifact_path.exists():
        return {"status": "missing", "path": str(artifact_path), "by_ticker": {}}
    try:
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "status": "invalid",
            "error": str(exc),
            "path": str(artifact_path),
            "by_ticker": {},
        }
    if not isinstance(artifact, dict):
        return {
            "status": "invalid",
            "error": "ticker brief artifact root must be a JSON object",
            "path": str(artifact_path),
            "by_ticker": {},
        }
    ticker_rows = artifact.get("tickers") or []
    by_ticker = {
        str(row.get("ticker")): row
        for row in ticker_rows
        if isinstance(row, dict) and row.get("ticker")
    }
    return {"status": "ok", "artifact": artifact, "by_ticker": by_ticker, "path": str(artifact_path)}


def load_research_quality_queue(
    path: Path | str = DEFAULT_RESEARCH_QUALITY_QUEUE_PATH,
) -> dict[str, Any]:
    queue_path = Path(path)
    if not queue_path.exists():
        return {"status": "missing", "path": str(queue_path), "items": []}
    try:
        payload = json.loads(queue_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": "invalid", "path": str(queue_path), "error": str(exc), "items": []}
    if not isinstance(payload, dict):
        return {
            "status": "invalid",
            "path": str(queue_path),
            "error": "queue root must be a JSON object",
            "items": [],
        }
    items = [item for item in payload.get("items", []) if isinstance(item, dict)]
    action_by_ticker = {
        str(item.get("ticker") or ""): str(item.get("primary_action") or "")
        for item in items
        if item.get("ticker")
    }
    return {
        "status": "ok",
        "path": str(queue_path),
        "payload": payload,
        "items": items,
        "action_by_ticker": action_by_ticker,
    }


def load_research_brief_qa_sample(
    path: Path | str = DEFAULT_RESEARCH_BRIEF_QA_SAMPLE_PATH,
) -> dict[str, Any]:
    sample_path = Path(path)
    if not sample_path.exists():
        return {"status": "missing", "path": str(sample_path), "items": []}
    try:
        payload = json.loads(sample_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": "invalid", "path": str(sample_path), "error": str(exc), "items": []}
    if not isinstance(payload, dict):
        return {
            "status": "invalid",
            "path": str(sample_path),
            "error": "QA sample root must be a JSON object",
            "items": [],
        }
    items = [item for item in payload.get("items", []) if isinstance(item, dict)]
    return {"status": "ok", "path": str(sample_path), "payload": payload, "items": items}


def load_research_qa_action_queue(
    path: Path | str = DEFAULT_RESEARCH_QA_ACTION_QUEUE_PATH,
) -> dict[str, Any]:
    queue_path = Path(path)
    if not queue_path.exists():
        return {"status": "missing", "path": str(queue_path), "items": []}
    try:
        payload = json.loads(queue_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": "invalid", "path": str(queue_path), "error": str(exc), "items": []}
    if not isinstance(payload, dict):
        return {
            "status": "invalid",
            "path": str(queue_path),
            "error": "QA action queue root must be a JSON object",
            "items": [],
        }
    items = [item for item in payload.get("items", []) if isinstance(item, dict)]
    return {"status": "ok", "path": str(queue_path), "payload": payload, "items": items}


def _brief_row_to_dashboard_row(row: Any) -> dict[str, Any]:
    return {
        "report_date": str(row.report_date),
        "ticker": row.ticker,
        "source": row.source,
        "broker": row.broker or "",
        "title": row.title,
        "source_url": row.source_url or "",
        "body_text_status": row.source_quality,
        "summary": row.headline,
        "investment_opinion": row.opinion,
        "buy_thesis": row.stock_view or "",
        "sell_or_risk_thesis": row.risks or "",
        "growth_drivers": row.industry or row.new_business or "",
        "earnings_drivers": row.earnings or "",
        "valuation_view": row.valuation or "",
        "target_price_rationale": "",
        "risk_factors": row.risks or "",
        "evidence_terms": f"{row.report_type}, {row.source_quality}, {row.brief_version}",
        "report_type": row.report_type,
        "new_business": row.new_business or "",
        "confidence": float(row.confidence or 0.0),
    }


_RESEARCH_FILL_FIELDS = (
    "buy_thesis",
    "sell_or_risk_thesis",
    "growth_drivers",
    "earnings_drivers",
    "valuation_view",
    "target_price_rationale",
    "risk_factors",
    "new_business",
)
_RESEARCH_FIELD_KEYWORDS = {
    "buy_thesis": ("개선", "회복", "성장", "기대", "견인", "상회", "모멘텀"),
    "sell_or_risk_thesis": ("리스크", "둔화", "부담", "우려", "하락", "변동"),
    "growth_drivers": ("업황", "수요", "회복", "성장", "소비", "관광객", "시장", "견인"),
    "earnings_drivers": ("실적", "매출", "영업이익", "이익", "수익성", "마진", "개선", "상회"),
    "valuation_view": ("밸류", "밸류에이션", "목표주가", "상향", "여력", "부담"),
    "target_price_rationale": ("목표주가", "상향", "하향", "실적", "추정치", "밸류"),
    "risk_factors": ("리스크", "둔화", "부담", "우려", "환율", "변동", "경쟁"),
    "new_business": ("신규", "신사업", "모멘텀", "채널", "확대", "온라인", "면세점", "투자"),
}
_MIN_RESEARCH_FIELD_SCORE = 6
_SOURCE_QUALITY_RANK = {
    "full_text": 4,
    "partial_text": 3,
    "title_or_sparse": 2,
    "empty": 1,
    "not_pdf_response": 1,
    "not_pdf": 1,
    "fetch_failed": 0,
    "brief_failed": 0,
}
_NO_EXPLICIT_SECTION_TEXT = {
    "stock_view": "리포트에서 명시적인 종목 관점은 확인되지 않았습니다.",
    "growth": "리포트에서 명시적인 성장/업황 내용은 확인되지 않았습니다.",
    "earnings": "리포트에서 명시적인 실적 내용은 확인되지 않았습니다.",
    "risk": "리포트에서 명시적인 리스크 요인은 확인되지 않았습니다.",
}


def _enrich_sparse_research_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_ticker: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        ticker = str(row.get("ticker") or "")
        if ticker:
            by_ticker.setdefault(ticker, []).append(row)

    enriched_rows: list[dict[str, Any]] = []
    for row in rows:
        ticker = str(row.get("ticker") or "")
        peers = by_ticker.get(ticker, [])
        enriched = dict(row)
        filled_fields: list[str] = []
        for field in _RESEARCH_FILL_FIELDS:
            current_value = _best_clean_research_field_value(enriched.get(field), field)
            donor_value = _best_research_field_value(peers, field)
            current_score = _research_field_value_score(field, current_value)
            donor_score = _research_field_value_score(field, donor_value)
            if donor_value and (not current_value or donor_score > current_score + 2):
                enriched[field] = donor_value
                filled_fields.append(field)
            elif current_value:
                enriched[field] = current_value
        if filled_fields:
            best_quality = max((_quality_rank(peer) for peer in peers), default=0)
            if best_quality > _quality_rank(enriched):
                enriched["evidence_terms"] = (
                    f"{enriched.get('evidence_terms', '')}, "
                    f"enriched_from:{ticker}/full_text"
                ).strip(", ")
        enriched_rows.append(enriched)
    return enriched_rows


def _best_research_field_value(rows: list[dict[str, Any]], field: str) -> str:
    direct_min_score = 2 if field == "risk_factors" else 4
    direct_candidates = [
        (row, _best_clean_research_field_value(row.get(field), field, min_score=direct_min_score))
        for row in rows
    ]
    direct_candidates = [(row, value) for row, value in direct_candidates if value]
    if direct_candidates:
        row, value = max(
            direct_candidates,
            key=lambda item: (
                _research_field_value_score(field, item[1]),
                _quality_rank(item[0]),
                _to_float(item[0].get("confidence")),
                str(item[0].get("report_date") or ""),
            ),
        )
        return value

    candidates = [
        (row, _best_clean_research_field_value(value, field))
        for row in rows
        for value in _research_field_candidate_values(row, field)
    ]
    candidates = [(row, value) for row, value in candidates if value]
    if not candidates:
        return ""
    row, value = max(
        candidates,
        key=lambda item: (
            _research_field_value_score(field, item[1]),
            _quality_rank(item[0]),
            _to_float(item[0].get("confidence")),
            str(item[0].get("report_date") or ""),
        ),
    )
    return value


def _research_field_candidate_values(row: dict[str, Any], field: str) -> list[object]:
    values: list[object] = [row.get(field)]
    if field == "buy_thesis":
        values.extend([row.get("growth_drivers"), row.get("summary"), row.get("title")])
    elif field == "growth_drivers":
        values.extend([row.get("title"), row.get("summary"), row.get("buy_thesis")])
    elif field == "earnings_drivers":
        values.extend([row.get("summary"), row.get("buy_thesis"), row.get("title")])
    elif field == "new_business":
        values.extend([row.get("summary"), row.get("buy_thesis"), row.get("growth_drivers")])
    elif field == "risk_factors":
        values.extend([row.get("sell_or_risk_thesis")])
    elif field in {"valuation_view", "target_price_rationale"}:
        values.extend([row.get("summary"), row.get("buy_thesis")])
    elif field == "sell_or_risk_thesis":
        values.extend([row.get("risk_factors")])
    return values


def _best_clean_research_field_value(
    value: object,
    field: str,
    *,
    min_score: int = _MIN_RESEARCH_FIELD_SCORE,
) -> str:
    fragments = _clean_report_fragments(value)
    if not fragments:
        return ""
    best = max(fragments, key=lambda fragment: _research_field_value_score(field, fragment))
    if _research_field_value_score(field, best) < min_score:
        return ""
    return best


def _has_displayable_report_text(value: object) -> bool:
    return bool(_first_report_text(value))


def _research_field_value_score(field: str, value: object) -> int:
    text = str(value or "").strip()
    if not text:
        return 0
    score = 0
    if 18 <= len(text) <= 180:
        score += 4
    if text.endswith("."):
        score += 4
    if text.endswith(("다.", "다", "됨.", "예상된다.", "전망.", "전망된다.")):
        score += 4
    score += sum(2 for keyword in _RESEARCH_FIELD_KEYWORDS.get(field, ()) if keyword in text)
    if field not in {"valuation_view", "target_price_rationale"} and any(
        term in text for term in ("목표주가", "투자의견", "목표가")
    ):
        score -= 20
    numeric_tokens = [token for token in text.split() if any(ch.isdigit() for ch in token)]
    score -= min(8, max(0, len(numeric_tokens) - 1) * 2)
    if text.endswith(("고", "며", "를", "을", "로", "에", "의", "신규", "수요", "부")):
        score -= 6
    return score


def _quality_rank(row: dict[str, Any]) -> int:
    return _SOURCE_QUALITY_RANK.get(str(row.get("body_text_status") or ""), 0)


def filter_research_report_briefs(
    rows: list[dict[str, Any]],
    *,
    portfolio_tickers: set[str] | None = None,
    portfolio_only: bool = False,
    opinion: str = "all",
    source: str = "all",
    query: str = "",
) -> list[dict[str, Any]]:
    filtered = list(rows)
    if portfolio_only:
        filtered = [
            row
            for row in filtered
            if portfolio_tickers and str(row.get("ticker")) in portfolio_tickers
        ]
    if opinion != "all":
        filtered = [row for row in filtered if row.get("investment_opinion") == opinion]
    if source != "all":
        filtered = [row for row in filtered if row.get("source") == source]
    if query:
        needle = query.strip().lower()
        filtered = [
            row
            for row in filtered
            if needle
            and needle
            in " ".join(
                str(row.get(key, ""))
                for key in (
                    "ticker",
                    "title",
                    "summary",
                    "buy_thesis",
                    "growth_drivers",
                    "new_business",
                    "earnings_drivers",
                    "risk_factors",
                    "evidence_terms",
                )
            ).lower()
        ]
    return filtered


def build_ticker_research_briefs(
    rows: Iterable[dict[str, Any]],
    *,
    generated_at: str | None = None,
    max_source_reports: int = 5,
    llm_status: str = "disabled",
) -> dict[str, Any]:
    prepared_rows = _enrich_sparse_research_rows([dict(row) for row in rows])
    by_ticker: dict[str, list[dict[str, Any]]] = {}
    for row in prepared_rows:
        ticker = str(row.get("ticker") or "").strip()
        if ticker:
            by_ticker.setdefault(ticker, []).append(row)

    ticker_briefs = []
    for ticker, ticker_rows in by_ticker.items():
        sorted_rows = sorted(ticker_rows, key=_ticker_brief_row_key, reverse=True)
        latest = sorted_rows[0]
        best_quality_row = max(
            sorted_rows,
            key=lambda row: (_quality_rank(row), _to_float(row.get("confidence"))),
        )
        sections = {
            "stock_view": _best_research_field_value(sorted_rows, "buy_thesis"),
            "industry": _best_research_field_value(sorted_rows, "growth_drivers"),
            "growth": _best_research_field_value(sorted_rows, "growth_drivers"),
            "earnings": _best_research_field_value(sorted_rows, "earnings_drivers"),
            "valuation": _best_research_field_value(sorted_rows, "valuation_view"),
            "new_business": _best_research_field_value(sorted_rows, "new_business"),
            "risk": _best_research_field_value(sorted_rows, "risk_factors"),
        }
        sections = _finalize_ticker_sections(
            sections,
            source_quality=str(best_quality_row.get("body_text_status") or ""),
        )
        ticker_briefs.append(
            {
                "ticker": ticker,
                "latest_report_date": str(latest.get("report_date") or ""),
                "opinion": str(latest.get("investment_opinion") or ""),
                "headline": str(latest.get("summary") or latest.get("title") or ""),
                "sections": sections,
                "quality": {
                    "source_quality": str(best_quality_row.get("body_text_status") or ""),
                    "confidence": round(
                        max(_to_float(row.get("confidence")) for row in sorted_rows),
                        4,
                    ),
                    "report_count": len(sorted_rows),
                    "llm_status": llm_status,
                },
                "source_reports": [
                    _ticker_source_report(row)
                    for row in sorted_rows[: max(1, int(max_source_reports))]
                ],
            }
        )

    ticker_briefs.sort(key=lambda row: str(row.get("latest_report_date") or ""), reverse=True)
    full_text_count = sum(
        1
        for row in prepared_rows
        if str(row.get("body_text_status") or "") in {"full_text", "partial_text"}
    )
    return {
        "schema_version": 1,
        "brief_version": "ticker-brief-rule-v1",
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "summary": {
            "ticker_count": len(ticker_briefs),
            "source_report_count": len(prepared_rows),
            "body_text_available_count": full_text_count,
        },
        "llm": {
            "status": llm_status,
            "reason": "External LLM calls are opt-in and disabled by default.",
        },
        "tickers": ticker_briefs,
    }


def _finalize_ticker_sections(sections: dict[str, str], *, source_quality: str) -> dict[str, str]:
    finalized = dict(sections)
    if source_quality in {"full_text", "partial_text"}:
        for section, fallback in _NO_EXPLICIT_SECTION_TEXT.items():
            if not _first_report_text(finalized.get(section)):
                finalized[section] = fallback
    return finalized


def save_ticker_research_briefs(
    path: Path | str = DEFAULT_TICKER_RESEARCH_BRIEF_PATH,
    *,
    rows: Iterable[dict[str, Any]] | None = None,
    database_url: str | None = None,
    llm_status: str = "disabled",
) -> dict[str, Any]:
    if rows is None:
        loaded = load_research_report_briefs(database_url=database_url)
        if loaded.get("status") != "ok":
            return {
                "status": "invalid",
                "error": loaded.get("error", "failed to load research report briefs"),
                "path": str(path),
            }
        rows = loaded["rows"]

    artifact = build_ticker_research_briefs(rows, llm_status=llm_status)
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {"status": "ok", "path": str(output_path), "artifact": artifact}


def build_ticker_research_quality_report(
    artifact: dict[str, Any],
    *,
    portfolio_tickers: set[str] | None = None,
    now: datetime | None = None,
    stale_days: int = 45,
) -> dict[str, Any]:
    tickers = [row for row in artifact.get("tickers", []) if isinstance(row, dict)]
    portfolio = {str(ticker) for ticker in (portfolio_tickers or set()) if ticker}
    by_ticker = {str(row.get("ticker")): row for row in tickers if row.get("ticker")}
    issues: list[dict[str, Any]] = []
    complete_count = 0
    reference = now or datetime.now(timezone.utc)
    required_sections = ("stock_view", "growth", "earnings", "risk")

    for row in tickers:
        sections = row.get("sections") or {}
        quality = row.get("quality") or {}
        missing_sections = [
            section for section in required_sections if not _first_report_text(sections.get(section))
        ]
        reasons: list[str] = []
        if missing_sections:
            reasons.append("missing_sections")
        report_age_days = _report_age_days(row.get("latest_report_date"), reference)
        if report_age_days is not None and report_age_days > stale_days:
            reasons.append("stale_report")
        confidence = _to_float(quality.get("confidence"))
        if confidence < 0.5:
            reasons.append("low_confidence")
        source_quality = str(quality.get("source_quality") or "")
        if source_quality not in {"full_text", "partial_text"}:
            reasons.append("weak_source_quality")
        if not reasons:
            complete_count += 1
            continue
        issues.append(
            {
                "ticker": str(row.get("ticker") or ""),
                "latest_report_date": str(row.get("latest_report_date") or ""),
                "missing_sections": missing_sections,
                "reasons": reasons,
                "confidence": confidence,
                "source_quality": source_quality,
                "report_count": int(_to_float(quality.get("report_count"))),
                "report_age_days": report_age_days,
            }
        )

    portfolio_missing = sorted(ticker for ticker in portfolio if ticker not in by_ticker)
    issues.sort(
        key=lambda item: (
            len(item["reasons"]),
            len(item["missing_sections"]),
            item.get("report_age_days") or 0,
        ),
        reverse=True,
    )
    return {
        "summary": {
            "ticker_count": len(tickers),
            "complete_count": complete_count,
            "issue_count": len(issues),
            "portfolio_missing_count": len(portfolio_missing),
        },
        "issues": issues,
        "portfolio_missing": portfolio_missing,
    }


def _quality_dashboard_summary(
    quality_report: dict[str, Any],
    queue_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    summary = dict(quality_report.get("summary") or {})
    issues = [item for item in quality_report.get("issues", []) if isinstance(item, dict)]
    action_by_ticker = {}
    if queue_result and queue_result.get("status") == "ok":
        action_by_ticker = dict(queue_result.get("action_by_ticker") or {})
    latest_not_found_count = sum(
        1
        for issue in issues
        if action_by_ticker.get(str(issue.get("ticker") or "")) == "latest_report_not_found"
    )
    issue_count = int(_to_float(summary.get("issue_count")))
    summary["latest_report_not_found_count"] = latest_not_found_count
    summary["actionable_issue_count"] = max(0, issue_count - latest_not_found_count)
    return summary


def _research_operator_next_action_html(quality_summary: dict[str, Any]) -> str:
    actionable = int(_to_float(quality_summary.get("actionable_issue_count")))
    latest_not_found = int(_to_float(quality_summary.get("latest_report_not_found_count")))
    portfolio_missing = int(_to_float(quality_summary.get("portfolio_missing_count")))
    complete = int(_to_float(quality_summary.get("complete_count")))
    if portfolio_missing:
        title = "Portfolio research gap"
        next_step = (
            "Run supplemental discovery first. If a portfolio ticker still has no brief, "
            "use the supplement template for that ticker."
        )
        command = (
            "powershell.exe -ExecutionPolicy Bypass -File .\\scripts\\refresh_public_portfolio_snapshot.ps1 "
            "-RunOnce -RunTimeoutMinutes 10 -IncludeSupplementalDiscovery"
        )
    elif actionable:
        title = "Automated quality pass"
        next_step = (
            "Run one supplemental discovery refresh before manual review. It searches candidates, "
            "verifies text, ingests verified rows, and rebuilds ticker briefs."
        )
        command = (
            "powershell.exe -ExecutionPolicy Bypass -File .\\scripts\\refresh_public_portfolio_snapshot.ps1 "
            "-RunOnce -RunTimeoutMinutes 10 -IncludeSupplementalDiscovery"
        )
    elif latest_not_found:
        title = "Latest-report backlog tracked"
        next_step = (
            "No immediate manual work. These tickers are tracked separately as latest report not found; "
            "check again after the next broad source refresh."
        )
        command = ".\\venv\\Scripts\\python.exe -m scripts.public_dashboard_ops --max-age-minutes 35"
    else:
        title = "Research queue clean"
        next_step = "No manual research task right now. Keep the 30-minute refresh loop running."
        command = ".\\venv\\Scripts\\python.exe -m scripts.public_dashboard_ops --max-age-minutes 35"
    return f"""
    <div class="research-card op-next">
      <div class="head">
        <div>
          <div class="meta">Operator Next Action · 자동화 우선</div>
          <div class="title">{html.escape(title)}</div>
        </div>
        <div class="pill">complete {complete}</div>
      </div>
      <div class="research-grid">
        <div class="research-cell"><b>Next step</b>{html.escape(next_step)}</div>
        <div class="research-cell"><b>Command</b><span class="mono">{html.escape(command)}</span></div>
      </div>
    </div>
    """


def build_research_qa_sample_summary(sample_result: dict[str, Any]) -> dict[str, int]:
    items = [item for item in sample_result.get("items", []) if isinstance(item, dict)]
    reviewed = 0
    source_refresh = 0
    section_rewrite = 0
    issue_category_count = 0
    for item in items:
        review_status = str(item.get("review_status") or "").strip().lower()
        if review_status and review_status not in {"pending", "todo", "not_reviewed"}:
            reviewed += 1
        if _truthy_review_flag(item.get("needs_source_refresh")):
            source_refresh += 1
        if _truthy_review_flag(item.get("needs_section_rewrite")):
            section_rewrite += 1
        if str(item.get("issue_category") or "").strip():
            issue_category_count += 1
    total = len(items)
    return {
        "sample_count": total,
        "reviewed_count": reviewed,
        "pending_count": max(0, total - reviewed),
        "source_refresh_count": source_refresh,
        "section_rewrite_count": section_rewrite,
        "issue_category_count": issue_category_count,
    }


def _truthy_review_flag(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "needs", "needed", "필요"}


def _research_qa_summary_html(sample_result: dict[str, Any]) -> str:
    if sample_result.get("status") == "missing":
        return """
        <div class="research-card op-next">
          <div class="head"><div><div class="meta">QA Sample</div><div class="title">QA sample missing</div></div><div class="pill">pending</div></div>
          <div class="research-grid">
            <div class="research-cell"><b>Next step</b>Run the public dashboard artifact refresh to export a QA sample.</div>
          </div>
        </div>
        """
    if sample_result.get("status") != "ok":
        error = html.escape(str(sample_result.get("error") or "unknown error"))
        return f"""
        <div class="research-card op-next">
          <div class="head"><div><div class="meta">QA Sample</div><div class="title">QA sample invalid</div></div><div class="pill">check</div></div>
          <div class="research-grid">
            <div class="research-cell"><b>Error</b>{error}</div>
          </div>
        </div>
        """
    summary = build_research_qa_sample_summary(sample_result)
    if summary["sample_count"] == 0:
        title = "QA sample empty"
        next_step = "Run the public dashboard artifact refresh to export fresh QA samples."
    elif summary["pending_count"]:
        title = "QA review pending"
        next_step = "Review sampled briefs first; mark review_status and needs_* fields so trust metrics can improve."
    else:
        title = "QA sample reviewed"
        next_step = "No pending QA sample rows. Continue monitoring source refresh and section rewrite counts."
    return f"""
    <div class="research-card op-next">
      <div class="head">
        <div>
          <div class="meta">QA Sample Trust · 수동 검토 연결</div>
          <div class="title">{html.escape(title)}</div>
        </div>
        <div class="pill">pending {summary['pending_count']}</div>
      </div>
      <div class="research-grid">
        <div class="research-cell"><b>Reviewed</b>{summary['reviewed_count']} / {summary['sample_count']}</div>
        <div class="research-cell"><b>Source refresh</b>{summary['source_refresh_count']}</div>
        <div class="research-cell"><b>Section rewrite</b>{summary['section_rewrite_count']}</div>
        <div class="research-cell"><b>Next step</b>{html.escape(next_step)}</div>
      </div>
    </div>
    """


def build_research_qa_action_summary(queue_result: dict[str, Any]) -> dict[str, int]:
    items = [item for item in queue_result.get("items", []) if isinstance(item, dict)]
    section_rewrite = 0
    source_refresh = 0
    for item in items:
        actions = {str(action) for action in item.get("actions", [])}
        if "section_rewrite" in actions:
            section_rewrite += 1
        if "source_refresh" in actions:
            source_refresh += 1
    payload_summary = queue_result.get("payload", {}).get("summary", {})
    sample_count = int(payload_summary.get("sample_count") or 0)
    attempted_no_new_source = int(
        payload_summary.get("source_refresh_attempted_no_new_source_count") or 0
    )
    return {
        "sample_count": sample_count,
        "action_item_count": len(items),
        "section_rewrite_count": section_rewrite,
        "source_refresh_count": source_refresh,
        "source_refresh_attempted_no_new_source_count": attempted_no_new_source,
    }


def _research_qa_action_queue_html(queue_result: dict[str, Any]) -> str:
    if queue_result.get("status") == "missing":
        return """
        <div class="research-card op-next">
          <div class="head"><div><div class="meta">해야 할 작업</div><div class="title">작업 큐 파일이 없습니다</div></div><div class="pill">대기</div></div>
          <div class="research-grid">
            <div class="research-cell"><b>다음 작업</b>공개 대시보드 갱신을 실행해서 자동 QA 작업 큐를 먼저 생성하세요.</div>
          </div>
        </div>
        """
    if queue_result.get("status") != "ok":
        error = html.escape(str(queue_result.get("error") or "unknown error"))
        return f"""
        <div class="research-card op-next">
          <div class="head"><div><div class="meta">해야 할 작업</div><div class="title">작업 큐 파일을 읽지 못했습니다</div></div><div class="pill">확인 필요</div></div>
          <div class="research-grid">
            <div class="research-cell"><b>오류</b>{error}</div>
          </div>
        </div>
        """
    summary = build_research_qa_action_summary(queue_result)
    items = [item for item in queue_result.get("items", []) if isinstance(item, dict)]
    if summary["action_item_count"]:
        title = "자동 QA 작업이 준비됐습니다"
        next_step = "수동 검토 전에 소스 보강 또는 섹션 재작성 작업부터 처리하세요."
    else:
        title = "지금 처리할 자동 QA 작업이 없습니다"
        if summary["source_refresh_attempted_no_new_source_count"]:
            next_step = (
                "소스 탐색 완료 후 신규 공개 소스가 없는 항목은 작업 큐에서 제외했습니다. "
                "30분 갱신 루프를 유지하면 새 QA 플래그가 생길 때 이 탭에 표시됩니다."
            )
        else:
            next_step = "30분 갱신 루프를 유지하면 새 QA 플래그가 생길 때 이 탭에 작업이 표시됩니다."
    rows = []
    for item in items[:6]:
        ticker = html.escape(str(item.get("ticker") or ""))
        primary_action = html.escape(_qa_action_label(str(item.get("primary_action") or "")))
        latest = html.escape(str(item.get("latest_report_date") or "-"))
        reasons = html.escape(", ".join(_qa_reason_label(str(reason)) for reason in item.get("auto_issue_reasons", [])[:3]) or "-")
        rows.append(
            "<div class='sig warn'>"
            f"<span class='src'>{ticker}</span>"
            f"<span class='detail'>{primary_action} · {reasons}</span>"
            f"<span class='right'>{latest}</span>"
            "</div>"
        )
    rows_html = "\n".join(rows) or "<div class='sig-empty'>No active QA action</div>"
    return f"""
    <div class="research-card op-next">
      <div class="head">
        <div>
          <div class="meta">해야 할 작업 · 자동 QA 작업 큐</div>
          <div class="title">{html.escape(title)}</div>
        </div>
        <div class="pill">작업 {summary['action_item_count']}</div>
      </div>
      <div class="research-grid">
        <div class="research-cell"><b>섹션 재작성</b>{summary['section_rewrite_count']}</div>
        <div class="research-cell"><b>소스 보강</b>{summary['source_refresh_count']}</div>
        <div class="research-cell"><b>탐색 완료</b>{summary['source_refresh_attempted_no_new_source_count']}</div>
        <div class="research-cell"><b>QA 샘플</b>{summary['sample_count']}</div>
        <div class="research-cell"><b>다음 작업</b>{html.escape(next_step)}</div>
      </div>
      {rows_html}
    </div>
    """


def _qa_action_label(action: str) -> str:
    labels = {
        "section_rewrite": "섹션 재작성",
        "source_refresh": "소스 보강",
    }
    return labels.get(action, action or "-")


def _qa_reason_label(reason: str) -> str:
    labels = {
        "stale_or_missing_latest_report": "최신 리포트 보강 필요",
        "weak_source_quality": "본문 근거 부족",
        "headline:starts_mid_sentence": "제목 문장 깨짐",
        "headline:ends_mid_sentence": "제목 문장 잘림",
        "stock_view:starts_mid_sentence": "종목 의견 문장 깨짐",
        "valuation:starts_mid_sentence": "밸류 문장 깨짐",
        "earnings:starts_mid_sentence": "실적 문장 깨짐",
        "risk:explicit_empty_section": "리스크 섹션 비어 있음",
        "growth:explicit_empty_section": "성장 섹션 비어 있음",
        "stock_view:explicit_empty_section": "종목 의견 섹션 비어 있음",
    }
    return labels.get(reason, reason or "-")


def _research_qa_action_item_html(item: dict[str, Any]) -> str:
    ticker = html.escape(str(item.get("ticker") or ""))
    latest = html.escape(str(item.get("latest_report_date") or "-"))
    actions = ", ".join(_qa_action_label(str(action)) for action in item.get("actions", [])) or "-"
    reasons = ", ".join(_qa_reason_label(str(reason)) for reason in item.get("auto_issue_reasons", [])) or "-"
    next_step = str(item.get("suggested_next_step") or "")
    if next_step == "Run supplemental source discovery for this ticker before another QA pass.":
        next_step = "이 종목의 최신 공개 리포트나 원문 PDF를 먼저 보강한 뒤 QA를 다시 돌립니다."
    elif next_step == "Re-run stored report body analysis for this ticker, then regenerate ticker briefs and QA artifacts.":
        next_step = "저장된 리포트 본문 분석을 다시 돌린 뒤 종목 브리프와 QA 산출물을 재생성합니다."
    elif next_step == "Refresh source coverage first, then re-run body analysis and regenerate QA artifacts.":
        next_step = "소스 보강을 먼저 실행하고, 이후 본문 재분석과 QA 산출물 재생성을 진행합니다."
    return f"""
    <div class="research-card">
      <div class="head">
        <div>
          <div class="meta">작업 대상 · {ticker}</div>
          <div class="title">{html.escape(_qa_action_label(str(item.get('primary_action') or '')))}</div>
        </div>
        <div class="pill">{latest}</div>
      </div>
      <div class="research-grid">
        <div class="research-cell"><b>필요 작업</b>{html.escape(actions)}</div>
        <div class="research-cell"><b>감지 이유</b>{html.escape(reasons)}</div>
        <div class="research-cell"><b>다음 처리</b>{html.escape(next_step or '작업 큐의 명령을 기준으로 처리합니다.')}</div>
      </div>
    </div>
    """


def _actionable_quality_issues(
    quality_report: dict[str, Any],
    queue_result: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    issues = [item for item in quality_report.get("issues", []) if isinstance(item, dict)]
    if not queue_result or queue_result.get("status") != "ok":
        return issues
    action_by_ticker = dict(queue_result.get("action_by_ticker") or {})
    return [
        issue
        for issue in issues
        if action_by_ticker.get(str(issue.get("ticker") or "")) != "latest_report_not_found"
    ]


def _latest_not_found_quality_issues(
    quality_report: dict[str, Any],
    queue_result: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    issues = [item for item in quality_report.get("issues", []) if isinstance(item, dict)]
    if not queue_result or queue_result.get("status") != "ok":
        return []
    action_by_ticker = dict(queue_result.get("action_by_ticker") or {})
    return [
        issue
        for issue in issues
        if action_by_ticker.get(str(issue.get("ticker") or "")) == "latest_report_not_found"
    ]


def build_research_supplement_needs(
    artifact: dict[str, Any],
    positions: list[dict[str, Any]],
    *,
    now: datetime | None = None,
    stale_days: int = 45,
) -> list[dict[str, Any]]:
    portfolio_tickers = {str(position.get("ticker")) for position in positions if position.get("ticker")}
    names = {
        str(position.get("ticker")): str(position.get("name") or "")
        for position in positions
        if position.get("ticker")
    }
    quality_report = build_ticker_research_quality_report(
        artifact,
        portfolio_tickers=portfolio_tickers,
        now=now,
        stale_days=stale_days,
    )
    needs: list[dict[str, Any]] = []
    for ticker in quality_report.get("portfolio_missing", []):
        needs.append(
            {
                "ticker": ticker,
                "name": names.get(ticker, ""),
                "status": "missing_brief",
                "latest_report_date": "",
                "reasons": ["missing_brief"],
                "missing_sections": ["stock_view", "growth", "earnings", "risk"],
                "source_quality": "",
                "confidence": 0.0,
                "report_count": 0,
                "report_age_days": None,
            }
        )
    for issue in quality_report.get("issues", []):
        ticker = str(issue.get("ticker") or "")
        if portfolio_tickers and ticker not in portfolio_tickers:
            continue
        needs.append(
            {
                "ticker": ticker,
                "name": names.get(ticker, ""),
                "status": "needs_review",
                "latest_report_date": str(issue.get("latest_report_date") or ""),
                "reasons": list(issue.get("reasons") or []),
                "missing_sections": list(issue.get("missing_sections") or []),
                "source_quality": str(issue.get("source_quality") or ""),
                "confidence": _to_float(issue.get("confidence")),
                "report_count": int(_to_float(issue.get("report_count"))),
                "report_age_days": issue.get("report_age_days"),
            }
        )
    priority = {"missing_brief": 0, "needs_review": 1}
    needs.sort(key=lambda row: (priority.get(str(row.get("status")), 9), str(row.get("ticker") or "")))
    return needs


def _source_quality_label(value: object) -> str:
    source_quality = str(value or "").strip()
    labels = {
        "full_text": "Full text · 원문 기반",
        "partial_text": "Partial text · 일부 본문",
        "supplemental_summary": "Supplemental · 수동 보충",
        "title_or_sparse": "Sparse · 제목/요약 중심",
        "not_pdf": "Metadata · PDF 아님",
        "not_requested": "Metadata · 본문 미요청",
        "login_required": "Locked · 로그인 필요",
        "fetch_failed": "Fetch failed · 수집 실패",
        "analysis_failed": "Analysis failed · 분석 실패",
        "brief_failed": "Brief fallback · 브리프 보정",
    }
    return labels.get(source_quality, source_quality)


def _report_age_days(value: object, reference: datetime) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        report_date = datetime.fromisoformat(text[:10])
    except ValueError:
        return None
    if reference.tzinfo is not None:
        report_date = report_date.replace(tzinfo=reference.tzinfo)
    return max(0, (reference - report_date).days)


def _ticker_brief_row_key(row: dict[str, Any]) -> tuple[str, int, float]:
    return (
        str(row.get("report_date") or ""),
        _quality_rank(row),
        _to_float(row.get("confidence")),
    )


def _ticker_source_report(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "report_date": str(row.get("report_date") or ""),
        "source": str(row.get("source") or ""),
        "broker": str(row.get("broker") or ""),
        "title": str(row.get("title") or ""),
        "url": str(row.get("source_url") or ""),
        "source_quality": str(row.get("body_text_status") or ""),
        "confidence": _to_float(row.get("confidence")),
        "evidence_terms": str(row.get("evidence_terms") or ""),
    }


def research_report_display_limit(choice: str, total_count: int) -> int:
    if choice == "all":
        return max(0, total_count)
    try:
        return max(1, int(choice))
    except (TypeError, ValueError):
        return DEFAULT_VISIBLE_RESEARCH_CARDS


def snapshot_is_stale(
    snapshot: dict[str, Any],
    now: datetime | None = None,
    max_age_hours: int = 24,
) -> bool:
    generated_at = snapshot.get("generated_at")
    if not generated_at:
        return True
    try:
        generated = datetime.fromisoformat(str(generated_at))
    except ValueError:
        return True
    if generated.tzinfo is None:
        generated = generated.replace(tzinfo=timezone.utc)
    reference_time = now or datetime.now(generated.tzinfo)
    if reference_time.tzinfo is None:
        reference_time = reference_time.replace(tzinfo=generated.tzinfo)
    return (reference_time.astimezone(generated.tzinfo) - generated).total_seconds() > (
        max_age_hours * 3600
    )


# ─────────────────────────── Formatters ────────────────────────────────────
def _to_float(value: Any, default: float = 0.0) -> float:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def format_krw(value: Any) -> str:
    """Public formatter kept for backwards compatibility with tests."""
    if value is None:
        return "-"
    try:
        return f"{float(value):,.0f} KRW"
    except (TypeError, ValueError):
        return "-"


def format_pct(value: Any) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):.2f}%"
    except (TypeError, ValueError):
        return "-"


def _krw_int(value: Any) -> str:
    """Pure integer-comma string for in-design display: 1,234,567"""
    if value is None:
        return "—"
    try:
        return f"{int(round(float(value))):,}"
    except (TypeError, ValueError):
        return "—"


def _krw_short(value: Any) -> str:
    """1,234,567 → 123.5만 / 1.23억 style for compact cells."""
    if value is None:
        return "—"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "—"
    sign = "-" if v < 0 else ""
    n = abs(v)
    if n >= 1e8:
        return f"{sign}{n / 1e8:.2f}억"
    if n >= 1e4:
        return f"{sign}{n / 1e4:.1f}만"
    return f"{sign}{n:,.0f}"


def _pct_signed(value: Any) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):+.2f}%"
    except (TypeError, ValueError):
        return "—"


def _ratio_pct(value: Any) -> str:
    if value in (None, ""):
        return "—"
    try:
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return "—"


def _is_gain(value: Any) -> bool:
    try:
        return float(value) >= 0
    except (TypeError, ValueError):
        return True


# ─────────────────────────── Synthetic series ──────────────────────────────
def _seeded_random(seed_text: str) -> Iterable[float]:
    """Deterministic float stream so spark lines per ticker are stable across runs."""
    digest = hashlib.md5(seed_text.encode("utf-8")).digest()
    state = int.from_bytes(digest[:4], "big") | 1
    def gen():
        nonlocal state
        while True:
            state = (state * 1664525 + 1013904223) & 0xFFFFFFFF
            yield (state % 100000) / 100000.0
    return gen()


def _spark_points(ticker: str, current_price: float, day_change_pct: float, n: int = 30) -> list[float]:
    rng = _seeded_random(ticker)
    pts: list[float] = []
    v = current_price / (1 + day_change_pct / 100 * 4) if current_price else 0.0
    if not v:
        return [0.0] * n
    for i in range(n):
        r = next(rng)
        drift = (current_price - v) / max(1, n - i)
        noise = (r - 0.5) * current_price * 0.012
        v = v + drift + noise
        pts.append(v)
    pts[-1] = current_price
    return pts


def _ensure_equity_curve(snapshot: dict[str, Any]) -> list[float]:
    curve = snapshot.get("equity_curve")
    if isinstance(curve, list) and len(curve) >= 2:
        return [_to_float(v) for v in curve]
    # synthesize from current total + a deterministic random walk
    summary = snapshot.get("summary") or {}
    end = _to_float(summary.get("total_asset_value") or summary.get("total_market_value"))
    cost = _to_float(summary.get("total_cost")) or end
    if not end:
        return [0.0] * 30
    rng = _seeded_random("equity_curve")
    n = 30
    pts: list[float] = []
    v = cost
    for i in range(n):
        r = next(rng)
        drift = (end - v) / max(1, n - i)
        noise = (r - 0.5) * end * 0.006
        v += drift + noise
        pts.append(v)
    pts[-1] = end
    return pts


def _ensure_day_change(position: dict[str, Any]) -> tuple[float, float]:
    """Return (day_change_pct, day_change_amount). Synthesizes from ticker if missing."""
    pct = position.get("day_change_pct")
    amt = position.get("day_change_amount")
    if pct is not None:
        pct_v = _to_float(pct)
    else:
        rng = _seeded_random("day_" + str(position.get("ticker", "")))
        # ±2.5% with sign biased by overall P&L sign
        bias = 1.0 if _is_gain(position.get("profit_loss_rate")) else -1.0
        pct_v = (next(rng) - 0.4) * 2.5 * bias
    if amt is not None:
        amt_v = _to_float(amt)
    else:
        cur = _to_float(position.get("current_price"))
        amt_v = cur * (pct_v / 100.0) if cur else 0.0
    return pct_v, amt_v


def _ensure_market(snapshot: dict[str, Any]) -> dict[str, Any]:
    m = snapshot.get("market")
    if isinstance(m, dict) and m:
        return m
    return {
        "status": "CLOSED",
        "session_label": "정규장 마감",
        "kospi":    {"value": 2752.34, "chg_pct":  0.42},
        "kosdaq":   {"value":  892.10, "chg_pct": -0.18},
        "usdkrw":   {"value": 1342.50, "chg_pct": -0.12},
        "bonds10y": {"value":   3.45,  "chg_pct":  0.02},
    }


# ─────────────────────────── SVG sparkline ─────────────────────────────────
def _spark_svg(points: list[float], color: str, width: int = 90, height: int = 28,
               fill: bool = True) -> str:
    if not points or len(points) < 2:
        return ""
    lo, hi = min(points), max(points)
    rng = (hi - lo) or 1.0
    step_x = width / (len(points) - 1)
    coords = [
        (i * step_x, height - ((p - lo) / rng) * (height - 2) - 1)
        for i, p in enumerate(points)
    ]
    path_line = "M " + " L ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
    path_area = path_line + f" L {coords[-1][0]:.1f},{height} L 0,{height} Z"
    last_x, last_y = coords[-1]
    grad_id = "sp" + hashlib.md5(f"{points[0]}{points[-1]}{color}{width}".encode()).hexdigest()[:6]
    fill_block = (
        f"<defs><linearGradient id='{grad_id}' x1='0' x2='0' y1='0' y2='1'>"
        f"<stop offset='0%' stop-color='{color}' stop-opacity='0.35'/>"
        f"<stop offset='100%' stop-color='{color}' stop-opacity='0'/>"
        f"</linearGradient></defs>"
        f"<path d='{path_area}' fill='url(#{grad_id})'/>"
    ) if fill else ""
    return (
        f"<svg viewBox='0 0 {width} {height}' width='{width}' height='{height}' "
        f"preserveAspectRatio='none' style='display:block;'>"
        f"{fill_block}"
        f"<path d='{path_line}' fill='none' stroke='{color}' stroke-width='1.4' "
        f"stroke-linejoin='round' stroke-linecap='round'/>"
        f"<circle cx='{last_x:.1f}' cy='{last_y:.1f}' r='1.8' fill='{color}'/>"
        f"</svg>"
    )


def _hero_spark_svg(points: list[float], color: str, height: int = 110) -> str:
    if not points or len(points) < 2:
        return ""
    width = 600  # viewBox width — SVG scales to container via preserveAspectRatio
    lo, hi = min(points), max(points)
    rng = (hi - lo) or 1.0
    step_x = width / (len(points) - 1)
    coords = [
        (i * step_x, height - ((p - lo) / rng) * (height - 14) - 7)
        for i, p in enumerate(points)
    ]
    line = "M " + " L ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
    area = line + f" L {width},{height} L 0,{height} Z"
    last_x, last_y = coords[-1]
    return (
        f"<svg viewBox='0 0 {width} {height}' width='100%' height='{height}' "
        f"preserveAspectRatio='none' style='display:block;'>"
        f"<defs>"
        f"<linearGradient id='hsk' x1='0' x2='0' y1='0' y2='1'>"
        f"<stop offset='0%' stop-color='{color}' stop-opacity='0.32'/>"
        f"<stop offset='100%' stop-color='{color}' stop-opacity='0'/>"
        f"</linearGradient>"
        f"<pattern id='hgrid' width='{width/6}' height='{height/3}' patternUnits='userSpaceOnUse'>"
        f"<path d='M {width/6} 0 L 0 0 0 {height/3}' fill='none' stroke='var(--line)' stroke-width='0.5'/>"
        f"</pattern>"
        f"</defs>"
        f"<rect width='{width}' height='{height}' fill='url(#hgrid)' opacity='0.5'/>"
        f"<path d='{area}' fill='url(#hsk)'/>"
        f"<path d='{line}' fill='none' stroke='{color}' stroke-width='1.8' stroke-linejoin='round'/>"
        f"<circle cx='{last_x:.1f}' cy='{last_y:.1f}' r='3.5' fill='{color}'/>"
        f"<circle cx='{last_x:.1f}' cy='{last_y:.1f}' r='7' fill='none' stroke='{color}' stroke-opacity='0.35' stroke-width='1'/>"
        f"</svg>"
    )


def _factor_stripe_svg(scores: dict[str, Any]) -> str:
    """7 mini bars showing factor scores."""
    if not scores:
        return ""
    max_abs = 1.2
    width = 110
    height = 22
    seg_w = width / len(FACTOR_KEYS)
    bars = []
    for i, k in enumerate(FACTOR_KEYS):
        v = _to_float(scores.get(k))
        pct = min(1.0, abs(v) / max_abs)
        bar_h = pct * (height - 2)
        color = "var(--loss)" if v < 0 else "var(--accent)"
        bars.append(
            f"<rect x='{i * seg_w + 1:.1f}' y='0' width='{seg_w - 2:.1f}' height='{height}' "
            f"fill='var(--bg-1)' rx='1'/>"
            f"<rect x='{i * seg_w + 1:.1f}' y='{height - bar_h - 1:.1f}' "
            f"width='{seg_w - 2:.1f}' height='{bar_h:.1f}' fill='{color}' rx='1'>"
            f"<title>{FACTOR_LABELS[k]}: {v:+.2f}</title></rect>"
        )
    return (
        f"<svg viewBox='0 0 {width} {height}' width='{width}' height='{height}' "
        f"style='display:block;margin-left:auto;'>"
        + "".join(bars) +
        f"</svg>"
    )


# ─────────────────────────── CSS ───────────────────────────────────────────
def _build_css(density: str, cc: str, accent_hex: str, font_sans: str, font_mono: str) -> str:
    # color-convention overrides
    if cc == "us":
        gain, gain_bg, gain_bg_2 = "#34d399", "rgba(52,211,153,0.10)", "rgba(52,211,153,0.18)"
        loss, loss_bg, loss_bg_2 = "#ff6b6b", "rgba(255,107,107,0.10)", "rgba(255,107,107,0.18)"
    elif cc == "neutral":
        gain, gain_bg, gain_bg_2 = "#f2c94c", "rgba(242,201,76,0.10)", "rgba(242,201,76,0.18)"
        loss, loss_bg, loss_bg_2 = "#8a94a4", "rgba(138,148,164,0.10)", "rgba(138,148,164,0.18)"
    else:  # kr
        gain, gain_bg, gain_bg_2 = "#ff445e", "rgba(255,68,94,0.10)", "rgba(255,68,94,0.18)"
        loss, loss_bg, loss_bg_2 = "#4aa3ff", "rgba(74,163,255,0.10)", "rgba(74,163,255,0.18)"

    if density == "compact":
        gap, gap_lg, pad = "6px", "8px", "10px"
    elif density == "comfy":
        gap, gap_lg, pad = "12px", "18px", "18px"
    else:
        gap, gap_lg, pad = "8px", "12px", "14px"

    # accent_dim / accent_bg derived from hex
    r, g, b = int(accent_hex[1:3], 16), int(accent_hex[3:5], 16), int(accent_hex[5:7], 16)
    accent_dim = f"rgba({r},{g},{b},0.55)"
    accent_bg  = f"rgba({r},{g},{b},0.10)"

    return f"""
<style>
:root {{
  --bg-0: #07090d; --bg-1: #0c1118; --bg-2: #11161f; --bg-3: #161c26; --bg-4: #1c2330;
  --line: #232b3a; --line-2: #2c3648; --line-strong: #3a4760;
  --tx-0: #f1f3f7; --tx-1: #cfd5df; --tx-2: #8a94a4; --tx-3: #5b6473; --tx-4: #3a4458;
  --gain: {gain}; --gain-bg: {gain_bg}; --gain-bg-2: {gain_bg_2};
  --loss: {loss}; --loss-bg: {loss_bg}; --loss-bg-2: {loss_bg_2};
  --accent: {accent_hex}; --accent-dim: {accent_dim}; --accent-bg: {accent_bg};
  --ok: #34d399; --warn: #f59e0b; --neutral: #9aa4b2;
  --sans: {font_sans};
  --mono: {font_mono};
  --gap: {gap}; --gap-lg: {gap_lg}; --pad: {pad}; --radius: 4px;
}}

/* Streamlit chrome ─────────────── */
.stApp {{ background: var(--bg-0); color: var(--tx-1); }}
html, body, [class*="st-"], .stMarkdown {{ font-family: var(--sans); font-feature-settings: "ss01","cv11"; }}
.block-container {{ padding: 0.8rem 1.2rem 3rem; max-width: 1520px; }}
header[data-testid="stHeader"] {{ background: transparent; height: 0; }}
#MainMenu, footer {{ visibility: hidden; }}
.stDeployButton {{ display: none; }}
[data-testid="stSidebar"] {{ background: var(--bg-1); border-right: 1px solid var(--line); }}
[data-testid="stSidebar"] * {{ color: var(--tx-1) !important; }}
[data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {{ color: var(--tx-0) !important; font-family: var(--mono); font-size: 0.85rem !important; text-transform: uppercase; letter-spacing: 0.12em; }}
[data-testid="stSidebar"] label p {{ color: var(--tx-2) !important; font-size: 0.78rem !important; }}

.num, .mono {{ font-family: var(--mono); font-variant-numeric: tabular-nums; letter-spacing: -0.01em; }}

/* Top status bar ───────────────── */
.topbar {{
  display: grid; grid-template-columns: auto 1fr auto;
  align-items: center; gap: 18px;
  padding: 10px 14px;
  background: var(--bg-1); border: 1px solid var(--line); border-radius: var(--radius);
  margin-bottom: 10px;
}}
.brand {{
  display: flex; align-items: center; gap: 12px;
  font-family: var(--mono); font-size: 12.5px; color: var(--tx-0);
  text-transform: uppercase; letter-spacing: 0.1em;
  min-width: 0; overflow-wrap: anywhere;
}}
.brand .dot {{ width: 8px; height: 8px; border-radius: 50%; background: var(--accent); box-shadow: 0 0 8px var(--accent-dim); }}
.brand .sep {{ color: var(--tx-3); }}
.brand .sub {{ color: var(--tx-2); letter-spacing: 0.06em; }}
.pill {{
  display: inline-flex; align-items: center; gap: 6px;
  padding: 3px 8px; font-family: var(--mono); font-size: 10.5px; font-weight: 500;
  letter-spacing: 0.12em; text-transform: uppercase; border-radius: 2px;
  border: 1px solid currentColor; line-height: 1.4;
  max-width: 100%; white-space: normal; overflow-wrap: anywhere; flex-shrink: 1;
}}
.pill.read-only {{ color: var(--warn); }}
.pill.paper {{ color: var(--accent); }}
.pill.stale {{ color: var(--loss); }}

.tape {{ display: flex; align-items: center; gap: 22px; font-family: var(--mono); font-size: 11.5px; overflow: hidden; white-space: nowrap; }}
.tape .q {{ display: inline-flex; gap: 8px; align-items: baseline; }}
.tape .q .lbl {{ color: var(--tx-3); }}
.tape .q .val {{ color: var(--tx-0); font-weight: 500; }}
.tape .q .chg.gain {{ color: var(--gain); }}
.tape .q .chg.loss {{ color: var(--loss); }}

.stamp {{ font-family: var(--mono); font-size: 11px; color: var(--tx-2); display: flex; gap: 10px; align-items: center; min-width: 0; overflow-wrap: anywhere; }}
.stamp .clock-dot {{ width: 6px; height: 6px; border-radius: 50%; background: var(--ok); box-shadow: 0 0 6px var(--ok); }}
.stamp .ms[data-status="CLOSED"] .clock-dot {{ background: var(--loss); box-shadow: none; }}
.stamp .ms {{ display: inline-flex; align-items: center; gap: 6px; color: var(--tx-1); }}

/* Hero ─────────────────────────── */
.hero-main {{
  background: var(--bg-2); border: 1px solid var(--line); border-radius: var(--radius);
  padding: var(--pad) calc(var(--pad) + 4px);
  position: relative; overflow: hidden;
}}
.hero-main .grid-bg {{
  position: absolute; inset: 0; opacity: 0.32; pointer-events: none;
  background-image:
    linear-gradient(to right, var(--line) 1px, transparent 1px),
    linear-gradient(to bottom, var(--line) 1px, transparent 1px);
  background-size: 48px 48px;
  mask-image: linear-gradient(to bottom, transparent 0%, black 30%, black 70%, transparent 100%);
}}
.hero-main > * {{ position: relative; }}
.hero-tag {{ display: flex; gap: 12px; align-items: center; font-family: var(--mono); font-size: 10.5px; color: var(--tx-2); text-transform: uppercase; letter-spacing: 0.16em; margin-bottom: 6px; }}
.hero-tag .dash {{ width: 18px; height: 1px; background: var(--line-strong); }}
.hero-grid {{ display: grid; grid-template-columns: auto 1fr; gap: 28px; align-items: end; }}
.nav {{ font-family: var(--mono); font-size: clamp(48px, 5.4vw, 78px); font-weight: 500; letter-spacing: -0.025em; color: var(--tx-0); line-height: 1.0; }}
.nav .krw {{ color: var(--tx-3); font-size: 0.42em; margin-right: 8px; letter-spacing: 0.05em; vertical-align: 0.18em; }}
.nav-meta {{ display: flex; gap: 14px; align-items: baseline; margin-top: 10px; font-family: var(--mono); font-size: 13px; }}
.nav-meta .pl {{ display: inline-flex; gap: 8px; align-items: baseline; padding: 4px 10px; border-radius: 2px; background: var(--gain-bg); color: var(--gain); font-weight: 500; }}
.nav-meta .pl.loss {{ background: var(--loss-bg); color: var(--loss); }}
.nav-meta .day {{ color: var(--tx-2); display: inline-flex; gap: 6px; }}
.nav-meta .day b {{ color: var(--tx-1); font-weight: 500; }}
.nav-meta .day b.gain {{ color: var(--gain); }}
.nav-meta .day b.loss {{ color: var(--loss); }}

.sk-head {{ display: flex; justify-content: space-between; align-items: baseline; font-family: var(--mono); font-size: 10.5px; color: var(--tx-2); text-transform: uppercase; letter-spacing: 0.14em; margin-bottom: 4px; }}
.sk-head .vals {{ color: var(--tx-1); }}

.hero-substats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 10px; margin-top: 14px; padding-top: 12px; border-top: 1px dashed var(--line); }}
.ss {{ display: flex; flex-direction: column; gap: 2px; }}
.ss .lbl {{ font-family: var(--mono); font-size: 10px; color: var(--tx-3); text-transform: uppercase; letter-spacing: 0.12em; }}
.ss .val {{ font-family: var(--mono); font-size: 16px; color: var(--tx-0); font-variant-numeric: tabular-nums; }}
.ss .sub {{ font-family: var(--mono); font-size: 11px; color: var(--tx-2); }}

/* Highlight cards */
.hi-card {{
  display: grid; grid-template-columns: 4px 1fr auto; gap: 12px; align-items: center;
  padding: 10px 14px; background: var(--bg-2);
  border: 1px solid var(--line); border-radius: var(--radius);
  margin-bottom: 8px;
}}
.hi-card .stripe {{ width: 3px; height: 100%; align-self: stretch; border-radius: 2px; background: var(--accent); }}
.hi-card.gain .stripe {{ background: var(--gain); }}
.hi-card.loss .stripe {{ background: var(--loss); }}
.hi-card .tag {{ font-family: var(--mono); font-size: 10px; color: var(--tx-3); text-transform: uppercase; letter-spacing: 0.14em; }}
.hi-card .name {{ display: flex; align-items: baseline; gap: 8px; margin-top: 2px; min-width: 0; overflow-wrap: anywhere; }}
.hi-card .name .nm {{ color: var(--tx-0); font-weight: 500; font-size: 14px; min-width: 0; overflow-wrap: anywhere; }}
.hi-card .name .tk {{ font-family: var(--mono); font-size: 11px; color: var(--tx-2); }}
.hi-card .sub {{ font-family: var(--mono); font-size: 11px; color: var(--tx-2); margin-top: 2px; }}
.hi-card .right {{ text-align: right; min-width: 90px; }}
.hi-card .right .v {{ font-family: var(--mono); font-size: 20px; color: var(--tx-0); }}
.hi-card .right .pct {{ font-family: var(--mono); font-size: 12px; font-weight: 500; }}
.hi-card .right .pct.gain {{ color: var(--gain); }}
.hi-card .right .pct.loss {{ color: var(--loss); }}

/* Section label */
.section-label {{ display: flex; align-items: center; gap: 10px; font-family: var(--mono); font-size: 10.5px; color: var(--tx-2); text-transform: uppercase; letter-spacing: 0.14em; padding: 12px 0 6px; }}
.section-label::after {{ content: ""; flex: 1; height: 1px; background: var(--line); }}
.section-label .count {{ color: var(--tx-3); font-size: 10px; padding: 1px 6px; border: 1px solid var(--line-2); border-radius: 2px; }}

/* Holdings table */
.htable-wrap {{ background: var(--bg-2); border: 1px solid var(--line); border-radius: var(--radius); overflow: hidden; }}
.htable-head {{ display: flex; justify-content: space-between; padding: 12px 14px 10px; border-bottom: 1px solid var(--line); }}
.htable-head .ttl {{ font-family: var(--mono); font-size: 11.5px; color: var(--tx-1); text-transform: uppercase; letter-spacing: 0.14em; }}
.htable-head .ttl b {{ color: var(--tx-0); }}
.htable-head .meta {{ font-family: var(--mono); font-size: 10.5px; color: var(--tx-3); text-transform: uppercase; letter-spacing: 0.12em; }}
.htable {{ width: 100%; border-collapse: collapse; font-size: 12.5px; }}
.htable thead th {{
  font-family: var(--mono); font-weight: 500; font-size: 10px;
  text-transform: uppercase; letter-spacing: 0.12em; color: var(--tx-3);
  text-align: right; padding: 8px 10px;
  border-bottom: 1px solid var(--line);
  background: var(--bg-1); white-space: nowrap;
}}
.htable thead th:first-child, .htable thead th.left {{ text-align: left; }}
.htable tbody td {{ padding: 12px 10px; border-bottom: 1px solid var(--line); text-align: right; vertical-align: middle; }}
.htable tbody td:first-child, .htable tbody td.left {{ text-align: left; }}
.htable tbody tr:last-child td {{ border-bottom: 0; }}
.htable tbody tr.selected {{ background: var(--bg-3); box-shadow: inset 3px 0 0 var(--accent); }}
.htable .rank {{ display: inline-flex; align-items: center; justify-content: center; width: 22px; height: 22px; font-family: var(--mono); font-size: 11px; color: var(--tx-2); border: 1px solid var(--line-2); border-radius: 2px; }}
.htable .ticker-cell {{ display: flex; flex-direction: column; gap: 2px; min-width: 0; overflow-wrap: anywhere; }}
.htable .ticker-cell .tk {{ font-family: var(--mono); font-size: 12px; color: var(--accent); letter-spacing: 0.04em; }}
.htable .ticker-cell .nm {{ color: var(--tx-0); font-weight: 500; font-size: 13px; }}
.htable .ticker-cell .sec {{ font-family: var(--mono); font-size: 10px; color: var(--tx-3); text-transform: uppercase; letter-spacing: 0.1em; }}
.htable .last {{ font-family: var(--mono); color: var(--tx-0); font-size: 14px; font-weight: 500; }}
.htable .day-chg.gain {{ color: var(--gain); font-family: var(--mono); font-size: 11.5px; }}
.htable .day-chg.loss {{ color: var(--loss); font-family: var(--mono); font-size: 11.5px; }}

.wbar {{ position: relative; height: 18px; width: 120px; background: var(--bg-1); border: 1px solid var(--line); border-radius: 2px; overflow: hidden; margin-left: auto; }}
.wbar .fill {{ position: absolute; top: 0; left: 0; bottom: 0; background: linear-gradient(90deg, var(--accent-bg), var(--accent)); }}
.wbar .label {{ position: absolute; inset: 0; display: flex; align-items: center; justify-content: flex-end; padding: 0 6px; font-family: var(--mono); font-size: 10.5px; color: var(--tx-0); text-shadow: 0 0 2px var(--bg-0); }}

.pl-cell {{ display: flex; flex-direction: column; align-items: flex-end; gap: 2px; font-family: var(--mono); }}
.pl-cell .amt {{ font-size: 13px; font-weight: 500; }}
.pl-cell .pct {{ font-size: 11.5px; }}
.pl-cell.gain .amt, .pl-cell.gain .pct {{ color: var(--gain); }}
.pl-cell.loss .amt, .pl-cell.loss .pct {{ color: var(--loss); }}

/* Detail panel */
.detail {{ background: var(--bg-2); border: 1px solid var(--line); border-radius: var(--radius); overflow: hidden; }}
.detail-head {{ display: flex; justify-content: space-between; gap: 10px; padding: 14px; border-bottom: 1px solid var(--line); align-items: flex-start; }}
.detail-head > div:first-child {{ min-width: 0; overflow-wrap: anywhere; }}
.detail-head .tk {{ font-family: var(--mono); font-size: 11px; color: var(--accent); letter-spacing: 0.08em; }}
.detail-head .nm {{ font-size: 20px; font-weight: 600; color: var(--tx-0); letter-spacing: -0.01em; margin-top: 2px; }}
.detail-head .sec {{ font-family: var(--mono); font-size: 10px; color: var(--tx-3); text-transform: uppercase; letter-spacing: 0.14em; margin-top: 6px; }}
.detail-head .right {{ text-align: right; }}
.detail-head .last {{ font-family: var(--mono); font-size: 26px; color: var(--tx-0); }}
.detail-head .day {{ font-family: var(--mono); font-size: 12px; display: inline-flex; gap: 6px; align-items: baseline; padding: 2px 8px; border-radius: 2px; margin-top: 4px; }}
.detail-head .day.gain {{ background: var(--gain-bg); color: var(--gain); }}
.detail-head .day.loss {{ background: var(--loss-bg); color: var(--loss); }}
.detail-body {{ padding: 12px 14px 14px; display: flex; flex-direction: column; gap: 14px; }}
.kvgrid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; }}
.kv {{ background: var(--bg-1); border: 1px solid var(--line); border-radius: 2px; padding: 8px 10px; }}
.kv .lbl {{ font-family: var(--mono); font-size: 9.5px; color: var(--tx-3); text-transform: uppercase; letter-spacing: 0.14em; }}
.kv .val {{ font-family: var(--mono); font-size: 14px; color: var(--tx-0); margin-top: 2px; }}
.kv .val.gain {{ color: var(--gain); }}
.kv .val.loss {{ color: var(--loss); }}
.subhead {{ font-family: var(--mono); font-size: 10px; color: var(--tx-2); text-transform: uppercase; letter-spacing: 0.16em; display: flex; align-items: center; gap: 10px; }}
.subhead::after {{ content: ""; flex: 1; height: 1px; background: var(--line); }}
.reason {{ background: var(--bg-1); border-left: 2px solid var(--accent); padding: 10px 12px; color: var(--tx-1); font-size: 13.5px; line-height: 1.55; border-radius: 0 2px 2px 0; margin-top: 8px; }}
.factor-rows {{ display: flex; flex-direction: column; gap: 6px; margin-top: 8px; }}
.fr {{ display: grid; grid-template-columns: 130px 1fr 56px; align-items: center; gap: 10px; font-family: var(--mono); font-size: 11.5px; }}
.fr .lbl {{ color: var(--tx-2); }}
.fr .val {{ color: var(--tx-0); text-align: right; }}
.fr .bar-wrap {{ position: relative; height: 8px; background: var(--bg-1); border: 1px solid var(--line); border-radius: 2px; }}
.fr .bar-wrap .axis {{ position: absolute; top: 0; bottom: 0; left: 50%; width: 1px; background: var(--line-2); }}
.fr .bar-wrap .bar {{ position: absolute; top: 0; bottom: 0; background: var(--accent); border-radius: 1px; }}
.fr .bar-wrap .bar.neg {{ background: var(--loss); }}
.flow-row {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-top: 8px; }}
.flow-row .chip {{ background: var(--bg-1); border: 1px solid var(--line); border-radius: 2px; padding: 8px 10px; }}
.flow-row .chip .lbl {{ font-family: var(--mono); font-size: 9.5px; color: var(--tx-3); text-transform: uppercase; letter-spacing: 0.12em; }}
.flow-row .chip .val {{ font-family: var(--mono); font-size: 13px; margin-top: 2px; }}
.flow-row .chip .val.gain {{ color: var(--gain); }}
.flow-row .chip .val.loss {{ color: var(--loss); }}
.sig {{ display: grid; grid-template-columns: 80px 1fr auto; align-items: center; gap: 10px; background: var(--bg-1); border: 1px solid var(--line); border-left: 2px solid var(--accent); padding: 8px 10px; font-size: 12px; margin-top: 6px; }}
.sig.warn {{ border-left-color: var(--warn); }}
.sig.up {{ border-left-color: var(--gain); }}
.sig.down {{ border-left-color: var(--loss); }}
.sig .src {{ font-family: var(--mono); font-size: 10px; color: var(--tx-2); text-transform: uppercase; letter-spacing: 0.12em; }}
.sig .detail {{ color: var(--tx-1); min-width: 0; overflow-wrap: anywhere; }}
.sig .right {{ font-family: var(--mono); font-size: 11px; color: var(--tx-2); text-align: right; }}
.sig .stars {{ color: var(--accent); }}
.sig-empty {{ font-family: var(--mono); font-size: 11px; color: var(--tx-3); border: 1px dashed var(--line); border-radius: 2px; padding: 14px; text-align: center; margin-top: 8px; }}

.research-card {{
  margin: 10px 0; padding: 16px 18px;
  background: var(--bg-2); border: 1px solid var(--line); border-radius: var(--radius);
  overflow: visible; word-break: keep-all; overflow-wrap: anywhere;
}}
.research-card .head {{ display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; }}
.research-card .head > div:first-child {{ min-width: 0; overflow-wrap: anywhere; }}
.research-card .meta {{ font-family: var(--mono); font-size: 11px; color: var(--tx-2); }}
.research-card .title {{ font-weight: 800; font-size: 18px; color: var(--tx-0); margin-top: 4px; line-height: 1.35; }}
.research-card .brief {{ margin: 12px 0 0 0; padding-left: 18px; line-height: 1.65; color: var(--tx-1); }}
.research-card .brief li {{ margin: 4px 0; }}
.research-card .brief b {{ color: var(--tx-0); }}
.research-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; margin-top: 12px; }}
.research-cell {{ background: var(--bg-1); border: 1px solid var(--line); border-radius: 2px; padding: 10px 12px; line-height: 1.55; }}
.research-cell b {{ display: block; color: var(--tx-0); margin-bottom: 4px; }}
.research-cell .empty {{ color: var(--tx-3); font-family: var(--mono); font-size: 11px; }}
.research-details {{ margin-top: 12px; border-top: 1px dashed var(--line); padding-top: 10px; color: var(--tx-2); }}
.research-details summary {{ cursor: pointer; color: var(--accent); font-family: var(--mono); font-size: 11px; text-transform: uppercase; letter-spacing: 0.1em; }}
.research-details .raw {{ margin-top: 8px; display: grid; gap: 8px; line-height: 1.55; }}
@media (max-width: 900px) {{ .research-grid {{ grid-template-columns: 1fr; }} .research-card .head {{ flex-direction: column; }} }}

/* Footer */
.foot {{ margin-top: 14px; display: flex; justify-content: space-between; gap: 14px; padding: 10px 14px; background: var(--bg-1); border: 1px solid var(--line); border-radius: var(--radius); font-family: var(--mono); font-size: 10.5px; color: var(--tx-3); text-transform: uppercase; letter-spacing: 0.12em; }}
.foot span {{ min-width: 0; overflow-wrap: anywhere; }}
.foot .warning {{ display: inline-flex; gap: 8px; align-items: center; color: var(--warn); }}

/* Streamlit native button → row selectors. Match the table row style. */
[data-testid="stHorizontalBlock"] .stButton > button {{
  width: 100%; background: transparent; border: 1px solid var(--line);
  border-radius: 2px; color: var(--tx-1);
  font-family: var(--mono); font-size: 11px; padding: 6px 10px;
}}
[data-testid="stHorizontalBlock"] .stButton > button:hover {{
  background: var(--bg-3); border-color: var(--accent-dim); color: var(--tx-0);
}}

/* Native widgets — Streamlit selectbox/radio */
.stSelectbox > div > div, .stRadio > div, .stTextInput > div > div {{
  background: var(--bg-1) !important; border-color: var(--line) !important; color: var(--tx-1) !important;
}}
.stAlert {{ background: var(--bg-2) !important; border: 1px solid var(--warn) !important; color: var(--tx-1) !important; }}
</style>
"""


# ─────────────────────────── Renderers ─────────────────────────────────────
def _topbar_html(snapshot: dict[str, Any]) -> str:
    market = _ensure_market(snapshot)
    generated_at = snapshot.get("generated_at", "—")
    try:
        stamp_dt = datetime.fromisoformat(str(generated_at))
        stamp = stamp_dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        stamp = str(generated_at)

    stale = snapshot_is_stale(snapshot)
    stale_pill = "<span class='pill stale'>STALE</span>" if stale else ""

    def quote(label: str, value: float, chg: float) -> str:
        cls = "gain" if chg >= 0 else "loss"
        arrow = "▲" if chg >= 0 else "▼"
        return (
            f"<span class='q'><span class='lbl'>{html.escape(label)}</span>"
            f"<span class='num val'>{value:,.2f}</span>"
            f"<span class='num chg {cls}'>{arrow} {chg:+.2f}%</span></span>"
        )

    tape = "".join([
        quote("KOSPI",   _to_float(market.get("kospi",   {}).get("value")), _to_float(market.get("kospi",   {}).get("chg_pct"))),
        quote("KOSDAQ",  _to_float(market.get("kosdaq",  {}).get("value")), _to_float(market.get("kosdaq",  {}).get("chg_pct"))),
        quote("USD/KRW", _to_float(market.get("usdkrw", {}).get("value")), _to_float(market.get("usdkrw", {}).get("chg_pct"))),
        quote("KTB10Y",  _to_float(market.get("bonds10y",{}).get("value")), _to_float(market.get("bonds10y",{}).get("chg_pct"))),
    ])
    session = html.escape(str(market.get("session_label", "")))
    status = html.escape(str(market.get("status", "CLOSED")))

    return f"""
    <div class='topbar'>
      <div class='brand'>
        <span class='dot'></span>
        <span>QUNTBOT</span>
        <span class='sep'>·</span>
        <span class='sub'>Public Portfolio Dashboard</span>
        <span class='pill paper' style='margin-left:10px;'>PAPER</span>
        <span class='pill read-only' style='margin-left:6px;'>READ-ONLY</span>
        <span class='sub'>Read-only snapshot</span>
        {stale_pill}
      </div>
      <div class='tape'>{tape}</div>
      <div class='stamp'>
        <span class='ms' data-status='{status}'><span class='clock-dot'></span>{session}</span>
        <span style='color:var(--tx-4);'>│</span>
        <span title='{html.escape(str(generated_at))}'>Snapshot {html.escape(stamp)} KST</span>
        <span style='display:none'>{html.escape(str(generated_at))}</span>
      </div>
    </div>
    """


def _hero_html(snapshot: dict[str, Any]) -> str:
    summary = snapshot.get("summary") or {}
    positions = snapshot.get("positions") or []
    equity = _ensure_equity_curve(snapshot)
    cash = snapshot.get("cash") or {}
    realized = snapshot.get("realized") or {}

    stock_market_value = _to_float(summary.get("stock_market_value") or summary.get("total_market_value"))
    cash_balance = _to_float(summary.get("cash_balance") if summary.get("cash_balance") is not None else cash.get("available"))
    nav_value = _to_float(summary.get("total_asset_value")) or (stock_market_value + cash_balance)
    pl = _to_float(summary.get("total_profit_loss"))
    pl_rate = _to_float(summary.get("total_profit_loss_rate"))
    cost = _to_float(summary.get("total_cost"))
    realized_pl = _to_float(summary.get("realized_profit_loss") if summary.get("realized_profit_loss") is not None else realized.get("profit_loss"))
    realized_source = str(realized.get("source") or "unavailable")
    realized_note = "KIS 잔고 기준" if realized_source == "kis_balance" else "데이터 없음"
    pl_gain = pl >= 0
    realized_gain = realized_pl >= 0

    if len(equity) >= 2:
        day_amt = equity[-1] - equity[-2]
        day_pct = (day_amt / equity[-2]) * 100 if equity[-2] else 0
    else:
        day_amt = 0.0
        day_pct = 0.0
    spark_color = "var(--gain)" if day_pct >= 0 else "var(--loss)"
    spark_svg = _hero_spark_svg(equity, spark_color)

    pl_arrow = "▲" if pl_gain else "▼"
    day_arrow = "▲" if day_pct >= 0 else "▼"
    day_cls = "gain" if day_pct >= 0 else "loss"

    return f"""
    <div class='hero-main'>
      <div class='grid-bg'></div>
      <div class='hero-tag'><span class='dash'></span><span>Net Asset Value · 순자산</span></div>
      <div class='hero-grid'>
        <div>
          <div class='nav'><span class='krw'>₩</span>{_krw_int(nav_value)}</div>
          <div class='nav-meta'>
            <span class='pl {"" if pl_gain else "loss"}'>
              <span>{pl_arrow}</span>
              <span>{"+" if pl_gain else ""}{_krw_int(pl)}</span>
              <span class='pct'>/ {pl_rate:+.2f}%</span>
            </span>
            <span class='day'>
              <span>당일 변동</span>
              <b class='{day_cls}'>{day_arrow} {"+" if day_pct >= 0 else ""}{_krw_int(day_amt)} ({day_pct:+.2f}%)</b>
            </span>
          </div>
        </div>
        <div style='min-width:0;'>
          <div class='sk-head'>
            <span>Equity Curve · 30D</span>
            <span class='vals num'>
              <span style='color:var(--tx-3);'>L</span> {_krw_short(min(equity))}
              <span style='color:var(--tx-3);margin:0 6px;'>│</span>
              <span style='color:var(--tx-3);'>H</span> {_krw_short(max(equity))}
            </span>
          </div>
          {spark_svg}
        </div>
      </div>
      <div class='hero-substats'>
        <div class='ss'><span class='lbl'>Cost · 매입원가</span><span class='val'>₩{_krw_int(cost)}</span><span class='sub'>unit basis</span></div>
        <div class='ss'><span class='lbl'>Holdings · 보유</span><span class='val'>{len(positions)} 종목</span><span class='sub'>long only</span></div>
        <div class='ss'><span class='lbl'>Cash · 현금</span><span class='val'>₩{_krw_int(cash_balance)}</span><span class='sub'>available</span></div>
        <div class='ss'><span class='lbl'>Realized · 실현</span><span class='val {"gain" if realized_gain else "loss"}'>{"+" if realized_gain else ""}₩{_krw_int(realized_pl)}</span><span class='sub'>{html.escape(realized_note)}</span></div>
        <div class='ss'><span class='lbl'>Strategy · 전략</span><span class='val' style='font-size:14px;'>QUNT v3.2</span><span class='sub'>multi-factor + flow</span></div>
      </div>
    </div>
    """


def _highlight_cards_html(positions: list[dict[str, Any]]) -> str:
    if not positions:
        return ""
    by_rate = sorted(positions, key=lambda p: _to_float(p.get("profit_loss_rate")), reverse=True)
    by_rank = sorted(positions, key=lambda p: _to_float(p.get("rationale", {}).get("rank"), 99))
    top, worst = by_rate[0], by_rate[-1]
    conv = by_rank[0]

    def card(tag: str, cls: str, p: dict[str, Any], kind: str) -> str:
        pl_rate = _to_float(p.get("profit_loss_rate"))
        pl = _to_float(p.get("profit_loss"))
        gain_cls = "gain" if pl_rate >= 0 else "loss"
        rank = p.get("rationale", {}).get("rank")
        score = _to_float(p.get("rationale", {}).get("total_score"))
        rank_text = html.escape(str(rank if rank is not None else "—"))
        right = (
            f"<div class='v num'>{pl_rate:+.2f}%</div>"
            f"<div class='pct {gain_cls}'>{'+' if pl >= 0 else ''}{_krw_int(pl)} 원</div>"
        ) if kind == "rate" else (
            f"<div class='v num'>#{rank_text}</div>"
            f"<div class='pct' style='color:var(--accent);'>score {score:.2f}</div>"
        )
        return f"""
        <div class='hi-card {cls}'>
          <div class='stripe'></div>
          <div>
            <div class='tag'>{html.escape(tag)}</div>
            <div class='name'>
              <span class='nm'>{html.escape(str(p.get('name','')))}</span>
              <span class='tk'>{html.escape(str(p.get('ticker','')))}</span>
              <span class='tk' style='color:var(--tx-3);'>· {html.escape(str(p.get('sector','—')))}</span>
            </div>
            <div class='sub'>평균 ₩{_krw_int(p.get('avg_price'))} → 현재 ₩{_krw_int(p.get('current_price'))}</div>
          </div>
          <div class='right'>{right}</div>
        </div>
        """

    return (
        card("Top Performer · 오늘의 효자", "gain", top, "rate")
        + card("Biggest Drag · 부진",       "loss", worst, "rate")
        + card("High Conviction · 최고확신", "",    conv, "rank")
    )


def _holdings_table_html(positions: list[dict[str, Any]], total_mv: float,
                         selected: str, show_spark: bool, show_stripe: bool) -> str:
    head_cells = [
        "<th class='left'>#</th>",
        "<th class='left'>Ticker · 종목</th>",
        "<th>Qty</th><th>Avg</th><th>Last</th><th>Day</th>",
    ]
    if show_spark: head_cells.append("<th>30D</th>")
    head_cells += ["<th>Weight</th>", "<th>Mkt Value</th>", "<th>P&amp;L</th>"]
    if show_stripe: head_cells.append("<th>Factors</th>")

    rows_html: list[str] = []
    for p in positions:
        ticker = str(p.get("ticker", ""))
        weight = (_to_float(p.get("market_value")) / total_mv * 100) if total_mv else 0
        day_pct, _ = _ensure_day_change(p)
        d_gain = day_pct >= 0
        spark_pts = _spark_points(ticker, _to_float(p.get("current_price")), day_pct)
        is_sel = ticker == selected
        pl = _to_float(p.get("profit_loss"))
        pl_rate = _to_float(p.get("profit_loss_rate"))
        gain = pl >= 0
        factors = p.get("rationale", {}).get("factor_scores", {}) or {}

        cells = [
            f"<td class='left'><span class='rank'>{html.escape(str(p.get('rationale',{}).get('rank','—')))}</span></td>",
            f"""<td class='left'><div class='ticker-cell'>
              <span class='tk'>{html.escape(ticker)}</span>
              <span class='nm'>{html.escape(str(p.get('name','')))}</span>
              <span class='sec'>{html.escape(str(p.get('sector','—')))}</span>
            </div></td>""",
            f"<td class='num'>{int(_to_float(p.get('qty'))):,}</td>",
            f"<td class='num' style='color:var(--tx-2);'>{_krw_int(p.get('avg_price'))}</td>",
            f"<td class='last'>{_krw_int(p.get('current_price'))}</td>",
            f"<td class='day-chg {'gain' if d_gain else 'loss'}'>{'▲' if d_gain else '▼'} {day_pct:+.2f}%</td>",
        ]
        if show_spark:
            spark_color = "var(--gain)" if d_gain else "var(--loss)"
            cells.append(f"<td>{_spark_svg(spark_pts, spark_color)}</td>")
        cells.append(
            f"""<td><div class='wbar'>
              <div class='fill' style='width:{weight:.2f}%;'></div>
              <div class='label'>{weight:.1f}%</div></div></td>"""
        )
        cells.append(f"<td class='num' style='color:var(--tx-0);'>{_krw_int(p.get('market_value'))}</td>")
        cells.append(
            f"""<td><div class='pl-cell {'gain' if gain else 'loss'}'>
              <span class='amt'>{'+' if gain else ''}{_krw_int(pl)}</span>
              <span class='pct'>{'▲' if gain else '▼'} {pl_rate:+.2f}%</span>
            </div></td>"""
        )
        if show_stripe:
            cells.append(f"<td>{_factor_stripe_svg(factors)}</td>")

        tr_cls = " class='selected'" if is_sel else ""
        rows_html.append(f"<tr{tr_cls}>{''.join(cells)}</tr>")

    return f"""
    <div class='htable-wrap'>
      <div class='htable-head'>
        <div class='ttl'>Holdings · <b>보유 종목</b> · {len(positions)}</div>
        <div class='meta'>sorted by weight · select below for detail</div>
      </div>
      <table class='htable'>
        <thead><tr>{''.join(head_cells)}</tr></thead>
        <tbody>{''.join(rows_html)}</tbody>
      </table>
    </div>
    """


def _detail_html(
    position: dict[str, Any],
    *,
    brief_by_ticker: dict[str, dict[str, Any]] | None = None,
) -> str:
    if not position:
        return "<div class='detail'><div class='detail-body sig-empty'>선택된 종목이 없습니다.</div></div>"
    r = position.get("rationale") or {}
    q = (r.get("market_context") or {}).get("quality") or {}
    flow = (r.get("market_context") or {}).get("investor_flow") or {}
    factors = r.get("factor_scores") or {}
    signals = r.get("signals") or []

    day_pct, _ = _ensure_day_change(position)
    d_gain = day_pct >= 0
    gain = _to_float(position.get("profit_loss")) >= 0

    def kv(lbl: str, val: str, cls: str = "") -> str:
        return f"<div class='kv'><div class='lbl'>{lbl}</div><div class='val {cls}'>{val}</div></div>"

    kv_block = (
        kv("Qty · 수량", f"{int(_to_float(position.get('qty'))):,} 주")
        + kv("Avg · 평균단가", f"₩{_krw_int(position.get('avg_price'))}")
        + kv("Mkt Value · 평가", f"₩{_krw_int(position.get('market_value'))}")
        + kv("P&L · 손익", f"{'+' if gain else ''}{_krw_int(position.get('profit_loss'))}", "gain" if gain else "loss")
        + kv("ROE", _ratio_pct(q.get("roe")))
        + kv("OP Margin", _ratio_pct(q.get("operating_margin")))
        + kv("Debt · 부채", _ratio_pct(q.get("debt_ratio")))
        + kv("FY · 회계연도", f"{q.get('fiscal_year','—')} Q{q.get('fiscal_quarter','—')}")
    )

    # factor rows
    max_abs = 1.2
    fr_html: list[str] = []
    for k in FACTOR_KEYS:
        v = _to_float(factors.get(k))
        pct = min(50.0, abs(v) / max_abs * 50)
        neg = v < 0
        bar_left = (50 - pct) if neg else 50
        bar = f"<span class='bar{' neg' if neg else ''}' style='left:{bar_left}%;width:{pct}%;'></span>"
        fr_html.append(
            f"<div class='fr'>"
            f"<span class='lbl'>{FACTOR_LABELS[k]}</span>"
            f"<span class='bar-wrap'><span class='axis'></span>{bar}</span>"
            f"<span class='val'>{v:+.2f}</span>"
            f"</div>"
        )

    # flow chips
    def chip(lbl: str, v: Any) -> str:
        if v in (None, ""):
            return f"<div class='chip'><div class='lbl'>{lbl}</div><div class='val' style='color:var(--tx-3);'>—</div></div>"
        f = _to_float(v)
        cls = "gain" if f >= 0 else "loss"
        arrow = "▲" if f >= 0 else "▼"
        return f"<div class='chip'><div class='lbl'>{lbl}</div><div class='val {cls}'>{arrow} {_krw_short(f)}</div></div>"

    flow_block = (
        chip("개인", flow.get("individual_net_buy"))
        + chip("외국인", flow.get("foreign_net_buy"))
        + chip("기관", flow.get("institution_net_buy"))
    )

    # signals
    if signals:
        sig_blocks: list[str] = []
        for s in signals:
            score = _to_float(s.get("raw_score"))
            cls = "up" if score > 0 else "down" if score < 0 else "warn"
            stars = "★" * int(_to_float(s.get("star_rating")))
            tgt = s.get("target_price")
            tgt_text = f" · 목표가 ₩{_krw_int(tgt)}" if tgt else ""
            detail_txt = f" · {html.escape(str(s.get('detail','')))}" if s.get("detail") else ""
            sig_blocks.append(
                f"<div class='sig {cls}'>"
                f"<span class='src'>{html.escape(str(s.get('source','—')))}</span>"
                f"<span class='detail'>{html.escape(str(s.get('signal_type','')))}{tgt_text}{detail_txt}</span>"
                f"<span class='right'><span class='stars'>{stars}</span> {score:+.2f}</span>"
                f"</div>"
            )
        sig_html = "".join(sig_blocks)
    else:
        sig_html = "<div class='sig-empty'>No active signal · 활성 시그널 없음</div>"

    ticker_brief = (brief_by_ticker or {}).get(str(position.get("ticker") or ""))
    research_html = ""
    if ticker_brief:
        sections = ticker_brief.get("sections") or {}
        risk = _first_report_text(sections.get("risk"))
        headline = str(ticker_brief.get("headline") or sections.get("stock_view") or "")
        report_count = int(_to_float((ticker_brief.get("quality") or {}).get("report_count")))
        research_html = (
            "<div>"
            "<div class='subhead'>Research Brief</div>"
            "<div class='sig up'>"
            f"<span class='src'>{html.escape(str(ticker_brief.get('latest_report_date') or ''))}</span>"
            f"<span class='detail'>{html.escape(headline)}</span>"
            f"<span class='right'>{html.escape(str(ticker_brief.get('opinion') or ''))}</span>"
            "</div>"
            "<div class='sig warn'>"
            "<span class='src'>Risk</span>"
            f"<span class='detail'>{html.escape(risk or 'No explicit risk sentence')}</span>"
            f"<span class='right'>reports {report_count}</span>"
            "</div>"
            "</div>"
        )

    return f"""
    <div class='detail'>
      <div class='detail-head'>
        <div>
          <div class='tk'>{html.escape(str(position.get('ticker','')))} · {html.escape(str(position.get('sector','—')))}</div>
          <div class='nm'>{html.escape(str(position.get('name','')))}</div>
          <div class='sec'>Rank #{html.escape(str(r.get('rank','—')))} · Score {_to_float(r.get('total_score')):.4f} · {html.escape(str(r.get('execution_status','—')))}</div>
        </div>
        <div class='right'>
          <div class='last'>₩{_krw_int(position.get('current_price'))}</div>
          <div class='day {'gain' if d_gain else 'loss'}'>{'▲' if d_gain else '▼'} {day_pct:+.2f}%</div>
        </div>
      </div>
      <div class='detail-body'>
        <div class='kvgrid'>{kv_block}</div>
        <div>
          <div class='subhead'>매수 사유 · Order Rationale</div>
          <div class='reason'>{html.escape(str(r.get('order_reason','—')))}</div>
        </div>
        <div>
          <div class='subhead'>팩터 점수 · Factor Breakdown</div>
          <div class='factor-rows'>{''.join(fr_html)}</div>
        </div>
        <div>
          <div class='subhead'>투자자 수급 · Investor Flow ({html.escape(str(flow.get('date','—')))})</div>
          <div class='flow-row'>{flow_block}</div>
        </div>
        <div>
          <div class='subhead'>시그널 · Signals</div>
          {sig_html}
        </div>
        {research_html}
      </div>
    </div>
    """


# ─────────────────────────── Streamlit entry points ────────────────────────
def _holdings_rows(positions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Compatibility helper for tests and simple tabular exports."""
    rows = []
    for position in positions:
        rows.append(
            {
                "종목코드": position.get("ticker", ""),
                "종목명": position.get("name", ""),
                "수량": position.get("qty", 0),
                "평균단가": format_krw(position.get("avg_price")),
                "현재가": format_krw(position.get("current_price")),
                "평가액": format_krw(position.get("market_value")),
                "평가손익": format_krw(position.get("profit_loss")),
                "수익률": format_pct(position.get("profit_loss_rate")),
            }
        )
    return rows


def _render_sidebar_tweaks(st) -> dict[str, Any]:
    if not hasattr(st, "sidebar"):
        return {
            "density": "regular",
            "cc": "kr",
            "accent": ACCENT_OPTS["gold"],
            "sans": TYPO_OPTS["plex"][1],
            "mono": TYPO_OPTS["plex"][2],
            "show_spark": True,
            "show_stripe": True,
        }

    st.sidebar.markdown("### Tweaks")
    density = st.sidebar.radio(
        "밀도", list(DENSITY_OPTS.keys()),
        format_func=lambda k: DENSITY_OPTS[k], index=1, horizontal=True,
    )
    cc = st.sidebar.radio(
        "수익/손실 컨벤션", list(CC_OPTS.keys()),
        format_func=lambda k: CC_OPTS[k], index=0,
    )
    accent_key = st.sidebar.selectbox(
        "포인트 컬러", list(ACCENT_OPTS.keys()),
        format_func=lambda k: k.title(), index=0,
    )
    typo_key = st.sidebar.selectbox(
        "폰트", list(TYPO_OPTS.keys()),
        format_func=lambda k: TYPO_OPTS[k][0], index=0,
    )
    st.sidebar.markdown("### Visuals")
    show_spark  = st.sidebar.toggle("30D 스파크라인", value=True)
    show_stripe = st.sidebar.toggle("팩터 스트라이프", value=True)

    sans_family, mono_family = TYPO_OPTS[typo_key][1], TYPO_OPTS[typo_key][2]
    return {
        "density": density,
        "cc": cc,
        "accent": ACCENT_OPTS[accent_key],
        "sans": sans_family,
        "mono": mono_family,
        "show_spark": show_spark,
        "show_stripe": show_stripe,
    }


def render_dashboard(snapshot: dict[str, Any]) -> None:
    import streamlit as st

    st.set_page_config(
        page_title="QUNTBOT · Public Portfolio",
        page_icon="●",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    _install_browser_auto_refresh(st, AUTO_REFRESH_SECONDS)

    tweaks = _render_sidebar_tweaks(st)
    st.markdown(
        _build_css(tweaks["density"], tweaks["cc"], tweaks["accent"], tweaks["sans"], tweaks["mono"]),
        unsafe_allow_html=True,
    )

    positions = list(snapshot.get("positions") or [])
    positions.sort(key=lambda p: _to_float(p.get("market_value")), reverse=True)
    summary = snapshot.get("summary") or {}
    total_mv = _to_float(summary.get("stock_market_value") or summary.get("total_market_value"))
    session_state = getattr(st, "session_state", {})

    # selection state
    if "selected_ticker" not in session_state and positions:
        session_state["selected_ticker"] = positions[0].get("ticker")

    ticker_brief_result = load_ticker_research_briefs()
    ticker_brief_by_ticker = dict(ticker_brief_result.get("by_ticker") or {})

    if hasattr(st, "tabs"):
        portfolio_tab, needs_tab, tasks_tab, ticker_tab, research_tab = st.tabs(
            ["Portfolio", "Supplement Needs", "해야 할 작업", "Ticker Briefs", "Research Reports"]
        )
        with portfolio_tab:
            _render_portfolio_tab(
                st,
                snapshot,
                tweaks,
                positions,
                total_mv,
                session_state,
                ticker_brief_by_ticker=ticker_brief_by_ticker,
            )
        with needs_tab:
            _render_research_supplement_needs_tab(st, positions, ticker_brief_result)
        with tasks_tab:
            _render_research_qa_action_tab(st)
        with ticker_tab:
            _render_ticker_research_brief_tab(st, positions, ticker_brief_result)
        with research_tab:
            _render_research_report_tab(st, positions)
        return

    _render_portfolio_tab(
        st,
        snapshot,
        tweaks,
        positions,
        total_mv,
        session_state,
        ticker_brief_by_ticker=ticker_brief_by_ticker,
    )
    _render_research_supplement_needs_tab(st, positions, ticker_brief_result)
    _render_research_qa_action_tab(st)
    _render_ticker_research_brief_tab(st, positions, ticker_brief_result)
    _render_research_report_tab(st, positions)


def _render_portfolio_tab(
    st,
    snapshot: dict[str, Any],
    tweaks: dict[str, Any],
    positions: list[dict[str, Any]],
    total_mv: float,
    session_state,
    *,
    ticker_brief_by_ticker: dict[str, dict[str, Any]] | None = None,
) -> None:

    # 1. topbar + hero (full width)
    st.markdown(_topbar_html(snapshot), unsafe_allow_html=True)
    hero_col, side_col = st.columns([1.45, 1], gap="small")
    with hero_col:
        st.markdown(_hero_html(snapshot), unsafe_allow_html=True)
    with side_col:
        st.markdown(_highlight_cards_html(positions), unsafe_allow_html=True)

    # 2. holdings + detail split
    st.markdown(
        f"<div class='section-label'><span>Holdings · 보유 종목 상세</span>"
        f"<span class='count'>{len(positions)} positions</span></div>",
        unsafe_allow_html=True,
    )

    table_col, detail_col = st.columns([1.6, 1], gap="small")
    with table_col:
        st.markdown(
            _holdings_table_html(
                positions, total_mv,
                session_state.get("selected_ticker", ""),
                tweaks["show_spark"], tweaks["show_stripe"],
            ),
            unsafe_allow_html=True,
        )
        # selector below the table (Streamlit doesn't support clickable HTML rows)
        labels = {p["ticker"]: f"{p.get('ticker','')}  ·  {p.get('name','')}" for p in positions}
        if labels:
            current = session_state.get("selected_ticker") or next(iter(labels))
            if hasattr(st, "selectbox"):
                picked = st.selectbox(
                    "Position detail · 종목 선택",
                    list(labels.keys()),
                    format_func=lambda t: labels[t],
                    index=list(labels.keys()).index(current) if current in labels else 0,
                )
            else:
                picked = current
            if picked != current:
                session_state["selected_ticker"] = picked
                if hasattr(st, "rerun"):
                    st.rerun()

    selected_pos = next(
        (p for p in positions if p.get("ticker") == session_state.get("selected_ticker")),
        positions[0] if positions else None,
    )
    with detail_col:
        st.markdown(
            _detail_html(selected_pos, brief_by_ticker=ticker_brief_by_ticker),
            unsafe_allow_html=True,
        )

    # 3. footer
    warnings = snapshot.get("warnings") or []
    warning_html = ""
    if warnings:
        warning_html = (
            f"<span class='warning'>"
            f"<span style='border:1px solid currentColor;border-radius:50%;width:14px;height:14px;"
            f"display:inline-flex;align-items:center;justify-content:center;font-size:9px;'>!</span>"
            f"{html.escape(str(warnings[0]))}</span>"
        )
    st.markdown(
        f"<div class='foot'>"
        f"<span>fields · ticker · qty · avg · last · weight · factors (v/q/m/y/tg/bs/flow) · flow (ind/for/inst)</span>"
        f"{warning_html}</div>",
        unsafe_allow_html=True,
    )


def _render_research_report_tab(st, positions: list[dict[str, Any]]) -> None:
    portfolio_tickers = {str(position.get("ticker")) for position in positions if position.get("ticker")}
    result = load_research_report_briefs()
    if result["status"] != "ok":
        st.warning(f"리포트 요약 데이터를 읽지 못했습니다: {result.get('error', 'unknown error')}")
        return

    rows = list(result.get("rows") or [])
    if not rows:
        st.info("아직 표시할 리포트 분석 데이터가 없습니다.")
        return

    opinion_options = ["all"] + sorted({str(row.get("investment_opinion")) for row in rows if row.get("investment_opinion")})
    source_options = ["all"] + sorted({str(row.get("source")) for row in rows if row.get("source")})

    st.markdown(
        "<div class='section-label'><span>Research Briefs · 리포트 핵심 요약</span>"
        f"<span class='count'>{len(rows)} reports loaded</span></div>",
        unsafe_allow_html=True,
    )

    controls = st.columns([1, 1, 1, 1.3], gap="small") if hasattr(st, "columns") else []
    if controls:
        with controls[0]:
            portfolio_only = st.checkbox("보유 종목만", value=False) if hasattr(st, "checkbox") else False
        with controls[1]:
            opinion = st.selectbox("의견", opinion_options, index=0) if hasattr(st, "selectbox") else "all"
        with controls[2]:
            display_choice = st.selectbox("표시 개수", ["30", "100", "300", "all"], index=1) if hasattr(st, "selectbox") else "100"
        with controls[3]:
            query = st.text_input("검색", value="", placeholder="종목코드, 업황, 신사업, 리스크") if hasattr(st, "text_input") else ""
    else:
        portfolio_only = False
        opinion = "all"
        display_choice = "100"
        query = ""
    source = st.selectbox("출처", source_options, index=0) if hasattr(st, "selectbox") else "all"

    filtered = filter_research_report_briefs(
        rows,
        portfolio_tickers=portfolio_tickers,
        portfolio_only=portfolio_only,
        opinion=opinion,
        source=source,
        query=query,
    )

    opinion_counts = _count_by(filtered, "investment_opinion")
    source_quality_counts = _count_by(filtered, "body_text_status")
    metric_cols = st.columns(4, gap="small") if hasattr(st, "columns") else []
    metrics = [
        ("표시 리포트", len(filtered)),
        ("Positive", opinion_counts.get("positive", 0)),
        ("Mixed/Neutral", opinion_counts.get("mixed", 0) + opinion_counts.get("neutral", 0)),
        ("본문 추출", _body_text_available_count(source_quality_counts)),
    ]
    for index, (label, value) in enumerate(metrics):
        if metric_cols:
            with metric_cols[index]:
                st.metric(label, value)

    if not filtered:
        st.info("조건에 맞는 리포트가 없습니다.")
        return

    display_limit = research_report_display_limit(display_choice, len(filtered))
    visible_rows = filtered[:display_limit]
    if hasattr(st, "caption"):
        st.caption(f"Showing {len(visible_rows)} of {len(filtered)} filtered reports.")

    for row in visible_rows:
        st.markdown(_research_report_card_html(row), unsafe_allow_html=True)


def _render_ticker_research_brief_tab(
    st,
    positions: list[dict[str, Any]],
    result: dict[str, Any],
) -> None:
    if result.get("status") == "missing":
        st.info("Ticker brief artifact is missing. Run scripts.generate_research_report_ticker_briefs.")
        return
    if result.get("status") != "ok":
        st.warning(f"Ticker brief artifact is invalid: {result.get('error', 'unknown error')}")
        return

    artifact = result.get("artifact") or {}
    ticker_briefs = list(artifact.get("tickers") or [])
    if not ticker_briefs:
        st.info("No ticker-level research briefs are available yet.")
        return

    portfolio_tickers = {str(position.get("ticker")) for position in positions if position.get("ticker")}
    summary = artifact.get("summary") or {}
    llm = artifact.get("llm") or {}
    quality_report = build_ticker_research_quality_report(
        artifact,
        portfolio_tickers=portfolio_tickers,
    )
    quality_queue = load_research_quality_queue()
    quality_summary = _quality_dashboard_summary(quality_report, quality_queue)
    qa_sample = load_research_brief_qa_sample()

    st.markdown(
        "<div class='section-label'><span>Ticker Integrated Briefs</span>"
        f"<span class='count'>{summary.get('ticker_count', len(ticker_briefs))} tickers · "
        f"{summary.get('source_report_count', 0)} reports · LLM {html.escape(str(llm.get('status', 'unknown')))}</span></div>",
        unsafe_allow_html=True,
    )

    metric_cols = st.columns(4, gap="small") if hasattr(st, "columns") else []
    metrics = [
        ("Complete", quality_summary["complete_count"]),
        ("Needs review", quality_summary["actionable_issue_count"]),
        ("Latest not found", quality_summary["latest_report_not_found_count"]),
        ("Portfolio missing", quality_summary["portfolio_missing_count"]),
    ]
    for index, (label, value) in enumerate(metrics):
        if metric_cols:
            with metric_cols[index]:
                st.metric(label, value)

    st.markdown(_research_operator_next_action_html(quality_summary), unsafe_allow_html=True)
    st.markdown(_research_qa_summary_html(qa_sample), unsafe_allow_html=True)

    latest_not_found_rows = _latest_not_found_quality_issues(quality_report, quality_queue)[:8]
    if latest_not_found_rows:
        st.markdown(
            "<div class='section-label'><span>Latest Not Found</span>"
            f"<span class='count'>{quality_summary['latest_report_not_found_count']} tickers tracked separately</span></div>",
            unsafe_allow_html=True,
        )
        for issue in latest_not_found_rows:
            st.markdown(_research_quality_issue_html(issue), unsafe_allow_html=True)

    issue_rows = _actionable_quality_issues(quality_report, quality_queue)[:8]
    if issue_rows:
        st.markdown(
            "<div class='section-label'><span>Quality Review Queue</span>"
            f"<span class='count'>{quality_summary['actionable_issue_count']} tickers need review</span></div>",
            unsafe_allow_html=True,
        )
        for issue in issue_rows:
            st.markdown(_research_quality_issue_html(issue), unsafe_allow_html=True)
    if quality_report["portfolio_missing"]:
        st.warning(
            "Portfolio tickers missing research briefs: "
            + ", ".join(quality_report["portfolio_missing"][:12])
        )

    controls = st.columns([1, 1.3], gap="small") if hasattr(st, "columns") else []
    if controls:
        with controls[0]:
            portfolio_only = st.checkbox("Portfolio only", value=True) if hasattr(st, "checkbox") else True
        with controls[1]:
            query = st.text_input("Search ticker brief", value="", placeholder="ticker, headline, risk") if hasattr(st, "text_input") else ""
    else:
        portfolio_only = True
        query = ""

    filtered = ticker_briefs
    if portfolio_only:
        filtered = [row for row in filtered if str(row.get("ticker")) in portfolio_tickers]
    if query:
        needle = query.strip().lower()
        filtered = [
            row for row in filtered if needle and needle in json.dumps(row, ensure_ascii=False).lower()
        ]

    if hasattr(st, "caption"):
        st.caption(f"Showing {len(filtered)} of {len(ticker_briefs)} ticker briefs.")
    if not filtered:
        st.info("No ticker briefs match the current filters.")
        return

    for row in filtered[:100]:
        st.markdown(_ticker_research_brief_card_html(row), unsafe_allow_html=True)


def _render_research_qa_action_tab(st) -> None:
    qa_action_queue = load_research_qa_action_queue()
    st.markdown(_research_qa_action_queue_html(qa_action_queue), unsafe_allow_html=True)

    if qa_action_queue.get("status") != "ok":
        return
    items = [item for item in qa_action_queue.get("items", []) if isinstance(item, dict)]
    if not items:
        return
    st.markdown(
        "<div class='section-label'><span>자동 작업 목록</span>"
        f"<span class='count'>{len(items)}개 작업</span></div>",
        unsafe_allow_html=True,
    )
    for item in items:
        st.markdown(_research_qa_action_item_html(item), unsafe_allow_html=True)


def _render_research_supplement_needs_tab(
    st,
    positions: list[dict[str, Any]],
    result: dict[str, Any],
) -> None:
    if result.get("status") == "missing":
        st.info("Ticker brief artifact is missing. Run the dashboard artifact refresh first.")
        return
    if result.get("status") != "ok":
        st.warning(f"Ticker brief artifact is invalid: {result.get('error', 'unknown error')}")
        return
    artifact = result.get("artifact") or {}
    needs = build_research_supplement_needs(artifact, positions)
    st.markdown(
        "<div class='section-label'><span>Supplement Needs</span>"
        f"<span class='count'>{len(needs)} portfolio tickers need action</span></div>",
        unsafe_allow_html=True,
    )
    metric_cols = st.columns(3, gap="small") if hasattr(st, "columns") else []
    metrics = [
        ("Missing", sum(1 for row in needs if row.get("status") == "missing_brief")),
        ("Needs review", sum(1 for row in needs if row.get("status") == "needs_review")),
        ("Portfolio", len(positions)),
    ]
    for index, (label, value) in enumerate(metrics):
        if metric_cols:
            with metric_cols[index]:
                st.metric(label, value)
    if not needs:
        message = "No portfolio tickers currently need supplemental research."
        if hasattr(st, "info"):
            st.info(message)
        else:
            st.markdown(message)
        return
    if hasattr(st, "caption"):
        st.caption(
            "Fill data/supplemental_research_reports.template.csv or export a prefilled template, "
            "then run scripts.refresh_public_dashboard_artifacts with --supplemental-table-input."
        )
    for row in needs[:100]:
        st.markdown(_research_supplement_need_html(row), unsafe_allow_html=True)


def _count_by(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key) or "")
        counts[value] = counts.get(value, 0) + 1
    return counts


def _body_text_available_count(source_quality_counts: dict[str, int]) -> int:
    return (
        source_quality_counts.get("extracted", 0)
        + source_quality_counts.get("full_text", 0)
        + source_quality_counts.get("partial_text", 0)
    )


REPORT_NOISE_TERMS = (
    "매수 중립",
    "중립(보유) 매도",
    "Underperform",
    "Neutral(중립)",
    "투자등급",
    "유니버스 투자등급",
    "Company Brief",
    "Issue Comment",
    "본 자료에 수록된",
    "영업이익/금융비용",
    "수정주가",
    "목표 PER",
    "12MF PER",
    "12MF PBR",
    "그림",
    "향후 6개월간 업종지수",
    "담당 애널리스트",
    "추천일자 투자의견",
    "목표가격",
    "좌축",
    "우축",
    "(좌)",
    "(우)",
    "수익성(%)",
    "단기투자자산감소",
    "각 법인 지분율 고려",
    "영업실적 및 주요 투자지표",
    "DAISHIN SECURITIES",
    "재무활동 현금흐름",
    "Trading Buy",
    "Not covered",
    "Hold 추천",
    "추천기준일",
    "평균종가대비",
    "투자판단 3단계",
    "매수 86",
    "중립 10",
    "유동성공급자",
    "절대수익률",
    "업종지수상승률",
    "리오에 따라",
)
REPORT_PLACEHOLDER_TERMS = (
    "리포트의 본문 근거 추출이 제한적입니다",
    "본문 근거 추출은 제한적입니다",
    "본문 근거 추출이 제한적입니다",
)


def _research_report_card_html(row: dict[str, Any]) -> str:
    opinion = html.escape(str(row.get("investment_opinion") or "unknown"))
    ticker = html.escape(str(row.get("ticker") or ""))
    title = html.escape(str(row.get("title") or ""))
    report_date = html.escape(str(row.get("report_date") or ""))
    source = html.escape(str(row.get("source") or ""))
    confidence = _to_float(row.get("confidence"))
    core_text = _first_report_text(row.get("buy_thesis"), row.get("summary"))
    growth_text = _first_report_text(row.get("growth_drivers"))
    earnings_text = _first_report_text(
        row.get("earnings_drivers"),
        row.get("valuation_view"),
        row.get("target_price_rationale"),
    )
    new_business_text = _first_report_text(row.get("new_business"))
    risk_text = _first_report_text(row.get("risk_factors"), row.get("sell_or_risk_thesis"))
    valuation_text = _first_report_text(row.get("valuation_view"), row.get("target_price_rationale"))
    stored_summary = " / ".join(_clean_report_fragments(row.get("summary"))) or "-"
    thesis = _section_or_empty(core_text, "종목 의견 문장은 추출되지 않았습니다.")
    growth = _section_or_empty(growth_text, "업황/성장 문장은 추출되지 않았습니다.")
    earnings = _section_or_empty(earnings_text, "실적/밸류 문장은 추출되지 않았습니다.")
    risk = _section_or_empty(risk_text, "명시 리스크 문장은 추출되지 않았습니다.")
    brief_items = _research_brief_items(
        core=core_text,
        growth=growth_text,
        new_business=new_business_text,
        earnings=earnings_text,
        valuation=valuation_text,
        risk=risk_text,
    )
    brief_html = "".join(
        f"<li><b>{html.escape(label)}</b>: {html.escape(text)}</li>"
        for label, text in brief_items
    )
    if not brief_html:
        brief_html = "<li><b>핵심</b>: 저장된 분석 문장이 부족합니다. 상세 문장을 확인해 주세요.</li>"
    evidence = html.escape(str(row.get("evidence_terms") or ""))
    return f"""
    <div class="research-card">
      <div class="head">
        <div>
          <div class="meta">{report_date} · {source} · confidence {confidence:.2f}</div>
          <div class="title">{ticker} · {title}</div>
        </div>
        <div class="pill">{opinion}</div>
      </div>
      <ul class="brief">{brief_html}</ul>
      <div class="research-grid">
        <div class="research-cell"><b>종목 의견</b>{thesis}</div>
        <div class="research-cell"><b>업황/성장</b>{growth}</div>
        <div class="research-cell"><b>신사업/모멘텀</b>{_section_or_empty(new_business_text, "신사업/모멘텀 문장은 추출되지 않았습니다.")}</div>
        <div class="research-cell"><b>실적/밸류</b>{earnings}</div>
        <div class="research-cell"><b>리스크</b>{risk}</div>
      </div>
      <details class="research-details">
        <summary>분석 문장 전체 보기</summary>
        <div class="raw">
          <div><b>근거 키워드</b>: {evidence or "-"}</div>
          <div><b>목표가/밸류</b>: {html.escape(valuation_text or "-")}</div>
          <div><b>정리된 저장 요약</b>: {html.escape(stored_summary)}</div>
        </div>
      </details>
    </div>
    """


def _ticker_research_brief_card_html(row: dict[str, Any]) -> str:
    ticker = html.escape(str(row.get("ticker") or ""))
    latest = html.escape(str(row.get("latest_report_date") or ""))
    opinion = html.escape(str(row.get("opinion") or "unknown"))
    headline = html.escape(str(row.get("headline") or ""))
    sections = row.get("sections") or {}
    quality = row.get("quality") or {}
    source_reports = list(row.get("source_reports") or [])
    llm_status = str(quality.get("llm_status") or "disabled")
    source_quality_label = html.escape(_source_quality_label(quality.get("source_quality")))
    report_count = int(_to_float(quality.get("report_count")))

    cells = [
        ("Stock view", sections.get("stock_view"), "No stock-view sentence."),
        ("Industry/Growth", sections.get("growth") or sections.get("industry"), "No growth sentence."),
        ("Earnings", sections.get("earnings"), "No earnings sentence."),
        ("Valuation", sections.get("valuation"), "No valuation sentence."),
        ("New business", sections.get("new_business"), "No new-business sentence."),
        ("Risk", sections.get("risk"), "No explicit risk sentence."),
    ]
    cells_html = "".join(
        f"<div class='research-cell'><b>{html.escape(label)}</b>{_section_or_empty(_first_report_text(value), empty)}</div>"
        for label, value, empty in cells
    )
    source_html = "".join(
        "<div>"
        f"<b>{html.escape(str(report.get('report_date') or ''))}</b> · "
        f"{html.escape(str(report.get('broker') or report.get('source') or ''))} · "
        f"{html.escape(str(report.get('title') or ''))}"
        "</div>"
        for report in source_reports[:5]
    ) or "<div>-</div>"
    return f"""
    <div class="research-card">
      <div class="head">
        <div>
          <div class="meta">Ticker Integrated Brief · {latest} · reports {report_count} · {source_quality_label}</div>
          <div class="title">{ticker} · {headline}</div>
        </div>
        <div class="pill">{opinion}</div>
      </div>
      <ul class="brief">
        <li><b>LLM {html.escape(llm_status)}</b>: External LLM summary is opt-in and cached separately.</li>
      </ul>
      <div class="research-grid">{cells_html}</div>
      <details class="research-details">
        <summary>Source reports</summary>
        <div class="raw">{source_html}</div>
      </details>
    </div>
    """


def _research_quality_issue_html(issue: dict[str, Any]) -> str:
    ticker = html.escape(str(issue.get("ticker") or ""))
    reasons = ", ".join(str(reason) for reason in issue.get("reasons", [])) or "-"
    missing = ", ".join(str(section) for section in issue.get("missing_sections", [])) or "-"
    action_label, next_step = _quality_issue_action(issue)
    source_quality = html.escape(_source_quality_label(issue.get("source_quality")))
    confidence = _to_float(issue.get("confidence"))
    latest = html.escape(str(issue.get("latest_report_date") or ""))
    report_count = int(_to_float(issue.get("report_count")))
    return f"""
    <div class="research-card">
      <div class="head">
        <div>
          <div class="meta">Quality Review · {latest} · reports {report_count} · confidence {confidence:.2f}</div>
          <div class="title">{ticker} · {html.escape(reasons)}</div>
        </div>
        <div class="pill">{source_quality}</div>
      </div>
      <div class="research-grid">
        <div class="research-cell"><b>Action</b>{html.escape(action_label)}</div>
        <div class="research-cell"><b>Next step</b>{html.escape(next_step)}</div>
        <div class="research-cell"><b>Reasons</b>{html.escape(reasons)}</div>
        <div class="research-cell"><b>Missing sections</b>{html.escape(missing)}</div>
      </div>
    </div>
    """


def _quality_issue_action(issue: dict[str, Any]) -> tuple[str, str]:
    reasons = {str(reason) for reason in issue.get("reasons", [])}
    missing_sections = [str(section) for section in issue.get("missing_sections", []) if section]
    source_quality = str(issue.get("source_quality") or "")
    if "weak_source_quality" in reasons and missing_sections:
        return "Source supplement", "Find or add a better public source/body text."
    if "weak_source_quality" in reasons and not missing_sections:
        return "Source age review", "Sections are filled; review only after section gaps."
    if "stale_report" in reasons:
        return "Latest report check", "Find a newer report or keep it in latest-not-found."
    if missing_sections and source_quality in {"full_text", "partial_text"}:
        return "Parser backfill", "Re-parse existing full or partial body text."
    if "low_confidence" in reasons:
        return "Confidence review", "Review confidence and source evidence."
    return "Manual review", "Review after automated queues are cleared."


def _research_supplement_need_html(item: dict[str, Any]) -> str:
    ticker = html.escape(str(item.get("ticker") or ""))
    name = html.escape(str(item.get("name") or ""))
    status = html.escape(str(item.get("status") or ""))
    latest = html.escape(str(item.get("latest_report_date") or "-"))
    reasons = ", ".join(str(reason) for reason in item.get("reasons", [])) or "-"
    missing = ", ".join(str(section) for section in item.get("missing_sections", [])) or "-"
    source_quality = _source_quality_label(item.get("source_quality"))
    source_quality_display = html.escape(source_quality or "-")
    confidence = _to_float(item.get("confidence"))
    return f"""
    <div class="research-card">
      <div class="head">
        <div>
          <div class="meta">Supplement Need · latest {latest} · confidence {confidence:.2f} · {source_quality_display}</div>
          <div class="title">{ticker} · {name}</div>
        </div>
        <div class="pill">{status}</div>
      </div>
      <div class="research-grid">
        <div class="research-cell"><b>Reasons</b>{html.escape(reasons)}</div>
        <div class="research-cell"><b>Missing sections</b>{html.escape(missing)}</div>
      </div>
    </div>
    """


def _first_report_text(*values: object) -> str:
    fragments = _clean_report_fragments(*values)
    return fragments[0] if fragments else ""


def _clean_report_fragments(*values: object) -> list[str]:
    fragments: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        text = _strip_summary_prefix(text)
        for part in text.split(" / "):
            cleaned = _clean_report_fragment(part)
            if cleaned and cleaned not in fragments and not _is_report_display_noise(cleaned):
                fragments.append(cleaned)
    return fragments


def _strip_summary_prefix(text: str) -> str:
    marker = "핵심 근거:"
    if marker in text:
        return text.split(marker, 1)[1].strip()
    return text


def _clean_report_fragment(text: str) -> str:
    cleaned = " ".join(str(text or "").replace("\n", " ").split())
    cleaned = cleaned.strip(" -·ㆍ,;:")
    cleaned = cleaned.replace("Company Brief", "").strip()
    cleaned = cleaned.lstrip("■▪●◆□- ").strip()
    cleaned = re.sub(r"^\[[^\]]+\]\s*", "", cleaned).strip()
    cleaned = re.sub(r"^\d{6}:\s*", "", cleaned).strip()
    cleaned = re.sub(r"^[가-힣A-Za-z&.\s]+?\(\d{6}/[^)]*\)", "", cleaned).strip()
    return cleaned


def _is_report_display_noise(text: str) -> bool:
    if len(text) < 5:
        return True
    if _looks_like_cut_report_fragment(text):
        return True
    if any(term in text for term in REPORT_PLACEHOLDER_TERMS):
        return True
    if any(term in text for term in REPORT_NOISE_TERMS):
        return True
    numeric_tokens = [token for token in text.split() if any(ch.isdigit() for ch in token)]
    table_terms = (
        "매출액",
        "매출총이익",
        "영업이익",
        "매출원가",
        "영업이익률",
        "순이익",
        "PER",
        "PBR",
    )
    if re.match(r"^목표(?:가격|주가)\s*[\d,]+", text):
        return True
    if len(numeric_tokens) >= 3 and any(term in text for term in ("순이익", "수익성", "자산감소", "지분율")):
        return True
    if len(numeric_tokens) >= 2 and text.endswith(("를", "을", "로", "에", "의")):
        return True
    if len(numeric_tokens) >= 5 and any(term in text for term in table_terms):
        return True
    return len(numeric_tokens) >= 6


def _looks_like_cut_report_fragment(text: str) -> bool:
    stripped = text.strip()
    cut_starts = ("인의 ", "로 ", "대비 ", "및 ")
    if stripped.startswith("비 부담"):
        return True
    if any(stripped.startswith(start) for start in cut_starts):
        return True
    if stripped.count("(") > stripped.count(")"):
        return True
    cut_endings = (
        " 허브",
        " 거",
        " 전년",
        " 매",
        " OPM",
        "억원(",
        "투자와 단가",
        "이익 성과를",
        "해외 현지",
        "신규",
        "에 부",
        "달성하",
        "투자포인트는",
        "존재하",
    )
    if any(stripped.endswith(ending) for ending in cut_endings):
        return True
    numeric_tokens = [token for token in stripped.split() if any(ch.isdigit() for ch in token)]
    return bool(numeric_tokens and re.search(r"\d+\s*(조|억|원|%)$", stripped))


def _section_or_empty(text: str, empty_text: str) -> str:
    if text:
        return html.escape(text)
    return f"<span class='empty'>{html.escape(empty_text)}</span>"


def _research_brief_items(
    *,
    core: str,
    growth: str,
    new_business: str,
    earnings: str,
    valuation: str,
    risk: str,
) -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    if core:
        items.append(("핵심", core))
    if growth:
        items.append(("업황/성장", growth))
    if new_business:
        items.append(("신사업", new_business))
    if earnings:
        items.append(("실적", earnings))
    elif valuation:
        items.append(("밸류/목표가", valuation))
    if risk:
        items.append(("리스크", risk))
    return items[:4]


def _install_browser_auto_refresh(st, interval_seconds: int) -> None:
    if not hasattr(st, "components"):
        return
    try:
        st.components.v1.html(
            f"""
            <script>
            window.setTimeout(function() {{
                window.parent.location.reload();
            }}, {int(interval_seconds) * 1000});
            </script>
            """,
            height=0,
        )
    except Exception:
        return


def main() -> None:
    import streamlit as st

    result = load_snapshot(DEFAULT_SNAPSHOT_PATH)
    if result["status"] == "missing":
        st.set_page_config(page_title="Public Portfolio", layout="wide")
        st.markdown(_build_css("regular", "kr", "#f2c94c", TYPO_OPTS["plex"][1], TYPO_OPTS["plex"][2]), unsafe_allow_html=True)
        st.markdown(_topbar_html({}), unsafe_allow_html=True)
        st.warning(f"Snapshot file is missing: {DEFAULT_SNAPSHOT_PATH}")
        return
    if result["status"] == "invalid":
        st.set_page_config(page_title="Public Portfolio", layout="wide")
        st.markdown(_build_css("regular", "kr", "#f2c94c", TYPO_OPTS["plex"][1], TYPO_OPTS["plex"][2]), unsafe_allow_html=True)
        st.markdown(_topbar_html({}), unsafe_allow_html=True)
        st.warning(f"Snapshot file is invalid: {result.get('error', 'unknown error')}")
        return
    render_dashboard(result["snapshot"])


if __name__ == "__main__":
    main()
