from __future__ import annotations

import argparse
import json
import time
from collections.abc import Callable, Sequence
from datetime import date
from pathlib import Path
import sys
from typing import Any

from sqlalchemy import Engine, select

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import DATA_DIR, KIS, PORTFOLIO, REBALANCE
from src.data.database import create_tables, get_engine, session_scope
from src.data.models import DailyPrice
from src.factors.engine import calculate_factor_scores
from src.factors.models import FactorScore
from src.trading.allocation import compute_score_weights
from src.trading.kis_client import KisClient
from src.trading.rebalance_policy import (
    compute_rebalance_sell_eligible_tickers,
    load_exit_entry_dates,
)
from src.trading.rebalancer import (
    RebalanceOrder,
    compute_rebalance_orders,
    is_execution_gap_too_large,
)
from src.trading.us_market_risk import (
    UsMarketBuyAdjustment,
    calculate_us_market_buy_adjustment,
    load_us_index_closes,
    scale_target_weights,
)


ScoreFunction = Callable[..., list[FactorScore]]
ClientFactory = Callable[[], Any]
CreateTablesFunction = Callable[[Any], None]
Sleeper = Callable[[float], None]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dry-run PAPER rebalance without placing orders.")
    parser.add_argument("--as-of-date", type=_parse_date, default=date.today())
    parser.add_argument("--top-n", type=int, default=PORTFOLIO.n_holdings)
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--output-md", type=Path, default=None)
    parser.add_argument("--output-json", type=Path, default=None)
    parser.add_argument(
        "--exit-state-path",
        type=Path,
        default=DATA_DIR / "exit_state.json",
        help="Local PAPER exit-state file used for rebalance holding-age checks.",
    )
    parser.add_argument(
        "--price-fallback",
        choices=("none", "latest-db"),
        default="none",
        help="Dry-run only fallback for quote failures. Real orders still require live quotes.",
    )
    parser.add_argument("--quote-retries", type=int, default=0)
    parser.add_argument("--quote-delay-sec", type=float, default=0.0)
    args = parser.parse_args(argv)
    if args.top_n <= 0:
        parser.error("--top-n must be greater than 0")
    if args.quote_retries < 0:
        parser.error("--quote-retries must be zero or greater")
    if args.quote_delay_sec < 0:
        parser.error("--quote-delay-sec must be zero or greater")
    return args


def run(
    args: argparse.Namespace,
    *,
    db_engine: Any | None = None,
    client_factory: ClientFactory = KisClient,
    score_func: ScoreFunction = calculate_factor_scores,
    create_tables_func: CreateTablesFunction = create_tables,
    sleeper: Sleeper = time.sleep,
) -> int:
    engine = db_engine if db_engine is not None else get_engine(args.database_url)
    create_tables_func(engine)

    scores = score_func(engine, as_of_date=args.as_of_date)
    if not scores:
        print(f"No factor scores found for as_of_date={args.as_of_date}")
        return 1

    target_scores = scores[:args.top_n]
    buffer_scores = scores[:max(args.top_n, REBALANCE.sell_rank_buffer)]
    target_tickers = [score.ticker for score in target_scores]
    buffer_tickers = {score.ticker for score in buffer_scores}
    client = client_factory()

    try:
        balance = client.get_balance()
    except Exception as exc:
        print(f"KIS lookup failed: {_safe_error_message(exc)}")
        return 1
    holdings = _parse_holdings(balance)
    output2 = (balance.get("output2") or [{}])[0]
    cash = int(output2.get("dnca_tot_amt", 0) or 0)

    held_tickers = {holding["ticker"] for holding in holdings}
    sell_eligible_tickers = compute_rebalance_sell_eligible_tickers(
        holdings=holdings,
        buffer_tickers=buffer_tickers,
        entry_dates=load_exit_entry_dates(args.exit_state_path),
        db_engine=engine,
        as_of_date=args.as_of_date,
        min_holding_trading_days=REBALANCE.min_holding_trading_days,
    )
    target_weights = {}
    if PORTFOLIO.weighting == "score_weighted":
        target_weights = compute_score_weights(
            [(score.ticker, score.total_score) for score in target_scores],
            min_weight=PORTFOLIO.min_position_weight,
            max_weight=PORTFOLIO.max_position_weight,
        )
    us_market_adjustment = calculate_us_market_buy_adjustment(
        load_us_index_closes(engine, as_of_date=args.as_of_date),
        as_of_date=args.as_of_date,
    )
    target_weights = scale_target_weights(
        target_weights,
        us_market_adjustment.buy_budget_multiplier,
    )
    prices: dict[str, int] = {}
    previous_closes: dict[str, int] = {}
    price_failures: list[str] = []
    price_fallbacks: dict[str, int] = {}
    price_retry_attempts: list[dict[str, Any]] = []
    for ticker in target_tickers:
        if ticker in held_tickers:
            continue
        previous_closes[ticker] = _load_previous_db_close(
            engine,
            ticker=ticker,
            as_of_date=args.as_of_date,
        )
        response, error, attempt = _get_current_price_with_retry(
            client,
            ticker=ticker,
            retries=args.quote_retries,
            delay_sec=args.quote_delay_sec,
            sleeper=sleeper,
        )
        if attempt["attempt_count"] > 1 or attempt["status"] == "failed":
            price_retry_attempts.append(attempt)
        if error is not None:
            fallback_price = _load_latest_db_close(
                engine,
                ticker=ticker,
                as_of_date=args.as_of_date,
            ) if args.price_fallback == "latest-db" else 0
            if fallback_price > 0:
                prices[ticker] = fallback_price
                previous_closes.pop(ticker, None)
                price_fallbacks[ticker] = fallback_price
                print(f"price_fallback,{ticker},{fallback_price},latest-db")
            else:
                price_failures.append(ticker)
                print(f"price_lookup_failed,{ticker},{_safe_error_message(error)}")
            continue
        assert response is not None
        if response.get("rt_cd") == "0":
            prices[ticker] = int(response.get("output", {}).get("stck_prpr", 0) or 0)
        else:
            fallback_price = _load_latest_db_close(
                engine,
                ticker=ticker,
                as_of_date=args.as_of_date,
            ) if args.price_fallback == "latest-db" else 0
            if fallback_price > 0:
                prices[ticker] = fallback_price
                previous_closes.pop(ticker, None)
                price_fallbacks[ticker] = fallback_price
                print(f"price_fallback,{ticker},{fallback_price},latest-db")
            else:
                price_failures.append(ticker)
                print(f"price_lookup_failed,{ticker},{response.get('msg1', '')}")

    skipped_buys = _build_skipped_buy_candidates(
        target_tickers=target_tickers,
        held_tickers=held_tickers,
        prices=prices,
        previous_closes=previous_closes,
    )
    sells, buys = compute_rebalance_orders(
        holdings=holdings,
        target_tickers=target_tickers,
        prices=prices,
        previous_closes=previous_closes,
        cash=cash,
        sell_eligible_tickers=sell_eligible_tickers,
        target_weights=target_weights,
        buy_budget_multiplier=us_market_adjustment.buy_budget_multiplier,
    )
    report = _format_markdown_report(
        as_of_date=args.as_of_date,
        target_scores=target_scores,
        holdings=holdings,
        cash=cash,
        sells=sells,
        buys=buys,
        target_weights=target_weights,
        skipped_buys=skipped_buys,
        price_failures=price_failures,
        price_fallbacks=price_fallbacks,
        price_retry_attempts=price_retry_attempts,
        us_market_adjustment=us_market_adjustment,
    )
    json_report = _format_json_report(
        as_of_date=args.as_of_date,
        target_scores=target_scores,
        holdings=holdings,
        cash=cash,
        sells=sells,
        buys=buys,
        target_weights=target_weights,
        skipped_buys=skipped_buys,
        price_failures=price_failures,
        price_fallbacks=price_fallbacks,
        price_retry_attempts=price_retry_attempts,
        us_market_adjustment=us_market_adjustment,
    )

    _print_csv_summary(args.as_of_date, target_scores, cash, sells, buys)
    if args.output_md:
        args.output_md.parent.mkdir(parents=True, exist_ok=True)
        args.output_md.write_text(report, encoding="utf-8")
        print(f"output_md={args.output_md}")
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(
            json.dumps(json_report, ensure_ascii=True, indent=2),
            encoding="utf-8",
        )
        print(f"output_json={args.output_json}")
    return 0


def _print_csv_summary(
    as_of_date: date,
    target_scores: list[FactorScore],
    cash: int,
    sells: list[RebalanceOrder],
    buys: list[RebalanceOrder],
) -> None:
    print("dry_run=true")
    print(f"as_of_date={as_of_date}")
    print(f"target_count={len(target_scores)}")
    print(f"cash={cash}")
    print(f"sell_count={len(sells)}")
    print(f"buy_count={len(buys)}")
    print("side,ticker,qty,reason")
    for order in sells + buys:
        print(f"{order.side},{order.ticker},{order.qty},{order.reason}")


def _format_markdown_report(
    *,
    as_of_date: date,
    target_scores: list[FactorScore],
    holdings: list[dict[str, Any]],
    cash: int,
    sells: list[RebalanceOrder],
    buys: list[RebalanceOrder],
    target_weights: dict[str, float],
    skipped_buys: list[dict[str, Any]],
    price_failures: list[str],
    price_fallbacks: dict[str, int],
    price_retry_attempts: list[dict[str, Any]],
    us_market_adjustment: UsMarketBuyAdjustment,
) -> str:
    retry_success_count = sum(1 for item in price_retry_attempts if item["status"] == "success")
    retry_failed_count = sum(1 for item in price_retry_attempts if item["status"] == "failed")
    lines = [
        "# Dry-run Rebalance Report",
        "",
        f"- as_of_date: `{as_of_date}`",
        f"- cash: `{cash:,}` KRW",
        f"- holdings: `{len(holdings)}`",
        f"- target_count: `{len(target_scores)}`",
        f"- sell_count: `{len(sells)}`",
        f"- buy_count: `{len(buys)}`",
        f"- skipped_buy_count: `{len(skipped_buys)}`",
        f"- price_lookup_failed_count: `{len(price_failures)}`",
        f"- price_fallback_count: `{len(price_fallbacks)}`",
        f"- price_retry_success_count: `{retry_success_count}`",
        f"- price_retry_failed_count: `{retry_failed_count}`",
        f"- us_market_risk_status: `{us_market_adjustment.status}`",
        f"- us_market_buy_budget_multiplier: `{us_market_adjustment.buy_budget_multiplier:.2f}`",
        f"- us_market_cash_target: `{us_market_adjustment.cash_target:.2%}`",
        "",
        "## Target Portfolio",
        "",
        "| rank | ticker | name | score | target_weight |",
        "| ---: | --- | --- | ---: | ---: |",
    ]
    for score in target_scores:
        lines.append(
            f"| {score.rank} | {score.ticker} | {score.name} | "
            f"{score.total_score:.4f} | {target_weights.get(score.ticker, 0.0):.2%} |"
        )
    lines.extend(["", "## Planned Orders", "", "| side | ticker | qty | reason |", "| --- | --- | ---: | --- |"])
    if not sells and not buys:
        lines.append("| - | - | 0 | No orders needed |")
    for order in sells + buys:
        lines.append(f"| {order.side} | {order.ticker} | {order.qty} | {order.reason} |")
    if skipped_buys:
        lines.extend([
            "",
            "## Skipped Buy Candidates",
            "",
            "| ticker | reason | execution_price | previous_close | gap | threshold |",
            "| --- | --- | ---: | ---: | ---: | ---: |",
        ])
        for item in skipped_buys:
            lines.append(
                f"| {item['ticker']} | {item['reason']} | "
                f"{int(item['execution_price']):,} | {int(item['previous_close']):,} | "
                f"{item['gap_pct']:.2%} | {item['threshold_pct']:.2%} |"
            )
    if price_failures:
        lines.extend(["", "## Price Lookup Failures", ""])
        for ticker in price_failures:
            lines.append(f"- `{ticker}`")
    if price_fallbacks:
        lines.extend(["", "## Price Fallbacks", "", "| ticker | price | source |", "| --- | ---: | --- |"])
        for ticker, price in sorted(price_fallbacks.items()):
            lines.append(f"| {ticker} | {price:,} | latest-db close |")
    if price_retry_attempts:
        lines.extend([
            "",
            "## Price Retry Summary",
            "",
            "| ticker | status | attempts | last_error |",
            "| --- | --- | ---: | --- |",
        ])
        for item in price_retry_attempts:
            lines.append(
                f"| {item['ticker']} | {item['status']} | "
                f"{item['attempt_count']} | {item['last_error']} |"
            )
    lines.append("")
    return "\n".join(lines)


def _format_json_report(
    *,
    as_of_date: date,
    target_scores: list[FactorScore],
    holdings: list[dict[str, Any]],
    cash: int,
    sells: list[RebalanceOrder],
    buys: list[RebalanceOrder],
    target_weights: dict[str, float],
    skipped_buys: list[dict[str, Any]],
    price_failures: list[str],
    price_fallbacks: dict[str, int],
    price_retry_attempts: list[dict[str, Any]],
    us_market_adjustment: UsMarketBuyAdjustment,
) -> dict[str, Any]:
    retry_success_count = sum(1 for item in price_retry_attempts if item["status"] == "success")
    retry_failed_count = sum(1 for item in price_retry_attempts if item["status"] == "failed")
    return {
        "dry_run": True,
        "as_of_date": str(as_of_date),
        "cash": cash,
        "holdings_count": len(holdings),
        "target_count": len(target_scores),
        "sell_count": len(sells),
        "buy_count": len(buys),
        "skipped_buy_count": len(skipped_buys),
        "price_lookup_failed_count": len(price_failures),
        "price_fallback_count": len(price_fallbacks),
        "price_retry_success_count": retry_success_count,
        "price_retry_failed_count": retry_failed_count,
        "price_retry_attempts": price_retry_attempts,
        "us_market_risk": {
            "status": us_market_adjustment.status,
            "buy_budget_multiplier": us_market_adjustment.buy_budget_multiplier,
            "cash_target": us_market_adjustment.cash_target,
            "reasons": us_market_adjustment.reasons,
            "returns": us_market_adjustment.returns,
        },
        "targets": [
            {
                "rank": score.rank,
                "ticker": score.ticker,
                "name": score.name,
                "total_score": score.total_score,
                "target_weight": target_weights.get(score.ticker, 0.0),
            }
            for score in target_scores
        ],
        "orders": [
            {"side": order.side, "ticker": order.ticker, "qty": order.qty, "reason": order.reason}
            for order in sells + buys
        ],
        "skipped_buys": skipped_buys,
        "price_lookup_failures": price_failures,
        "price_fallbacks": [
            {"ticker": ticker, "price": price, "source": "latest-db"}
            for ticker, price in sorted(price_fallbacks.items())
        ],
    }


def _build_skipped_buy_candidates(
    *,
    target_tickers: list[str],
    held_tickers: set[str],
    prices: dict[str, int],
    previous_closes: dict[str, int],
) -> list[dict[str, Any]]:
    skipped = []
    for ticker in target_tickers:
        if ticker in held_tickers or ticker not in prices:
            continue
        execution_price = prices[ticker]
        previous_close = previous_closes.get(ticker)
        if not is_execution_gap_too_large(
            execution_price=execution_price,
            previous_close=previous_close,
            max_abs_gap_pct=PORTFOLIO.max_abs_open_gap_pct,
        ):
            continue
        gap_pct = (float(execution_price) / float(previous_close)) - 1.0
        skipped.append(
            {
                "ticker": ticker,
                "reason": "gap_move_too_large",
                "execution_price": execution_price,
                "previous_close": previous_close,
                "gap_pct": round(gap_pct, 4),
                "threshold_pct": PORTFOLIO.max_abs_open_gap_pct,
            }
        )
    return skipped


def _load_latest_db_close(engine: Any, *, ticker: str, as_of_date: date) -> int:
    with session_scope(engine) as session:
        row = session.scalars(
            select(DailyPrice)
            .where(DailyPrice.ticker == ticker, DailyPrice.date <= as_of_date)
            .order_by(DailyPrice.date.desc())
            .limit(1)
        ).first()
    if row is None or row.close is None:
        return 0
    return int(row.close)


def _load_previous_db_close(engine: Any, *, ticker: str, as_of_date: date) -> int:
    if not isinstance(engine, Engine):
        return 0
    with session_scope(engine) as session:
        row = session.scalars(
            select(DailyPrice)
            .where(DailyPrice.ticker == ticker, DailyPrice.date < as_of_date)
            .order_by(DailyPrice.date.desc())
            .limit(1)
        ).first()
    if row is None or row.close is None:
        return 0
    return int(row.close)


def _get_current_price_with_retry(
    client: Any,
    *,
    ticker: str,
    retries: int,
    delay_sec: float,
    sleeper: Sleeper,
) -> tuple[dict[str, Any] | None, Exception | None, dict[str, Any]]:
    last_error: Exception | None = None
    attempt_count = 0
    for attempt in range(retries + 1):
        attempt_count = attempt + 1
        if attempt > 0 and delay_sec > 0:
            sleeper(delay_sec)
        try:
            response = client.get_current_price(ticker)
            return response, None, {
                "ticker": ticker,
                "attempt_count": attempt_count,
                "status": "success",
                "last_error": _safe_error_message(last_error) if last_error else "",
            }
        except Exception as exc:
            last_error = exc
    return None, last_error, {
        "ticker": ticker,
        "attempt_count": attempt_count,
        "status": "failed",
        "last_error": _safe_error_message(last_error) if last_error else "",
    }


def _parse_holdings(raw: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for item in raw.get("output1") or []:
        qty = _parse_int_number(item.get("hldg_qty", 0))
        if qty <= 0:
            continue
        rows.append({
            "ticker": item.get("pdno", ""),
            "name": item.get("prdt_name", ""),
            "qty": qty,
            "avg_price": _parse_int_number(item.get("pchs_avg_pric", 0)),
            "current_price": _parse_int_number(item.get("prpr", 0)),
            "eval_profit_loss": _parse_int_number(item.get("evlu_pfls_amt", 0)),
            "profit_loss_rate": float(item.get("evlu_pfls_rt", 0) or 0),
        })
    return rows


def _parse_int_number(value: Any) -> int:
    if value in (None, ""):
        return 0
    return int(float(value))


def _safe_error_message(exc: Exception) -> str:
    message = str(exc)
    if KIS.account_no:
        message = message.replace(KIS.account_no, f"{KIS.account_no[:4]}****")
    if KIS.app_key:
        message = message.replace(KIS.app_key, "<KIS_APP_KEY>")
    if KIS.app_secret:
        message = message.replace(KIS.app_secret, "<KIS_APP_SECRET>")
    return message


def main(argv: Sequence[str] | None = None) -> int:
    return run(parse_args(argv))


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


if __name__ == "__main__":
    raise SystemExit(main())
