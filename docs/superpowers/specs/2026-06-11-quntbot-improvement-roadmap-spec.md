# Quntbot Improvement Roadmap Spec

## Phase 1: Telegram Signal Score Removal

- Delete MTProto Telegram signal parser, reader, smoke script, scheduler job, repository functions, and tests.
- Remove `telegram_score` from `FactorScore`, reports, snapshots, and rank output.
- Keep Telegram notification config and notifier behavior intact.
- Do not drop old production DB tables; only stop creating them in new DB schemas.

Acceptance:
- No runtime code imports `TelegramSignal`, `TELEGRAM_SIGNAL`, or `telegram_score`.
- New SQLite schemas include no `telegram_signals` table.
- Telegram notifier tests still import and pass.

## Phase 2: 100-Point Factor Budget

- `FactorConfig` exposes point budgets that must sum to exactly 100.
- `FactorScore` stores value, quality, momentum, yield, technical, auxiliary, and total score.
- Missing scoring factors contribute zero unless they are required common-stock fundamentals.
- Auxiliary score is split across Busanstock, investor flow, and research report signals.

Acceptance:
- `total_score` stays in 0..100.
- Factor contributions sum to `total_score` after clipping.
- Rank scripts and public snapshots expose score breakdowns without Telegram fields.

## Phase 3: Technical Scoring

- `technical_hard_filter()` blocks only extreme overheat or volatility.
- `technical_score()` contributes up to 15 points using trend, RSI, volatility, and volume checks.
- Live and backtest scoring both use the same factor engine helpers.

Acceptance:
- Weak but non-extreme candidates remain rankable with low technical points.
- Extreme technical risk is still excluded.
- Backtest scorer keeps producing candidates for normal steady trends.

## Phase 4: ETF Support

- Add `instrument_type` to `Stock` with `COMMON_STOCK` default and `ETF` support.
- Collect ETF universe rows through pykrx ETF APIs.
- Bypass common-stock fundamentals and DART quality metrics for ETFs.
- Use zero transaction tax for ETF backtest sells.
- Preserve dry-run, readiness, preflight, and PAPER-first execution gates.

Acceptance:
- ETF universe rows can be collected and persisted.
- ETF backtest sell cost excludes transaction tax.
- Existing trading scheduler no longer depends on Telegram signal polling.
