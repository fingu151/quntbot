from __future__ import annotations

from collections.abc import Iterable
from datetime import date, timedelta
from typing import Any

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from src.data.models import (
    BusanstockSignal,
    DailyPrice,
    Fundamental,
    InvestorFlow,
    MarketIndexPrice,
    QualityMetric,
    ResearchReportAnalysis,
    ResearchReportBrief,
    ResearchReportSignal,
    Stock,
    utc_now,
)


SQLITE_UPSERT_BATCH_SIZE = 500
SQLITE_LOOKUP_BATCH_SIZE = 200


def _chunks(rows: list[dict[str, Any]], size: int) -> Iterable[list[dict[str, Any]]]:
    for start in range(0, len(rows), size):
        yield rows[start : start + size]


def _upsert_many(
    session: Session,
    model: type,
    rows: Iterable[dict[str, Any]],
    conflict_columns: list[str],
    update_columns: list[str],
) -> int:
    has_updated_at = "updated_at" in model.__table__.columns
    now = utc_now()
    prepared = [
        {**row, **({"updated_at": now} if has_updated_at else {})}
        for row in rows
    ]
    if not prepared:
        return 0

    for batch in _chunks(prepared, SQLITE_UPSERT_BATCH_SIZE):
        statement = insert(model).values(batch)
        excluded = statement.excluded
        update_values = {column: getattr(excluded, column) for column in update_columns}
        if has_updated_at:
            update_values["updated_at"] = utc_now()

        statement = statement.on_conflict_do_update(
            index_elements=conflict_columns,
            set_=update_values,
        )
        session.execute(statement)
    return len(prepared)


def upsert_stocks(session: Session, rows: Iterable[dict[str, Any]]) -> int:
    prepared = [
        {**row, "instrument_type": row.get("instrument_type", "COMMON_STOCK")}
        for row in rows
    ]
    return _upsert_many(
        session,
        Stock,
        prepared,
        conflict_columns=["ticker"],
        update_columns=["name", "market", "instrument_type", "is_active"],
    )


def deactivate_stocks_not_in(session: Session, tickers: Iterable[str]) -> int:
    active_tickers = list(tickers)
    statement = (
        update(Stock)
        .where(Stock.is_active.is_(True), Stock.ticker.not_in(active_tickers))
        .values(is_active=False, updated_at=utc_now())
    )
    result = session.execute(statement)
    return int(result.rowcount or 0)


def upsert_daily_prices(session: Session, rows: Iterable[dict[str, Any]]) -> int:
    return _upsert_many(
        session,
        DailyPrice,
        rows,
        conflict_columns=["ticker", "date"],
        update_columns=[
            "open",
            "high",
            "low",
            "close",
            "volume",
            "trading_value",
            "market_cap",
        ],
    )


def upsert_market_index_prices(session: Session, rows: Iterable[dict[str, Any]]) -> int:
    return _upsert_many(
        session,
        MarketIndexPrice,
        rows,
        conflict_columns=["symbol", "date"],
        update_columns=["open", "high", "low", "close", "volume"],
    )


def upsert_fundamentals(session: Session, rows: Iterable[dict[str, Any]]) -> int:
    return _upsert_many(
        session,
        Fundamental,
        rows,
        conflict_columns=["ticker", "date"],
        update_columns=["bps", "per", "pbr", "eps", "div", "dps"],
    )


def upsert_quality_metrics(session: Session, rows: Iterable[dict[str, Any]]) -> int:
    return _upsert_many(
        session,
        QualityMetric,
        rows,
        conflict_columns=["ticker", "fiscal_year", "fiscal_quarter"],
        update_columns=["roe", "operating_margin", "debt_ratio", "published_at"],
    )


def upsert_investor_flows(session: Session, rows: Iterable[dict[str, Any]]) -> int:
    return _upsert_many(
        session,
        InvestorFlow,
        rows,
        conflict_columns=["ticker", "date"],
        update_columns=["individual_net_buy", "foreign_net_buy", "institution_net_buy"],
    )


def upsert_research_report_signals(session: Session, rows: Iterable[dict[str, Any]]) -> int:
    return _upsert_many(
        session,
        ResearchReportSignal,
        rows,
        conflict_columns=["report_date", "ticker", "source", "title"],
        update_columns=[
            "region",
            "broker",
            "rating",
            "rating_score",
            "target_price",
            "previous_target_price",
            "target_price_change_pct",
            "sentiment_score",
            "raw_score",
            "source_url",
        ],
    )


def upsert_research_report_analyses(session: Session, rows: Iterable[dict[str, Any]]) -> int:
    return _upsert_many(
        session,
        ResearchReportAnalysis,
        rows,
        conflict_columns=["report_signal_id"],
        update_columns=[
            "ticker",
            "report_date",
            "source",
            "broker",
            "title",
            "source_url",
            "body_text_status",
            "body_text_chars",
            "summary",
            "investment_opinion",
            "buy_thesis",
            "sell_or_risk_thesis",
            "growth_drivers",
            "earnings_drivers",
            "valuation_view",
            "target_price_rationale",
            "risk_factors",
            "evidence_terms",
            "analysis_version",
            "confidence",
        ],
    )


def upsert_research_report_briefs(session: Session, rows: Iterable[dict[str, Any]]) -> int:
    return _upsert_many(
        session,
        ResearchReportBrief,
        rows,
        conflict_columns=["report_signal_id"],
        update_columns=[
            "ticker",
            "report_date",
            "source",
            "broker",
            "title",
            "source_url",
            "report_type",
            "headline",
            "opinion",
            "stock_view",
            "earnings",
            "industry",
            "new_business",
            "valuation",
            "risks",
            "source_quality",
            "brief_version",
            "confidence",
        ],
    )


def get_research_report_signals_by_keys(
    session: Session,
    keys: Iterable[tuple[date, str, str, str]],
) -> list[ResearchReportSignal]:
    prepared = list(keys)
    if not prepared:
        return []
    rows: list[ResearchReportSignal] = []
    for batch in _chunks(prepared, SQLITE_LOOKUP_BATCH_SIZE):
        clauses = [
            (
                (ResearchReportSignal.report_date == report_date)
                & (ResearchReportSignal.ticker == ticker)
                & (ResearchReportSignal.source == source)
                & (ResearchReportSignal.title == title)
            )
            for report_date, ticker, source, title in batch
        ]
        rows.extend(session.scalars(select(ResearchReportSignal).where(or_(*clauses))).all())
    return rows


def upsert_busanstock_signals(session: Session, rows: Iterable[dict[str, Any]]) -> int:
    return _upsert_many(
        session,
        BusanstockSignal,
        rows,
        conflict_columns=["signal_date", "ticker", "source_section"],
        update_columns=["signal_type", "raw_score", "detail"],
    )


def replace_busanstock_signals_for_date(
    session: Session,
    signal_date: date,
    rows: Iterable[dict[str, Any]],
) -> int:
    session.execute(delete(BusanstockSignal).where(BusanstockSignal.signal_date == signal_date))
    return upsert_busanstock_signals(session, rows)


def get_latest_busanstock_signals(session: Session, as_of_date: date) -> dict[str, float]:
    """Return {ticker: summed raw_score} for the same-day Busanstock report."""
    latest_date = as_of_date
    rows = session.scalars(
        select(BusanstockSignal).where(BusanstockSignal.signal_date == latest_date)
    ).all()
    scores: dict[str, float] = {}
    for row in rows:
        scores[row.ticker] = scores.get(row.ticker, 0.0) + float(row.raw_score)
    return scores


def get_recent_investor_flow_scores(
    session: Session,
    as_of_date: date,
    *,
    lookback_days: int = 5,
) -> dict[str, float]:
    """Return retail-vs-smart-money flow overlay scores by ticker."""
    start_date = as_of_date - timedelta(days=lookback_days * 2)
    flow_rows = session.scalars(
        select(InvestorFlow).where(
            InvestorFlow.date >= start_date,
            InvestorFlow.date <= as_of_date,
        )
    ).all()
    if not flow_rows:
        return {}

    by_ticker: dict[str, dict[str, float]] = {}
    for row in flow_rows:
        values = by_ticker.setdefault(
            row.ticker,
            {"individual": 0.0, "foreign": 0.0, "institution": 0.0, "trading_value": 0.0},
        )
        values["individual"] += float(row.individual_net_buy or 0.0)
        values["foreign"] += float(row.foreign_net_buy or 0.0)
        values["institution"] += float(row.institution_net_buy or 0.0)

    price_rows = session.scalars(
        select(DailyPrice).where(
            DailyPrice.date >= start_date,
            DailyPrice.date <= as_of_date,
            DailyPrice.ticker.in_(by_ticker),
        )
    ).all()
    for row in price_rows:
        if row.ticker in by_ticker:
            by_ticker[row.ticker]["trading_value"] += float(row.trading_value or 0.0)

    scores: dict[str, float] = {}
    for ticker, values in by_ticker.items():
        score = _investor_flow_score(values)
        if score != 0.0:
            scores[ticker] = score
    return scores


def _investor_flow_score(values: dict[str, float]) -> float:
    individual = values["individual"]
    foreign = values["foreign"]
    institution = values["institution"]
    trading_value = values["trading_value"] or (
        abs(individual) + abs(foreign) + abs(institution)
    )
    if trading_value <= 0:
        return 0.0

    individual_ratio = individual / trading_value
    foreign_ratio = foreign / trading_value
    institution_ratio = institution / trading_value

    if individual > 0 and foreign < 0 and institution < 0:
        if individual_ratio >= 0.05 and foreign_ratio <= -0.02 and institution_ratio <= -0.02:
            return -1.0
        return -0.7
    if foreign > 0 and institution > 0:
        return 0.6
    if foreign > 0 or institution > 0:
        return 0.3
    return 0.0


def get_recent_research_report_scores(
    session: Session,
    as_of_date: date,
    *,
    lookback_days: int = 30,
) -> dict[str, float]:
    """Return recency-weighted research-report overlay scores in roughly [-1, 1]."""
    start_date = as_of_date - timedelta(days=lookback_days)
    rows = session.scalars(
        select(ResearchReportSignal).where(
            ResearchReportSignal.report_date >= start_date,
            ResearchReportSignal.report_date <= as_of_date,
        )
    ).all()
    if not rows:
        return {}

    weighted: dict[str, float] = {}
    weights: dict[str, float] = {}
    for row in rows:
        age_days = max(0, (as_of_date - row.report_date).days)
        recency_weight = max(0.2, 1.0 - (age_days / max(lookback_days, 1)))
        raw_score = max(-1.0, min(1.0, float(row.raw_score)))
        weighted[row.ticker] = weighted.get(row.ticker, 0.0) + raw_score * recency_weight
        weights[row.ticker] = weights.get(row.ticker, 0.0) + recency_weight

    scores = {}
    for ticker, weighted_score in weighted.items():
        weight = weights.get(ticker, 0.0)
        if weight <= 0:
            continue
        score = weighted_score / weight
        if score != 0.0:
            scores[ticker] = score
    return scores


def count_rows(session: Session) -> dict[str, int]:
    return {
        "stocks": session.scalar(select(func.count()).select_from(Stock)) or 0,
        "daily_prices": session.scalar(select(func.count()).select_from(DailyPrice)) or 0,
        "fundamentals": session.scalar(select(func.count()).select_from(Fundamental)) or 0,
    }
