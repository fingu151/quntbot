# Agent Work Continuity Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve the local agent operations dashboard so Markdown and Streamlit both show current safety state, work history, verification, stop point, and next safe action.

**Architecture:** Keep `scripts/generate_agent_ops_dashboard.py` as the shared local-only dashboard model and Markdown renderer. Add `scripts/agent_ops_streamlit_dashboard.py` as a read-only Streamlit view that imports the shared model and renders visual status cards and tables without broker, DB-write, network, or order paths.

**Tech Stack:** Python standard library, Streamlit, pytest, AST import checks.

---

## File Structure

- Modify `scripts/generate_agent_ops_dashboard.py`: add dashboard model dataclasses, progress parsing, artifact status parsing, and richer Markdown sections.
- Modify `tests/test_generate_agent_ops_dashboard.py`: add tests for progress extraction, continuity lanes, Markdown sections, and preserved safety behavior.
- Create `scripts/agent_ops_streamlit_dashboard.py`: Streamlit read-only renderer for the shared model.
- Create `tests/test_agent_ops_streamlit_dashboard.py`: import-safety, loader, and fake-Streamlit render tests.
- Modify `HANDOFF_FOR_AGENTS.md`: add commands for Markdown and Streamlit work continuity dashboard.
- Modify `progress.md`: record the completed dashboard extension and verification results.

## Task 1: Shared Model Tests

**Files:**
- Modify: `tests/test_generate_agent_ops_dashboard.py`
- Modify later: `scripts/generate_agent_ops_dashboard.py`

- [ ] **Step 1: Add failing tests for progress extraction and Markdown sections**

Append tests that create local `progress.md`, `HANDOFF_FOR_AGENTS.md`, and dry-run JSON fixtures. The tests should assert:

```python
def test_build_dashboard_model_extracts_latest_progress_sections(tmp_path):
    import scripts.generate_agent_ops_dashboard as dashboard

    progress = tmp_path / "progress.md"
    handoff = tmp_path / "HANDOFF_FOR_AGENTS.md"
    dry_run = tmp_path / "dry_run.json"
    progress.write_text(
        "# quntbot Progress Log\n\n"
        "## 2026-05-13 Dashboard work\n\n"
        "### Completed\n\n"
        "- improved Markdown dashboard\n"
        "- added Streamlit dashboard\n\n"
        "### Verification\n\n"
        "- targeted tests passed\n\n"
        "### Notes\n\n"
        "- continue with browser verification later\n",
        encoding="utf-8",
    )
    handoff.write_text("# Handoff\n\nNext safe command: run dashboard\n", encoding="utf-8")
    dry_run.write_text(
        json.dumps(
            {
                "dry_run": True,
                "as_of_date": "2026-05-13",
                "target_count": 3,
                "buy_count": 2,
                "sell_count": 1,
                "price_lookup_failed_count": 0,
                "price_fallback_count": 0,
            }
        ),
        encoding="utf-8",
    )

    model = dashboard.build_dashboard_model(
        dry_run_json=dry_run,
        expected_date="2026-05-13",
        progress_path=progress,
        handoff_path=handoff,
        comparison_path=tmp_path / "missing_comparison.md",
    )

    assert model.latest_progress_title == "2026-05-13 Dashboard work"
    assert "improved Markdown dashboard" in model.completed_items
    assert "targeted tests passed" in model.verification_items
    assert "continue with browser verification later" in model.note_items
    assert model.current_state["overall_local_safety"] == "clean"
    assert model.task_lanes["done"]["status"] == "inferred"
```

Also add:

```python
def test_render_dashboard_includes_work_continuity_sections(tmp_path):
    import scripts.generate_agent_ops_dashboard as dashboard

    dry_run = tmp_path / "dry_run.json"
    dry_run.write_text(
        json.dumps(
            {
                "dry_run": True,
                "as_of_date": "2026-05-13",
                "price_lookup_failed_count": 0,
                "price_fallback_count": 0,
            }
        ),
        encoding="utf-8",
    )
    progress = tmp_path / "progress.md"
    progress.write_text(
        "# quntbot Progress Log\n\n"
        "## 2026-05-13 Dashboard work\n\n"
        "### Completed\n\n- model added\n\n"
        "### Verification\n\n- tests passed\n",
        encoding="utf-8",
    )

    model = dashboard.build_dashboard_model(
        dry_run_json=dry_run,
        expected_date="2026-05-13",
        progress_path=progress,
        handoff_path=tmp_path / "HANDOFF_FOR_AGENTS.md",
        comparison_path=tmp_path / "rebalance_comparison_latest.md",
    )
    markdown = dashboard.render_dashboard_model(model)

    assert "## Summary" in markdown
    assert "## Current State" in markdown
    assert "## Work Continuity" in markdown
    assert "## Next Safe Command" in markdown
    assert "2026-05-13 Dashboard work" in markdown
    assert "model added" in markdown
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
.\venv\Scripts\python.exe -m pytest tests\test_generate_agent_ops_dashboard.py -q
```

Expected: fail because `build_dashboard_model` and `render_dashboard_model` do not exist.

## Task 2: Shared Model Implementation

**Files:**
- Modify: `scripts/generate_agent_ops_dashboard.py`
- Test: `tests/test_generate_agent_ops_dashboard.py`

- [ ] **Step 1: Add model dataclass and progress parser**

Add:

```python
@dataclass(frozen=True)
class DashboardModel:
    expected_date: str
    generated_for_date: str
    current_trade_mode: str
    dry_run_summary: DryRunSummary
    latest_progress_title: str
    completed_items: list[str]
    verification_items: list[str]
    note_items: list[str]
    current_state: dict[str, str]
    task_lanes: dict[str, dict[str, str]]
    evidence: list[dict[str, str]]
    timeline: list[dict[str, str]]
    next_safe_command: str
    warnings: list[str]
```

Add a parser that reads only the first latest progress entry and extracts `Completed`, `Verification`, and `Notes` bullet lists.

- [ ] **Step 2: Add `build_dashboard_model`**

Build the model from local paths. Preserve existing dry-run safety logic by calling `load_dry_run_summary()` and `_overall_safety_status()`.

- [ ] **Step 3: Add `render_dashboard_model`**

Render the new Markdown sections and keep a compatibility wrapper:

```python
def render_dashboard(summary: DryRunSummary, *, expected_date: str) -> str:
    model = _model_from_summary(summary, expected_date=expected_date)
    return render_dashboard_model(model)
```

- [ ] **Step 4: Update `run`**

Call `build_dashboard_model(...)`, write `render_dashboard_model(model)`, and keep console output lines:

```text
dashboard_written=...
dry_run_status=...
safety_status=...
```

- [ ] **Step 5: Run targeted tests**

Run:

```powershell
.\venv\Scripts\python.exe -m pytest tests\test_generate_agent_ops_dashboard.py -q
```

Expected: pass.

## Task 3: Streamlit Dashboard Tests

**Files:**
- Create: `tests/test_agent_ops_streamlit_dashboard.py`
- Create later: `scripts/agent_ops_streamlit_dashboard.py`

- [ ] **Step 1: Add failing import-safety and render tests**

Create tests that assert the Streamlit module does not import `KisClient`, `TradingEngine`, `execute_rebalance`, `src.trading`, or `src.data.database`. Add a fake Streamlit object and assert `render_dashboard(model)` emits the dashboard title, safety status, completed work, verification, and evidence.

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
.\venv\Scripts\python.exe -m pytest tests\test_agent_ops_streamlit_dashboard.py -q
```

Expected: fail because the module does not exist.

## Task 4: Streamlit Dashboard Implementation

**Files:**
- Create: `scripts/agent_ops_streamlit_dashboard.py`
- Test: `tests/test_agent_ops_streamlit_dashboard.py`

- [ ] **Step 1: Implement read-only Streamlit renderer**

Create a module with:

- `DEFAULT_DRY_RUN_PATH`
- `render_dashboard(model)`
- `main()`

`main()` should read sidebar values for expected date and dry-run path, call
`build_dashboard_model`, and render the model. The module must not import any
trading, KIS, or DB writer helpers.

- [ ] **Step 2: Run targeted Streamlit tests**

Run:

```powershell
.\venv\Scripts\python.exe -m pytest tests\test_agent_ops_streamlit_dashboard.py -q
```

Expected: pass.

## Task 5: Documentation And Verification

**Files:**
- Modify: `HANDOFF_FOR_AGENTS.md`
- Modify: `progress.md`
- Test: targeted dashboard tests and syntax check

- [ ] **Step 1: Update handoff commands**

Add commands:

```powershell
.\venv\Scripts\python.exe scripts\generate_agent_ops_dashboard.py --expected-date 2026-05-13
.\venv\Scripts\python.exe -m streamlit run scripts\agent_ops_streamlit_dashboard.py
```

- [ ] **Step 2: Record progress**

Add a top progress entry for the work continuity dashboard, including changed files and verification commands.

- [ ] **Step 3: Run verification**

Run:

```powershell
.\venv\Scripts\python.exe -m pytest tests\test_generate_agent_ops_dashboard.py tests\test_agent_ops_streamlit_dashboard.py -q
.\venv\Scripts\python.exe -m py_compile scripts\generate_agent_ops_dashboard.py scripts\agent_ops_streamlit_dashboard.py tests\test_generate_agent_ops_dashboard.py tests\test_agent_ops_streamlit_dashboard.py
.\venv\Scripts\python.exe scripts\generate_agent_ops_dashboard.py --expected-date 2026-05-13
```

Expected: tests pass, compile succeeds, smoke writes `data/agent_ops_dashboard_latest.md`.

## Self-Review

- Spec coverage: current state, work continuity, evidence, timeline, Markdown, Streamlit, safety boundaries, and verification are covered by Tasks 1-5.
- Placeholder scan: no implementation step depends on unspecified behavior.
- Type consistency: `DashboardModel`, `build_dashboard_model`, and `render_dashboard_model` are defined before Streamlit imports them.
- Git limitation: this workspace is not a git repository, so commit steps are intentionally omitted.
