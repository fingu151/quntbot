# Agent Operations Dashboard Design

Date: 2026-05-12

## Goal

Create a lightweight, text-first operations dashboard that shows how quntbot
agent roles, evidence, task state, and trading safety gates line up during
daily work.

This is phase 1. It intentionally avoids a web UI, background server, database
migration, or LobeHub dependency. If the Markdown dashboard proves useful and
stable, a browser dashboard can be designed later as phase 2.

## Decision

Build a Markdown report generator:

```text
scripts/generate_agent_ops_dashboard.py
  -> data/agent_ops_dashboard_latest.md
```

The generator reads existing project artifacts and produces a human-readable
dashboard. It must not place orders, call KIS, mutate trading reports, update
strategy parameters, or require network access.

## Inputs

The first version reads only local files that already exist in the project:

- `docs/agent-roster.md`
- `HANDOFF_FOR_AGENTS.md`
- `progress.md`
- `data/dry_run_rebalance_latest.json`
- `data/dry_run_rebalance_latest.md`
- `data/rebalance_comparison_latest.md`
- `logs/`

Missing files should be reported as `missing`, not treated as fatal unless the
file is required for the section being generated.

## Output Sections

### Agent Roster

Summarize the current operating roles from `docs/agent-roster.md`:

- Planner
- Bug Investigator
- Data and DB
- Strategy and Factor
- Backtest
- Trading Safety
- Research Brief
- Portfolio Review
- Operations
- Test and Verification
- Docs and Handoff

The section should show lead/support usage guidance, not pretend that separate
installed agents exist.

### Task State

Use a LobeHub-inspired but local-only status grouping:

- `needs_input`: blocked, failed, stale, or requires user confirmation.
- `backlog`: known next actions that are not currently running.
- `running`: the current or most recent operational flow.
- `scheduled`: recurring or time-based work described in handoff notes.
- `done`: latest completed checks or reports.

Phase 1 may derive these from handoff text, latest report presence, and known
script names. It should clearly label inferred status as inferred.

### Evidence

Show the local evidence that supports the current dashboard:

- files read,
- latest report paths,
- latest log paths,
- dry-run JSON date,
- rebalance comparison path,
- relevant source documents.

Evidence entries should include a status such as `present`, `missing`,
`stale-risk`, or `inferred`.

### Safety Gates

Show no-order trading readiness from local artifacts only:

- `TRADE_MODE` expectation is PAPER.
- dry-run report exists.
- dry-run `as_of_date` matches the expected date when available.
- `price_lookup_failed_count` is zero or explicitly flagged.
- `price_fallback_count` is zero or explicitly flagged.
- stale report risk is visible.
- readiness command is printed as the next safe command, not executed by the
  dashboard generator.

If any safety field cannot be read, the section should say `unknown` rather than
assuming safe.

### Timeline

List recent operational milestones in order:

- latest dry-run report,
- latest comparison report,
- latest readiness/checklist log when present,
- recent handoff or progress note references.

The timeline should prefer dates from filenames or report content. If a date is
inferred from file metadata, mark it as inferred.

## Data Flow

```text
local artifacts -> parsers -> normalized dashboard model -> Markdown renderer
```

The parser layer should be small and defensive:

- JSON reports use `json`.
- Markdown reports use targeted line extraction.
- Logs use filename and short snippets only.
- Paths are kept relative to the repo root in the rendered report.

## Error Handling

- Missing optional files produce warnings in the report.
- Malformed JSON produces a blocked safety status for the affected section.
- Encoding problems should not crash the whole dashboard; the generator may
  replace unreadable text and report the file as `read-error`.
- The script exits non-zero only when it cannot write the dashboard output.

## Safety Boundaries

The dashboard is observational. It must not:

- execute rebalance preparation,
- execute readiness checks,
- call broker APIs,
- place PAPER or LIVE orders,
- edit portfolio reports,
- change factor weights or parameters,
- store secrets or raw credentials.

Any future browser UI must keep the same observational boundary unless a
separate Trading Safety design approves otherwise.

## Verification

Phase 1 verification should include:

- Python syntax check for the new script.
- A targeted unit test for parsing a minimal dry-run JSON.
- A targeted unit test for rendering missing/unknown safety fields.
- A smoke run that writes `data/agent_ops_dashboard_latest.md`.

Documentation-only changes may use read-back and required-section search.

## Phase 2 Trigger

Only consider a browser dashboard after the Markdown report is useful for real
operations for several runs without becoming noisy or misleading.

Phase 2 can then reuse the same normalized dashboard model and add visual views:

- roster cards,
- status columns,
- safety gate badges,
- evidence table,
- timeline view.
