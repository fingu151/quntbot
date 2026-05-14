# Phase 3 Stops Simulation Design

Date: 2026-05-06

## Goal

Backtests should reflect the operating sell rules:

- Stop-loss when the close is at or below the entry price threshold.
- Trailing-stop when the close is at or below the peak price threshold.
- Regular rebalance exits remain supported.

## Decision

The backtest uses daily OHLC data only, so stop checks are split into trigger and execution:

1. A stop is triggered from the current trading day's close.
2. The triggered position is sold at the next trading day's open.
3. If the trigger happens on the last available trading day, the position is sold at the same day's close with a `_close_fallback` reason.

This matches the current operating assumption: the bot observes end-of-day signals and sends the next available market order.

## State Tracked

`run_backtest` tracks two additional position dictionaries:

- `entry_prices`: average entry price including buy commission and slippage.
- `peak_prices`: highest close observed while the position is held.

Pending stops are stored as `(ticker, reason)` pairs until the next trading day.

## Reason Priority

If both stop-loss and trailing-stop conditions trigger for the same ticker on the same close, `stop_loss` wins. Stop-loss protects capital from the entry price, while trailing-stop protects profit from the peak.

## Same-Day Reentry

If a pending stop is executed at today's open, that ticker is excluded from today's rebalance buys. There is no multi-day cooldown in this implementation.

## Toggle

`run_backtest(enable_stops=False)` preserves the old rebalance-only behavior for comparison. The CLI exposes:

- `--enable-stops` (default)
- `--disable-stops`

## Future Intraday Upgrade

If minute data becomes available, replace the close-trigger/next-open approximation with intraday threshold detection. At that point, stop execution price should be derived from the first threshold-crossing bar, with a documented slippage model.

