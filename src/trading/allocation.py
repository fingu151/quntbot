from __future__ import annotations

from collections.abc import Iterable


def compute_score_weights(
    scores: Iterable[tuple[str, float]],
    *,
    min_weight: float,
    max_weight: float,
) -> dict[str, float]:
    items = [(ticker, float(score)) for ticker, score in scores]
    if not items:
        return {}
    if min_weight <= 0:
        raise ValueError("min_weight must be positive")
    if max_weight <= 0 or max_weight < min_weight:
        raise ValueError("max_weight must be >= min_weight and positive")
    if min_weight * len(items) > 1.0:
        raise ValueError("min_weight is too high for the number of scores")
    if max_weight * len(items) < 1.0:
        return {ticker: round(max_weight, 12) for ticker, _ in items}

    min_score = min(score for _, score in items)
    raw = {ticker: max(score - min_score, 0.0) + 1.0 for ticker, score in items}
    total_raw = sum(raw.values())
    weights = {ticker: value / total_raw for ticker, value in raw.items()}

    clamped: dict[str, float] = {}
    flexible = set(weights)
    remaining = 1.0

    while flexible:
        changed = False
        flexible_total = sum(weights[ticker] for ticker in flexible)
        if flexible_total <= 0:
            share = remaining / len(flexible)
            proposed = {ticker: share for ticker in flexible}
        else:
            proposed = {
                ticker: remaining * (weights[ticker] / flexible_total)
                for ticker in flexible
            }

        for ticker, weight in list(proposed.items()):
            if weight < min_weight:
                clamped[ticker] = min_weight
                remaining -= min_weight
                flexible.remove(ticker)
                changed = True
            elif weight > max_weight:
                clamped[ticker] = max_weight
                remaining -= max_weight
                flexible.remove(ticker)
                changed = True

        if not changed:
            clamped.update(proposed)
            flexible.clear()

        if remaining <= 0:
            break

    return {ticker: round(weight, 12) for ticker, weight in clamped.items() if weight > 0}
