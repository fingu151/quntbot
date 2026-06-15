from __future__ import annotations

import argparse
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
    parser = argparse.ArgumentParser(description="Run a Phase 3 backtest comparison matrix.")
    parser.add_argument("--start-date", type=_parse_date, default=date.fromisoformat(BACKTEST.start_date))
    parser.add_argument("--end-date", type=_parse_date, default=date.fromisoformat(BACKTEST.end_date))
    parser.add_argument("--top-ns", type=_parse_positive_ints, default=[PORTFOLIO.n_holdings])
    parser.add_argument(
        "--rebalance-frequencies",
        type=_parse_rebalance_frequencies,
        default=[REBALANCE.frequency],
    )
    parser.add_argument("--cost-scenarios", type=_parse_cost_scenarios, default=["custom"])
    parser.add_argument("--initial-capital", type=float, default=PORTFOLIO.initial_capital)
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--output-csv", type=Path, default=None)
    parser.add_argument("--output-md", type=Path, default=None)
    parser.add_argument("--include-stops-disabled", action="store_true")
    parser.add_argument("--stop-loss-pct", type=float, default=EXIT_RULES.stop_loss_pct)
    parser.add_argument("--trailing-stop-pct", type=float, default=EXIT_RULES.trailing_stop_pct)
    parser.add_argument("--stop-cooldown-days", type=int, default=EXIT_RULES.stop_cooldown_days)
    parser.add_argument("--enable-atr-stop", action=argparse.BooleanOptionalAction, default=EXIT_RULES.enable_atr_stop)
    parser.add_argument("--atr-window", type=int, default=EXIT_RULES.atr_window)
    parser.add_argument("--atr-multiplier", type=float, default=EXIT_RULES.atr_multiplier)
    parser.add_argument(
        "--atr-only-stop",
        action=argparse.BooleanOptionalAction,
        default=EXIT_RULES.atr_only_stop,
    )
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
    parser.add_argument(
        "--inverse-etf-require-market-confirmation",
        action=argparse.BooleanOptionalAction,
        default=INVERSE_ETF.require_market_confirmation,
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
    args = parser.parse_args(argv)
    if args.start_date > args.end_date:
        parser.error("--start-date must be on or before --end-date")
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
    header = (
        "top_n,rebalance_frequency,cost_scenario,stops,final_equity,total_return,cagr,"
        "max_drawdown,sharpe_ratio,win_rate,average_holding_days,trade_count"
    )
    rows = [header]
    result_rows: list[dict[str, str]] = []
    print(header)
    stop_modes = [True, False] if args.include_stops_disabled else [True]
    for top_n in args.top_ns:
        for frequency in args.rebalance_frequencies:
            for cost_scenario in args.cost_scenarios:
                cost_settings = _cost_settings(cost_scenario, args)
                for enable_stops in stop_modes:
                    result = run_backtest_func(
                        engine,
                        start_date=args.start_date,
                        end_date=args.end_date,
                        top_n=top_n,
                        initial_capital=args.initial_capital,
                        commission_rate=cost_settings["commission_rate"],
                        tax_rate_kospi=cost_settings["tax_rate_kospi"],
                        tax_rate_kosdaq=cost_settings["tax_rate_kosdaq"],
                        slippage_rate=cost_settings["slippage_rate"],
                        enable_stops=enable_stops,
                        rebalance_frequency=frequency,
                        stop_loss_pct=args.stop_loss_pct,
                        trailing_stop_pct=args.trailing_stop_pct,
                        stop_cooldown_days=args.stop_cooldown_days,
                        enable_atr_stop=args.enable_atr_stop,
                        atr_window=args.atr_window,
                        atr_multiplier=args.atr_multiplier,
                        atr_only_stop=args.atr_only_stop,
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
                        inverse_etf_require_market_confirmation=args.inverse_etf_require_market_confirmation,
                        market_risk_rsi_window=args.market_risk_rsi_window,
                        market_risk_rsi_threshold=args.market_risk_rsi_threshold,
                        one_market_overheat_cash_target=args.one_market_overheat_cash_target,
                        both_markets_overheat_cash_target=args.both_markets_overheat_cash_target,
                        nasdaq_moderate_drop_pct=args.nasdaq_moderate_drop_pct,
                        nasdaq_severe_drop_pct=args.nasdaq_severe_drop_pct,
                        nasdaq_moderate_cash_target=args.nasdaq_moderate_cash_target,
                        nasdaq_severe_cash_target=args.nasdaq_severe_cash_target,
                    )
                    result_row = _result_row(top_n, frequency, cost_scenario, enable_stops, result)
                    result_rows.append(result_row)
                    row = _format_csv_row(result_row)
                    rows.append(row)
                    print(row)
    if args.output_csv is not None:
        args.output_csv.parent.mkdir(parents=True, exist_ok=True)
        args.output_csv.write_text("\n".join(rows) + "\n", encoding="utf-8")
        print(f"wrote_csv={args.output_csv}")
    if args.output_md is not None:
        args.output_md.parent.mkdir(parents=True, exist_ok=True)
        args.output_md.write_text(_format_markdown_report(result_rows), encoding="utf-8")
        print(f"wrote_md={args.output_md}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    return run(parse_args(argv))


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def _parse_positive_ints(value: str) -> list[int]:
    parsed = [int(part.strip()) for part in value.split(",") if part.strip()]
    if not parsed or any(item <= 0 for item in parsed):
        raise argparse.ArgumentTypeError("must be a comma-separated list of positive integers")
    return parsed


def _parse_rebalance_frequencies(value: str) -> list[str]:
    parsed = [part.strip() for part in value.split(",") if part.strip()]
    allowed = {"daily", "weekly", "monthly"}
    invalid = sorted(set(parsed) - allowed)
    if not parsed or invalid:
        raise argparse.ArgumentTypeError("must contain only daily, weekly, or monthly")
    return parsed


def _parse_ticker_tuple(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _parse_cost_scenarios(value: str) -> list[str]:
    parsed = [part.strip() for part in value.split(",") if part.strip()]
    allowed = {"custom", "base", "zero", "slippage20", "slippage30"}
    invalid = sorted(set(parsed) - allowed)
    if not parsed or invalid:
        raise argparse.ArgumentTypeError(
            "must contain only custom, base, zero, slippage20, or slippage30"
        )
    return parsed


def _cost_settings(scenario: str, args: argparse.Namespace) -> dict[str, float]:
    if scenario == "custom":
        return {
            "commission_rate": args.commission_rate,
            "tax_rate_kospi": args.tax_rate_kospi,
            "tax_rate_kosdaq": args.tax_rate_kosdaq,
            "slippage_rate": args.slippage_rate,
        }
    if scenario == "zero":
        return {
            "commission_rate": 0.0,
            "tax_rate_kospi": 0.0,
            "tax_rate_kosdaq": 0.0,
            "slippage_rate": 0.0,
        }
    slippage_rate = COST.slippage_rate
    if scenario == "slippage20":
        slippage_rate = 0.0020
    elif scenario == "slippage30":
        slippage_rate = 0.0030
    return {
        "commission_rate": COST.commission_rate,
        "tax_rate_kospi": COST.tax_rate_kospi,
        "tax_rate_kosdaq": COST.tax_rate_kosdaq,
        "slippage_rate": slippage_rate,
    }


def _result_row(
    top_n: int,
    frequency: str,
    cost_scenario: str,
    enable_stops: bool,
    result: BacktestResult,
) -> dict[str, str]:
    stops = "on" if enable_stops else "off"
    return {
        "top_n": str(top_n),
        "rebalance_frequency": frequency,
        "cost_scenario": cost_scenario,
        "stops": stops,
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
        row[column]
        for column in (
            "top_n",
            "rebalance_frequency",
            "cost_scenario",
            "stops",
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


def _format_markdown_report(rows: list[dict[str, str]]) -> str:
    lines = ["# Backtest Matrix Report", ""]
    if not rows:
        lines.append("No scenarios were run.")
        return "\n".join(lines) + "\n"
    best = max(rows, key=lambda row: float(row["sharpe_ratio"]))
    best_return = max(rows, key=lambda row: _parse_percent(row["total_return"]))
    lowest_mdd = max(rows, key=lambda row: _parse_percent(row["max_drawdown"]))
    lowest_trades = min(rows, key=lambda row: int(row["trade_count"]))
    lines.append(
        "Best by Sharpe: "
        f"top_n={best['top_n']}, "
        f"rebalance={best['rebalance_frequency']}, "
        f"cost={best['cost_scenario']}, "
        f"stops={best['stops']}"
    )
    lines.append(_summary_line("Best by Return", best_return))
    lines.append(_summary_line("Lowest MDD", lowest_mdd))
    lines.append(_summary_line("Lowest Trades", lowest_trades))
    lines.extend(
        [
            "",
            "| top_n | rebalance | cost | stops | final_equity | total_return | sharpe |",
            "|---:|---|---|---|---:|---:|---:|",
        ]
    )
    for row in rows:
        lines.append(
            f"| {row['top_n']} | {row['rebalance_frequency']} | {row['cost_scenario']} | "
            f"{row['stops']} | {row['final_equity']} | {row['total_return']} | "
            f"{row['sharpe_ratio']} |"
        )
    return "\n".join(lines) + "\n"


def _summary_line(label: str, row: dict[str, str]) -> str:
    return (
        f"{label}: "
        f"top_n={row['top_n']}, "
        f"rebalance={row['rebalance_frequency']}, "
        f"cost={row['cost_scenario']}, "
        f"stops={row['stops']}"
    )


def _parse_percent(value: str) -> float:
    return float(value.removesuffix("%"))


if __name__ == "__main__":
    raise SystemExit(main())
