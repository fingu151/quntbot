# Environment Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore a runnable Python environment for quntbot Phase 0 validation.

**Architecture:** Keep the broken legacy `venv/` untouched for now and create a new workspace-local `.venv/` from an available Python runtime. Install the pinned dependencies from `requirements.txt`, then validate the current project entry point and test harness.

**Tech Stack:** Python, venv, pip, pytest, python-dotenv.

---

### Task 1: Confirm Environment Inputs

**Files:**
- Read: `AGENTS.md`
- Read: `CLAUDE.md`
- Read: `README.md`
- Read: `interview-summary.md`
- Read: `config.py`
- Read: `requirements.txt`
- Read: `.env.example`

- [ ] **Step 1: Confirm current Python commands**

Run: `Get-Command python,py,python3 -ErrorAction SilentlyContinue | Select-Object Name,Source,Version`

Expected: Shows whether local Python is available.

- [ ] **Step 2: Confirm old virtualenv target**

Run: `Get-Content -LiteralPath '.\venv\pyvenv.cfg' -Encoding UTF8`

Expected: Shows the old interpreter path.

### Task 2: Create New Virtual Environment

**Files:**
- Create: `.venv/`

- [ ] **Step 1: Create `.venv` using the available Python executable**

Run: `<python-exe> -m venv .venv`

Expected: `.venv/Scripts/python.exe` exists.

- [ ] **Step 2: Check new Python version**

Run: `.\.venv\Scripts\python.exe --version`

Expected: Python version prints successfully.

### Task 3: Install Dependencies

**Files:**
- Read: `requirements.txt`

- [ ] **Step 1: Upgrade pip**

Run: `.\.venv\Scripts\python.exe -m pip install --upgrade pip`

Expected: pip upgrade completes or reports already satisfied.

- [ ] **Step 2: Install project requirements**

Run: `.\.venv\Scripts\python.exe -m pip install -r requirements.txt`

Expected: Dependencies install without errors.

### Task 4: Validate Phase 0

**Files:**
- Read: `config.py`
- Read: `tests/`

- [ ] **Step 1: AST syntax check**

Run: `.\.venv\Scripts\python.exe -m py_compile config.py`

Expected: Exit code 0.

- [ ] **Step 2: Run config validation**

Run: `.\.venv\Scripts\python.exe config.py`

Expected: JSON settings print and `[OK] 설정 일관성 통과` appears, or warnings are explicitly reported.

- [ ] **Step 3: Run tests**

Run: `.\.venv\Scripts\python.exe -m pytest -q`

Expected: Test command runs. If no tests exist, pytest may report no tests collected; record that as current project state.
