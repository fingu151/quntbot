# Phase 1 Data Pipeline Design

## Goal

Build the first usable data pipeline for quntbot: store the stock universe, daily OHLCV prices, and available fundamental metrics in SQLite so later phases can calculate factors and run backtests.

## Scope

Phase 1 covers data storage and repeatable collection. It does not calculate factor scores, rebalance portfolios, place orders, send Telegram alerts, or build the dashboard.

## Data Sources

The primary provider is `pykrx`.

- Universe: KOSPI200 and KOSDAQ150 index constituents through `stock.get_index_portfolio_deposit_file`.
- Stock names: `stock.get_market_ticker_name`.
- Daily prices: `stock.get_market_ohlcv_by_date`.
- Fundamentals available from pykrx: `stock.get_market_fundamental_by_date`, including BPS, PER, PBR, EPS, DIV, and DPS.

ROE, operating margin, and debt ratio are intentionally not implemented in Phase 1 because they are not exposed by the confirmed pykrx functions above. Those quality metrics will be added in a later data-source design, likely using DART or another financial statement source.

## Architecture

The data layer is split into four small modules.

- `src/data/models.py`: SQLAlchemy table definitions.
- `src/data/database.py`: engine/session helpers and table creation.
- `src/data/repositories.py`: idempotent inserts and updates.
- `src/data/collectors.py`: provider interfaces and pykrx-backed collection flow.

The script `scripts/sync_phase1_data.py` runs the collector and prints row counts so the user can verify the result by sight.

## Tables

`stocks`

- `ticker`: primary key.
- `name`: stock name.
- `market`: index bucket used by this project, either `KOSPI200` or `KOSDAQ150`.
- `is_active`: active universe membership flag.
- `updated_at`: UTC timestamp.

`daily_prices`

- Unique key: `ticker`, `date`.
- Stores open, high, low, close, volume, trading value, and market cap when available.

`fundamentals`

- Unique key: `ticker`, `date`.
- Stores BPS, PER, PBR, EPS, DIV, and DPS when available.

`sync_runs`

- Records each synchronization attempt, status, counts, and error message.

## Error Handling

Provider calls are kept outside the repository layer. The collector records a failed sync run if a provider call raises. Repository operations are idempotent, so the same date range can be re-run safely.

## Testing

Tests use SQLite temporary databases and fake providers. Default tests do not hit pykrx or the network.

The first visible success criteria are:

- Tables can be created.
- Duplicate inserts update existing rows instead of duplicating them.
- A fake provider can sync a small universe, prices, and fundamentals into SQLite.
- The sync script can be run for a small date range.
