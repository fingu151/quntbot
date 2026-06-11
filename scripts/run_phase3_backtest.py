from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Callable, Sequence
from datetime import date
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import BACKTEST, COST, EXIT_RULES, INVERSE_ETF, MACRO_RISK, MARKET_RISK, PORTFOLIO, REBALANCE
from src.backtest.engine import run_backtest
from src.backtest.models import BacktestResult
from src.data.database import create_tables, get_engine


RunBacktestFunction = Callable[..., BacktestResult]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Phase 3 backtest.")
    parser.add_argument("--start-date", type=_parse_date, default=date.fromisoformat(BACKTEST.start_date))
    parser.add_argument("--end-date", type=_parse_date, default=date.fromisoformat(BACKTEST.end_date))
    parser.add_argument("--top-n", type=int, default=PORTFOLIO.n_holdings)
    parser.add_argument("--initial-capital", type=float, default=PORTFOLIO.initial_capital)
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--trade-summary", action="store_true")
    parser.add_argument(
        "--rebalance-frequency",
        choices=("daily", "weekly", "monthly"),
        default=REBALANCE.frequency,
    )
    parser.add_argument("--stop-loss-pct", type=float, default=EXIT_RULES.stop_loss_pct)
    parser.add_argument("--trailing-stop-pct", type=float, default=EXIT_RULES.trailing_stop_pct)
    parser.add_argument("--stop-cooldown-days", type=int, default=EXIT_RULES.stop_cooldown_days)
    parser.add_argument("--enable-atr-stop", action=argparse.BooleanOptionalAction, default=EXIT_RULES.enable_atr_stop)
    parser.add_argument("--atr-window", type=int, default=EXIT_RULES.atr_window)
    parser.add_argument("--atr-multiplier", type=float, default=EXIT_RULES.atr_multiplier)
    parser.add_argument("--profit-take-pct", type=float, default=EXIT_RULES.profit_take_pct)
    parser.add_argument(
        "--profit-take-sell-fraction",
        type=float,
        default=EXIT_RULES.profit_take_sell_fraction,
    )
    parser.add_argument("--breakeven-stop-pct", type=float, default=EXIT_RULES.breakeven_stop_pct)
    parser.add_argument("--sell-rank-buffer", type=int, default=REBALANCE.sell_rank_buffer)
    parser.add_argument(
        "--min-holding-trading-days",
        type=int,
        default=REBALANCE.min_holding_trading_days,
    )
    parser.add_argument(
        "--weighting",
        choices=("equal", "score_weighted"),
        default=PORTFOLIO.weighting,
    )
    parser.add_argument("--min-position-weight", type=float, default=PORTFOLIO.min_position_weight)
    parser.add_argument("--max-position-weight", type=float, default=PORTFOLIO.max_position_weight)
    parser.add_argument(
        "--enable-market-risk-overlay",
        action=argparse.BooleanOptionalAction,
        default=MARKET_RISK.enable_overlay,
    )
    parser.add_argument(
        "--enable-macro-risk-overlay",
        action=argparse.BooleanOptionalAction,
        default=MACRO_RISK.enable_overlay,
    )
    parser.add_argument(
        "--enable-inverse-etf-hedge",
        action=argparse.BooleanOptionalAction,
        default=INVERSE_ETF.enabled,
    )
    parser.add_argument(
        "--inverse-etf-allowed-tickers",
        type=_parse_ticker_tuple,
        default=INVERSE_ETF.allowed_tickers,
    )
    parser.add_argument(
        "--inverse-etf-leveraged-tickers",
        type=_parse_ticker_tuple,
        default=INVERSE_ETF.leveraged_tickers,
    )
    parser.add_argument("--market-risk-rsi-window", type=int, default=MARKET_RISK.rsi_window)
    parser.add_argument("--market-risk-rsi-threshold", type=float, default=MARKET_RISK.rsi_overheat_threshold)
    parser.add_argument(
        "--one-market-overheat-cash-target",
        type=float,
        default=MARKET_RISK.one_market_overheat_cash_target,
    )
    parser.add_argument(
        "--both-markets-overheat-cash-target",
        type=float,
        default=MARKET_RISK.both_markets_overheat_cash_target,
    )
    parser.add_argument("--nasdaq-moderate-drop-pct", type=float, default=MARKET_RISK.nasdaq_moderate_drop_pct)
    parser.add_argument("--nasdaq-severe-drop-pct", type=float, default=MARKET_RISK.nasdaq_severe_drop_pct)
    parser.add_argument(
        "--nasdaq-moderate-cash-target",
        type=float,
        default=MARKET_RISK.nasdaq_moderate_cash_target,
    )
    parser.add_argument(
        "--nasdaq-severe-cash-target",
        type=float,
        default=MARKET_RISK.nasdaq_severe_cash_target,
    )
    parser.add_argument("--commission-rate", type=float, default=COST.commission_rate)
    parser.add_argument("--tax-rate-kospi", type=float, default=COST.tax_rate_kospi)
    parser.add_argument("--tax-rate-kosdaq", type=float, default=COST.tax_rate_kosdaq)
    parser.add_argument("--slippage-rate", type=float, default=COST.slippage_rate)
    stops = parser.add_mutually_exclusive_group()
    stops.add_argument("--enable-stops", dest="enable_stops", action="store_true", default=True)
    stops.add_argument("--disable-stops", dest="enable_stops", action="store_false")
    args = parser.parse_args(argv)
    if args.start_date > args.end_date:
        parser.error("--start-date must be on or before --end-date")
    if args.top_n <= 0:
        parser.error("--top-n must be greater than 0")
    if args.initial_capital <= 0:
        parser.error("--initial-capital must be positive")
    if args.stop_loss_pct >= 0:
        parser.error("--stop-loss-pct must be negative")
    if args.trailing_stop_pct >= 0:
        parser.error("--trailing-stop-pct must be negative")
    if args.stop_cooldown_days < 0:
        parser.error("--stop-cooldown-days must be zero or greater")
    if args.atr_window <= 0:
        parser.error("--atr-window must be greater than 0")
    if args.atr_multiplier <= 0:
        parser.error("--atr-multiplier must be greater than 0")
    if args.profit_take_pct <= 0:
        parser.error("--profit-take-pct must be positive")
    if not 0 < args.profit_take_sell_fraction < 1:
        parser.error("--profit-take-sell-fraction must be between 0 and 1")
    if args.sell_rank_buffer <= 0:
        parser.error("--sell-rank-buffer must be greater than 0")
    if args.min_holding_trading_days < 0:
        parser.error("--min-holding-trading-days must be zero or greater")
    if args.min_position_weight <= 0:
        parser.error("--min-position-weight must be greater than 0")
    if args.max_position_weight > 1:
        parser.error("--max-position-weight must be at most 1")
    if args.min_position_weight > args.max_position_weight:
        parser.error("--min-position-weight must be less than or equal to --max-position-weight")
    for option_name in (
        "one_market_overheat_cash_target",
        "both_markets_overheat_cash_target",
        "nasdaq_moderate_cash_target",
        "nasdaq_severe_cash_target",
    ):
        value = getattr(args, option_name)
        if not 0 <= value <= 1:
            parser.error(f"--{option_name.replace('_', '-')} must be between 0 and 1")
    if args.market_risk_rsi_window <= 0:
        parser.error("--market-risk-rsi-window must be greater than 0")
    if args.nasdaq_severe_drop_pct > args.nasdaq_moderate_drop_pct:
        parser.error("--nasdaq-severe-drop-pct must be less than or equal to --nasdaq-moderate-drop-pct")
    for option_name in ("commission_rate", "tax_rate_kospi", "tax_rate_kosdaq", "slippage_rate"):
        if getattr(args, option_name) < 0:
            parser.error(f"--{option_name.replace('_', '-')} must be zero or greater")
    return args


def run(
    args: argparse.Namespace,
    *,
    run_backtest_func: RunBacktestFunction = run_backtest,
) -> int:
    engine = get_engine(args.database_url)
    create_tables(engine)
    result = run_backtest_func(
        engine,
        start_date=args.start_date,
        end_date=args.end_date,
        top_n=args.top_n,
        initial_capital=args.initial_capital,
        commission_rate=args.commission_rate,
        tax_rate_kospi=args.tax_rate_kospi,
        tax_rate_kosdaq=args.tax_rate_kosdaq,
        slippage_rate=args.slippage_rate,
        enable_stops=args.enable_stops,
        rebalance_frequency=args.rebalance_frequency,
        stop_loss_pct=args.stop_loss_pct,
        trailing_stop_pct=args.trailing_stop_pct,
        stop_cooldown_days=args.stop_cooldown_days,
        enable_atr_stop=args.enable_atr_stop,
        atr_window=args.atr_window,
        atr_multiplier=args.atr_multiplier,
        profit_take_pct=args.profit_take_pct,
        profit_take_sell_fraction=args.profit_take_sell_fraction,
        breakeven_stop_pct=args.breakeven_stop_pct,
        sell_rank_buffer=args.sell_rank_buffer,
        min_holding_trading_days=args.min_holding_trading_days,
        weighting=args.weighting,
        min_position_weight=args.min_position_weight,
        max_position_weight=args.max_position_weight,
        enable_market_risk_overlay=args.enable_market_risk_overlay,
        enable_macro_risk_overlay=args.enable_macro_risk_overlay,
        enable_inverse_etf_hedge=args.enable_inverse_etf_hedge,
        inverse_etf_allowed_tickers=args.inverse_etf_allowed_tickers,
        inverse_etf_leveraged_tickers=args.inverse_etf_leveraged_tickers,
        market_risk_rsi_window=args.market_risk_rsi_window,
        market_risk_rsi_threshold=args.market_risk_rsi_threshold,
        one_market_overheat_cash_target=args.one_market_overheat_cash_target,
        both_markets_overheat_cash_target=args.both_markets_overheat_cash_target,
        nasdaq_moderate_drop_pct=args.nasdaq_moderate_drop_pct,
        nasdaq_severe_drop_pct=args.nasdaq_severe_drop_pct,
        nasdaq_moderate_cash_target=args.nasdaq_moderate_cash_target,
        nasdaq_severe_cash_target=args.nasdaq_severe_cash_target,
    )
    print(f"initial_capital={result.initial_capital:.2f}")
    print(f"final_equity={result.final_equity:.2f}")
    print(f"total_return={result.total_return:.2%}")
    print(f"cagr={result.cagr:.2%}")
    print(f"max_drawdown={result.max_drawdown:.2%}")
    print(f"sharpe_ratio={result.sharpe_ratio:.4f}")
    print(f"win_rate={result.win_rate:.2%}")
    print(f"average_holding_days={result.average_holding_days:.2f}")
    print(f"trade_count={len(result.trades)}")
    if args.trade_summary:
        buy_count = sum(1 for trade in result.trades if trade.side == "BUY")
        sell_count = sum(1 for trade in result.trades if trade.side == "SELL")
        reason_counts = Counter(trade.reason for trade in result.trades)
        reasons = ", ".join(f"{reason}:{count}" for reason, count in sorted(reason_counts.items()))
        print(f"buy_count={buy_count}")
        print(f"sell_count={sell_count}")
        print(f"trade_reasons={reasons}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    return run(parse_args(argv))


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def _parse_ticker_tuple(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


if __name__ == "__main__":
    raise SystemExit(main())
