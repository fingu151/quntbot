from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Sequence
from datetime import date
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import BACKTEST, COST, PORTFOLIO
from src.backtest.models import BacktestResult
from src.data.database import create_tables, get_engine
from src.strategies.adaptive_alpha import DEFAULT_ADAPTIVE_ALPHA, AdaptiveAlphaConfig, run_adaptive_alpha_backtest


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the isolated Adaptive Alpha backtest.")
    parser.add_argument("--start-date", type=_parse_date, default=date.fromisoformat(BACKTEST.start_date))
    parser.add_argument("--end-date", type=_parse_date, default=date.fromisoformat(BACKTEST.end_date))
    parser.add_argument("--initial-capital", type=float, default=PORTFOLIO.initial_capital)
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--output-md", type=Path, default=None)
    parser.add_argument("--top-n", type=int, default=DEFAULT_ADAPTIVE_ALPHA.top_n)
    parser.add_argument("--sell-rank-buffer", type=int, default=DEFAULT_ADAPTIVE_ALPHA.sell_rank_buffer)
    parser.add_argument("--trailing-stop-pct", type=float, default=DEFAULT_ADAPTIVE_ALPHA.trailing_stop_pct)
    parser.add_argument("--atr-multiplier", type=float, default=DEFAULT_ADAPTIVE_ALPHA.atr_multiplier)
    parser.add_argument("--profit-take-pct", type=float, default=DEFAULT_ADAPTIVE_ALPHA.profit_take_pct)
    parser.add_argument("--commission-rate", type=float, default=COST.commission_rate)
    parser.add_argument("--tax-rate-kospi", type=float, default=COST.tax_rate_kospi)
    parser.add_argument("--tax-rate-kosdaq", type=float, default=COST.tax_rate_kosdaq)
    parser.add_argument("--slippage-rate", type=float, default=COST.slippage_rate)
    args = parser.parse_args(argv)
    if args.start_date > args.end_date:
        parser.error("--start-date must be on or before --end-date")
    if args.initial_capital <= 0:
        parser.error("--initial-capital must be positive")
    if args.top_n <= 0:
        parser.error("--top-n must be greater than 0")
    if args.sell_rank_buffer < args.top_n:
        parser.error("--sell-rank-buffer must be greater than or equal to --top-n")
    if args.trailing_stop_pct >= 0:
        parser.error("--trailing-stop-pct must be negative")
    if args.atr_multiplier <= 0:
        parser.error("--atr-multiplier must be greater than 0")
    if args.profit_take_pct <= 0:
        parser.error("--profit-take-pct must be positive")
    return args


def run(args: argparse.Namespace) -> int:
    engine = get_engine(args.database_url)
    create_tables(engine)
    config = AdaptiveAlphaConfig(
        top_n=args.top_n,
        sell_rank_buffer=args.sell_rank_buffer,
        trailing_stop_pct=args.trailing_stop_pct,
        atr_multiplier=args.atr_multiplier,
        profit_take_pct=args.profit_take_pct,
    )
    result = run_adaptive_alpha_backtest(
        engine,
        start_date=args.start_date,
        end_date=args.end_date,
        config=config,
        initial_capital=args.initial_capital,
        commission_rate=args.commission_rate,
        tax_rate_kospi=args.tax_rate_kospi,
        tax_rate_kosdaq=args.tax_rate_kosdaq,
        slippage_rate=args.slippage_rate,
    )
    _print_summary(result)
    if args.output_md is not None:
        args.output_md.parent.mkdir(parents=True, exist_ok=True)
        args.output_md.write_text(_format_markdown(result), encoding="utf-8")
        print(f"wrote_md={args.output_md}")
    return 0


def _print_summary(result: BacktestResult) -> None:
    print(f"initial_capital={result.initial_capital:.2f}")
    print(f"final_equity={result.final_equity:.2f}")
    print(f"total_return={result.total_return:.2%}")
    print(f"cagr={result.cagr:.2%}")
    print(f"max_drawdown={result.max_drawdown:.2%}")
    print(f"sharpe_ratio={result.sharpe_ratio:.4f}")
    print(f"win_rate={result.win_rate:.2%}")
    print(f"average_holding_days={result.average_holding_days:.2f}")
    print(f"trade_count={len(result.trades)}")
    sells = [trade for trade in result.trades if trade.side == "SELL"]
    reasons = Counter(trade.reason for trade in sells)
    print("sell_reasons=" + ", ".join(f"{reason}:{count}" for reason, count in sorted(reasons.items())))


def _format_markdown(result: BacktestResult) -> str:
    sells = [trade for trade in result.trades if trade.side == "SELL"]
    reasons = Counter(trade.reason for trade in sells)
    reason_lines = "\n".join(f"- `{reason}`: {count}" for reason, count in sorted(reasons.items()))
    return (
        "# Adaptive Alpha Backtest\n\n"
        f"- Final equity: `{result.final_equity:.2f}`\n"
        f"- Total return: `{result.total_return:.2%}`\n"
        f"- CAGR: `{result.cagr:.2%}`\n"
        f"- Max drawdown: `{result.max_drawdown:.2%}`\n"
        f"- Sharpe ratio: `{result.sharpe_ratio:.4f}`\n"
        f"- Win rate: `{result.win_rate:.2%}`\n"
        f"- Average holding days: `{result.average_holding_days:.2f}`\n"
        f"- Trade count: `{len(result.trades)}`\n\n"
        "## Sell Reasons\n\n"
        f"{reason_lines}\n"
    )


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def main(argv: Sequence[str] | None = None) -> int:
    return run(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
