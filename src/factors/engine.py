from __future__ import annotations

from datetime import date

import pandas as pd
from sqlalchemy import Engine, select

from config import FACTOR
from src.data.database import session_scope
from src.data.models import DailyPrice, Fundamental, Stock
from src.factors.models import FactorScore
from src.factors.scoring import combine_scores, score_series


def calculate_factor_scores(
    engine: Engine,
    *,
    as_of_date: date,
    lookback_days: int | None = None,
) -> list[FactorScore]:
    lookback_days = lookback_days or FACTOR.momentum_lookback_days
    raw = _load_factor_inputs(engine, as_of_date=as_of_date, lookback_days=lookback_days)
    if raw.empty:
        return []

    raw["per_score"] = score_series(
        raw["per"],
        higher_is_better=False,
        method=FACTOR.scoring_method,
        require_positive=True,
    )
    raw["pbr_score"] = score_series(
        raw["pbr"],
        higher_is_better=False,
        method=FACTOR.scoring_method,
        require_positive=True,
    )
    raw["value_score"] = raw[["per_score", "pbr_score"]].mean(axis=1)
    raw["quality_score"] = 0.0
    raw["momentum_score"] = score_series(
        raw["momentum_return"],
        higher_is_better=True,
        method=FACTOR.scoring_method,
    )
    raw["total_score"] = combine_scores(
        raw,
        weights={
            "value_score": FACTOR.value_weight,
            "quality_score": FACTOR.quality_weight,
            "momentum_score": FACTOR.momentum_weight,
        },
    )
    ranked = raw.dropna(subset=["value_score", "momentum_score", "total_score"]).sort_values(
        ["total_score", "ticker"],
        ascending=[False, True],
    )

    results: list[FactorScore] = []
    for rank, (_, row) in enumerate(ranked.iterrows(), start=1):
        results.append(
            FactorScore(
                ticker=row["ticker"],
                name=row["name"],
                market=row["market"],
                as_of_date=as_of_date,
                value_score=float(row["value_score"]),
                quality_score=float(row["quality_score"]),
                momentum_score=float(row["momentum_score"]),
                total_score=float(row["total_score"]),
                rank=rank,
            )
        )
    return results


def _load_factor_inputs(engine: Engine, *, as_of_date: date, lookback_days: int) -> pd.DataFrame:
    with session_scope(engine) as session:
        stocks = session.scalars(select(Stock).where(Stock.is_active.is_(True))).all()
        rows = []
        for stock in stocks:
            prices = session.scalars(
                select(DailyPrice)
                .where(DailyPrice.ticker == stock.ticker, DailyPrice.date <= as_of_date)
                .order_by(DailyPrice.date.asc())
            ).all()
            if len(prices) <= lookback_days:
                continue

            current_price = prices[-1]
            lookback_price = prices[-(lookback_days + 1)]
            if not current_price.close or not lookback_price.close:
                continue

            fundamental = session.scalars(
                select(Fundamental)
                .where(Fundamental.ticker == stock.ticker, Fundamental.date <= as_of_date)
                .order_by(Fundamental.date.desc())
            ).first()
            if fundamental is None:
                continue

            rows.append(
                {
                    "ticker": stock.ticker,
                    "name": stock.name,
                    "market": stock.market,
                    "per": fundamental.per,
                    "pbr": fundamental.pbr,
                    "momentum_return": (current_price.close / lookback_price.close) - 1.0,
                }
            )
    return pd.DataFrame(rows)
