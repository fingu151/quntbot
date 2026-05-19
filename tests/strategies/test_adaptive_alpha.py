from datetime import date, timedelta

from src.backtest.models import BacktestResult
from src.data.database import create_tables, get_engine, session_scope
from src.data.repositories import upsert_daily_prices
from src.factors.models import FactorScore
from src.strategies.adaptive_alpha import (
    AdaptiveAlphaConfig,
    calculate_adaptive_alpha_scores,
    run_adaptive_alpha_backtest,
)


def _score(ticker: str, total_score: float) -> FactorScore:
    return FactorScore(
        ticker=ticker,
        name=ticker,
        market="KOSPI",
        as_of_date=date(2026, 5, 1),
        value_score=total_score,
        quality_score=total_score,
        momentum_score=total_score,
        yield_score=0.0,
        telegram_score=0.0,
        total_score=total_score,
        rank=1,
    )


def _seed_prices(engine, ticker: str, closes: list[float]) -> None:
    start = date(2026, 1, 1)
    rows = []
    for index, close in enumerate(closes):
        price_date = start + timedelta(days=index)
        rows.append(
            {
                "ticker": ticker,
                "date": price_date,
                "open": close,
                "high": close * 1.01,
                "low": close * 0.99,
                "close": close,
                "volume": 1000,
            }
        )
    with session_scope(engine) as session:
        upsert_daily_prices(session, rows)


def test_adaptive_alpha_reorders_base_scores_by_trend_quality():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    _seed_prices(engine, "STRONG", [100 + index for index in range(80)])
    _seed_prices(engine, "WEAK", [180 - index for index in range(80)])

    def base_scorer(engine, *, as_of_date):
        return [_score("WEAK", 80), _score("STRONG", 78)]

    scores = calculate_adaptive_alpha_scores(
        engine,
        as_of_date=date(2026, 3, 21),
        base_scorer=base_scorer,
        config=AdaptiveAlphaConfig(
            technical_weight=0.45,
            volatility_penalty_weight=0.20,
        ),
    )

    assert [score.ticker for score in scores] == ["STRONG", "WEAK"]
    assert scores[0].rank == 1
    assert scores[0].total_score > scores[1].total_score


def test_run_adaptive_alpha_backtest_passes_isolated_strategy_defaults():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    captured = {}

    def fake_run_backtest(engine, **kwargs):
        captured.update(kwargs)
        return BacktestResult(
            initial_capital=100,
            final_equity=110,
            total_return=0.10,
            cagr=0.10,
            max_drawdown=-0.03,
            sharpe_ratio=1.0,
            win_rate=0.5,
            average_holding_days=5.0,
            trades=[],
            equity_curve=[],
        )

    result = run_adaptive_alpha_backtest(
        engine,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 2, 1),
        run_backtest_func=fake_run_backtest,
    )

    assert result.final_equity == 110
    assert captured["top_n"] == 30
    assert captured["stop_loss_pct"] == -0.07
    assert captured["trailing_stop_pct"] == -0.08
    assert captured["stop_cooldown_days"] == 3
    assert captured["enable_atr_stop"] is True
    assert captured["atr_multiplier"] == 2.2
    assert captured["profit_take_pct"] == 0.18
    assert captured["sell_rank_buffer"] == 45
    assert captured["enable_market_risk_overlay"] is True
    assert callable(captured["scoring_func"])
