from __future__ import annotations

import csv
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import select

from src.data.database import create_tables, get_engine, session_scope
from src.data.models import TradeJournalEvent
from src.data.repositories import (
    get_trade_journal_events,
    upsert_daily_prices,
    upsert_trade_journal_events,
)
from src.trading.kis_client import FilledOrder
from src.trading.trade_journal import TradeJournalRecorder
from scripts.generate_trade_journal_report import build_trade_journal_report, run as run_report


def _engine():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    return engine


def _filled_order(
    *,
    order_no: str,
    ticker: str = "005930",
    side: str = "BUY",
    qty: int = 2,
    price: float = 70_000.0,
    filled_at: datetime = datetime(2026, 5, 8, 10, 0, 0),
) -> FilledOrder:
    return FilledOrder(
        order_no=order_no,
        ticker=ticker,
        name="Samsung",
        side=side,
        ordered_qty=qty,
        filled_qty=qty,
        avg_fill_price=price,
        filled_amount=qty * price,
        ordered_at=filled_at,
        filled_at=filled_at,
        raw={"odno": order_no},
    )


def test_trade_journal_event_upsert_is_idempotent() -> None:
    engine = _engine()
    row = {
        "trade_date": date(2026, 5, 8),
        "order_no": "0000001",
        "ticker": "005930",
        "name": "Samsung",
        "side": "BUY",
        "filled_qty": 2,
        "avg_fill_price": 70_000.0,
        "gross_amount": 140_000.0,
        "fee": 0.0,
        "tax": 0.0,
        "order_reason": "include",
        "order_source": "rebalance",
        "order_status": "filled",
        "rank": 1,
        "total_score": 1.25,
        "dry_run_json": "dry.json",
        "execution_report_json": "execution.json",
        "raw_json": "{}",
    }

    with session_scope(engine) as session:
        first = upsert_trade_journal_events(session, [row])
        second = upsert_trade_journal_events(session, [{**row, "total_score": 2.5}])

    with session_scope(engine) as session:
        events = session.scalars(select(TradeJournalEvent)).all()

    assert first == 1
    assert second == 1
    assert len(events) == 1
    assert events[0].total_score == 2.5


def test_trade_journal_recorder_matches_fills_to_dry_run_context(tmp_path: Path) -> None:
    engine = _engine()
    dry_run = tmp_path / "dry.json"
    execution = tmp_path / "execution.json"
    dry_run.write_text(
        """{
          "targets": [{
            "ticker": "005930",
            "rank": 1,
            "total_score": 3.5,
            "value_score": 0.1,
            "quality_score": 0.2,
            "momentum_score": 0.3,
            "yield_score": 0.4,
            "technical_score": 0.5,
            "auxiliary_score": 0.6,
            "busanstock_score": 0.7,
            "investor_flow_score": 0.8,
            "research_report_score": 0.9
          }],
          "orders": [{"side": "BUY", "ticker": "005930", "qty": 2, "reason": "include"}]
        }""",
        encoding="utf-8",
    )
    execution.write_text("{}", encoding="utf-8")

    class FillProvider:
        def get_daily_filled_orders(self, start_date, end_date, order_nos=None):
            return [_filled_order(order_no="0000001")]

    recorder = TradeJournalRecorder(engine, FillProvider())
    summary = recorder.record_rebalance_execution(
        trade_date=date(2026, 5, 8),
        dry_run_json=dry_run,
        execution_report_json=execution,
        order_numbers={"BUY": ["0000001"]},
        successful_tickers={"BUY": ["005930"], "SELL": []},
    )

    with session_scope(engine) as session:
        events = get_trade_journal_events(session)

    assert summary["recorded_count"] == 1
    assert summary["unmatched_count"] == 0
    assert events[0].order_reason == "include"
    assert events[0].rank == 1
    assert events[0].research_report_score == 0.9


def test_trade_journal_recorder_retries_delayed_fill_lookup(tmp_path: Path) -> None:
    engine = _engine()
    dry_run = tmp_path / "dry.json"
    dry_run.write_text(
        """{
          "targets": [{"ticker": "005930", "rank": 1, "total_score": 3.5}],
          "orders": [{"side": "BUY", "ticker": "005930", "qty": 2, "reason": "include"}]
        }""",
        encoding="utf-8",
    )

    class DelayedFillProvider:
        def __init__(self) -> None:
            self.calls = 0

        def get_daily_filled_orders(self, start_date, end_date, order_nos=None):
            self.calls += 1
            if self.calls == 1:
                return []
            return [_filled_order(order_no="0000001")]

    fill_provider = DelayedFillProvider()
    recorder = TradeJournalRecorder(
        engine,
        fill_provider,
        fill_retry_attempts=2,
        fill_retry_delay_sec=0,
    )

    summary = recorder.record_rebalance_execution(
        trade_date=date(2026, 5, 8),
        dry_run_json=dry_run,
        execution_report_json=None,
        order_numbers={"BUY": ["0000001"]},
        successful_tickers={"BUY": ["005930"], "SELL": []},
    )

    assert fill_provider.calls == 2
    assert summary["recorded_count"] == 1
    assert summary["unmatched_count"] == 0


def test_trade_journal_report_replays_average_cost_and_writes_outputs(tmp_path: Path) -> None:
    engine = _engine()
    with session_scope(engine) as session:
        upsert_trade_journal_events(
            session,
            [
                {
                    "trade_date": date(2026, 5, 8),
                    "order_no": "B1",
                    "ticker": "005930",
                    "name": "Samsung",
                    "side": "BUY",
                    "filled_qty": 2,
                    "avg_fill_price": 70_000.0,
                    "gross_amount": 140_000.0,
                    "fee": 0.0,
                    "tax": 0.0,
                    "order_reason": "rank 1 entry",
                    "order_source": "rebalance",
                    "order_status": "filled",
                    "rank": 1,
                    "total_score": 3.5,
                },
                {
                    "trade_date": date(2026, 5, 10),
                    "order_no": "B2",
                    "ticker": "005930",
                    "name": "Samsung",
                    "side": "BUY",
                    "filled_qty": 1,
                    "avg_fill_price": 80_000.0,
                    "gross_amount": 80_000.0,
                    "fee": 0.0,
                    "tax": 0.0,
                    "order_reason": "add",
                    "order_source": "rebalance",
                    "order_status": "filled",
                    "rank": 1,
                    "total_score": 3.5,
                },
                {
                    "trade_date": date(2026, 5, 12),
                    "order_no": "S1",
                    "ticker": "005930",
                    "name": "Samsung",
                    "side": "SELL",
                    "filled_qty": 2,
                    "avg_fill_price": 90_000.0,
                    "gross_amount": 180_000.0,
                    "fee": 0.0,
                    "tax": 0.0,
                    "order_reason": "profit take",
                    "order_source": "exit_monitor",
                    "order_status": "filled",
                },
            ],
        )
        upsert_daily_prices(
            session,
            [
                {
                    "ticker": "005930",
                    "date": date(2026, 5, 8),
                    "open": 70_000,
                    "high": 95_000,
                    "low": 68_000,
                    "close": 80_000,
                    "volume": 100,
                    "trading_value": 8_000_000,
                    "market_cap": 1_000_000_000,
                },
                {
                    "ticker": "005930",
                    "date": date(2026, 5, 12),
                    "open": 90_000,
                    "high": 110_000,
                    "low": 85_000,
                    "close": 90_000,
                    "volume": 100,
                    "trading_value": 9_000_000,
                    "market_cap": 1_000_000_000,
                },
            ],
        )

    report = build_trade_journal_report(engine)

    assert report.closed_rows[0]["ticker"] == "005930"
    assert report.closed_rows[0]["entry_avg_price"] == 73333.3333
    assert report.closed_rows[0]["exit_avg_price"] == 90000.0
    assert report.closed_rows[0]["realized_profit_loss"] == 33333.3333
    assert report.closed_rows[0]["realized_profit_loss_pct"] == 22.7273
    assert report.closed_rows[0]["max_return_pct"] == 50.0
    assert report.closed_rows[0]["max_drawdown_pct"] == -7.2727
    assert report.closed_rows[0]["peak_to_exit_drawdown_pct"] == -18.1818
    assert report.open_rows[0]["open_qty"] == 1
    assert report.open_rows[0]["avg_cost"] == 73333.3333

    md_path = tmp_path / "journal.md"
    closed_csv = tmp_path / "closed.csv"
    open_csv = tmp_path / "open.csv"
    exit_code = run_report(
        database_url="sqlite:///:memory:",
        db_engine=engine,
        output_md=md_path,
        closed_csv=closed_csv,
        open_csv=open_csv,
    )

    assert exit_code == 0
    markdown = md_path.read_text(encoding="utf-8")
    assert "# PAPER Trade Journal" in markdown
    assert "## Numeric Review" in markdown
    with closed_csv.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert rows[0]["sell_reason"] == "profit take"
    assert rows[0]["peak_to_exit_drawdown_pct"] == "-18.1818"
