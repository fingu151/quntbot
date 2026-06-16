from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from datetime import date
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import BACKTEST, COST, PORTFOLIO
from loguru import logger
from src.backtest.models import BacktestResult
from src.data.database import create_tables, get_engine
from src.strategies.adaptive_alpha import DEFAULT_ADAPTIVE_ALPHA, AdaptiveAlphaConfig, run_adaptive_alpha_backtest


BacktestFunction = Callable[..., BacktestResult]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Adaptive Alpha parameter matrix.")
    parser.add_argument("--start-date", type=_parse_date, default=date.fromisoformat(BACKTEST.start_date))
    parser.add_argument("--end-date", type=_parse_date, default=date.fromisoformat(BACKTEST.end_date))
    parser.add_argument("--initial-capital", type=float, default=PORTFOLIO.initial_capital)
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--output-csv", type=Path, default=None)
    parser.add_argument("--output-md", type=Path, default=None)
    parser.add_argument("--top-n", type=int, default=DEFAULT_ADAPTIVE_ALPHA.top_n)
    parser.add_argument("--sell-rank-buffers", type=_parse_ints, default=[40, 45])
    parser.add_argument("--atr-multipliers", type=_parse_floats, default=[2.0, 2.2])
    parser.add_argument("--profit-take-pcts", type=_parse_floats, default=[0.16, 0.18])
    parser.add_argument("--trailing-stop-pct", type=float, default=DEFAULT_ADAPTIVE_ALPHA.trailing_stop_pct)
    parser.add_argument(
        "--post-profit-trailing-stop-pct",
        type=float,
        default=DEFAULT_ADAPTIVE_ALPHA.post_profit_trailing_stop_pct,
    )
    parser.add_argument("--slippage-rate", type=float, default=COST.slippage_rate)
    args = parser.parse_args(argv)
    if args.start_date > args.end_date:
        parser.error("--start-date must be on or before --end-date")
    if args.initial_capital <= 0:
        parser.error("--initial-capital must be positive")
    if args.top_n <= 0:
        parser.error("--top-n must be greater than 0")
    if any(value < args.top_n for value in args.sell_rank_buffers):
        parser.error("--sell-rank-buffers must be greater than or equal to --top-n")
    if any(value <= 0 for value in args.atr_multipliers):
        parser.error("--atr-multipliers must be positive")
    if any(value <= 0 for value in args.profit_take_pcts):
        parser.error("--profit-take-pcts must be positive")
    if args.trailing_stop_pct >= 0:
        parser.error("--trailing-stop-pct must be negative")
    if args.post_profit_trailing_stop_pct >= 0:
        parser.error("--post-profit-trailing-stop-pct must be negative")
    if args.slippage_rate < 0:
        parser.error("--slippage-rate must be zero or greater")
    return args


def run(
    args: argparse.Namespace,
    *,
    backtest_func: BacktestFunction = run_adaptive_alpha_backtest,
) -> int:
    logger.remove()
    engine = get_engine(args.database_url)
    create_tables(engine)
    result_rows: list[dict[str, str]] = []
    header = (
        "sell_rank_buffer,atr_multiplier,profit_take_pct,final_equity,total_return,cagr,"
        "max_drawdown,sharpe_ratio,win_rate,average_holding_days,trade_count"
    )
    print(header)
    csv_rows = [header]
    for sell_rank_buffer in args.sell_rank_buffers:
        for atr_multiplier in args.atr_multipliers:
            for profit_take_pct in args.profit_take_pcts:
                config = AdaptiveAlphaConfig(
                    top_n=args.top_n,
                    sell_rank_buffer=sell_rank_buffer,
                    trailing_stop_pct=args.trailing_stop_pct,
                    post_profit_trailing_stop_pct=args.post_profit_trailing_stop_pct,
                    atr_multiplier=atr_multiplier,
                    profit_take_pct=profit_take_pct,
                )
                result = backtest_func(
                    engine,
                    start_date=args.start_date,
                    end_date=args.end_date,
                    config=config,
                    initial_capital=args.initial_capital,
                    commission_rate=COST.commission_rate,
                    tax_rate_kospi=COST.tax_rate_kospi,
                    tax_rate_kosdaq=COST.tax_rate_kosdaq,
                    slippage_rate=args.slippage_rate,
                )
                row = _result_row(sell_rank_buffer, atr_multiplier, profit_take_pct, result)
                result_rows.append(row)
                csv_row = _format_csv_row(row)
                csv_rows.append(csv_row)
                print(csv_row)
    if args.output_csv is not None:
        args.output_csv.parent.mkdir(parents=True, exist_ok=True)
        args.output_csv.write_text("\n".join(csv_rows) + "\n", encoding="utf-8")
        print(f"wrote_csv={args.output_csv}")
    if args.output_md is not None:
        args.output_md.parent.mkdir(parents=True, exist_ok=True)
        args.output_md.write_text(_format_markdown(result_rows), encoding="utf-8")
        print(f"wrote_md={args.output_md}")
    return 0


def _result_row(
    sell_rank_buffer: int,
    atr_multiplier: float,
    profit_take_pct: float,
    result: BacktestResult,
) -> dict[str, str]:
    return {
        "sell_rank_buffer": str(sell_rank_buffer),
        "atr_multiplier": f"{atr_multiplier:.2f}",
        "profit_take_pct": f"{profit_take_pct:.2f}",
        "final_equity": f"{result.final_equity:.2f}",
        "total_return": f"{result.total_return:.2%}",
        "cagr": f"{result.cagr:.2%}",
        "max_drawdown": f"{result.max_drawdown:.2%}",
        "sharpe_ratio": f"{result.sharpe_ratio:.4f}",
        "win_rate": f"{result.win_rate:.2%}",
        "average_holding_days": f"{result.average_holding_days:.2f}",
        "trade_count": str(len(result.trades)),
    }


def _format_csv_row(row: dict[str, str]) -> str:
    return ",".join(
        row[key]
        for key in (
            "sell_rank_buffer",
            "atr_multiplier",
            "profit_take_pct",
            "final_equity",
            "total_return",
            "cagr",
            "max_drawdown",
            "sharpe_ratio",
            "win_rate",
            "average_holding_days",
            "trade_count",
        )
    )


def _format_markdown(rows: list[dict[str, str]]) -> str:
    if not rows:
        return "# Adaptive Alpha Matrix\n\nNo rows.\n"
    best_sharpe = max(rows, key=lambda row: float(row["sharpe_ratio"]))
    best_return = max(rows, key=lambda row: _parse_percent(row["total_return"]))
    lowest_mdd = max(rows, key=lambda row: _parse_percent(row["max_drawdown"]))
    lines = [
        "# Adaptive Alpha Matrix",
        "",
        (
            "Best by Sharpe: "
            f"buffer={best_sharpe['sell_rank_buffer']}, atr={best_sharpe['atr_multiplier']}, "
            f"profit={best_sharpe['profit_take_pct']}, sharpe={best_sharpe['sharpe_ratio']}"
        ),
        (
            "Best by Return: "
            f"buffer={best_return['sell_rank_buffer']}, atr={best_return['atr_multiplier']}, "
            f"profit={best_return['profit_take_pct']}, return={best_return['total_return']}"
        ),
        (
            "Lowest MDD: "
            f"buffer={lowest_mdd['sell_rank_buffer']}, atr={lowest_mdd['atr_multiplier']}, "
            f"profit={lowest_mdd['profit_take_pct']}, mdd={lowest_mdd['max_drawdown']}"
        ),
        "",
        "| Buffer | ATR | Profit Take | Final Equity | Total Return | MDD | Sharpe | Trades |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        lines.append(
            f"| {row['sell_rank_buffer']} | {row['atr_multiplier']} | {row['profit_take_pct']} | "
            f"{row['final_equity']} | {row['total_return']} | {row['max_drawdown']} | "
            f"{row['sharpe_ratio']} | {row['trade_count']} |"
        )
    return "\n".join(lines) + "\n"


def _parse_percent(value: str) -> float:
    return float(value.rstrip("%")) / 100.0


def _parse_ints(value: str) -> list[int]:
    parsed = [int(part.strip()) for part in value.split(",") if part.strip()]
    if not parsed:
        raise argparse.ArgumentTypeError("must contain at least one integer")
    return parsed


def _parse_floats(value: str) -> list[float]:
    parsed = [float(part.strip()) for part in value.split(",") if part.strip()]
    if not parsed:
        raise argparse.ArgumentTypeError("must contain at least one number")
    return parsed


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def main(argv: Sequence[str] | None = None) -> int:
    return run(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
