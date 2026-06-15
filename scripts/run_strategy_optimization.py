from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
import sys

from sqlalchemy import func, select

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import COST, FACTOR, PORTFOLIO
from src.backtest.engine import _make_fast_score_func, run_backtest
from src.backtest.models import BacktestResult
from src.factors.models import FactorScore
from src.data.database import create_tables, get_engine, session_scope
from src.data.models import QualityMetric
from src.strategies.adaptive_alpha import (
    ADAPTIVE_ALPHA_V2,
    DEFAULT_ADAPTIVE_ALPHA,
    run_adaptive_alpha_backtest,
)


BaseBacktestFunction = Callable[..., BacktestResult]
AdaptiveBacktestFunction = Callable[..., BacktestResult]
ScoreFunction = Callable[..., list[FactorScore]]
ScoreFunctionFactory = Callable[..., ScoreFunction]
DEFAULT_CANDIDATES = [
    "current_top30",
    "top15",
    "top20",
    "adaptive_alpha_tuned",
    "adaptive_alpha_v2",
    "inverse_hedge_conservative",
    "crash_guard_top30",
    "crash_guard_inverse_top30",
    "crash_guard_v2_reentry",
    "dynamic_topn_crash_guard",
    "dynamic_topn_deep_defense",
    "dynamic_topn_deep_reentry10",
    "dynamic_topn_deep_reentry10_cash10",
    "dynamic_topn_deep_reentry10_cash10_vol20",
]
EXPERIMENTAL_CANDIDATES = [
    "dynamic_topn_loose_guard",
    "dynamic_topn_fast_reentry",
    "dynamic_topn_deep_reentry10_cash5",
    "dynamic_topn_deep_reentry10_cash10_vol25",
    "dynamic_topn_deep_reentry10_cash10_vol20_flow45",
    "dynamic_topn_deep_reentry10_cash10_vol20_flow40",
    "dynamic_topn_deep_reentry10_cash10_vol20_breadth45",
    "dynamic_topn_deep_reentry10_cash10_vol20_breadth40",
    "dynamic_topn_deep_reentry15_cash15_crash45",
    "dynamic_topn_deep_reentry10_cash10_vol20_winner_room",
]
VALID_CANDIDATES = [*DEFAULT_CANDIDATES, *EXPERIMENTAL_CANDIDATES]
DEFAULT_WINDOWS = {
    "recent": (date(2024, 5, 16), date(2026, 5, 19)),
    "bear": (date(2021, 7, 1), date(2023, 1, 31)),
    "long": (date(2020, 7, 1), date(2026, 5, 18)),
}


@dataclass(frozen=True)
class ScenarioRow:
    window: str
    candidate: str
    start_date: date
    end_date: date
    result: BacktestResult
    sell_reasons: str


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    today = date.today().isoformat()
    parser = argparse.ArgumentParser(description="Run Sharpe-balanced strategy optimization candidates.")
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--windows", type=_parse_windows, default=list(DEFAULT_WINDOWS))
    parser.add_argument("--candidates", type=_parse_candidates, default=DEFAULT_CANDIDATES)
    parser.add_argument("--recent-start", type=_parse_date, default=DEFAULT_WINDOWS["recent"][0])
    parser.add_argument("--recent-end", type=_parse_date, default=DEFAULT_WINDOWS["recent"][1])
    parser.add_argument("--bear-start", type=_parse_date, default=DEFAULT_WINDOWS["bear"][0])
    parser.add_argument("--bear-end", type=_parse_date, default=DEFAULT_WINDOWS["bear"][1])
    parser.add_argument("--long-start", type=_parse_date, default=DEFAULT_WINDOWS["long"][0])
    parser.add_argument("--long-end", type=_parse_date, default=DEFAULT_WINDOWS["long"][1])
    parser.add_argument("--initial-capital", type=float, default=PORTFOLIO.initial_capital)
    parser.add_argument("--slippage-rate", type=float, default=COST.slippage_rate)
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=Path(f"data/strategy_optimization_{today}.csv"),
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        default=Path(f"data/strategy_optimization_{today}.md"),
    )
    args = parser.parse_args(argv)
    for name in ("recent", "bear", "long"):
        if getattr(args, f"{name}_start") > getattr(args, f"{name}_end"):
            parser.error(f"--{name}-start must be on or before --{name}-end")
    if args.initial_capital <= 0:
        parser.error("--initial-capital must be positive")
    if args.slippage_rate < 0:
        parser.error("--slippage-rate must be zero or greater")
    return args


def run(
    args: argparse.Namespace,
    *,
    base_backtest_func: BaseBacktestFunction = run_backtest,
    adaptive_backtest_func: AdaptiveBacktestFunction = run_adaptive_alpha_backtest,
    score_func_factory: ScoreFunctionFactory | None = None,
) -> int:
    engine = get_engine(args.database_url)
    create_tables(engine)
    if score_func_factory is None:
        score_func_factory = _default_score_func_factory
    windows = _selected_windows(args)
    rows: list[ScenarioRow] = []
    for window_name, (start_date, end_date) in windows.items():
        base_scoring_func = (
            score_func_factory(engine, start_date=start_date, end_date=end_date)
            if any(_is_base_candidate(candidate) for candidate in args.candidates)
            else None
        )
        for candidate in args.candidates:
            result = _run_candidate(
                engine,
                candidate=candidate,
                start_date=start_date,
                end_date=end_date,
                initial_capital=args.initial_capital,
                slippage_rate=args.slippage_rate,
                base_backtest_func=base_backtest_func,
                adaptive_backtest_func=adaptive_backtest_func,
                base_scoring_func=base_scoring_func,
            )
            rows.append(
                ScenarioRow(
                    window=window_name,
                    candidate=candidate,
                    start_date=start_date,
                    end_date=end_date,
                    result=result,
                    sell_reasons=_sell_reason_summary(result),
                )
            )

    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    args.output_csv.write_text(_format_csv(rows), encoding="utf-8")
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.write_text(
        _format_markdown(rows, quality_summary=_quality_summary(engine)),
        encoding="utf-8",
    )
    print(f"wrote_csv={args.output_csv}")
    print(f"wrote_md={args.output_md}")
    return 0


def _run_candidate(
    engine: object,
    *,
    candidate: str,
    start_date: date,
    end_date: date,
    initial_capital: float,
    slippage_rate: float,
    base_backtest_func: BaseBacktestFunction,
    adaptive_backtest_func: AdaptiveBacktestFunction,
    base_scoring_func: ScoreFunction | None = None,
) -> BacktestResult:
    common = {
        "start_date": start_date,
        "end_date": end_date,
        "initial_capital": initial_capital,
        "commission_rate": COST.commission_rate,
        "tax_rate_kospi": COST.tax_rate_kospi,
        "tax_rate_kosdaq": COST.tax_rate_kosdaq,
        "slippage_rate": slippage_rate,
    }
    if candidate == "current_top30":
        return base_backtest_func(
            engine,
            **common,
            **_scoring_kwargs(base_scoring_func),
            top_n=30,
            rebalance_frequency="weekly",
            enable_inverse_etf_hedge=False,
        )
    if candidate == "top15":
        return base_backtest_func(
            engine,
            **common,
            **_scoring_kwargs(base_scoring_func),
            top_n=15,
            rebalance_frequency="weekly",
            enable_inverse_etf_hedge=False,
        )
    if candidate == "top20":
        return base_backtest_func(
            engine,
            **common,
            **_scoring_kwargs(base_scoring_func),
            top_n=20,
            rebalance_frequency="weekly",
            enable_inverse_etf_hedge=False,
        )
    if candidate == "adaptive_alpha_tuned":
        return adaptive_backtest_func(
            engine,
            **common,
            config=DEFAULT_ADAPTIVE_ALPHA,
            enable_inverse_etf_hedge=False,
        )
    if candidate == "adaptive_alpha_v2":
        return adaptive_backtest_func(
            engine,
            **common,
            config=ADAPTIVE_ALPHA_V2,
            enable_inverse_etf_hedge=False,
        )
    if candidate == "inverse_hedge_conservative":
        return adaptive_backtest_func(
            engine,
            **common,
            config=ADAPTIVE_ALPHA_V2,
            enable_inverse_etf_hedge=True,
            inverse_etf_require_market_confirmation=True,
        )
    if candidate == "crash_guard_top30":
        return base_backtest_func(
            engine,
            **common,
            **_scoring_kwargs(base_scoring_func),
            top_n=30,
            rebalance_frequency="weekly",
            enable_crash_guard=True,
            crash_guard_moderate_cash_target=0.35,
            crash_guard_severe_cash_target=0.55,
            enable_inverse_etf_hedge=False,
        )
    if candidate == "crash_guard_inverse_top30":
        return base_backtest_func(
            engine,
            **common,
            **_scoring_kwargs(base_scoring_func),
            top_n=30,
            rebalance_frequency="weekly",
            enable_crash_guard=True,
            crash_guard_moderate_cash_target=0.35,
            crash_guard_severe_cash_target=0.55,
            enable_inverse_etf_hedge=True,
            inverse_etf_require_market_confirmation=True,
        )
    if candidate == "crash_guard_v2_reentry":
        return base_backtest_func(
            engine,
            **common,
            **_scoring_kwargs(base_scoring_func),
            top_n=30,
            rebalance_frequency="weekly",
            enable_crash_guard=True,
            crash_guard_moderate_cash_target=0.35,
            crash_guard_severe_cash_target=0.55,
            enable_crash_guard_reentry=True,
            crash_guard_reentry_cash_target=0.15,
            crash_guard_reentry_ma_days=20,
            crash_guard_reentry_rsi_window=14,
            crash_guard_reentry_rsi_threshold=45.0,
            crash_guard_reentry_positive_days=3,
            enable_inverse_etf_hedge=False,
        )
    if candidate == "dynamic_topn_crash_guard":
        return base_backtest_func(
            engine,
            **common,
            **_scoring_kwargs(base_scoring_func),
            top_n=30,
            rebalance_frequency="weekly",
            enable_crash_guard=True,
            crash_guard_moderate_cash_target=0.35,
            crash_guard_severe_cash_target=0.55,
            enable_crash_guard_reentry=True,
            crash_guard_reentry_cash_target=0.15,
            enable_dynamic_top_n=True,
            defensive_top_n=20,
            severe_defensive_top_n=15,
            enable_inverse_etf_hedge=False,
        )
    if candidate == "dynamic_topn_loose_guard":
        return base_backtest_func(
            engine,
            **common,
            **_scoring_kwargs(base_scoring_func),
            top_n=30,
            rebalance_frequency="weekly",
            enable_crash_guard=True,
            crash_guard_moderate_cash_target=0.30,
            crash_guard_severe_cash_target=0.45,
            enable_crash_guard_reentry=True,
            crash_guard_reentry_cash_target=0.10,
            enable_dynamic_top_n=True,
            defensive_top_n=22,
            severe_defensive_top_n=18,
            enable_inverse_etf_hedge=False,
        )
    if candidate == "dynamic_topn_fast_reentry":
        return base_backtest_func(
            engine,
            **common,
            **_scoring_kwargs(base_scoring_func),
            top_n=30,
            rebalance_frequency="weekly",
            enable_crash_guard=True,
            crash_guard_moderate_cash_target=0.35,
            crash_guard_severe_cash_target=0.55,
            enable_crash_guard_reentry=True,
            crash_guard_reentry_cash_target=0.05,
            crash_guard_reentry_rsi_threshold=40.0,
            crash_guard_reentry_positive_days=2,
            enable_dynamic_top_n=True,
            defensive_top_n=20,
            severe_defensive_top_n=15,
            enable_inverse_etf_hedge=False,
        )
    if candidate == "dynamic_topn_deep_reentry10":
        return base_backtest_func(
            engine,
            **common,
            **_scoring_kwargs(base_scoring_func),
            top_n=30,
            rebalance_frequency="weekly",
            enable_crash_guard=True,
            crash_guard_moderate_cash_target=0.40,
            crash_guard_severe_cash_target=0.60,
            enable_crash_guard_reentry=True,
            crash_guard_reentry_cash_target=0.10,
            enable_dynamic_top_n=True,
            defensive_top_n=18,
            severe_defensive_top_n=12,
            enable_inverse_etf_hedge=False,
        )
    if candidate == "dynamic_topn_deep_reentry10_cash5":
        return base_backtest_func(
            engine,
            **common,
            **_scoring_kwargs(base_scoring_func),
            top_n=30,
            rebalance_frequency="weekly",
            baseline_cash_target=0.05,
            enable_crash_guard=True,
            crash_guard_moderate_cash_target=0.40,
            crash_guard_severe_cash_target=0.60,
            enable_crash_guard_reentry=True,
            crash_guard_reentry_cash_target=0.10,
            enable_dynamic_top_n=True,
            defensive_top_n=18,
            severe_defensive_top_n=12,
            enable_inverse_etf_hedge=False,
        )
    if candidate == "dynamic_topn_deep_reentry10_cash10":
        return base_backtest_func(
            engine,
            **common,
            **_scoring_kwargs(base_scoring_func),
            top_n=30,
            rebalance_frequency="weekly",
            baseline_cash_target=0.10,
            enable_crash_guard=True,
            crash_guard_moderate_cash_target=0.40,
            crash_guard_severe_cash_target=0.60,
            enable_crash_guard_reentry=True,
            crash_guard_reentry_cash_target=0.10,
            enable_dynamic_top_n=True,
            defensive_top_n=18,
            severe_defensive_top_n=12,
            enable_inverse_etf_hedge=False,
        )
    if candidate == "dynamic_topn_deep_reentry10_cash10_vol20":
        return base_backtest_func(
            engine,
            **common,
            **_scoring_kwargs(base_scoring_func),
            top_n=30,
            rebalance_frequency="weekly",
            baseline_cash_target=0.10,
            enable_volatility_cash_overlay=True,
            volatility_cash_window=20,
            volatility_moderate_annualized=0.20,
            volatility_severe_annualized=0.30,
            volatility_moderate_cash_target=0.20,
            volatility_severe_cash_target=0.35,
            enable_crash_guard=True,
            crash_guard_moderate_cash_target=0.40,
            crash_guard_severe_cash_target=0.60,
            enable_crash_guard_reentry=True,
            crash_guard_reentry_cash_target=0.10,
            enable_dynamic_top_n=True,
            defensive_top_n=18,
            severe_defensive_top_n=12,
            enable_inverse_etf_hedge=False,
        )
    if candidate == "dynamic_topn_deep_reentry10_cash10_vol25":
        return base_backtest_func(
            engine,
            **common,
            **_scoring_kwargs(base_scoring_func),
            top_n=30,
            rebalance_frequency="weekly",
            baseline_cash_target=0.10,
            enable_volatility_cash_overlay=True,
            volatility_cash_window=20,
            volatility_moderate_annualized=0.25,
            volatility_severe_annualized=0.35,
            volatility_moderate_cash_target=0.20,
            volatility_severe_cash_target=0.35,
            enable_crash_guard=True,
            crash_guard_moderate_cash_target=0.40,
            crash_guard_severe_cash_target=0.60,
            enable_crash_guard_reentry=True,
            crash_guard_reentry_cash_target=0.10,
            enable_dynamic_top_n=True,
            defensive_top_n=18,
            severe_defensive_top_n=12,
            enable_inverse_etf_hedge=False,
        )
    if candidate == "dynamic_topn_deep_reentry10_cash10_vol20_flow45":
        return base_backtest_func(
            engine,
            **common,
            **_scoring_kwargs(base_scoring_func),
            top_n=30,
            rebalance_frequency="weekly",
            baseline_cash_target=0.10,
            enable_volatility_cash_overlay=True,
            volatility_cash_window=20,
            volatility_moderate_annualized=0.20,
            volatility_severe_annualized=0.30,
            volatility_moderate_cash_target=0.20,
            volatility_severe_cash_target=0.35,
            enable_flow_breadth_cash_overlay=True,
            flow_breadth_window=20,
            flow_breadth_moderate_threshold=0.45,
            flow_breadth_severe_threshold=0.40,
            flow_breadth_moderate_cash_target=0.20,
            flow_breadth_severe_cash_target=0.30,
            enable_crash_guard=True,
            crash_guard_moderate_cash_target=0.40,
            crash_guard_severe_cash_target=0.60,
            enable_crash_guard_reentry=True,
            crash_guard_reentry_cash_target=0.10,
            enable_dynamic_top_n=True,
            defensive_top_n=18,
            severe_defensive_top_n=12,
            enable_inverse_etf_hedge=False,
        )
    if candidate == "dynamic_topn_deep_reentry10_cash10_vol20_flow40":
        return base_backtest_func(
            engine,
            **common,
            **_scoring_kwargs(base_scoring_func),
            top_n=30,
            rebalance_frequency="weekly",
            baseline_cash_target=0.10,
            enable_volatility_cash_overlay=True,
            volatility_cash_window=20,
            volatility_moderate_annualized=0.20,
            volatility_severe_annualized=0.30,
            volatility_moderate_cash_target=0.20,
            volatility_severe_cash_target=0.35,
            enable_flow_breadth_cash_overlay=True,
            flow_breadth_window=20,
            flow_breadth_moderate_threshold=0.40,
            flow_breadth_severe_threshold=0.35,
            flow_breadth_moderate_cash_target=0.20,
            flow_breadth_severe_cash_target=0.30,
            enable_crash_guard=True,
            crash_guard_moderate_cash_target=0.40,
            crash_guard_severe_cash_target=0.60,
            enable_crash_guard_reentry=True,
            crash_guard_reentry_cash_target=0.10,
            enable_dynamic_top_n=True,
            defensive_top_n=18,
            severe_defensive_top_n=12,
            enable_inverse_etf_hedge=False,
        )
    if candidate == "dynamic_topn_deep_reentry10_cash10_vol20_breadth45":
        return base_backtest_func(
            engine,
            **common,
            **_scoring_kwargs(base_scoring_func),
            top_n=30,
            rebalance_frequency="weekly",
            baseline_cash_target=0.10,
            enable_volatility_cash_overlay=True,
            volatility_cash_window=20,
            volatility_moderate_annualized=0.20,
            volatility_severe_annualized=0.30,
            volatility_moderate_cash_target=0.20,
            volatility_severe_cash_target=0.35,
            enable_price_breadth_cash_overlay=True,
            price_breadth_ma_days=60,
            price_breadth_min_count=50,
            price_breadth_moderate_threshold=0.45,
            price_breadth_severe_threshold=0.35,
            price_breadth_moderate_cash_target=0.20,
            price_breadth_severe_cash_target=0.35,
            enable_crash_guard=True,
            crash_guard_moderate_cash_target=0.40,
            crash_guard_severe_cash_target=0.60,
            enable_crash_guard_reentry=True,
            crash_guard_reentry_cash_target=0.10,
            enable_dynamic_top_n=True,
            defensive_top_n=18,
            severe_defensive_top_n=12,
            enable_inverse_etf_hedge=False,
        )
    if candidate == "dynamic_topn_deep_reentry10_cash10_vol20_breadth40":
        return base_backtest_func(
            engine,
            **common,
            **_scoring_kwargs(base_scoring_func),
            top_n=30,
            rebalance_frequency="weekly",
            baseline_cash_target=0.10,
            enable_volatility_cash_overlay=True,
            volatility_cash_window=20,
            volatility_moderate_annualized=0.20,
            volatility_severe_annualized=0.30,
            volatility_moderate_cash_target=0.20,
            volatility_severe_cash_target=0.35,
            enable_price_breadth_cash_overlay=True,
            price_breadth_ma_days=60,
            price_breadth_min_count=50,
            price_breadth_moderate_threshold=0.40,
            price_breadth_severe_threshold=0.30,
            price_breadth_moderate_cash_target=0.20,
            price_breadth_severe_cash_target=0.35,
            enable_crash_guard=True,
            crash_guard_moderate_cash_target=0.40,
            crash_guard_severe_cash_target=0.60,
            enable_crash_guard_reentry=True,
            crash_guard_reentry_cash_target=0.10,
            enable_dynamic_top_n=True,
            defensive_top_n=18,
            severe_defensive_top_n=12,
            enable_inverse_etf_hedge=False,
        )
    if candidate == "dynamic_topn_deep_reentry15_cash15_crash45":
        return base_backtest_func(
            engine,
            **common,
            **_scoring_kwargs(base_scoring_func),
            top_n=30,
            rebalance_frequency="weekly",
            baseline_cash_target=0.15,
            enable_volatility_cash_overlay=True,
            volatility_cash_window=20,
            volatility_moderate_annualized=0.20,
            volatility_severe_annualized=0.30,
            volatility_moderate_cash_target=0.20,
            volatility_severe_cash_target=0.35,
            enable_crash_guard=True,
            crash_guard_moderate_cash_target=0.45,
            crash_guard_severe_cash_target=0.65,
            enable_crash_guard_reentry=True,
            crash_guard_reentry_cash_target=0.15,
            enable_dynamic_top_n=True,
            defensive_top_n=18,
            severe_defensive_top_n=12,
            enable_inverse_etf_hedge=False,
        )
    if candidate == "dynamic_topn_deep_reentry10_cash10_vol20_winner_room":
        return base_backtest_func(
            engine,
            **common,
            **_scoring_kwargs(base_scoring_func),
            top_n=30,
            rebalance_frequency="weekly",
            baseline_cash_target=0.10,
            enable_volatility_cash_overlay=True,
            volatility_cash_window=20,
            volatility_moderate_annualized=0.20,
            volatility_severe_annualized=0.30,
            volatility_moderate_cash_target=0.20,
            volatility_severe_cash_target=0.35,
            profit_take_sell_fraction=0.45,
            post_profit_trailing_stop_pct=-0.10,
            breakeven_stop_pct=-0.03,
            enable_crash_guard=True,
            crash_guard_moderate_cash_target=0.40,
            crash_guard_severe_cash_target=0.60,
            enable_crash_guard_reentry=True,
            crash_guard_reentry_cash_target=0.10,
            enable_dynamic_top_n=True,
            defensive_top_n=18,
            severe_defensive_top_n=12,
            enable_inverse_etf_hedge=False,
        )
    if candidate == "dynamic_topn_deep_defense":
        return base_backtest_func(
            engine,
            **common,
            **_scoring_kwargs(base_scoring_func),
            top_n=30,
            rebalance_frequency="weekly",
            enable_crash_guard=True,
            crash_guard_moderate_cash_target=0.40,
            crash_guard_severe_cash_target=0.60,
            enable_crash_guard_reentry=True,
            crash_guard_reentry_cash_target=0.20,
            enable_dynamic_top_n=True,
            defensive_top_n=18,
            severe_defensive_top_n=12,
            enable_inverse_etf_hedge=False,
        )
    raise ValueError(f"Unknown candidate: {candidate}")


def _default_score_func_factory(
    engine: object,
    *,
    start_date: date,
    end_date: date,
) -> ScoreFunction:
    return _make_fast_score_func(
        engine,
        lookback_days=FACTOR.momentum_lookback_days,
        start_date=start_date,
        end_date=end_date,
    )


def _is_base_candidate(candidate: str) -> bool:
    return candidate in {
        "current_top30",
        "top15",
        "top20",
        "crash_guard_top30",
        "crash_guard_inverse_top30",
        "crash_guard_v2_reentry",
        "dynamic_topn_crash_guard",
        "dynamic_topn_loose_guard",
        "dynamic_topn_fast_reentry",
        "dynamic_topn_deep_reentry10",
        "dynamic_topn_deep_reentry10_cash5",
        "dynamic_topn_deep_reentry10_cash10",
        "dynamic_topn_deep_reentry10_cash10_vol20",
        "dynamic_topn_deep_reentry10_cash10_vol25",
        "dynamic_topn_deep_reentry10_cash10_vol20_flow45",
        "dynamic_topn_deep_reentry10_cash10_vol20_flow40",
        "dynamic_topn_deep_reentry10_cash10_vol20_breadth45",
        "dynamic_topn_deep_reentry10_cash10_vol20_breadth40",
        "dynamic_topn_deep_reentry15_cash15_crash45",
        "dynamic_topn_deep_reentry10_cash10_vol20_winner_room",
        "dynamic_topn_deep_defense",
    }


def _scoring_kwargs(scoring_func: ScoreFunction | None) -> dict[str, ScoreFunction]:
    return {"scoring_func": scoring_func} if scoring_func is not None else {}


def _selected_windows(args: argparse.Namespace) -> dict[str, tuple[date, date]]:
    return {
        name: (getattr(args, f"{name}_start"), getattr(args, f"{name}_end"))
        for name in args.windows
    }


def _quality_summary(engine: object) -> str:
    with session_scope(engine) as session:
        rows = session.execute(
            select(
                QualityMetric.fiscal_year,
                func.count(QualityMetric.id),
                func.min(QualityMetric.published_at),
                func.max(QualityMetric.published_at),
            )
            .group_by(QualityMetric.fiscal_year)
            .order_by(QualityMetric.fiscal_year)
        ).all()
    if not rows:
        return "No quality_metrics rows found."
    return "; ".join(
        f"{year}: count={count}, published_at={min_date}..{max_date}"
        for year, count, min_date, max_date in rows
    )


def _sell_reason_summary(result: BacktestResult) -> str:
    counts = Counter(trade.reason for trade in result.trades if trade.side == "SELL")
    return ";".join(f"{reason}:{count}" for reason, count in sorted(counts.items()))


def _format_csv(rows: list[ScenarioRow]) -> str:
    header = (
        "window,candidate,start_date,end_date,final_equity,total_return,cagr,"
        "max_drawdown,sharpe_ratio,win_rate,average_holding_days,trade_count,sell_reasons"
    )
    lines = [header]
    for row in rows:
        result = row.result
        lines.append(
            ",".join(
                [
                    row.window,
                    row.candidate,
                    row.start_date.isoformat(),
                    row.end_date.isoformat(),
                    f"{result.final_equity:.2f}",
                    f"{result.total_return:.2%}",
                    f"{result.cagr:.2%}",
                    f"{result.max_drawdown:.2%}",
                    f"{result.sharpe_ratio:.4f}",
                    f"{result.win_rate:.2%}",
                    f"{result.average_holding_days:.2f}",
                    str(len(result.trades)),
                    row.sell_reasons,
                ]
            )
        )
    return "\n".join(lines) + "\n"


def _format_markdown(rows: list[ScenarioRow], *, quality_summary: str) -> str:
    lines = [
        "# Strategy Optimization Report",
        "",
        f"Quality metrics: {quality_summary}",
        "",
    ]
    if rows:
        best = max(rows, key=lambda row: row.result.sharpe_ratio)
        best_return = max(rows, key=lambda row: row.result.total_return)
        best_mdd = max(rows, key=lambda row: row.result.max_drawdown)
        lines.extend(
            [
                f"Best by Sharpe: {best.window}/{best.candidate} ({best.result.sharpe_ratio:.4f})",
                f"Best by Return: {best_return.window}/{best_return.candidate} ({best_return.result.total_return:.2%})",
                f"Lowest MDD: {best_mdd.window}/{best_mdd.candidate} ({best_mdd.result.max_drawdown:.2%})",
                "",
            ]
        )
    lines.extend(
        [
            "| Window | Candidate | Return | MDD | Sharpe | Trades | Sell reasons |",
            "| --- | --- | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for row in rows:
        result = row.result
        lines.append(
            f"| {row.window} | {row.candidate} | {result.total_return:.2%} | "
            f"{result.max_drawdown:.2%} | {result.sharpe_ratio:.4f} | "
            f"{len(result.trades)} | {row.sell_reasons or '-'} |"
        )
    return "\n".join(lines) + "\n"


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def _parse_windows(value: str) -> list[str]:
    values = [item.strip() for item in value.split(",") if item.strip()]
    invalid = sorted(set(values) - set(DEFAULT_WINDOWS))
    if not values or invalid:
        raise argparse.ArgumentTypeError("must contain only recent, bear, or long")
    return values


def _parse_candidates(value: str) -> list[str]:
    values = [item.strip() for item in value.split(",") if item.strip()]
    invalid = sorted(set(values) - set(VALID_CANDIDATES))
    if not values or invalid:
        raise argparse.ArgumentTypeError(f"unknown candidates: {', '.join(invalid)}")
    return values


def main(argv: Sequence[str] | None = None) -> int:
    return run(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
