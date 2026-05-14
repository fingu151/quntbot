# Public Portfolio Dashboard Design

## Purpose

Build a local-first, public read-only portfolio dashboard for quntbot. The
dashboard lets friends view the current PAPER portfolio, entry prices, current
profit and loss, entry rationale, and related signal/news context without giving
them any ability to edit data or submit orders.

The first implementation is a local MVP. External access through a tunnel or
hosting layer is intentionally deferred until the local snapshot and dashboard
are verified.

## Selected Approach

Use a manual snapshot flow:

1. A local script queries KIS PAPER holdings and reads existing quntbot reports,
   factor data, and signal tables.
2. The script writes a static public snapshot to
   `data/public_portfolio_snapshot.json`.
3. A Streamlit dashboard reads only that snapshot and renders the public view.

The Streamlit app must not call KIS, submit orders, mutate the DB, or edit any
report. Visitors can refresh the page freely without triggering broker API
calls.

## Agents

- Lead: Planner Agent
- Supporting: Trading Safety Agent, Portfolio Review Agent, Data and DB Agent,
  Research Brief Agent, Operations Agent, Test and Verification Agent
- Subagent findings:
  - KIS holdings are available through `KisClient.get_holdings()` with ticker,
    name, qty, avg_price, current_price, eval_profit_loss, and
    profit_loss_rate.
  - Dry-run reports contain `targets`, `orders`, `skipped_buys`, safety counts,
    and rank/score context.
  - Execution reports contain planned/executed buy/sell tickers and
    match-status fields, but not fill prices.
  - Telegram and Busanstock details exist in DB models, though repository helper
    functions currently return only aggregated raw scores.

## Public Data Scope

The MVP intentionally exposes all portfolio values in the generated snapshot:

- ticker
- name
- quantity
- average entry price
- current price
- market value
- profit/loss amount
- profit/loss rate
- buy or sell rationale
- factor score summary
- Telegram signal summary when available
- Busanstock signal details when available
- investor-flow and quality metric context when available

This is acceptable for the MVP because the user explicitly chose full public
visibility and wants the option to reduce visibility later.

## Non-Goals

- No order submission.
- No KIS calls from the Streamlit dashboard request path.
- No user accounts, comments, likes, or editing UI.
- No cloud deployment or public tunnel setup in the first implementation.
- No new external news API in the first implementation.
- No investment advice language or automated recommendation finalization.

## Snapshot Generator

Add `scripts/generate_public_portfolio_snapshot.py`.

Responsibilities:

- Confirm safe read-only operation before doing any work.
- Query KIS PAPER holdings through `KisClient.get_holdings()`.
- Read latest dry-run JSON, latest execution report when available, and local DB
  rationale sources.
- Build one normalized JSON payload for the public dashboard.
- Never call `place_order`, `buy`, `sell`, `execute_rebalance`, or any execution
  script.
- Mask no values in the MVP because full public visibility is selected.

Expected default inputs:

- `data/dry_run_rebalance_latest.json`
- latest matching `data/rebalance_execution_*.json` if present
- `data/quntbot.db`

Expected output:

- `data/public_portfolio_snapshot.json`

Suggested top-level JSON shape:

```json
{
  "schema_version": 1,
  "generated_at": "2026-05-12T09:15:00+09:00",
  "source": {
    "holdings": "kis_paper",
    "rationale": "local_reports_and_db",
    "kis_called_by_snapshot": true,
    "dashboard_calls_kis": false
  },
  "summary": {
    "holding_count": 10,
    "total_market_value": 100000000,
    "total_cost": 98000000,
    "total_profit_loss": 2000000,
    "total_profit_loss_rate": 2.04
  },
  "positions": [
    {
      "ticker": "005930",
      "name": "Samsung Electronics",
      "qty": 10,
      "avg_price": 70000,
      "current_price": 72000,
      "market_value": 720000,
      "profit_loss": 20000,
      "profit_loss_rate": 2.86,
      "rationale": {
        "order_reason": "target allocation buy",
        "rank": 1,
        "total_score": 1.2345,
        "factor_scores": {
          "value": 0.1,
          "quality": 0.2,
          "momentum": 0.3,
          "yield": 0.0,
          "telegram": 0.0,
          "busanstock": 0.0,
          "investor_flow": 0.0
        },
        "signals": []
      }
    }
  ],
  "warnings": []
}
```

## Dashboard

Add `scripts/public_portfolio_dashboard.py` as a Streamlit app.

Responsibilities:

- Read `data/public_portfolio_snapshot.json`.
- Render a public read-only portfolio view.
- Show stale or missing snapshot warnings clearly.
- Display an explicit read-only badge.
- Avoid any controls that mutate data, execute orders, refresh KIS, or write
  files.

Primary sections:

- Header: dashboard title, generated timestamp, read-only status.
- Summary metrics: total market value, total cost, total profit/loss, total
  profit/loss rate.
- Holdings table: ticker, name, qty, avg_price, current_price, market_value,
  profit_loss, profit_loss_rate.
- Position detail panel: rationale, score components, Telegram/Busanstock
  details, quality/investor-flow context.
- Warnings: missing snapshot, stale snapshot, incomplete rationale, report
  mismatches.

## Rationale Sources

The MVP should prefer sources in this order:

1. Latest KIS holdings for actual position state.
2. Latest execution report for actual buy/sell ticker confirmation.
3. Latest dry-run `targets[]` and `orders[]` for rank, score, and order reason.
4. Factor engine output or DB-backed factor rows recalculated for the relevant
   date when needed.
5. Direct DB queries for Telegram and Busanstock details.
6. DB quality and investor-flow rows for explanatory context.

If a rationale source is missing, the snapshot should preserve the position and
add a warning instead of hiding the holding.

## Safety Rules

- Dashboard is read-only.
- Snapshot generation may call KIS read endpoints only.
- The Streamlit dashboard must not instantiate `KisClient`.
- The dashboard must not import trading execution helpers.
- Snapshot generation must not call any function that can submit, cancel, or
  modify orders.
- Any future external access must be designed separately before opening the app
  outside the local machine.

## Testing

Required first-pass verification:

- Unit tests for snapshot normalization using fake KIS holdings and fake report
  data.
- Unit tests proving dashboard data loading handles missing and malformed
  snapshots.
- Syntax check for new scripts.
- Streamlit smoke command or import-level check that does not call KIS.

Suggested commands:

```powershell
.\venv\Scripts\python.exe -m pytest tests\test_generate_public_portfolio_snapshot.py tests\test_public_portfolio_dashboard.py -q
.\venv\Scripts\python.exe -m py_compile scripts\generate_public_portfolio_snapshot.py scripts\public_portfolio_dashboard.py
```

## Implementation Order

1. Add snapshot schema and generator tests.
2. Implement snapshot generator with fakeable dependencies.
3. Add dashboard loading/render helper tests.
4. Implement Streamlit dashboard.
5. Run syntax and targeted tests.
6. Start the local Streamlit app and visually verify the page.

## Later Extensions

- Add visibility modes to hide quantity, cost basis, or absolute profit/loss.
- Add automatic snapshot refresh on a local schedule.
- Add Cloudflare Tunnel, Tailscale, or another external access layer.
- Add richer news sources only after a separate source-fidelity and safety
  review.
- Add a public changelog of buys and sells derived from execution reports.
