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

from config import BACKTEST, COST, EXIT_RULES, PORTFOLIO, REBALANCE
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


if __name__ == "__main__":
    raise SystemExit(main())
