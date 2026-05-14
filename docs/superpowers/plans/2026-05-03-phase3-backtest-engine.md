# Phase 3 Backtest Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a project-native backtest engine for the Phase 2 factor ranking strategy.

**Architecture:** Keep metrics pure in `src/backtest/metrics.py`, result objects in `src/backtest/models.py`, DB-backed simulation in `src/backtest/engine.py`, and manual execution in `scripts/run_phase3_backtest.py`.

**Tech Stack:** Python 3.12, SQLAlchemy, pandas, pytest, SQLite.

---

### Task 1: Backtest Metrics

**Files:**
- Create: `src/backtest/metrics.py`
- Create: `tests/backtest/test_metrics.py`

- [ ] **Step 1: Write failing tests**

Test total return, CAGR, max drawdown, Sharpe ratio, win rate, and average holding days on deterministic values.

- [ ] **Step 2: Run tests to verify failure**

Run: `.\.venv\Scripts\python.exe -m pytest tests/backtest/test_metrics.py -q -p no:cacheprovider`

Expected: FAIL because `src.backtest.metrics` does not exist yet.

- [ ] **Step 3: Implement metrics**

Implement pure metric functions.

- [ ] **Step 4: Run tests to verify pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/backtest/test_metrics.py -q -p no:cacheprovider`

Expected: PASS.

### Task 2: Backtest Engine

**Files:**
- Create: `src/backtest/models.py`
- Create: `src/backtest/engine.py`
- Create: `tests/backtest/test_engine.py`

- [ ] **Step 1: Write failing tests**

Use a temporary SQLite database with deterministic prices and an injected score function. Assert the engine buys top-ranked stocks, rebalances when ranks change, and costs reduce equity.

- [ ] **Step 2: Run tests to verify failure**

Run: `.\.venv\Scripts\python.exe -m pytest tests/backtest/test_engine.py -q -p no:cacheprovider`

Expected: FAIL because backtest engine functions do not exist yet.

- [ ] **Step 3: Implement models and engine**

Implement `BacktestTrade`, `EquityPoint`, `BacktestResult`, and `run_backtest`.

- [ ] **Step 4: Run tests to verify pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/backtest/test_engine.py -q -p no:cacheprovider`

Expected: PASS.

### Task 3: Manual Backtest Script

**Files:**
- Create: `scripts/run_phase3_backtest.py`
- Create: `tests/backtest/test_run_script.py`

- [ ] **Step 1: Write failing tests**

Test argument parsing, injected run function output, and direct `--help` execution.

- [ ] **Step 2: Run tests to verify failure**

Run: `.\.venv\Scripts\python.exe -m pytest tests/backtest/test_run_script.py -q -p no:cacheprovider`

Expected: FAIL because the script does not exist yet.

- [ ] **Step 3: Implement script**

Add `parse_args`, `run`, and `main` functions.

- [ ] **Step 4: Run tests to verify pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/backtest/test_run_script.py -q -p no:cacheprovider`

Expected: PASS.

### Task 4: Full Verification

**Files:**
- Read: all Phase 3 files.

- [ ] **Step 1: Run all tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/data tests/factors tests/backtest -q -p no:cacheprovider`

Expected: PASS.

- [ ] **Step 2: Run AST syntax check**

Run: `.\.venv\Scripts\python.exe -m py_compile config.py src/data/models.py src/data/database.py src/data/repositories.py src/data/collectors.py src/factors/models.py src/factors/scoring.py src/factors/engine.py src/backtest/models.py src/backtest/metrics.py src/backtest/engine.py scripts/sync_phase1_data.py scripts/rank_phase2_factors.py scripts/run_phase3_backtest.py`

Expected: Exit code 0.

- [ ] **Step 3: Run script help**

Run: `.\.venv\Scripts\python.exe scripts/run_phase3_backtest.py --help`

Expected: Help text prints successfully.
