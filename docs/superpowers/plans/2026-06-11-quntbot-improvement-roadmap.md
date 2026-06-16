# Quntbot Improvement Roadmap

## Classification

- Request type: heavy / multi-phase feature roadmap
- Lead: Strategy and Factor Agent
- Support: Signal, Data and DB, Backtest, Trading Safety, Operations, Test and Verification
- Safety stance: PAPER and no-order dry runs remain ahead of every order-adjacent path

## Phase Structure

1. Remove MTProto Telegram stock-signal scoring.
2. Replace implicit factor weights with an explicit 100-point score budget.
3. Move technical analysis from broad exclusion to hard-filter plus score contribution.
4. Add ETF instrument support for universe rows, scoring, backtest cost branching, and dry-run visibility.
5. Run regression verification and update operations documentation.

## Scope Decisions

- Keep `TelegramConfig`, `TELEGRAM`, `src/notify/notifier.py`, and order/risk notification tests.
- Remove `TelegramSignalConfig`, `TELEGRAM_SIGNAL`, `telegram_score`, MTProto Telegram parser/reader/smoke paths, scheduler polling, and rank/snapshot output fields.
- Leave existing database `telegram_signals` tables orphaned in old DB files. New database creation no longer creates that table.
- Start the 100-point budget with Value 25, Quality 25, Momentum 20, Yield 5, Technical 15, Auxiliary 10.
- Auxiliary score includes Busanstock, investor flow, and research report signals.
- Treat ETFs as a distinct instrument type. Do not apply PER/PBR/DART quality scoring to ETFs.

## Verification Gates

- Phase 1: factor/backtest/trading/notify tests and compile check.
- Phase 2: score sum and 0..100 contract tests, rank/snapshot score breakdown checks.
- Phase 3: technical score tests and live/backtest scorer consistency coverage.
- Phase 4: ETF universe collection test, ETF backtest tax branch test, dry-run target/order visibility.
- Final: full `pytest`, compileall, and no-order readiness check before any PAPER execution.
