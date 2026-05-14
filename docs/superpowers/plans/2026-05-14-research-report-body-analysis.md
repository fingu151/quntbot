# Research Report Body Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Store structured Korean analyst-report body summaries for Hankyung and Mirae Asset reports without touching order execution.

**Architecture:** Keep `research_report_signals` as metadata and scoring input. Add a separate `research_report_analyses` table keyed by signal row, a deterministic `rule-v1` analyzer, and reader/script telemetry that explains body extraction and analysis quality.

**Tech Stack:** Python 3.12, SQLAlchemy, SQLite, requests, pypdf, pytest.

---

## File Structure

- Create `src/signals/research_report_analysis.py`: deterministic body-text analyzer.
- Modify `src/data/models.py`: add `ResearchReportAnalysis`.
- Modify `src/data/repositories.py`: add analysis upsert and lookup helpers.
- Modify `src/signals/research_report_reader.py`: create analysis rows after metadata persistence.
- Modify `scripts/sync_korean_research_reports.py`: print analysis telemetry.
- Modify `tests/data/test_repositories.py`: repository coverage.
- Create `tests/signals/test_research_report_analysis.py`: analyzer coverage.
- Modify `tests/signals/test_research_report_reader.py`: reader integration coverage.
- Modify `tests/signals/test_sync_korean_research_reports.py`: CLI telemetry coverage.
- Modify `progress.md` and `HANDOFF_FOR_AGENTS.md`: operational handoff after verification.

## Task 1: Analyzer Contract

**Files:**
- Create: `src/signals/research_report_analysis.py`
- Test: `tests/signals/test_research_report_analysis.py`

- [ ] Step 1: Add failing tests for Korean body analysis.
- [ ] Step 2: Implement `ResearchReportBodyAnalysis`, `analyze_research_report_body`, and deterministic sentence bucketing.
- [ ] Step 3: Run:

```powershell
.\venv\Scripts\python.exe -m pytest tests\signals\test_research_report_analysis.py -q
```

Expected: all analyzer tests pass.

## Task 2: DB Storage Contract

**Files:**
- Modify: `src/data/models.py`
- Modify: `src/data/repositories.py`
- Test: `tests/data/test_repositories.py`

- [ ] Step 1: Add tests for upserting one analysis row and updating it by `report_signal_id`.
- [ ] Step 2: Add `ResearchReportAnalysis` model and repository helpers.
- [ ] Step 3: Run:

```powershell
.\venv\Scripts\python.exe -m pytest tests\data\test_repositories.py -q
```

Expected: repository tests pass.

## Task 3: Reader Integration

**Files:**
- Modify: `src/signals/research_report_reader.py`
- Test: `tests/signals/test_research_report_reader.py`

- [ ] Step 1: Extend telemetry with `analysis_rows_stored`, `analysis_success_count`, and `analysis_failed_count`.
- [ ] Step 2: After metadata upsert, fetch persisted signal rows and create analysis rows.
- [ ] Step 3: Preserve metadata rows when PDF fetch or analysis fails.
- [ ] Step 4: Run:

```powershell
.\venv\Scripts\python.exe -m pytest tests\signals\test_research_report_reader.py -q
```

Expected: reader tests pass.

## Task 4: Script Telemetry

**Files:**
- Modify: `scripts/sync_korean_research_reports.py`
- Test: `tests/signals/test_sync_korean_research_reports.py`

- [ ] Step 1: Print analysis telemetry from the script.
- [ ] Step 2: Keep `orders_submitted=0` in output.
- [ ] Step 3: Run:

```powershell
.\venv\Scripts\python.exe -m pytest tests\signals\test_sync_korean_research_reports.py -q
```

Expected: script tests pass.

## Task 5: Verification and Handoff

**Files:**
- Modify: `progress.md`
- Modify: `HANDOFF_FOR_AGENTS.md`

- [ ] Step 1: Run combined targeted tests:

```powershell
.\venv\Scripts\python.exe -m pytest tests\signals\test_research_report_analysis.py tests\signals\test_research_report_reader.py tests\data\test_repositories.py tests\signals\test_sync_korean_research_reports.py -q
```

- [ ] Step 2: Run syntax check:

```powershell
.\venv\Scripts\python.exe -m py_compile src\signals\research_report_analysis.py src\signals\research_report_reader.py src\data\models.py src\data\repositories.py scripts\sync_korean_research_reports.py
```

- [ ] Step 3: Record changed behavior and verification output in `progress.md`.
- [ ] Step 4: Add handoff commands for Hankyung and Mirae Asset body analysis.

## Self-Review

- Spec coverage: analyzer, DB contract, reader integration, CLI telemetry, safety boundary, and handoff are covered.
- Placeholder scan: no implementation step depends on unspecified files or hidden services.
- Type consistency: analysis rows use `report_signal_id` as the unique key and `rule-v1` as the deterministic version.

