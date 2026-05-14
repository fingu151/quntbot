# Phase 2 Quality Score Implementation

## Goal

Use stored DART quality metrics for the Phase 2 `quality_score` instead of deriving a temporary ROE proxy from `EPS / BPS`.

## Inputs

`quality_metrics` stores one row per ticker/fiscal period:

- `roe`: already TTM net income divided by average equity.
- `operating_margin`: already TTM operating income divided by TTM revenue.
- `debt_ratio`: latest liabilities divided by latest equity.
- `published_at`: DART report publication date when available.

## As-Of Policy

For a ranking `as_of_date`, use the latest quality row whose data was knowable at that date.

- If `published_at` is set, the row is available when `published_at <= as_of_date`.
- If `published_at` is null, use a conservative availability date of fiscal quarter end plus 45 calendar days.
- Among available rows, pick the highest `(fiscal_year, fiscal_quarter)`.

## Scoring

Score the three quality components independently:

- ROE: higher is better.
- Operating margin: higher is better.
- Debt ratio: lower is better.

Then calculate:

```text
quality_score = mean(roe_score, operating_margin_score, debt_score)
```

`pandas.mean(axis=1)` skips missing component scores, so partial quality data is still usable.

## Missing Data Policy

Keep the existing `combine_scores` behavior: missing optional components are neutralized to `0.0` in total score.

This means:

- If all three quality metrics are missing, `quality_score` is reported as `0.0`.
- Value and momentum can still rank the ticker.
- Coverage is logged so the user can see when DART data is sparse.

## Backtest Consistency

The optimized backtest scorer must load and apply the same latest-available quality rows. Otherwise live ranking and backtest ranking can diverge.
