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

from config import DATA_DIR, INVERSE_ETF, KIS, PORTFOLIO, REBALANCE
from src.data.database import create_tables, get_engine, session_scope
from src.data.models import DailyPrice, MarketIndexPrice
from src.factors.engine import calculate_factor_scores
from src.factors.models import FactorScore
from src.trading.allocation import compute_score_weights
from src.trading.inverse_etf_hedge import (
    InverseEtfSignal,
    calculate_inverse_etf_signal,
    compute_inverse_etf_orders,
)
from src.trading.kis_client import KisClient
from src.trading.macro_risk import MacroExposureAdjustment, load_macro_exposure_adjustment
from src.trading.rebalance_policy import (
    compute_rebalance_sell_eligible_tickers,
    load_exit_entry_dates,
)
from src.trading.rebalancer import (
    RebalanceOrder,
    compute_macro_reduction_orders,
    compute_rebalance_orders,
    is_execution_gap_too_large,
)
from src.trading.us_market_risk import scale_target_weights


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
    entry_dates = load_exit_entry_dates(args.exit_state_path)
    sell_eligible_tickers = compute_rebalance_sell_eligible_tickers(
        holdings=holdings,
        buffer_tickers=buffer_tickers,
        entry_dates=entry_dates,
        db_engine=engine,
        as_of_date=args.as_of_date,
        min_holding_trading_days=REBALANCE.min_holding_trading_days,
    )
    inverse_allowed = set(INVERSE_ETF.allowed_tickers)
    if inverse_allowed:
        sell_eligible_tickers = [
            ticker for ticker in sell_eligible_tickers if ticker not in inverse_allowed
        ]
    target_weights = {}
    if PORTFOLIO.weighting == "score_weighted":
        target_weights = compute_score_weights(
            [(score.ticker, score.total_score) for score in target_scores],
            min_weight=PORTFOLIO.min_position_weight,
            max_weight=PORTFOLIO.max_position_weight,
        )
    macro_adjustment = load_macro_exposure_adjustment(engine, as_of_date=args.as_of_date)
    inverse_signal = calculate_inverse_etf_signal(
        as_of_date=args.as_of_date,
        macro_adjustment=macro_adjustment,
        domestic_index_closes=_load_domestic_index_closes(engine, as_of_date=args.as_of_date),
        config=INVERSE_ETF,
    )
    us_market_adjustment = macro_adjustment.us_market
    bond_yield_adjustment = macro_adjustment.bond_yield
    combined_buy_budget_multiplier = macro_adjustment.buy_budget_multiplier
    target_weights = scale_target_weights(
        target_weights,
        combined_buy_budget_multiplier,
    )
    prices: dict[str, int] = {}
    previous_closes: dict[str, int] = {}
    price_failures: list[str] = []
    price_fallbacks: dict[str, int] = {}
    price_retry_attempts: list[dict[str, Any]] = []
    quote_tickers = _quote_tickers_for_dry_run(
        target_tickers=target_tickers,
        held_tickers=held_tickers,
        inverse_signal=inverse_signal,
    )
    for ticker in quote_tickers:
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
        buy_budget_multiplier=combined_buy_budget_multiplier,
    )
    macro_sells, macro_reduction_skipped = compute_macro_reduction_orders(
        holdings=[
            holding for holding in holdings if str(holding.get("ticker", "")) not in inverse_allowed
        ],
        prices=prices,
        cash=cash,
        target_cash_ratio=macro_adjustment.cash_target,
        existing_sells=sells,
    )
    sells.extend(macro_sells)
    portfolio_value = cash + sum(
        int(holding.get("qty", 0) or 0)
        * int(
            prices.get(str(holding.get("ticker", "")))
            or holding.get("current_price")
            or 0
        )
        for holding in holdings
    )
    inverse_orders, inverse_skipped = compute_inverse_etf_orders(
        holdings=holdings,
        prices=prices,
        cash=cash,
        portfolio_value=portfolio_value,
        signal=inverse_signal,
        entry_dates=entry_dates,
        as_of_date=args.as_of_date,
        config=INVERSE_ETF,
    )
    sells.extend([order for order in inverse_orders if order.side == "SELL"])
    buys.extend([order for order in inverse_orders if order.side == "BUY"])
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
        bond_yield_adjustment=bond_yield_adjustment,
        combined_buy_budget_multiplier=combined_buy_budget_multiplier,
        macro_adjustment=macro_adjustment,
        macro_reduction_skipped=macro_reduction_skipped,
        inverse_signal=inverse_signal,
        inverse_orders=inverse_orders,
        inverse_skipped=inverse_skipped,
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
        bond_yield_adjustment=bond_yield_adjustment,
        combined_buy_budget_multiplier=combined_buy_budget_multiplier,
        macro_adjustment=macro_adjustment,
        macro_reduction_skipped=macro_reduction_skipped,
        inverse_signal=inverse_signal,
        inverse_orders=inverse_orders,
        inverse_skipped=inverse_skipped,
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
    us_market_adjustment: Any,
    bond_yield_adjustment: Any,
    combined_buy_budget_multiplier: float,
    macro_adjustment: MacroExposureAdjustment,
    macro_reduction_skipped: list[dict[str, str]],
    inverse_signal: InverseEtfSignal,
    inverse_orders: list[RebalanceOrder],
    inverse_skipped: list[dict[str, str]],
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
        f"- bond_yield_risk_status: `{bond_yield_adjustment.status}`",
        f"- bond_yield_buy_budget_multiplier: `{bond_yield_adjustment.buy_budget_multiplier:.2f}`",
        f"- bond_yield_cash_target: `{bond_yield_adjustment.cash_target:.2%}`",
        f"- combined_buy_budget_multiplier: `{combined_buy_budget_multiplier:.2f}`",
        f"- macro_risk_status: `{macro_adjustment.status}`",
        f"- macro_cash_target: `{macro_adjustment.cash_target:.2%}`",
        f"- macro_buy_budget_multiplier: `{macro_adjustment.buy_budget_multiplier:.2f}`",
        f"- macro_reduction_skipped_count: `{len(macro_reduction_skipped)}`",
        f"- inverse_etf_hedge_status: `{inverse_signal.status}`",
        f"- inverse_etf_target_weight: `{inverse_signal.target_weight:.2%}`",
        f"- inverse_etf_orders_generated: `{bool(inverse_orders)}`",
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
    if macro_reduction_skipped:
        lines.extend([
            "",
            "## Macro Reduction Skips",
            "",
            "| ticker | reason |",
            "| --- | --- |",
        ])
        for item in macro_reduction_skipped:
            lines.append(f"| {item['ticker']} | {item['reason']} |")
    lines.extend([
        "",
        "## Inverse ETF Hedge",
        "",
        f"- status: `{inverse_signal.status}`",
        f"- target_weight: `{inverse_signal.target_weight:.2%}`",
        f"- selected_tickers: `{', '.join(inverse_signal.selected_tickers) or '-'}`",
        f"- leverage_type: `{inverse_signal.leverage_type}`",
        f"- execution_allowed: `true`",
        "",
        "| reason | symbol | value | threshold | severity |",
        "| --- | --- | ---: | ---: | --- |",
    ])
    if inverse_signal.evidence:
        for item in inverse_signal.evidence:
            value = item.get("return", item.get("rsi", item.get("cash_target", "")))
            threshold = item.get("threshold", "")
            lines.append(
                f"| {item.get('reason', '')} | {item.get('symbol', item.get('macro_status', ''))} | "
                f"{value} | {threshold} | {item.get('severity', '')} |"
            )
    else:
        lines.append("| - | - |  |  | no hedge evidence |")
    if inverse_skipped:
        lines.extend(["", "| skipped_ticker | reason |", "| --- | --- |"])
        for item in inverse_skipped:
            lines.append(f"| {item['ticker']} | {item['reason']} |")
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
    us_market_adjustment: Any,
    bond_yield_adjustment: Any,
    combined_buy_budget_multiplier: float,
    macro_adjustment: MacroExposureAdjustment,
    macro_reduction_skipped: list[dict[str, str]],
    inverse_signal: InverseEtfSignal,
    inverse_orders: list[RebalanceOrder],
    inverse_skipped: list[dict[str, str]],
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
        "bond_yield_risk": {
            "status": bond_yield_adjustment.status,
            "buy_budget_multiplier": bond_yield_adjustment.buy_budget_multiplier,
            "cash_target": bond_yield_adjustment.cash_target,
            "reasons": bond_yield_adjustment.reasons,
            "changes_bp": bond_yield_adjustment.changes_bp,
        },
        "combined_buy_budget_multiplier": combined_buy_budget_multiplier,
        "macro_exposure_adjustment": macro_adjustment.as_dict(
            orders_generated=any(order.reason.startswith("macro_risk_reduce") for order in sells),
            execution_allowed=True,
        ),
        "macro_reduction_skipped": macro_reduction_skipped,
        "inverse_etf_hedge": inverse_signal.as_dict(
            orders=inverse_orders,
            skipped=inverse_skipped,
            execution_allowed=True,
        ),
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


def _load_domestic_index_closes(engine: Any, *, as_of_date: date) -> dict[str, list[float]]:
    if not isinstance(engine, Engine):
        return {}
    with session_scope(engine) as session:
        rows = session.scalars(
            select(MarketIndexPrice)
            .where(
                MarketIndexPrice.symbol.in_(("KOSPI", "KOSDAQ")),
                MarketIndexPrice.date < as_of_date,
            )
            .order_by(MarketIndexPrice.symbol, MarketIndexPrice.date)
        ).all()
    closes: dict[str, list[float]] = {"KOSPI": [], "KOSDAQ": []}
    for row in rows:
        if row.close is not None and row.close > 0:
            closes.setdefault(row.symbol, []).append(float(row.close))
    return closes


def _quote_tickers_for_dry_run(
    *,
    target_tickers: list[str],
    held_tickers: set[str],
    inverse_signal: InverseEtfSignal,
) -> list[str]:
    tickers: list[str] = []
    for ticker in target_tickers + inverse_signal.selected_tickers:
        if ticker in held_tickers or ticker in tickers:
            continue
        tickers.append(ticker)
    return tickers


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
