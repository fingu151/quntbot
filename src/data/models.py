from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def utc_now() -> datetime:
    # Python 3.10 호환을 위해 timezone.utc 사용 (3.11+ 의 datetime.UTC 와 동등)
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Stock(Base):
    __tablename__ = "stocks"

    ticker: Mapped[str] = mapped_column(String(12), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    market: Mapped[str] = mapped_column(String(20), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)


class DailyPrice(Base):
    __tablename__ = "daily_prices"
    __table_args__ = (UniqueConstraint("ticker", "date", name="uq_daily_prices_ticker_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(12), nullable=False, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    open: Mapped[float | None] = mapped_column(Float)
    high: Mapped[float | None] = mapped_column(Float)
    low: Mapped[float | None] = mapped_column(Float)
    close: Mapped[float | None] = mapped_column(Float)
    volume: Mapped[float | None] = mapped_column(Float)
    trading_value: Mapped[float | None] = mapped_column(Float)
    market_cap: Mapped[float | None] = mapped_column(Float)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)


class MarketIndexPrice(Base):
    __tablename__ = "market_index_prices"
    __table_args__ = (UniqueConstraint("symbol", "date", name="uq_market_index_prices_symbol_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    open: Mapped[float | None] = mapped_column(Float)
    high: Mapped[float | None] = mapped_column(Float)
    low: Mapped[float | None] = mapped_column(Float)
    close: Mapped[float | None] = mapped_column(Float)
    volume: Mapped[float | None] = mapped_column(Float)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)


class Fundamental(Base):
    __tablename__ = "fundamentals"
    __table_args__ = (UniqueConstraint("ticker", "date", name="uq_fundamentals_ticker_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(12), nullable=False, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    bps: Mapped[float | None] = mapped_column(Float)
    per: Mapped[float | None] = mapped_column(Float)
    pbr: Mapped[float | None] = mapped_column(Float)
    eps: Mapped[float | None] = mapped_column(Float)
    div: Mapped[float | None] = mapped_column(Float)
    dps: Mapped[float | None] = mapped_column(Float)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)


class QualityMetric(Base):
    __tablename__ = "quality_metrics"
    __table_args__ = (
        UniqueConstraint(
            "ticker",
            "fiscal_year",
            "fiscal_quarter",
            name="uq_quality_metrics_ticker_period",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(12), nullable=False, index=True)
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)
    fiscal_quarter: Mapped[int] = mapped_column(Integer, nullable=False)
    roe: Mapped[float | None] = mapped_column(Float)
    operating_margin: Mapped[float | None] = mapped_column(Float)
    debt_ratio: Mapped[float | None] = mapped_column(Float)
    published_at: Mapped[date | None] = mapped_column(Date)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)


class TelegramSignal(Base):
    __tablename__ = "telegram_signals"
    __table_args__ = (
        UniqueConstraint("message_date", "ticker", name="uq_telegram_signals_date_ticker"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    message_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    ticker: Mapped[str] = mapped_column(String(12), nullable=False, index=True)
    signal_type: Mapped[str] = mapped_column(String(10), nullable=False)  # "수혜" | "주의"
    star_rating: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    raw_score: Mapped[float] = mapped_column(Float, nullable=False)
    target_price: Mapped[float | None] = mapped_column(Float)
    message_id: Mapped[int | None] = mapped_column(Integer)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)


class BusanstockSignal(Base):
    __tablename__ = "busanstock_signals"
    __table_args__ = (
        UniqueConstraint(
            "signal_date",
            "ticker",
            "source_section",
            name="uq_busanstock_signals_date_ticker_section",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    signal_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    ticker: Mapped[str] = mapped_column(String(12), nullable=False, index=True)
    signal_type: Mapped[str] = mapped_column(String(20), nullable=False)
    source_section: Mapped[str] = mapped_column(String(40), nullable=False)
    raw_score: Mapped[float] = mapped_column(Float, nullable=False)
    detail: Mapped[str | None] = mapped_column(Text)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)


class InvestorFlow(Base):
    __tablename__ = "investor_flows"
    __table_args__ = (
        UniqueConstraint("ticker", "date", name="uq_investor_flows_ticker_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(12), nullable=False, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    individual_net_buy: Mapped[float | None] = mapped_column(Float)
    foreign_net_buy: Mapped[float | None] = mapped_column(Float)
    institution_net_buy: Mapped[float | None] = mapped_column(Float)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)


class ResearchReportSignal(Base):
    __tablename__ = "research_report_signals"
    __table_args__ = (
        UniqueConstraint(
            "report_date",
            "ticker",
            "source",
            "title",
            name="uq_research_reports_date_ticker_source_title",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    ticker: Mapped[str] = mapped_column(String(12), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    region: Mapped[str] = mapped_column(String(20), nullable=False)
    broker: Mapped[str | None] = mapped_column(String(80))
    rating: Mapped[str | None] = mapped_column(String(40))
    rating_score: Mapped[float | None] = mapped_column(Float)
    target_price: Mapped[float | None] = mapped_column(Float)
    previous_target_price: Mapped[float | None] = mapped_column(Float)
    target_price_change_pct: Mapped[float | None] = mapped_column(Float)
    sentiment_score: Mapped[float | None] = mapped_column(Float)
    raw_score: Mapped[float] = mapped_column(Float, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)


class ResearchReportAnalysis(Base):
    __tablename__ = "research_report_analyses"
    __table_args__ = (
        UniqueConstraint("report_signal_id", name="uq_research_report_analysis_signal"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_signal_id: Mapped[int] = mapped_column(
        ForeignKey("research_report_signals.id"),
        nullable=False,
        index=True,
    )
    ticker: Mapped[str] = mapped_column(String(12), nullable=False, index=True)
    report_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    broker: Mapped[str | None] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)
    body_text_status: Mapped[str] = mapped_column(String(30), nullable=False)
    body_text_chars: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    investment_opinion: Mapped[str] = mapped_column(String(20), nullable=False)
    buy_thesis: Mapped[str | None] = mapped_column(Text)
    sell_or_risk_thesis: Mapped[str | None] = mapped_column(Text)
    growth_drivers: Mapped[str | None] = mapped_column(Text)
    earnings_drivers: Mapped[str | None] = mapped_column(Text)
    valuation_view: Mapped[str | None] = mapped_column(Text)
    target_price_rationale: Mapped[str | None] = mapped_column(Text)
    risk_factors: Mapped[str | None] = mapped_column(Text)
    evidence_terms: Mapped[str | None] = mapped_column(Text)
    analysis_version: Mapped[str] = mapped_column(String(30), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)


class ResearchReportBrief(Base):
    __tablename__ = "research_report_briefs"
    __table_args__ = (
        UniqueConstraint("report_signal_id", name="uq_research_report_brief_signal"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_signal_id: Mapped[int] = mapped_column(
        ForeignKey("research_report_signals.id"),
        nullable=False,
        index=True,
    )
    ticker: Mapped[str] = mapped_column(String(12), nullable=False, index=True)
    report_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    broker: Mapped[str | None] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)
    report_type: Mapped[str] = mapped_column(String(40), nullable=False)
    headline: Mapped[str] = mapped_column(Text, nullable=False)
    opinion: Mapped[str] = mapped_column(String(20), nullable=False)
    stock_view: Mapped[str | None] = mapped_column(Text)
    earnings: Mapped[str | None] = mapped_column(Text)
    industry: Mapped[str | None] = mapped_column(Text)
    new_business: Mapped[str | None] = mapped_column(Text)
    valuation: Mapped[str | None] = mapped_column(Text)
    risks: Mapped[str | None] = mapped_column(Text)
    source_quality: Mapped[str] = mapped_column(String(30), nullable=False)
    brief_version: Mapped[str] = mapped_column(String(30), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)


class SyncRun(Base):
    __tablename__ = "sync_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    universe_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    price_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fundamental_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)


class QualitySyncRun(Base):
    __tablename__ = "quality_sync_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    year_from: Mapped[int | None] = mapped_column(Integer)
    year_to: Mapped[int | None] = mapped_column(Integer)
    metric_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
