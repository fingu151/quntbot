# quntbot

quntbot is a Korean equity quant trading project built around KRX market data,
factor ranking, read-only research overlays, backtests, and PAPER-first KIS
rebalance operations.

## Current Shape

- Data: KRX/pykrx prices, fundamentals, investor flows, DART quality metrics,
  market indices, macro indicators, and broker research reports.
- Ranking: a 100-point factor budget:
  Value 25, Quality 25, Momentum 20, Yield 5, Technical 15, Auxiliary 10.
- Auxiliary signals: Busanstock, investor flow, and research-report overlays.
  MTProto Telegram stock-signal scoring has been removed.
- Portfolio defaults: 30 holdings, score-weighted allocation, weekly rebalance,
  and the tuned staged-exit defaults in `config.py`.
- Trading safety: all order-adjacent paths stay behind PAPER mode, dry-run
  reports, preflight checks, stale-report checks, quote checks, and readiness
  gates.
- Notifications: Telegram bot alerts use the Bot API through `requests`; they
  are separate from the removed Telegram stock-signal scorer.

## Main Entry Points

```powershell
# Validate config.
.\venv\Scripts\python.exe config.py

# Run the one-command PAPER daily flow during regular KST market hours.
.\venv\Scripts\python.exe scripts\daily_paper_run.py --confirm EXECUTE_PAPER_REBALANCE

# Print the runbook/fallback commands without placing orders.
.\venv\Scripts\python.exe scripts\print_rebalance_operations_checklist.py --as-of-date 2026-06-15 --top-n 30

# Sync recent market data.
.\venv\Scripts\python.exe scripts\sync_phase1_data.py --start-date 2026-05-01 --end-date 2026-05-12 --workers 1

# Rank factors without orders.
.\venv\Scripts\python.exe scripts\rank_phase2_factors.py --as-of-date 2026-05-12 --top-n 10

# Prepare and review a no-order PAPER rebalance plan.
.\venv\Scripts\python.exe scripts\prepare_and_review_rebalance.py --as-of-date 2026-05-12 --top-n 30 --output-json data\dry_run_rebalance_latest.json --output-md data\dry_run_rebalance_latest.md

# Check readiness without placing orders.
.\venv\Scripts\python.exe scripts\check_rebalance_readiness.py --dry-run-json data\dry_run_rebalance_latest.json --expected-date 2026-05-12

# Run tests.
.\venv\Scripts\python.exe -m pytest -q
```

## Daily PAPER Operation

Use `scripts\daily_paper_run.py` for the normal one-command PAPER trading day:
read-only Hankyung and Mirae research refresh, Phase 1 sync, dry-run review,
readiness check, PAPER execution, post-review, bundle archive, then a
terminal-held intraday stop-loss/trailing-stop monitor. Keep the terminal open
after success; closing it stops the intraday monitor.

Use `scripts\run_bot.py` instead only when you want the full scheduler from
before the market opens: pre-market sync, scheduled rebalance, stop monitor,
intraday macro dry-run, Busanstock polling, and research-report polling. Do not
run `daily_paper_run.py` and `run_bot.py` at the same time on the same trading
day.

## Important Files

- `config.py`: current strategy, safety, KIS, macro, and hedge defaults.
- `src/data/`: ORM models, repositories, collectors, and quality sync support.
- `src/factors/`: 100-point factor scoring and buy-filter logic.
- `src/signals/`: Busanstock and research-report ingestion/analysis.
- `src/trading/`: KIS client, dry-run/rebalance logic, scheduler, exits, journal.
- `src/backtest/`: historical simulation engine and metrics.
- `scripts/`: operational CLIs, no-order reviews, syncs, dashboards, reports.
- `docs/agent-roster.md`: source of truth for agent roles and workflow rules.
- `HANDOFF_FOR_AGENTS.md`: current operational handoff and verified commands.

## Environment

Copy `.env.example` to `.env` and fill only the credentials you need. Keep
`TRADE_MODE=PAPER` unless you are deliberately doing a separate LIVE review.
Never commit `.env`, tokens, account numbers, sessions, or local DB files.
