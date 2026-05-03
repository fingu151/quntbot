from __future__ import annotations

from typing import Literal

import pandas as pd


ScoringMethod = Literal["zscore", "rank"]


def score_series(
    values: pd.Series,
    *,
    higher_is_better: bool,
    method: ScoringMethod = "zscore",
    require_positive: bool = False,
) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce").astype(float)
    if require_positive:
        numeric = numeric.where(numeric > 0)

    oriented = numeric if higher_is_better else -numeric
    if method == "zscore":
        return _zscore(oriented)
    if method == "rank":
        return oriented.rank(pct=True)
    raise ValueError(f"Unsupported scoring method: {method}")


def combine_scores(frame: pd.DataFrame, *, weights: dict[str, float]) -> pd.Series:
    total = pd.Series(0.0, index=frame.index)
    for column, weight in weights.items():
        if column not in frame:
            continue
        total = total.add(frame[column].fillna(0.0) * weight, fill_value=0.0)
    return total


def _zscore(values: pd.Series) -> pd.Series:
    valid = values.dropna()
    if valid.empty:
        return pd.Series(float("nan"), index=values.index)
    std = valid.std(ddof=0)
    if std == 0:
        return values.where(values.isna(), 0.0)
    return (values - valid.mean()) / std
