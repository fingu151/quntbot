# Phase 1 Data Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a repeatable SQLite-backed Phase 1 data pipeline for stock universe, daily prices, and available fundamental metrics.

**Architecture:** Use SQLAlchemy models for durable storage, repository functions for idempotent writes, provider classes for pykrx access, and one CLI script for manual sync. Tests use temporary SQLite databases and fake providers, so normal verification does not depend on the network.

**Tech Stack:** Python 3.12, SQLAlchemy 2.x, pandas, pykrx, pytest, SQLite.

---

### Task 1: Database Models And Session Helpers

**Files:**
- Create: `src/data/models.py`
- Create: `src/data/database.py`
- Create: `tests/data/test_database.py`

- [ ] **Step 1: Write failing tests**

Create tests that call `create_tables(engine)` and assert the four expected tables exist.

- [ ] **Step 2: Run tests to verify failure**

Run: `.\.venv\Scripts\python.exe -m pytest tests/data/test_database.py -q -p no:cacheprovider`

Expected: FAIL because `src.data.database` does not exist yet.

- [ ] **Step 3: Implement models and database helpers**

Define `Stock`, `DailyPrice`, `Fundamental`, and `SyncRun`, plus `get_engine`, `create_tables`, and `session_scope`.

- [ ] **Step 4: Run tests to verify pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/data/test_database.py -q -p no:cacheprovider`

Expected: PASS.

### Task 2: Idempotent Repository Writes

**Files:**
- Create: `src/data/repositories.py`
- Create: `tests/data/test_repositories.py`

- [ ] **Step 1: Write failing tests**

Test that stock, price, and fundamental upserts insert once and update on repeated keys.

- [ ] **Step 2: Run tests to verify failure**

Run: `.\.venv\Scripts\python.exe -m pytest tests/data/test_repositories.py -q -p no:cacheprovider`

Expected: FAIL because repository functions do not exist yet.

- [ ] **Step 3: Implement repository functions**

Implement `upsert_stocks`, `upsert_daily_prices`, `upsert_fundamentals`, and count helpers.

- [ ] **Step 4: Run tests to verify pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/data/test_repositories.py -q -p no:cacheprovider`

Expected: PASS.

### Task 3: Collector With Fake Provider Tests

**Files:**
- Create: `src/data/collectors.py`
- Create: `tests/data/test_collectors.py`

- [ ] **Step 1: Write failing tests**

Create a fake provider that returns two stocks, two price rows, and two fundamental rows. Assert `sync_phase1_data` stores the expected counts and records a successful sync run.

- [ ] **Step 2: Run tests to verify failure**

Run: `.\.venv\Scripts\python.exe -m pytest tests/data/test_collectors.py -q -p no:cacheprovider`

Expected: FAIL because collector functions do not exist yet.

- [ ] **Step 3: Implement collector and pykrx provider**

Implement `MarketDataProvider`, `PykrxMarketDataProvider`, and `sync_phase1_data`.

- [ ] **Step 4: Run tests to verify pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/data/test_collectors.py -q -p no:cacheprovider`

Expected: PASS.

### Task 4: Manual Sync Script

**Files:**
- Create: `scripts/sync_phase1_data.py`
- Create: `tests/data/test_sync_script.py`

- [ ] **Step 1: Write failing tests**

Test argument parsing and that the script can call a fake sync function.

- [ ] **Step 2: Run tests to verify failure**

Run: `.\.venv\Scripts\python.exe -m pytest tests/data/test_sync_script.py -q -p no:cacheprovider`

Expected: FAIL because the script does not exist yet.

- [ ] **Step 3: Implement script**

Add `parse_args`, `run`, and `main` functions. Default end date is today, and default start date is 30 calendar days before end date for a small first sync.

- [ ] **Step 4: Run tests to verify pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/data/test_sync_script.py -q -p no:cacheprovider`

Expected: PASS.

### Task 5: Full Verification

**Files:**
- Read: all Phase 1 files.

- [ ] **Step 1: Run all Phase 1 tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/data -q -p no:cacheprovider`

Expected: PASS.

- [ ] **Step 2: Run AST syntax check**

Run: `.\.venv\Scripts\python.exe -m py_compile config.py src/data/models.py src/data/database.py src/data/repositories.py src/data/collectors.py scripts/sync_phase1_data.py`

Expected: Exit code 0.

- [ ] **Step 3: Run config validation**

Run: `.\.venv\Scripts\python.exe config.py`

Expected: `[OK] 설정 일관성 통과`.
