from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class FactorScore:
    ticker: str
    name: str
    market: str
    as_of_date: date
    value_score: float
    quality_score: float
    momentum_score: float
    total_score: float
    rank: int
