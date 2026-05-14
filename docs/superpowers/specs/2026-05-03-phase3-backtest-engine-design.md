# Phase 3 Backtest Engine Design

## Goal

Build a simple project-native backtest engine that simulates the current factor-ranking strategy before any KIS order integration is implemented.

## Scope

Phase 3 runs historical portfolio simulation. It does not connect to KIS, place real or paper orders, monitor live stop-loss/trailing-stop conditions, send Telegram messages, or render a dashboard.

## Strategy Model

The first backtest version uses daily regular rebalancing:

- On each available trading date, calculate factor scores using the Phase 2 engine.
- Select the top `N` ranked stocks, defaulting to `PORTFOLIO.n_holdings`.
- Target equal-weight holdings across selected stocks.
- Rebalance from current holdings into the target list.

This intentionally keeps the first simulation understandable. Stop-loss and trailing-stop simulation will be added after the regular rebalancing baseline is working.

## Cost Model

Costs use `config.COST`:

- Buy trades include commission and slippage.
- Sell trades include commission, transaction tax, and slippage.
- KOSPI and KOSDAQ tax rates are selected from the stock market field when available.

The current config still uses 0.18% transaction tax. That value is not changed in Phase 3 because project rules require parameter changes to be backed by actual source data or logs.

## Architecture

- `src/backtest/models.py`: immutable result objects for trades, equity curve points, and summary results.
- `src/backtest/metrics.py`: CAGR, MDD, Sharpe, win rate, and average holding days calculations.
- `src/backtest/engine.py`: SQLite-backed portfolio simulation.
- `scripts/run_phase3_backtest.py`: manual CLI to print a summary.

## Data Requirements

The engine needs:

- `daily_prices.close` for each traded ticker and date.
- `stocks.market` to choose the sell tax rate.
- Phase 2 factor scores or an injected scoring function for tests.

Tests use deterministic temporary SQLite data and injected score functions, so they do not require external market API calls.

## Visible Success Criteria

- The engine can buy top-ranked stocks and rebalance when rankings change.
- Trading costs reduce final equity.
- Metrics report total return, CAGR, MDD, Sharpe, win rate, and average holding days.
- A script can print the summary without placing orders.
