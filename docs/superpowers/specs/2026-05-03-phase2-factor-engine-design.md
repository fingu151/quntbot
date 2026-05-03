# Phase 2 Factor Engine Design

## Goal

Build a factor scoring engine that reads Phase 1 SQLite data and ranks candidate stocks for later rebalancing and trading phases.

## Scope

Phase 2 calculates and displays scores. It does not run backtests, rebalance portfolios, place KIS orders, monitor stops, or send Telegram alerts.

## Available Inputs

Phase 1 currently stores:

- Stock universe: ticker, name, market, active flag.
- Daily prices: open, high, low, close, volume, trading value, market cap.
- Fundamentals from pykrx: BPS, PER, PBR, EPS, DIV, DPS.

ROE, operating margin, and debt ratio are not available yet. Phase 2 keeps a `quality_score` field, but uses a neutral score until those metrics are added by a future financial statement data source.

## Scoring Rules

Value score:

- Uses PER and PBR.
- Lower PER is better.
- Lower PBR is better.
- Non-positive PER/PBR values are treated as missing because they usually represent loss-making or unusable valuation data.

Momentum score:

- Uses close-to-close return over `FACTOR.momentum_lookback_days` stored trading rows.
- A ticker needs both a current close and a lookback close.
- Higher return is better.

Quality score:

- Neutral score of `0.0` for Phase 2.
- The output model includes the field so the later ROE/operating-margin/debt-ratio implementation can plug in without changing callers.

Total score:

- `value_score * value_weight + quality_score * quality_weight + momentum_score * momentum_weight`.
- Weights come from `config.FACTOR`.
- Default scoring method is `zscore`, matching the existing configuration.

## Architecture

- `src/factors/models.py`: dataclass result model for factor scores.
- `src/factors/scoring.py`: reusable z-score/rank score utilities.
- `src/factors/engine.py`: DB loading, factor calculation, final ranking.
- `scripts/rank_phase2_factors.py`: manual CLI to print top-ranked candidates.

## Testing

Tests use temporary SQLite databases populated with small deterministic rows.

The visible success criteria are:

- Low PER/PBR receives a better value score.
- Higher 6-month-style return receives a better momentum score.
- Total scores rank candidates in descending order.
- The script can print top candidates without placing orders.
