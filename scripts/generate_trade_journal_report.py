from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path
import sys
from typing import Any

from sqlalchemy import Engine, select

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import DATA_DIR, DATABASE_URL
from src.data.database import create_tables, get_engine, session_scope
from src.data.models import DailyPrice, TradeJournalEvent
from src.data.repositories import get_trade_journal_events


@dataclass(frozen=True)
class TradeJournalReport:
    closed_rows: list[dict[str, Any]]
    open_rows: list[dict[str, Any]]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate PAPER trade journal reports.")
    parser.add_argument("--database-url", default=DATABASE_URL)
    parser.add_argument("--output-md", type=Path, default=DATA_DIR / "trade_journal_latest.md")
    parser.add_argument(
        "--closed-csv",
        type=Path,
        default=DATA_DIR / "trade_journal_closed_trades.csv",
    )
    parser.add_argument(
        "--open-csv",
        type=Path,
        default=DATA_DIR / "trade_journal_open_positions.csv",
    )
    return parser.parse_args(argv)


def run(
    args: argparse.Namespace | None = None,
    *,
    database_url: str | None = None,
    db_engine: Engine | None = None,
    output_md: Path | None = None,
    closed_csv: Path | None = None,
    open_csv: Path | None = None,
) -> int:
    if args is None:
        args = argparse.Namespace(
            database_url=database_url or DATABASE_URL,
            output_md=output_md or DATA_DIR / "trade_journal_latest.md",
            closed_csv=closed_csv or DATA_DIR / "trade_journal_closed_trades.csv",
            open_csv=open_csv or DATA_DIR / "trade_journal_open_positions.csv",
        )
    engine = db_engine or get_engine(args.database_url)
    create_tables(engine)
    report = build_trade_journal_report(engine)
    _write_csv(args.closed_csv, report.closed_rows, CLOSED_FIELDS)
    _write_csv(args.open_csv, report.open_rows, OPEN_FIELDS)
    _write_markdown(args.output_md, report)
    print(f"trade_journal_md={args.output_md}")
    print(f"closed_trade_count={len(report.closed_rows)}")
    print(f"open_position_count={len(report.open_rows)}")
    return 0


def build_trade_journal_report(engine: Engine) -> TradeJournalReport:
    with session_scope(engine) as session:
        events = get_trade_journal_events(session)
        closed_rows, open_rows = _replay_average_cost(session, events)
    return TradeJournalReport(closed_rows=closed_rows, open_rows=open_rows)


def _replay_average_cost(
    session: Any,
    events: list[TradeJournalEvent],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    state_by_ticker: dict[str, dict[str, Any]] = {}
    closed_rows: list[dict[str, Any]] = []
    for event in events:
        if event.order_status != "filled" or event.filled_qty <= 0 or event.avg_fill_price <= 0:
            continue
        state = state_by_ticker.setdefault(
            event.ticker,
            {
                "qty": 0,
                "cost": 0.0,
                "entry_date": event.trade_date,
                "buy_reason": "",
                "rank": None,
                "total_score": None,
                "name": event.name,
            },
        )
        if event.side == "BUY":
            if state["qty"] <= 0:
                state["entry_date"] = event.trade_date
                state["buy_reason"] = event.order_reason or ""
                state["rank"] = event.rank
                state["total_score"] = event.total_score
                state["name"] = event.name
            state["qty"] += event.filled_qty
            state["cost"] += event.avg_fill_price * event.filled_qty
            continue
        if event.side != "SELL" or state["qty"] <= 0:
            continue
        sell_qty = min(event.filled_qty, state["qty"])
        entry_avg = state["cost"] / state["qty"]
        realized = (event.avg_fill_price - entry_avg) * sell_qty - event.fee - event.tax
        invested = entry_avg * sell_qty
        max_return, max_drawdown, peak_to_exit_drawdown = _price_extremes(
            session,
            event.ticker,
            state["entry_date"],
            event.trade_date,
            entry_avg,
            event.avg_fill_price,
        )
        closed_rows.append(
            {
                "ticker": event.ticker,
                "name": state["name"] or event.name,
                "buy_date": str(state["entry_date"]),
                "sell_date": str(event.trade_date),
                "holding_days": (event.trade_date - state["entry_date"]).days,
                "sold_qty": sell_qty,
                "entry_avg_price": _round(entry_avg),
                "exit_avg_price": _round(event.avg_fill_price),
                "realized_profit_loss": _round(realized),
                "realized_profit_loss_pct": _round((realized / invested) * 100 if invested else 0.0),
                "buy_reason": state["buy_reason"],
                "sell_reason": event.order_reason or "",
                "rank": state["rank"],
                "total_score": _round(state["total_score"]),
                "max_return_pct": _round(max_return) if max_return is not None else "",
                "max_drawdown_pct": _round(max_drawdown) if max_drawdown is not None else "",
                "peak_to_exit_drawdown_pct": _round(peak_to_exit_drawdown)
                if peak_to_exit_drawdown is not None
                else "",
            }
        )
        state["cost"] -= entry_avg * sell_qty
        state["qty"] -= sell_qty
        if state["qty"] <= 0:
            state["qty"] = 0
            state["cost"] = 0.0
            state["buy_reason"] = ""
            state["rank"] = None
            state["total_score"] = None

    open_rows = []
    for ticker, state in sorted(state_by_ticker.items()):
        if state["qty"] <= 0:
            continue
        avg_cost = state["cost"] / state["qty"]
        open_rows.append(
            {
                "ticker": ticker,
                "name": state["name"],
                "buy_date": str(state["entry_date"]),
                "open_qty": state["qty"],
                "avg_cost": _round(avg_cost),
                "invested_amount": _round(state["cost"]),
                "buy_reason": state["buy_reason"],
                "rank": state["rank"],
                "total_score": _round(state["total_score"]),
            }
        )
    return closed_rows, open_rows


def _price_extremes(
    session: Any,
    ticker: str,
    start_date: date,
    end_date: date,
    entry_avg: float,
    exit_avg: float,
) -> tuple[float | None, float | None, float | None]:
    if entry_avg <= 0:
        return None, None, None
    rows = session.scalars(
        select(DailyPrice)
        .where(
            DailyPrice.ticker == ticker,
            DailyPrice.date >= start_date,
            DailyPrice.date <= end_date,
        )
        .order_by(DailyPrice.date)
    ).all()
    if not rows:
        return None, None, None
    highs = [float(row.high or row.close or 0) for row in rows if (row.high or row.close)]
    lows = [float(row.low or row.close or 0) for row in rows if (row.low or row.close)]
    max_return = ((max(highs) / entry_avg) - 1.0) * 100 if highs else None
    max_drawdown = ((min(lows) / entry_avg) - 1.0) * 100 if lows else None
    peak_to_exit_drawdown = ((exit_avg / max(highs)) - 1.0) * 100 if highs else None
    return max_return, max_drawdown, peak_to_exit_drawdown


def _write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def _write_markdown(path: Path, report: TradeJournalReport) -> None:
    lines = [
        "# PAPER Trade Journal",
        "",
        f"- closed_trade_count: `{len(report.closed_rows)}`",
        f"- open_position_count: `{len(report.open_rows)}`",
        "",
        "## Closed Trades",
        "",
        "| ticker | buy_date | sell_date | qty | entry | exit | pnl | pnl_pct | buy_reason | sell_reason |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    if not report.closed_rows:
        lines.append("| - | - | - | 0 | 0 | 0 | 0 | 0 | - | - |")
    for row in report.closed_rows:
        lines.append(
            f"| {row['ticker']} | {row['buy_date']} | {row['sell_date']} | "
            f"{row['sold_qty']} | {row['entry_avg_price']} | {row['exit_avg_price']} | "
            f"{row['realized_profit_loss']} | {row['realized_profit_loss_pct']} | "
            f"{row['buy_reason']} | {row['sell_reason']} |"
        )
    lines.extend([
        "",
        "## Numeric Review",
        "",
        "| ticker | buy_reason | sell_trigger | max_return_pct | max_drawdown_pct | peak_to_exit_drawdown_pct | exit_pnl_pct | holding_days |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ])
    if not report.closed_rows:
        lines.append("| - | - | - | 0 | 0 | 0 | 0 | 0 |")
    for row in report.closed_rows:
        lines.append(
            f"| {row['ticker']} | {row['buy_reason']} | {row['sell_reason']} | "
            f"{row['max_return_pct']} | {row['max_drawdown_pct']} | "
            f"{row['peak_to_exit_drawdown_pct']} | "
            f"{row['realized_profit_loss_pct']} | {row['holding_days']} |"
        )
    lines.extend([
        "",
        "## Open Positions",
        "",
        "| ticker | buy_date | qty | avg_cost | invested | buy_reason |",
        "| --- | --- | ---: | ---: | ---: | --- |",
    ])
    if not report.open_rows:
        lines.append("| - | - | 0 | 0 | 0 | - |")
    for row in report.open_rows:
        lines.append(
            f"| {row['ticker']} | {row['buy_date']} | {row['open_qty']} | "
            f"{row['avg_cost']} | {row['invested_amount']} | {row['buy_reason']} |"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _round(value: Any) -> float | None:
    if value is None:
        return None
    return round(float(value), 4)


CLOSED_FIELDS = [
    "ticker",
    "name",
    "buy_date",
    "sell_date",
    "holding_days",
    "sold_qty",
    "entry_avg_price",
    "exit_avg_price",
    "realized_profit_loss",
    "realized_profit_loss_pct",
    "buy_reason",
    "sell_reason",
    "rank",
    "total_score",
    "max_return_pct",
    "max_drawdown_pct",
    "peak_to_exit_drawdown_pct",
]

OPEN_FIELDS = [
    "ticker",
    "name",
    "buy_date",
    "open_qty",
    "avg_cost",
    "invested_amount",
    "buy_reason",
    "rank",
    "total_score",
]


def main(argv: list[str] | None = None) -> int:
    return run(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
