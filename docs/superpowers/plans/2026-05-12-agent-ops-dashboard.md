# Agent Operations Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local-only Markdown dashboard generator for quntbot agent operations, evidence, task state, and trading safety gates.

**Status:** Implemented and verified on 2026-05-12. The final implementation
also blocks malformed dry-run JSON and stale expected dates in the overall local
safety status.

**Architecture:** Add one focused script that reads existing local artifacts, normalizes them into a small dashboard model, and renders `data/agent_ops_dashboard_latest.md`. Add targeted tests for dry-run JSON parsing, missing safety fields, and end-to-end Markdown rendering.

**Tech Stack:** Python standard library (`argparse`, `json`, `dataclasses`, `datetime`, `pathlib`), pytest.

---

## File Structure

- Create `scripts/generate_agent_ops_dashboard.py`: CLI, local artifact readers, dry-run parser, dashboard model, Markdown renderer, and writer.
- Create `tests/test_generate_agent_ops_dashboard.py`: targeted parser, renderer, and CLI tests.
- Read existing reference files before implementation:
  - `docs/superpowers/specs/2026-05-12-agent-ops-dashboard-design.md`
  - `docs/agent-roster.md`
  - `scripts/review_rebalance_reports.py`
  - `scripts/check_rebalance_readiness.py`
  - `tests/trading/test_review_rebalance_reports.py`

## Task 1: Dry-Run Safety Parsing Tests

**Files:**
- Create: `tests/test_generate_agent_ops_dashboard.py`
- Read: `data/dry_run_rebalance_latest.json`

- [x] **Step 1: Write failing parser tests**

Add this test file:

```python
import json
from pathlib import Path


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_load_dry_run_summary_reports_clean_fields(tmp_path):
    import scripts.generate_agent_ops_dashboard as dashboard

    path = tmp_path / "dry_run.json"
    _write_json(
        path,
        {
            "dry_run": True,
            "as_of_date": "2026-05-12",
            "target_count": 10,
            "sell_count": 0,
            "buy_count": 10,
            "skipped_buy_count": 0,
            "price_lookup_failed_count": 0,
            "price_fallback_count": 0,
            "price_retry_success_count": 8,
            "price_retry_failed_count": 0,
        },
    )

    summary = dashboard.load_dry_run_summary(path)

    assert summary.path == path
    assert summary.status == "present"
    assert summary.as_of_date == "2026-05-12"
    assert summary.target_count == 10
    assert summary.buy_count == 10
    assert summary.price_lookup_failed_count == 0
    assert summary.price_fallback_count == 0
    assert summary.safety_status == "clean"


def test_load_dry_run_summary_marks_missing_fields_unknown(tmp_path):
    import scripts.generate_agent_ops_dashboard as dashboard

    path = tmp_path / "dry_run.json"
    _write_json(path, {"dry_run": True, "as_of_date": "2026-05-12"})

    summary = dashboard.load_dry_run_summary(path)

    assert summary.status == "present"
    assert summary.price_lookup_failed_count is None
    assert summary.price_fallback_count is None
    assert summary.safety_status == "unknown"


def test_load_dry_run_summary_reports_missing_file(tmp_path):
    import scripts.generate_agent_ops_dashboard as dashboard

    path = tmp_path / "missing.json"

    summary = dashboard.load_dry_run_summary(path)

    assert summary.path == path
    assert summary.status == "missing"
    assert summary.safety_status == "unknown"
```

- [x] **Step 2: Run tests and verify they fail because the module is missing**

Run:

```powershell
.\venv\Scripts\python.exe -m pytest tests\test_generate_agent_ops_dashboard.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.generate_agent_ops_dashboard'`.

## Task 2: Minimal Parser and Renderer Implementation

**Files:**
- Create: `scripts/generate_agent_ops_dashboard.py`
- Modify: `tests/test_generate_agent_ops_dashboard.py`

- [x] **Step 1: Implement the dashboard script**

Create `scripts/generate_agent_ops_dashboard.py` with:

```python
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date
import json
from pathlib import Path
import sys
from typing import Any, Sequence

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import DATA_DIR, TRADE_MODE


@dataclass(frozen=True)
class DryRunSummary:
    path: Path
    status: str
    safety_status: str
    as_of_date: str | None = None
    target_count: int | None = None
    sell_count: int | None = None
    buy_count: int | None = None
    skipped_buy_count: int | None = None
    price_lookup_failed_count: int | None = None
    price_fallback_count: int | None = None
    price_retry_success_count: int | None = None
    price_retry_failed_count: int | None = None
    error: str | None = None


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a local-only Markdown dashboard for quntbot agent operations."
    )
    parser.add_argument(
        "--dry-run-json",
        type=Path,
        default=DATA_DIR / "dry_run_rebalance_latest.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DATA_DIR / "agent_ops_dashboard_latest.md",
    )
    parser.add_argument("--expected-date", default=str(date.today()))
    return parser.parse_args(argv)


def load_dry_run_summary(path: Path) -> DryRunSummary:
    if not path.exists():
        return DryRunSummary(path=path, status="missing", safety_status="unknown")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return DryRunSummary(
            path=path,
            status="read-error",
            safety_status="unknown",
            error=str(exc),
        )

    failed_count = _optional_int(payload, "price_lookup_failed_count")
    fallback_count = _optional_int(payload, "price_fallback_count")
    if failed_count is None or fallback_count is None:
        safety_status = "unknown"
    elif failed_count == 0 and fallback_count == 0 and payload.get("dry_run") is True:
        safety_status = "clean"
    else:
        safety_status = "blocked"

    return DryRunSummary(
        path=path,
        status="present",
        safety_status=safety_status,
        as_of_date=_optional_str(payload, "as_of_date"),
        target_count=_optional_int(payload, "target_count"),
        sell_count=_optional_int(payload, "sell_count"),
        buy_count=_optional_int(payload, "buy_count"),
        skipped_buy_count=_optional_int(payload, "skipped_buy_count"),
        price_lookup_failed_count=failed_count,
        price_fallback_count=fallback_count,
        price_retry_success_count=_optional_int(payload, "price_retry_success_count"),
        price_retry_failed_count=_optional_int(payload, "price_retry_failed_count"),
    )


def render_dashboard(summary: DryRunSummary, *, expected_date: str) -> str:
    lines = [
        "# Agent Operations Dashboard",
        "",
        f"- generated_for_date: `{expected_date}`",
        f"- trade_mode_expectation: `PAPER`",
        f"- current_trade_mode: `{TRADE_MODE}`",
        "",
        "## Agent Roster",
        "",
        "| role | purpose |",
        "| --- | --- |",
        "| Planner | bound scope before edits |",
        "| Bug Investigator | reproduce and localize failures |",
        "| Data and DB | verify DB state before data decisions |",
        "| Strategy and Factor | review scoring and ranking behavior |",
        "| Backtest | validate historical assumptions |",
        "| Trading Safety | guard PAPER/LIVE order paths |",
        "| Research Brief | prepare sourced analyst notes |",
        "| Portfolio Review | inspect dry-run rebalance plans |",
        "| Operations | maintain runbooks and reports |",
        "| Test and Verification | prove changes before completion |",
        "| Docs and Handoff | preserve cross-session context |",
        "",
        "## Task State",
        "",
        "| group | status | evidence |",
        "| --- | --- | --- |",
        "| needs_input | inferred | missing or blocked safety fields appear here |",
        "| backlog | inferred | next safe command and docs updates |",
        "| running | inferred | latest dry-run/report review flow |",
        "| scheduled | inferred | handoff-described recurring work |",
        "| done | inferred | latest generated local reports |",
        "",
        "## Evidence",
        "",
        "| item | status | path |",
        "| --- | --- | --- |",
        f"| dry-run JSON | {summary.status} | `{_rel(summary.path)}` |",
        "| agent roster | present | `docs/agent-roster.md` |",
        "| handoff | present | `HANDOFF_FOR_AGENTS.md` |",
        "| progress | present | `progress.md` |",
        "",
        "## Safety Gates",
        "",
        "| gate | status | value |",
        "| --- | --- | --- |",
        f"| TRADE_MODE is PAPER | {_status_bool(TRADE_MODE == 'PAPER')} | `{TRADE_MODE}` |",
        f"| dry-run report | {summary.status} | `{_rel(summary.path)}` |",
        f"| dry-run as_of_date | {_date_status(summary.as_of_date, expected_date)} | `{summary.as_of_date or 'unknown'}` |",
        f"| price lookup failures | {_count_status(summary.price_lookup_failed_count)} | `{_fmt(summary.price_lookup_failed_count)}` |",
        f"| fallback prices | {_count_status(summary.price_fallback_count)} | `{_fmt(summary.price_fallback_count)}` |",
        f"| overall local safety | {summary.safety_status} | no broker calls performed |",
        "",
        "Next safe command:",
        "",
        f"```powershell\n.\\venv\\Scripts\\python.exe scripts\\check_rebalance_readiness.py --dry-run-json {_rel(summary.path)} --expected-date {expected_date}\n```",
        "",
        "## Timeline",
        "",
        "| event | status | source |",
        "| --- | --- | --- |",
        f"| latest dry-run report | {summary.status} | `{_rel(summary.path)}` |",
        "| rebalance comparison | inferred | `data/rebalance_comparison_latest.md` |",
        "| handoff notes | present | `HANDOFF_FOR_AGENTS.md` |",
    ]
    if summary.error:
        lines.extend(["", "## Warnings", "", f"- dry-run read error: `{summary.error}`"])
    return "\n".join(lines) + "\n"


def run(args: argparse.Namespace) -> int:
    summary = load_dry_run_summary(args.dry_run_json)
    markdown = render_dashboard(summary, expected_date=str(args.expected_date))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(markdown, encoding="utf-8")
    print(f"dashboard_written={args.output}")
    print(f"dry_run_status={summary.status}")
    print(f"safety_status={summary.safety_status}")
    return 0


def _optional_int(payload: dict[str, Any], key: str) -> int | None:
    if key not in payload or payload[key] is None:
        return None
    return int(payload[key])


def _optional_str(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    return str(value) if value is not None else None


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT_DIR.resolve()))
    except ValueError:
        return str(path)


def _status_bool(value: bool) -> str:
    return "clean" if value else "blocked"


def _date_status(actual: str | None, expected: str) -> str:
    if actual is None:
        return "unknown"
    return "clean" if actual == expected else "stale-risk"


def _count_status(value: int | None) -> str:
    if value is None:
        return "unknown"
    return "clean" if value == 0 else "blocked"


def _fmt(value: int | None) -> str:
    return "unknown" if value is None else str(value)


def main(argv: Sequence[str] | None = None) -> int:
    return run(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
```

- [x] **Step 2: Run parser tests**

Run:

```powershell
.\venv\Scripts\python.exe -m pytest tests\test_generate_agent_ops_dashboard.py -q
```

Expected: the three tests from Task 1 pass.

- [x] **Step 3: Add renderer and CLI tests**

Append these tests to `tests/test_generate_agent_ops_dashboard.py`:

```python
def test_render_dashboard_includes_unknown_safety_fields(tmp_path):
    import scripts.generate_agent_ops_dashboard as dashboard

    path = tmp_path / "dry_run.json"
    _write_json(path, {"dry_run": True, "as_of_date": "2026-05-12"})
    summary = dashboard.load_dry_run_summary(path)

    markdown = dashboard.render_dashboard(summary, expected_date="2026-05-12")

    assert "## Safety Gates" in markdown
    assert "| price lookup failures | unknown | `unknown` |" in markdown
    assert "| fallback prices | unknown | `unknown` |" in markdown
    assert "| overall local safety | unknown | no broker calls performed |" in markdown


def test_run_writes_markdown_dashboard(tmp_path, capsys):
    import scripts.generate_agent_ops_dashboard as dashboard

    dry_run = tmp_path / "dry_run.json"
    output = tmp_path / "dashboard.md"
    _write_json(
        dry_run,
        {
            "dry_run": True,
            "as_of_date": "2026-05-12",
            "target_count": 2,
            "sell_count": 0,
            "buy_count": 2,
            "price_lookup_failed_count": 0,
            "price_fallback_count": 0,
        },
    )
    args = dashboard.parse_args(
        [
            "--dry-run-json",
            str(dry_run),
            "--output",
            str(output),
            "--expected-date",
            "2026-05-12",
        ]
    )

    result = dashboard.run(args)

    assert result == 0
    text = output.read_text(encoding="utf-8")
    assert "# Agent Operations Dashboard" in text
    assert "## Agent Roster" in text
    assert "## Task State" in text
    assert "## Evidence" in text
    assert "## Safety Gates" in text
    assert "## Timeline" in text
    assert "scripts\\check_rebalance_readiness.py" in text
    output_text = capsys.readouterr().out
    assert "dashboard_written=" in output_text
    assert "safety_status=clean" in output_text
```

- [x] **Step 4: Run all dashboard tests**

Run:

```powershell
.\venv\Scripts\python.exe -m pytest tests\test_generate_agent_ops_dashboard.py -q
```

Expected: 5 passed.

## Task 3: Smoke Run and Syntax Verification

**Files:**
- Modify: `data/agent_ops_dashboard_latest.md` generated by the new script.
- Read: `docs/superpowers/specs/2026-05-12-agent-ops-dashboard-design.md`

- [x] **Step 1: Run Python syntax check**

Run:

```powershell
.\venv\Scripts\python.exe -m py_compile scripts\generate_agent_ops_dashboard.py tests\test_generate_agent_ops_dashboard.py
```

Expected: exit code 0 and no output.

- [x] **Step 2: Generate the real dashboard**

Run:

```powershell
.\venv\Scripts\python.exe scripts\generate_agent_ops_dashboard.py --expected-date 2026-05-12
```

Expected output includes:

```text
dashboard_written=data\agent_ops_dashboard_latest.md
dry_run_status=present
safety_status=clean
```

- [x] **Step 3: Check required dashboard sections**

Run:

```powershell
rg -n "Agent Operations Dashboard|Agent Roster|Task State|Evidence|Safety Gates|Timeline|Next safe command" data\agent_ops_dashboard_latest.md
```

Expected: matches for every listed section.

- [x] **Step 4: Check prohibited behavior text is absent**

Run:

```powershell
rg -n "placing order|executed order|called KIS|LIVE order allowed|network required" data\agent_ops_dashboard_latest.md
```

Expected: no matches and exit code 1.

- [x] **Step 5: Run git status or record non-git workspace**

Run:

```powershell
git status --short
```

Expected in this workspace:

```text
fatal: not a git repository (or any of the parent directories): .git
```

If this exact fatal message appears, do not attempt a commit. Report that the
workspace is not a git repository.

## Self-Review Checklist

- Spec coverage: the plan implements the Markdown generator, local inputs, five output sections, safety boundaries, missing-file behavior, parser tests, renderer tests, smoke run, and phase-1 no-web constraint.
- Placeholder scan: no `TBD`, `TODO`, `implement later`, or vague test instruction remains.
- Type consistency: `DryRunSummary`, `load_dry_run_summary`, `render_dashboard`, `parse_args`, and `run` are defined before tests rely on them.
