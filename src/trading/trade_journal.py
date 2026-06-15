from __future__ import annotations

import json
import time
from collections.abc import Callable, Iterable
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import Engine

from src.data.database import create_tables, get_engine, session_scope
from src.data.repositories import insert_trade_journal_run, upsert_trade_journal_events
from src.trading.kis_client import FilledOrder


class TradeJournalRecorder:
    def __init__(
        self,
        db_engine: Engine,
        fill_provider: Any,
        *,
        fill_retry_attempts: int = 3,
        fill_retry_delay_sec: float = 0.7,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self._db_engine = db_engine
        self._fill_provider = fill_provider
        self._fill_retry_attempts = max(1, fill_retry_attempts)
        self._fill_retry_delay_sec = max(0.0, fill_retry_delay_sec)
        self._sleeper = sleeper

    def record_rebalance_execution(
        self,
        *,
        trade_date: date,
        dry_run_json: Path,
        execution_report_json: Path | None,
        order_numbers: dict[str, list[str]] | None,
        successful_tickers: dict[str, list[str]],
    ) -> dict[str, int | str]:
        context = _load_dry_run_context(dry_run_json)
        expected = _expected_successes(order_numbers, successful_tickers)
        if not expected:
            return self._record_run(
                trade_date=trade_date,
                run_source="rebalance",
                status="no_orders",
                recorded_count=0,
                unmatched=[],
                dry_run_json=dry_run_json,
                execution_report_json=execution_report_json,
            )

        try:
            fills = self._get_daily_filled_orders(
                trade_date,
                trade_date,
                order_nos={item["order_no"] for item in expected if item.get("order_no")},
            )
        except Exception as exc:
            return self._record_run(
                trade_date=trade_date,
                run_source="rebalance",
                status="unmatched",
                recorded_count=0,
                unmatched=[item.get("order_no") or item["ticker"] for item in expected],
                dry_run_json=dry_run_json,
                execution_report_json=execution_report_json,
                error_message=str(exc),
            )

        events = [
            _event_from_fill(
                fill,
                trade_date=trade_date,
                order_source="rebalance",
                order_reason=context["reasons"].get((fill.side, fill.ticker), ""),
                score_context=context["targets"].get(fill.ticker, {}),
                dry_run_json=dry_run_json,
                execution_report_json=execution_report_json,
            )
            for fill in fills
            if any(_matches_expected_fill(fill, item) for item in expected)
        ]
        unmatched = [
            item.get("order_no") or item["ticker"]
            for item in expected
            if not any(_matches_expected_fill(fill, item) for fill in fills)
        ]
        recorded_count = self._upsert_events(events)
        return self._record_run(
            trade_date=trade_date,
            run_source="rebalance",
            status="recorded" if not unmatched else "unmatched",
            recorded_count=recorded_count,
            unmatched=unmatched,
            dry_run_json=dry_run_json,
            execution_report_json=execution_report_json,
        )

    def record_order_acceptance(
        self,
        *,
        ticker: str,
        side: str,
        qty: int,
        order_no: str,
        order_reason: str,
        order_source: str,
        trade_date: date,
    ) -> dict[str, int | str]:
        if not order_no:
            return self._record_run(
                trade_date=trade_date,
                run_source=order_source,
                status="unmatched",
                recorded_count=0,
                unmatched=[ticker],
                error_message="missing_order_no",
            )
        try:
            fills = self._get_daily_filled_orders(
                trade_date,
                trade_date,
                order_nos={order_no},
            )
        except Exception as exc:
            return self._record_run(
                trade_date=trade_date,
                run_source=order_source,
                status="unmatched",
                recorded_count=0,
                unmatched=[order_no],
                error_message=str(exc),
            )
        events = [
            _event_from_fill(
                fill,
                trade_date=trade_date,
                order_source=order_source,
                order_reason=order_reason,
            )
            for fill in fills
            if fill.order_no == order_no and fill.ticker == ticker and fill.side == side
        ]
        recorded_count = self._upsert_events(events)
        unmatched = [] if recorded_count else [order_no]
        return self._record_run(
            trade_date=trade_date,
            run_source=order_source,
            status="recorded" if recorded_count else "unmatched",
            recorded_count=recorded_count,
            unmatched=unmatched,
        )

    def _get_daily_filled_orders(
        self,
        start_date: date,
        end_date: date,
        *,
        order_nos: set[str],
    ) -> list[FilledOrder]:
        last_error: Exception | None = None
        for attempt in range(self._fill_retry_attempts):
            try:
                fills = list(
                    self._fill_provider.get_daily_filled_orders(
                        start_date,
                        end_date,
                        order_nos=order_nos,
                    )
                )
            except Exception as exc:
                last_error = exc
                fills = []
            if fills:
                return fills
            if attempt < self._fill_retry_attempts - 1 and self._fill_retry_delay_sec:
                self._sleeper(self._fill_retry_delay_sec)
        if last_error is not None:
            raise last_error
        return []

    def _upsert_events(self, events: list[dict[str, Any]]) -> int:
        if not events:
            return 0
        with session_scope(self._db_engine) as session:
            return upsert_trade_journal_events(session, events)

    def _record_run(
        self,
        *,
        trade_date: date,
        run_source: str,
        status: str,
        recorded_count: int,
        unmatched: Iterable[str],
        dry_run_json: Path | None = None,
        execution_report_json: Path | None = None,
        error_message: str | None = None,
    ) -> dict[str, int | str]:
        unmatched_list = [str(item) for item in unmatched if item]
        with session_scope(self._db_engine) as session:
            insert_trade_journal_run(
                session,
                {
                    "run_source": run_source,
                    "trade_date": trade_date,
                    "status": status,
                    "recorded_count": recorded_count,
                    "unmatched_count": len(unmatched_list),
                    "dry_run_json": str(dry_run_json) if dry_run_json else None,
                    "execution_report_json": str(execution_report_json)
                    if execution_report_json
                    else None,
                    "unmatched_order_nos": ",".join(unmatched_list),
                    "error_message": error_message,
                },
            )
        return {
            "status": status,
            "recorded_count": recorded_count,
            "unmatched_count": len(unmatched_list),
        }


def record_rebalance_trade_journal(
    *,
    engine: Any,
    trade_date: date,
    dry_run_json: Path,
    execution_report_json: Path | None,
    order_numbers: dict[str, list[str]] | None,
    successful_tickers: dict[str, list[str]],
    database_url: str | None = None,
) -> dict[str, int | str]:
    db_engine = get_engine(database_url)
    create_tables(db_engine)
    recorder = TradeJournalRecorder(db_engine, engine)
    summary = recorder.record_rebalance_execution(
        trade_date=trade_date,
        dry_run_json=dry_run_json,
        execution_report_json=execution_report_json,
        order_numbers=order_numbers,
        successful_tickers=successful_tickers,
    )
    try:
        from scripts.generate_trade_journal_report import run as run_report

        run_report(db_engine=db_engine)
    except Exception as exc:
        summary = {**summary, "report_error": str(exc)}
    return summary


def _expected_successes(
    order_numbers: dict[str, list[str]] | None,
    successful_tickers: dict[str, list[str]],
) -> list[dict[str, str]]:
    expected: list[dict[str, str]] = []
    order_numbers = order_numbers or {}
    for side in ("SELL", "BUY"):
        tickers = [str(ticker) for ticker in successful_tickers.get(side, [])]
        numbers = [str(order_no) for order_no in order_numbers.get(side, [])]
        if numbers and len(numbers) == len(tickers):
            expected.extend(
                {"side": side, "ticker": ticker, "order_no": order_no}
                for ticker, order_no in zip(tickers, numbers)
            )
        else:
            expected.extend({"side": side, "ticker": ticker, "order_no": ""} for ticker in tickers)
    return expected


def _matches_expected_fill(fill: FilledOrder, expected: dict[str, str]) -> bool:
    if fill.side != expected["side"] or fill.ticker != expected["ticker"]:
        return False
    order_no = expected.get("order_no", "")
    return not order_no or fill.order_no == order_no


def _load_dry_run_context(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload = {}
    reasons = {
        (str(item.get("side", "")), str(item.get("ticker", ""))): str(item.get("reason", ""))
        for item in payload.get("orders") or []
        if item.get("ticker")
    }
    targets = {
        str(item.get("ticker", "")): dict(item)
        for item in payload.get("targets") or []
        if item.get("ticker")
    }
    return {"reasons": reasons, "targets": targets}


def _event_from_fill(
    fill: FilledOrder,
    *,
    trade_date: date,
    order_source: str,
    order_reason: str,
    score_context: dict[str, Any] | None = None,
    dry_run_json: Path | None = None,
    execution_report_json: Path | None = None,
) -> dict[str, Any]:
    score_context = score_context or {}
    raw = dict(fill.raw)
    return {
        "trade_date": fill.filled_at.date() if fill.filled_at else trade_date,
        "order_no": fill.order_no,
        "ticker": fill.ticker,
        "name": fill.name,
        "side": fill.side,
        "filled_qty": fill.filled_qty,
        "avg_fill_price": fill.avg_fill_price,
        "gross_amount": fill.filled_amount,
        "fee": _float_raw(raw, "fee", "ord_fee", "fee_amt"),
        "tax": _float_raw(raw, "tax", "tax_amt", "stex"),
        "order_reason": order_reason,
        "order_source": order_source,
        "order_status": "filled",
        "rank": _optional_int(score_context.get("rank")),
        "total_score": _optional_float(score_context.get("total_score")),
        "value_score": _optional_float(score_context.get("value_score")),
        "quality_score": _optional_float(score_context.get("quality_score")),
        "momentum_score": _optional_float(score_context.get("momentum_score")),
        "yield_score": _optional_float(score_context.get("yield_score")),
        "technical_score": _optional_float(score_context.get("technical_score")),
        "auxiliary_score": _optional_float(score_context.get("auxiliary_score")),
        "busanstock_score": _optional_float(score_context.get("busanstock_score")),
        "investor_flow_score": _optional_float(score_context.get("investor_flow_score")),
        "research_report_score": _optional_float(score_context.get("research_report_score")),
        "ordered_at": fill.ordered_at,
        "filled_at": fill.filled_at,
        "dry_run_json": str(dry_run_json) if dry_run_json else None,
        "execution_report_json": str(execution_report_json) if execution_report_json else None,
        "raw_json": json.dumps(raw, ensure_ascii=True, sort_keys=True),
    }


def _float_raw(raw: dict[str, Any], *keys: str) -> float:
    for key in keys:
        value = raw.get(key)
        if value not in (None, ""):
            return float(value)
    return 0.0


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)
