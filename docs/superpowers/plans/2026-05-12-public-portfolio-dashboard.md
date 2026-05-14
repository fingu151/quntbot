# Public Portfolio Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local-first public read-only portfolio dashboard backed by a manually generated snapshot.

**Architecture:** A snapshot generator reads KIS PAPER holdings plus local dry-run, execution, factor, and signal data, then writes `data/public_portfolio_snapshot.json`. A Streamlit dashboard reads only that snapshot and renders a public read-only page without broker calls, DB writes, or order execution paths.

**Tech Stack:** Python 3.12, Streamlit, SQLAlchemy, existing KIS client, local SQLite, pytest.

---

## File Structure

- Create `scripts/generate_public_portfolio_snapshot.py`: read-only snapshot generator with fakeable pure helpers.
- Create `scripts/public_portfolio_dashboard.py`: Streamlit dashboard plus import-safe data loading helpers.
- Create `tests/test_generate_public_portfolio_snapshot.py`: snapshot generator unit tests with fake holdings and local JSON fixtures.
- Create `tests/test_public_portfolio_dashboard.py`: dashboard loader/formatting tests that do not import or call KIS.
- Modify `HANDOFF_FOR_AGENTS.md`: add the new commands after implementation passes.

## Task 1: Snapshot Generator Tests

**Files:**
- Create: `tests/test_generate_public_portfolio_snapshot.py`
- Create later: `scripts/generate_public_portfolio_snapshot.py`

- [ ] **Step 1: Write failing tests for snapshot summary and rationale merging**

Add tests that import:

```python
from scripts.generate_public_portfolio_snapshot import (
    build_snapshot,
    load_json_file,
)
```

Add fake holdings:

```python
holdings = [
    {
        "ticker": "005930",
        "name": "Samsung Electronics",
        "qty": 10,
        "avg_price": 70000,
        "current_price": 72000,
        "eval_profit_loss": 20000,
        "profit_loss_rate": 2.86,
    }
]
```

Add dry-run payload with `targets` and `orders` for ticker `005930`, then assert:

```python
snapshot["schema_version"] == 1
snapshot["source"]["dashboard_calls_kis"] is False
snapshot["summary"]["holding_count"] == 1
snapshot["summary"]["total_market_value"] == 720000
snapshot["summary"]["total_cost"] == 700000
snapshot["summary"]["total_profit_loss"] == 20000
snapshot["positions"][0]["rationale"]["rank"] == 1
snapshot["positions"][0]["rationale"]["order_reason"] == "target allocation buy"
```

- [ ] **Step 2: Write failing tests for missing rationale warnings**

Use a holding ticker not present in dry-run targets or orders and assert:

```python
snapshot["positions"][0]["rationale"]["order_reason"] == ""
assert "missing_rationale:000660" in snapshot["warnings"]
```

- [ ] **Step 3: Run tests and verify they fail because the module does not exist**

Run:

```powershell
.\venv\Scripts\python.exe -m pytest tests\test_generate_public_portfolio_snapshot.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.generate_public_portfolio_snapshot'`.

## Task 2: Snapshot Generator Implementation

**Files:**
- Create: `scripts/generate_public_portfolio_snapshot.py`
- Test: `tests/test_generate_public_portfolio_snapshot.py`

- [ ] **Step 1: Implement pure helpers**

Create:

```python
def load_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))

def build_snapshot(
    holdings: list[dict[str, Any]],
    *,
    dry_run: dict[str, Any] | None = None,
    execution: dict[str, Any] | None = None,
    signal_details: dict[str, list[dict[str, Any]]] | None = None,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    ...
```

The implementation must compute `market_value = qty * current_price`,
`cost = qty * avg_price`, summary totals, and per-position rationale from
`dry_run["targets"]` and `dry_run["orders"]`.

- [ ] **Step 2: Implement CLI shell**

Add `parse_args`, `run`, and `main` so this command writes the snapshot:

```powershell
.\venv\Scripts\python.exe scripts\generate_public_portfolio_snapshot.py --output data\public_portfolio_snapshot.json
```

The CLI may instantiate `KisClient` only inside `run`, not at module import.

- [ ] **Step 3: Run targeted generator tests**

Run:

```powershell
.\venv\Scripts\python.exe -m pytest tests\test_generate_public_portfolio_snapshot.py -q
```

Expected: PASS.

## Task 3: Signal Detail Queries

**Files:**
- Modify: `scripts/generate_public_portfolio_snapshot.py`
- Test: `tests/test_generate_public_portfolio_snapshot.py`

- [ ] **Step 1: Add failing test for signal details**

Use `signal_details={"005930": [{"source": "busanstock", "detail": "TP up", "raw_score": 1.0}]}` and assert the first position rationale includes that signal.

- [ ] **Step 2: Implement DB query helper**

Add:

```python
def load_signal_details(database_url: str | None, tickers: list[str], as_of_date: date | None) -> dict[str, list[dict[str, Any]]]:
    ...
```

It should query `TelegramSignal` and `BusanstockSignal` directly, returning readable dictionaries. If the DB is missing or query fails, return `{}` and let `build_snapshot` add warnings only for missing rationale, not missing signals.

- [ ] **Step 3: Run targeted generator tests**

Run:

```powershell
.\venv\Scripts\python.exe -m pytest tests\test_generate_public_portfolio_snapshot.py -q
```

Expected: PASS.

## Task 4: Dashboard Tests

**Files:**
- Create: `tests/test_public_portfolio_dashboard.py`
- Create later: `scripts/public_portfolio_dashboard.py`

- [ ] **Step 1: Write failing tests for snapshot loading**

Import:

```python
from scripts.public_portfolio_dashboard import (
    format_krw,
    load_snapshot,
    snapshot_is_stale,
)
```

Assert:

```python
format_krw(1234567) == "1,234,567 KRW"
load_snapshot(missing_path)["status"] == "missing"
load_snapshot(malformed_path)["status"] == "invalid"
snapshot_is_stale({"generated_at": "2026-05-12T09:00:00+09:00"}, now=..., max_age_hours=24) is False
```

- [ ] **Step 2: Run tests and verify they fail because the dashboard module does not exist**

Run:

```powershell
.\venv\Scripts\python.exe -m pytest tests\test_public_portfolio_dashboard.py -q
```

Expected: FAIL with `ModuleNotFoundError`.

## Task 5: Dashboard Implementation

**Files:**
- Create: `scripts/public_portfolio_dashboard.py`
- Test: `tests/test_public_portfolio_dashboard.py`

- [ ] **Step 1: Implement import-safe helpers**

Add `load_snapshot`, `format_krw`, `format_pct`, and `snapshot_is_stale`.
Do not import `KisClient`, `TradingEngine`, or `execute_rebalance`.

- [ ] **Step 2: Implement Streamlit renderer**

Add `render_dashboard(snapshot)` and `main()`. The dashboard should show:

- read-only status
- generated timestamp
- summary metrics
- holdings table
- per-position rationale and signal details
- warnings

- [ ] **Step 3: Run targeted dashboard tests**

Run:

```powershell
.\venv\Scripts\python.exe -m pytest tests\test_public_portfolio_dashboard.py -q
```

Expected: PASS.

## Task 6: Integration Verification and Docs

**Files:**
- Modify: `HANDOFF_FOR_AGENTS.md`

- [ ] **Step 1: Run combined tests**

Run:

```powershell
.\venv\Scripts\python.exe -m pytest tests\test_generate_public_portfolio_snapshot.py tests\test_public_portfolio_dashboard.py -q
```

Expected: PASS.

- [ ] **Step 2: Run syntax checks**

Run:

```powershell
.\venv\Scripts\python.exe -m py_compile scripts\generate_public_portfolio_snapshot.py scripts\public_portfolio_dashboard.py tests\test_generate_public_portfolio_snapshot.py tests\test_public_portfolio_dashboard.py
```

Expected: no output and exit code 0.

- [ ] **Step 3: Generate local snapshot only if KIS credentials are available**

Run:

```powershell
.\venv\Scripts\python.exe scripts\generate_public_portfolio_snapshot.py --output data\public_portfolio_snapshot.json
```

Expected: `snapshot_written=data\public_portfolio_snapshot.json`. If KIS fails, preserve the error and do not claim live snapshot success.

- [ ] **Step 4: Update handoff**

Add concise commands:

```powershell
.\venv\Scripts\python.exe scripts\generate_public_portfolio_snapshot.py --output data\public_portfolio_snapshot.json
.\venv\Scripts\streamlit.exe run scripts\public_portfolio_dashboard.py
```

- [ ] **Step 5: Final report**

Report changed files, commands run, result, agent roles used, and any remaining risk.

## Self-Review

- Spec coverage: snapshot generator, public Streamlit dashboard, full visibility, KIS-read-only safety, no dashboard KIS calls, tests, and future external access deferral are covered.
- Placeholder scan: no `TODO` or `TBD` items are present.
- Type consistency: tests and implementation tasks use `build_snapshot`, `load_json_file`, `load_signal_details`, `load_snapshot`, `format_krw`, and `snapshot_is_stale` consistently.
