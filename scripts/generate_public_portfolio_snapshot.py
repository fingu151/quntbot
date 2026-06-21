from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from datetime import date, datetime
import json
from pathlib import Path
import sys
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

import requests
from sqlalchemy import desc, select

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import DATA_DIR, DATABASE_URL, REBALANCE
from src.data.database import get_engine, session_scope
from src.data.models import BusanstockSignal, InvestorFlow, QualityMetric
from src.factors.engine import calculate_factor_scores


KST = ZoneInfo("Asia/Seoul")
SnapshotHoldingProvider = Callable[[], list[dict[str, Any]]]
SnapshotAccountProvider = Callable[[], dict[str, Any]]
MarketSnapshotProvider = Callable[[], dict[str, Any]]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a public read-only portfolio snapshot for Streamlit."
    )
    parser.add_argument(
        "--dry-run-json",
        type=Path,
        default=REBALANCE.dry_run_preflight_report_path,
    )
    parser.add_argument(
        "--execution-report-json",
        type=Path,
        default=None,
        help="Optional PAPER execution report. Defaults to the latest data/rebalance_execution_*.json.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DATA_DIR / "public_portfolio_snapshot.json",
    )
    parser.add_argument("--database-url", default=DATABASE_URL)
    parser.add_argument("--as-of-date", type=_parse_date, default=None)
    parser.add_argument(
        "--fallback-existing-snapshot",
        action="store_true",
        help=(
            "If KIS holdings cannot be loaded, reuse positions from the existing "
            "public snapshot and mark the snapshot with a warning."
        ),
    )
    return parser.parse_args(argv)


def run(
    args: argparse.Namespace,
    *,
    holdings_provider: SnapshotHoldingProvider | None = None,
    account_provider: SnapshotAccountProvider | None = None,
    market_provider: MarketSnapshotProvider | None = None,
) -> int:
    provider = holdings_provider
    account: dict[str, Any] = {}
    fallback_warning = ""
    try:
        if provider is not None:
            holdings = provider()
        else:
            account = (account_provider or _load_kis_account_snapshot)()
            holdings = list(account.get("holdings") or [])
        holdings_source = "kis_paper"
        kis_called_by_snapshot = True
    except Exception as exc:
        if not getattr(args, "fallback_existing_snapshot", False):
            raise
        holdings = _load_holdings_from_existing_snapshot(args.output)
        if not holdings:
            raise
        holdings_source = "previous_public_snapshot"
        kis_called_by_snapshot = False
        fallback_warning = f"kis_holdings_unavailable_reused_previous_snapshot:{type(exc).__name__}"
        account = _account_from_existing_snapshot(args.output)
    tickers = [str(row.get("ticker", "")) for row in holdings if row.get("ticker")]
    dry_run = load_json_file(args.dry_run_json)
    execution_path = args.execution_report_json or find_latest_execution_report(DATA_DIR)
    execution = load_json_file(execution_path) if execution_path else {}
    signal_date = args.as_of_date or _date_from_dry_run(dry_run)
    signal_details = load_signal_details(args.database_url, tickers, signal_date)
    market_context = load_market_context(args.database_url, tickers, signal_date)
    factor_details = load_factor_details(args.database_url, tickers, signal_date)
    try:
        market = (market_provider or fetch_live_market_snapshot)()
    except Exception as exc:
        market = _market_from_existing_snapshot(args.output)
        fallback_warning = (
            f"{fallback_warning};market_unavailable_reused_previous_snapshot:{type(exc).__name__}"
            if fallback_warning
            else f"market_unavailable_reused_previous_snapshot:{type(exc).__name__}"
        )

    snapshot = build_snapshot(
        holdings,
        dry_run=dry_run,
        execution=execution,
        account=account,
        market=market,
        signal_details=signal_details,
        market_context=market_context,
        factor_details=factor_details,
    )
    snapshot["source"]["holdings"] = holdings_source
    snapshot["source"]["kis_called_by_snapshot"] = kis_called_by_snapshot
    if fallback_warning:
        snapshot.setdefault("warnings", []).append(fallback_warning)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"snapshot_written={args.output}")
    print(f"holding_count={snapshot['summary']['holding_count']}")
    print(f"dashboard_calls_kis={snapshot['source']['dashboard_calls_kis']}")
    return 0


def build_snapshot(
    holdings: list[dict[str, Any]],
    *,
    dry_run: dict[str, Any] | None = None,
    execution: dict[str, Any] | None = None,
    account: dict[str, Any] | None = None,
    market: dict[str, Any] | None = None,
    signal_details: dict[str, list[dict[str, Any]]] | None = None,
    market_context: dict[str, dict[str, Any]] | None = None,
    factor_details: dict[str, dict[str, float]] | None = None,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    current_time = (generated_at or datetime.now(KST)).astimezone(KST)
    dry_run_payload = dry_run or {}
    execution_payload = execution or {}
    account_payload = account or {}
    signal_map = signal_details or {}
    context_map = market_context or {}
    factor_map = factor_details or {}
    target_by_ticker = _target_map(dry_run_payload)
    order_by_ticker = _order_reason_map(dry_run_payload)
    name_by_ticker = _target_name_map(dry_run_payload)
    executed_tickers = _executed_tickers(execution_payload)
    price_by_ticker: dict[str, int] = {}
    warnings: list[str] = []
    positions = []
    total_market_value = 0
    total_cost = 0
    total_profit_loss = 0

    for holding in holdings:
        ticker = str(holding.get("ticker", ""))
        qty = _to_int(holding.get("qty"))
        avg_price = _to_int(holding.get("avg_price"))
        current_price = _to_int(holding.get("current_price"))
        market_value = qty * current_price
        cost = qty * avg_price
        profit_loss = _to_int(holding.get("eval_profit_loss"))
        if profit_loss == 0 and cost:
            profit_loss = market_value - cost
        profit_loss_rate = _to_float(holding.get("profit_loss_rate"))
        if profit_loss_rate == 0.0 and cost:
            profit_loss_rate = (profit_loss / cost) * 100

        total_market_value += market_value
        total_cost += cost
        total_profit_loss += profit_loss
        price_by_ticker[ticker] = current_price

        target = target_by_ticker.get(ticker, {})
        order_reason = order_by_ticker.get(ticker, "")
        if not target and not order_reason:
            warnings.append(f"missing_rationale:{ticker}")

        positions.append(
            {
                "ticker": ticker,
                "name": str(holding.get("name", "")),
                "qty": qty,
                "avg_price": avg_price,
                "current_price": current_price,
                "market_value": market_value,
                "cost": cost,
                "profit_loss": profit_loss,
                "profit_loss_rate": round(profit_loss_rate, 4),
                "rationale": {
                    "order_reason": order_reason,
                    "rank": _optional_int(target.get("rank")),
                    "total_score": _optional_float(target.get("total_score")),
                    "factor_scores": _factor_scores(target, factor_map.get(ticker, {})),
                    "signals": _public_signals(signal_map.get(ticker, [])),
                    "market_context": context_map.get(ticker, {}),
                    "execution_status": _execution_status(ticker, executed_tickers),
                },
            }
        )

    orders = _build_orders(
        dry_run_payload,
        execution_payload,
        executed_tickers,
        name_by_ticker,
        price_by_ticker,
    )
    total_profit_loss_rate = (total_profit_loss / total_cost) * 100 if total_cost else 0.0
    cash = _cash_summary(account_payload)
    realized = _realized_summary(account_payload, execution_payload)
    cash_balance = _to_int(cash.get("available"))
    total_asset_value = _to_int(account_payload.get("total_asset_value"))
    if total_asset_value <= 0:
        total_asset_value = total_market_value + cash_balance
    return {
        "schema_version": 1,
        "generated_at": current_time.isoformat(),
        "source": {
            "holdings": "kis_paper",
            "rationale": "local_reports_and_db",
            "kis_called_by_snapshot": True,
            "dashboard_calls_kis": False,
        },
        "summary": {
            "holding_count": len(positions),
            "total_market_value": total_market_value,
            "stock_market_value": total_market_value,
            "cash_balance": cash_balance,
            "total_asset_value": total_asset_value,
            "total_cost": total_cost,
            "total_profit_loss": total_profit_loss,
            "total_profit_loss_rate": round(total_profit_loss_rate, 2),
            "realized_profit_loss": _to_int(realized.get("profit_loss")),
        },
        "cash": cash,
        "realized": realized,
        "market": market or _empty_market(current_time),
        "positions": positions,
        "orders": orders,
        "warnings": warnings,
    }


def load_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _load_holdings_from_existing_snapshot(path: Path) -> list[dict[str, Any]]:
    snapshot = load_json_file(path)
    holdings: list[dict[str, Any]] = []
    for position in snapshot.get("positions") or []:
        if not isinstance(position, dict) or not position.get("ticker"):
            continue
        holdings.append(
            {
                "ticker": position.get("ticker"),
                "name": position.get("name", ""),
                "qty": position.get("qty", 0),
                "avg_price": position.get("avg_price", 0),
                "current_price": position.get("current_price", 0),
                "eval_profit_loss": position.get("profit_loss", 0),
                "profit_loss_rate": position.get("profit_loss_rate", 0),
            }
        )
    return holdings


def _account_from_existing_snapshot(path: Path) -> dict[str, Any]:
    snapshot = load_json_file(path)
    return {
        "cash": snapshot.get("cash") or {},
        "realized": snapshot.get("realized") or {},
        "total_asset_value": (snapshot.get("summary") or {}).get("total_asset_value"),
    }


def _market_from_existing_snapshot(path: Path) -> dict[str, Any]:
    snapshot = load_json_file(path)
    market = snapshot.get("market") or {}
    return market if isinstance(market, dict) else {}


def _load_kis_account_snapshot() -> dict[str, Any]:
    from src.trading.kis_client import KisClient

    raw = KisClient().get_balance()
    return _account_snapshot_from_kis_balance(raw)


def _account_snapshot_from_kis_balance(raw: dict[str, Any]) -> dict[str, Any]:
    output2 = (raw.get("output2") or [{}])[0] or {}
    holdings = []
    for item in raw.get("output1") or []:
        qty = _to_int(item.get("hldg_qty"))
        if qty <= 0:
            continue
        holdings.append(
            {
                "ticker": item.get("pdno", ""),
                "name": item.get("prdt_name", ""),
                "qty": qty,
                "avg_price": _to_int(item.get("pchs_avg_pric")),
                "current_price": _to_int(item.get("prpr")),
                "eval_profit_loss": _to_int(item.get("evlu_pfls_amt")),
                "profit_loss_rate": _to_float(item.get("evlu_pfls_rt")),
            }
        )
    securities_value = _first_int(output2, "scts_evlu_amt", "evlu_amt_smtl_amt")
    total_asset_value = _first_int(output2, "tot_evlu_amt", "nass_amt")
    derived_cash = max(0, total_asset_value - securities_value) if total_asset_value and securities_value else 0
    cash_available = _first_int(output2, "prvs_rcdl_excc_amt", "ord_psbl_cash")
    if cash_available <= 0:
        cash_available = derived_cash
    if cash_available <= 0:
        cash_available = _first_int(output2, "nxdy_excc_amt", "dnca_tot_amt")
    withdrawable = _first_int(output2, "nxdy_excc_amt", "dnca_tot_amt")
    realized_profit_loss = _first_int(
        output2,
        "rlzt_pfls",
        "rlzt_pfls_amt",
    )
    return {
        "holdings": holdings,
        "cash": {
            "available": cash_available,
            "withdrawable": withdrawable,
            "deposit_total": _first_int(output2, "dnca_tot_amt"),
            "derived_from_total_asset": derived_cash,
            "source": "kis_balance",
        },
        "realized": {
            "profit_loss": realized_profit_loss,
            "source": "kis_balance" if realized_profit_loss else "unavailable",
        },
        "total_asset_value": total_asset_value,
        "raw_output2_keys": sorted(str(key) for key in output2.keys()),
    }


def fetch_live_market_snapshot(
    *,
    fetcher: Callable[[str], dict[str, Any]] | None = None,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    now = (generated_at or datetime.now(KST)).astimezone(KST)
    fetch = fetcher or _fetch_yahoo_chart
    symbol_map = {
        "kospi": "KS11",
        "kosdaq": "KQ11",
        "usdkrw": "KRW=X",
    }
    market: dict[str, Any] = {
        "generated_at": now.isoformat(),
        "source": "yahoo_chart",
        "status": _market_status(now),
        "session_label": "정규장" if _market_status(now) == "OPEN" else "정규장 마감",
    }
    warnings: list[str] = []
    for key, symbol in symbol_map.items():
        try:
            market[key] = _parse_yahoo_chart_quote(fetch(symbol))
        except Exception as exc:
            warnings.append(f"{key}:{type(exc).__name__}")
    if warnings:
        market["warnings"] = warnings
    return market


def _fetch_yahoo_chart(symbol: str) -> dict[str, Any]:
    yahoo_symbol = {"KS11": "^KS11", "KQ11": "^KQ11"}.get(symbol, symbol)
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(yahoo_symbol, safe='')}?range=5d&interval=1d"
    response = requests.get(
        url,
        timeout=10,
        headers={"User-Agent": "Mozilla/5.0"},
    )
    response.raise_for_status()
    return response.json()


def _parse_yahoo_chart_quote(payload: dict[str, Any]) -> dict[str, float]:
    result = ((payload.get("chart") or {}).get("result") or [{}])[0] or {}
    meta = result.get("meta") or {}
    value = _to_float(meta.get("regularMarketPrice") or meta.get("previousClose"))
    previous = _to_float(meta.get("chartPreviousClose") or meta.get("previousClose"))
    if previous <= 0:
        indicators = ((result.get("indicators") or {}).get("quote") or [{}])[0] or {}
        closes = [float(item) for item in indicators.get("close", []) if item not in (None, "")]
        if len(closes) >= 2:
            previous = closes[-2]
        if closes and value <= 0:
            value = closes[-1]
    chg_pct = ((value - previous) / previous * 100) if previous else 0.0
    return {"value": round(value, 4), "chg_pct": round(chg_pct, 4)}


def _market_status(now: datetime) -> str:
    local = now.astimezone(KST)
    minutes = local.hour * 60 + local.minute
    return "OPEN" if local.weekday() < 5 and 9 * 60 <= minutes <= 15 * 60 + 30 else "CLOSED"


def _empty_market(now: datetime) -> dict[str, Any]:
    return {
        "generated_at": now.isoformat(),
        "source": "unavailable",
        "status": _market_status(now),
        "session_label": "정규장" if _market_status(now) == "OPEN" else "정규장 마감",
    }


def _cash_summary(account: dict[str, Any]) -> dict[str, Any]:
    cash = account.get("cash") or {}
    return {
        "available": _to_int(cash.get("available")),
        "withdrawable": _to_int(cash.get("withdrawable")),
        "deposit_total": _to_int(cash.get("deposit_total")),
        "derived_from_total_asset": _to_int(cash.get("derived_from_total_asset")),
        "source": str(cash.get("source") or "unavailable"),
    }


def _realized_summary(account: dict[str, Any], execution: dict[str, Any]) -> dict[str, Any]:
    realized = account.get("realized") or {}
    profit_loss = _to_int(realized.get("profit_loss"))
    return {
        "profit_loss": profit_loss,
        "source": str(realized.get("source") or "unavailable"),
        "latest_execution_sold_count": int(_to_int(execution.get("sold_count"))),
    }


def _first_int(row: dict[str, Any], *keys: str) -> int:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return _to_int(value)
    return 0


def find_latest_execution_report(data_dir: Path) -> Path | None:
    reports = sorted(data_dir.glob("rebalance_execution_*.json"), key=lambda path: path.name)
    return reports[-1] if reports else None


def load_signal_details(
    database_url: str | None,
    tickers: list[str],
    as_of_date: date | None,
) -> dict[str, list[dict[str, Any]]]:
    if not tickers or as_of_date is None:
        return {}
    try:
        engine = get_engine(database_url)
        with session_scope(engine) as session:
            busanstock_rows = session.scalars(
                select(BusanstockSignal).where(
                    BusanstockSignal.ticker.in_(tickers),
                    BusanstockSignal.signal_date == as_of_date,
                )
            ).all()
    except Exception:
        return {}

    result: dict[str, list[dict[str, Any]]] = {}
    for row in busanstock_rows:
        result.setdefault(row.ticker, []).append(
            {
                "source": "busanstock",
                "date": str(row.signal_date),
                "signal_type": row.signal_type,
                "source_section": row.source_section,
                "raw_score": float(row.raw_score),
                "detail": row.detail or "",
            }
        )
    return result


def load_market_context(
    database_url: str | None,
    tickers: list[str],
    as_of_date: date | None,
) -> dict[str, dict[str, Any]]:
    if not tickers:
        return {}
    try:
        engine = get_engine(database_url)
        with session_scope(engine) as session:
            quality_rows = session.scalars(
                select(QualityMetric)
                .where(QualityMetric.ticker.in_(tickers))
                .order_by(
                    QualityMetric.ticker,
                    desc(QualityMetric.published_at),
                    desc(QualityMetric.fiscal_year),
                    desc(QualityMetric.fiscal_quarter),
                )
            ).all()
            flow_query = select(InvestorFlow).where(InvestorFlow.ticker.in_(tickers))
            if as_of_date is not None:
                flow_query = flow_query.where(InvestorFlow.date <= as_of_date)
            flow_rows = session.scalars(
                flow_query.order_by(InvestorFlow.ticker, desc(InvestorFlow.date))
            ).all()
    except Exception:
        return {}

    result: dict[str, dict[str, Any]] = {}
    seen_quality: set[str] = set()
    for row in quality_rows:
        if row.ticker in seen_quality:
            continue
        seen_quality.add(row.ticker)
        result.setdefault(row.ticker, {})["quality"] = {
            "fiscal_year": row.fiscal_year,
            "fiscal_quarter": row.fiscal_quarter,
            "roe": row.roe,
            "operating_margin": row.operating_margin,
            "debt_ratio": row.debt_ratio,
            "published_at": str(row.published_at) if row.published_at else "",
        }

    seen_flow: set[str] = set()
    for row in flow_rows:
        if row.ticker in seen_flow:
            continue
        seen_flow.add(row.ticker)
        result.setdefault(row.ticker, {})["investor_flow"] = {
            "date": str(row.date),
            "individual_net_buy": row.individual_net_buy,
            "foreign_net_buy": row.foreign_net_buy,
            "institution_net_buy": row.institution_net_buy,
        }
    return result


def load_factor_details(
    database_url: str | None,
    tickers: list[str],
    as_of_date: date | None,
) -> dict[str, dict[str, float]]:
    if not tickers or as_of_date is None:
        return {}
    try:
        engine = get_engine(database_url)
        scores = calculate_factor_scores(engine, as_of_date=as_of_date)
    except Exception:
        return {}

    wanted = set(tickers)
    result: dict[str, dict[str, float]] = {}
    for score in scores:
        if score.ticker not in wanted:
            continue
        result[score.ticker] = {
            "value": score.value_score,
            "quality": score.quality_score,
            "momentum": score.momentum_score,
            "yield": score.yield_score,
            "technical": score.technical_score,
            "auxiliary": score.auxiliary_score,
            "busanstock": score.busanstock_score,
            "investor_flow": score.investor_flow_score,
            "research_report": score.research_report_score,
        }
    return result


def _load_kis_holdings() -> list[dict[str, Any]]:
    from src.trading.kis_client import KisClient

    return KisClient().get_holdings()


def _public_signals(signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {key: value for key, value in signal.items() if key != "message_id"}
        for signal in signals
    ]


def _target_map(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("ticker", "")): dict(item)
        for item in (payload.get("targets") or [])
        if item.get("ticker")
    }


def _target_name_map(payload: dict[str, Any]) -> dict[str, str]:
    return {
        str(item.get("ticker", "")): str(item.get("name", ""))
        for item in (payload.get("targets") or [])
        if item.get("ticker")
    }


def _build_orders(
    dry_run: dict[str, Any],
    execution: dict[str, Any],
    executed_tickers: set[str],
    name_by_ticker: dict[str, str],
    price_by_ticker: dict[str, int],
) -> list[dict[str, Any]]:
    order_date = _date_from_execution(execution) or str(dry_run.get("as_of_date", ""))
    orders: list[dict[str, Any]] = []
    for item in dry_run.get("orders") or []:
        ticker = str(item.get("ticker", ""))
        if not ticker:
            continue
        orders.append(
            {
                "date": order_date,
                "ticker": ticker,
                "name": name_by_ticker.get(ticker, ""),
                "side": str(item.get("side", "")).lower(),
                "qty": _to_int(item.get("qty")),
                "price": _to_int(price_by_ticker.get(ticker)),
                "status": "filled" if ticker in executed_tickers else "planned",
                "reason": str(item.get("reason", "")),
            }
        )
    return orders


def _date_from_execution(execution: dict[str, Any]) -> str:
    value = execution.get("executed_at")
    if not value:
        return ""
    return str(value)[:10].replace("-", ".")


def _order_reason_map(payload: dict[str, Any]) -> dict[str, str]:
    reasons: dict[str, str] = {}
    for item in payload.get("orders") or []:
        ticker = str(item.get("ticker", ""))
        if ticker and ticker not in reasons:
            reasons[ticker] = str(item.get("reason", ""))
    return reasons


def _executed_tickers(payload: dict[str, Any]) -> set[str]:
    return {str(ticker) for ticker in (payload.get("bought") or []) + (payload.get("sold") or [])}


def _execution_status(ticker: str, executed_tickers: set[str]) -> str:
    if not executed_tickers:
        return "unknown"
    return "executed" if ticker in executed_tickers else "not_in_latest_execution"


def _factor_scores(target: dict[str, Any], fallback: dict[str, float]) -> dict[str, float]:
    return {
        "value": _factor_value(target, fallback, "value", "value_score"),
        "quality": _factor_value(target, fallback, "quality", "quality_score"),
        "momentum": _factor_value(target, fallback, "momentum", "momentum_score"),
        "yield": _factor_value(target, fallback, "yield", "yield_score"),
        "technical": _factor_value(target, fallback, "technical", "technical_score"),
        "auxiliary": _factor_value(target, fallback, "auxiliary", "auxiliary_score"),
        "busanstock": _factor_value(target, fallback, "busanstock", "busanstock_score"),
        "investor_flow": _factor_value(
            target,
            fallback,
            "investor_flow",
            "investor_flow_score",
        ),
        "research_report": _factor_value(
            target,
            fallback,
            "research_report",
            "research_report_score",
        ),
    }


def _factor_value(
    target: dict[str, Any],
    fallback: dict[str, float],
    fallback_key: str,
    target_key: str,
) -> float:
    if target_key in target and target[target_key] not in (None, ""):
        return _to_float(target[target_key])
    return _to_float(fallback.get(fallback_key))


def _date_from_dry_run(payload: dict[str, Any]) -> date | None:
    value = payload.get("as_of_date")
    if not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return _to_int(value)


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return _to_float(value)


def _to_int(value: Any) -> int:
    if value in (None, ""):
        return 0
    return int(float(value))


def _to_float(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    return float(value)


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def main(argv: Sequence[str] | None = None) -> int:
    return run(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
