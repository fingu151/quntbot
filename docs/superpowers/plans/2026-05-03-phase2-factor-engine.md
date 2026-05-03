# Phase 2 Factor Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a tested factor scoring engine that ranks Phase 1 stocks by valuation and momentum data.

**Architecture:** Keep scoring math isolated in `src/factors/scoring.py`, output objects in `src/factors/models.py`, database-backed calculation in `src/factors/engine.py`, and manual display in `scripts/rank_phase2_factors.py`.

**Tech Stack:** Python 3.12, pandas, SQLAlchemy, pytest, SQLite.

---

### Task 1: Scoring Utilities

**Files:**
- Create: `src/factors/scoring.py`
- Create: `tests/factors/test_scoring.py`

- [ ] **Step 1: Write failing tests**

Test that z-score scoring ranks lower-is-better metrics correctly, higher-is-better metrics correctly, and constant series returns neutral scores.

- [ ] **Step 2: Run tests to verify failure**

Run: `.\.venv\Scripts\python.exe -m pytest tests/factors/test_scoring.py -q -p no:cacheprovider`

Expected: FAIL because `src.factors.scoring` does not exist yet.

- [ ] **Step 3: Implement scoring utilities**

Implement `score_series`, `combine_scores`, and input cleanup for invalid values.

- [ ] **Step 4: Run tests to verify pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/factors/test_scoring.py -q -p no:cacheprovider`

Expected: PASS.

### Task 2: Factor Engine

**Files:**
- Create: `src/factors/models.py`
- Create: `src/factors/engine.py`
- Create: `tests/factors/test_engine.py`

- [ ] **Step 1: Write failing tests**

Create a temporary SQLite database with three stocks, prices, and fundamentals. Assert lower valuation and stronger momentum rank higher.

- [ ] **Step 2: Run tests to verify failure**

Run: `.\.venv\Scripts\python.exe -m pytest tests/factors/test_engine.py -q -p no:cacheprovider`

Expected: FAIL because engine functions do not exist yet.

- [ ] **Step 3: Implement factor models and engine**

Implement `FactorScore`, `calculate_factor_scores`, and DB loading helpers.

- [ ] **Step 4: Run tests to verify pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/factors/test_engine.py -q -p no:cacheprovider`

Expected: PASS.

### Task 3: Manual Ranking Script

**Files:**
- Create: `scripts/rank_phase2_factors.py`
- Create: `tests/factors/test_rank_script.py`

- [ ] **Step 1: Write failing tests**

Test argument parsing and that the script prints top-ranked results with an injected scoring function.

- [ ] **Step 2: Run tests to verify failure**

Run: `.\.venv\Scripts\python.exe -m pytest tests/factors/test_rank_script.py -q -p no:cacheprovider`

Expected: FAIL because the script does not exist yet.

- [ ] **Step 3: Implement script**

Add `parse_args`, `run`, and `main`, including direct script execution support.

- [ ] **Step 4: Run tests to verify pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/factors/test_rank_script.py -q -p no:cacheprovider`

Expected: PASS.

### Task 4: Full Verification

**Files:**
- Read: all Phase 2 files.

- [ ] **Step 1: Run all data and factor tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/data tests/factors -q -p no:cacheprovider`

Expected: PASS.

- [ ] **Step 2: Run AST syntax check**

Run: `.\.venv\Scripts\python.exe -m py_compile config.py src/data/models.py src/data/database.py src/data/repositories.py src/data/collectors.py src/factors/models.py src/factors/scoring.py src/factors/engine.py scripts/sync_phase1_data.py scripts/rank_phase2_factors.py`

Expected: Exit code 0.

- [ ] **Step 3: Run script help**

Run: `.\.venv\Scripts\python.exe scripts/rank_phase2_factors.py --help`

Expected: Help text prints successfully.
