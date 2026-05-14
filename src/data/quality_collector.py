from __future__ import annotations

from typing import Any, Protocol

from loguru import logger
from sqlalchemy import Engine, select

from src.data.database import session_scope
from src.data.models import QualitySyncRun, Stock, utc_now
from src.data.repositories import upsert_quality_metrics


class QuotaExhausted(RuntimeError):
    pass


class QualityMetricsProvider(Protocol):
    def get_quality_metrics(
        self,
        ticker: str,
        *,
        year_from: int,
        year_to: int,
    ) -> list[dict[str, Any]]:
        ...


def sync_phase1_quality(
    *,
    engine: Engine,
    provider: QualityMetricsProvider,
    year_from: int,
    year_to: int,
    tickers: list[str] | None = None,
) -> dict[str, Any]:
    error: Exception | None = None
    result: dict[str, Any] | None = None

    with session_scope(engine) as session:
        sync_run = QualitySyncRun(
            status="running",
            year_from=year_from,
            year_to=year_to,
        )
        session.add(sync_run)
        session.flush()

        metric_count = 0
        ticker_errors: list[tuple[str, Exception]] = []
        try:
            target_tickers = tickers
            if target_tickers is None:
                target_tickers = list(
                    session.scalars(
                        select(Stock.ticker)
                        .where(Stock.is_active.is_(True))
                        .order_by(Stock.ticker)
                    )
                )

            for ticker in target_tickers:
                try:
                    rows = provider.get_quality_metrics(
                        ticker,
                        year_from=year_from,
                        year_to=year_to,
                    )
                except QuotaExhausted:
                    raise
                except Exception as exc:
                    ticker_errors.append((ticker, exc))
                    logger.warning(f"DART quality sync skipped ticker={ticker}: {exc}")
                    continue
                metric_count += upsert_quality_metrics(session, rows)

            if ticker_errors and metric_count == 0:
                raise ticker_errors[0][1]

            sync_run.status = "partial_success" if ticker_errors else "success"
            sync_run.metric_count = metric_count
            sync_run.finished_at = utc_now()
            if ticker_errors:
                sync_run.error_message = _format_ticker_errors(ticker_errors)
            result = {"metric_count": metric_count, "status": sync_run.status}
        except QuotaExhausted as exc:
            sync_run.status = "quota_exhausted"
            sync_run.metric_count = metric_count
            sync_run.finished_at = utc_now()
            sync_run.error_message = str(exc)
            result = {"metric_count": metric_count, "status": "quota_exhausted"}
        except Exception as exc:
            sync_run.status = "failed"
            sync_run.metric_count = metric_count
            sync_run.finished_at = utc_now()
            sync_run.error_message = str(exc)
            error = exc

    if error is not None:
        raise error
    if result is None:
        raise RuntimeError("quality sync finished without a result")
    return result


def _format_ticker_errors(ticker_errors: list[tuple[str, Exception]]) -> str:
    samples = [f"{ticker}: {exc}" for ticker, exc in ticker_errors[:5]]
    suffix = "" if len(ticker_errors) <= 5 else f"; ... {len(ticker_errors) - 5} more"
    return f"{len(ticker_errors)} ticker(s) failed: " + "; ".join(samples) + suffix
