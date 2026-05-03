from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from datetime import date
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import BACKTEST, PORTFOLIO
from src.backtest.engine import run_backtest
from src.backtest.models import BacktestResult
from src.data.database import get_engine


RunBacktestFunction = Callable[..., BacktestResult]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Phase 3 backtest.")
    parser.add_argument("--start-date", type=_parse_date, default=date.fromisoformat(BACKTEST.start_date))
    parser.add_argument("--end-date", type=_parse_date, default=date.fromisoformat(BACKTEST.end_date))
    parser.add_argument("--top-n", type=int, default=PORTFOLIO.n_holdings)
    parser.add_argument("--initial-capital", type=float, default=PORTFOLIO.initial_capital)
    parser.add_argument("--database-url", default=None)
    args = parser.parse_args(argv)
    if args.start_date > args.end_date:
        parser.error("--start-date must be on or before --end-date")
    if args.top_n <= 0:
        parser.error("--top-n must be greater than 0")
    if args.initial_capital <= 0:
        parser.error("--initial-capital must be positive")
    return args


def run(
    args: argparse.Namespace,
    *,
    run_backtest_func: RunBacktestFunction = run_backtest,
) -> int:
    engine = get_engine(args.database_url)
    result = run_backtest_func(
        engine,
        start_date=args.start_date,
        end_date=args.end_date,
        top_n=args.top_n,
        initial_capital=args.initial_capital,
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
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    return run(parse_args(argv))


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


if __name__ == "__main__":
    raise SystemExit(main())
