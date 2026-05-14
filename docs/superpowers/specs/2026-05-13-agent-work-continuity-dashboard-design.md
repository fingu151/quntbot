# Agent Work Continuity Dashboard Design

Date: 2026-05-13

## Goal

Improve the existing agent operations dashboard so a returning user can see:

- what they wanted to do,
- what work was completed,
- whether it was fully verified,
- where the work stopped,
- what the next safe action is.

The dashboard must keep the existing local-only, read-only safety boundary.

## Decision

Use one shared dashboard model and render it in two forms:

```text
local artifacts -> dashboard model -> Markdown report
                                  -> Streamlit dashboard
```

The Markdown report remains the durable handoff artifact at
`data/agent_ops_dashboard_latest.md`. The new Streamlit dashboard is a visual
view over the same local evidence.

## Inputs

The dashboard reads existing local files only:

- `docs/agent-roster.md`
- `HANDOFF_FOR_AGENTS.md`
- `progress.md`
- `data/dry_run_rebalance_latest.json`
- `data/dry_run_rebalance_latest.md`
- `data/rebalance_comparison_latest.md`
- `logs/`

Missing inputs are shown as `missing` or `unknown`; the dashboard does not
create trading reports or run operational commands.

## Output Priority

The dashboard uses option 3 from the user decision: current state and work
history have equal weight.

### Current State

Show the information needed before resuming work:

- `TRADE_MODE` and PAPER expectation.
- dry-run report presence and `as_of_date`.
- price lookup failure and fallback counts.
- overall local safety status.
- latest known verification result from `progress.md`.
- next safe command.

Any `blocked`, `stale-risk`, or `unknown` status should be visible near the top.

### Work Continuity

Show what happened and what remains:

- latest progress headline,
- completed work bullets,
- verification bullets,
- notes that affect the next session,
- inferred task lanes: `needs_input`, `running`, `backlog`, `done`.

When a status is inferred from text rather than a structured report, label it
as `inferred` so the dashboard does not overstate certainty.

### Evidence And Timeline

Show why the dashboard believes the current state:

- source file paths,
- latest report paths,
- dry-run counts,
- comparison report summary,
- recent progress entries.

Paths are rendered relative to the repository root.

## Markdown Requirements

Enhance `scripts/generate_agent_ops_dashboard.py` so the generated Markdown
contains:

- Summary,
- Current State,
- Work Continuity,
- Evidence,
- Safety Gates,
- Timeline,
- Next Safe Command.

The existing safety behavior stays intact: malformed dry-run JSON and stale
dates remain blocked.

## Streamlit Requirements

Create `scripts/agent_ops_streamlit_dashboard.py`.

The Streamlit dashboard should:

- load the shared model from `scripts/generate_agent_ops_dashboard.py`,
- avoid KIS, trading client, order execution, DB writes, and network calls,
- show compact status cards for current state,
- show work continuity sections for completed, verification, notes, and next
  action,
- show evidence and safety tables,
- expose a simple sidebar with expected date and dry-run JSON path,
- render useful errors for missing or malformed local files.

## Safety Boundaries

The dashboard must not:

- call KIS or any broker API,
- place PAPER or LIVE orders,
- execute readiness checks automatically,
- mutate the database,
- change factor weights or strategy parameters,
- write files other than the requested Markdown output.

The Streamlit view is read-only. It should not refresh reports by executing
scripts.

## Error Handling

- Missing optional files become dashboard warnings.
- Malformed dry-run JSON blocks overall safety.
- Missing dry-run counts produce `unknown`, not `clean`.
- Encoding errors in progress or handoff text should not crash dashboard
  rendering; unreadable sections should show `read-error`.

## Verification

Verification should include:

- targeted tests for the shared dashboard model,
- targeted tests for Markdown rendering,
- targeted tests that the Streamlit module does not import trading or KIS
  helpers,
- Python syntax check for the modified and new scripts,
- smoke generation of `data/agent_ops_dashboard_latest.md`.

Because this workspace is not a git repository, design and plan commits are
not available. Record that limitation in the final report.
