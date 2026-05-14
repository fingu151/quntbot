# quntbot Agent Roster

This document defines the specialist agent roles Codex should use when working on
quntbot. These are operating roles, not separate installed programs. For each
task, the Orchestrator Agent classifies the work, assigns the smallest useful set
of specialist roles, delegates independent work when it improves coverage, and
performs the final review before any user-facing completion claim.

## Non-Negotiable Project Rules

- Before modifying code, read at least five related files.
- Do not answer from guesswork. If uncertain, use search or file reads.
- Actively use the agent roster for every task: the Orchestrator Agent must
  select a lead role, attach useful supporting roles, and use subagents for
  independent non-blocking work when delegation can improve coverage without
  weakening final verification.
- Before implementation, write a short plan and confirm the intended scope.
- Change one thing at a time. Do not mix unrelated fixes.
- After changes, run at least one verification path: syntax check, tests, or log
  inspection.
- For parameter decisions, use actual DB, report, or log numbers before changing
  values.
- For trading paths, PAPER safety and no-order dry runs come before any order
  execution path.
- Research, catalyst, idea, and portfolio-review agents may prepare analysis,
  but they must not finalize investment advice, approve risk, or execute orders.

## Default Workflow

1. The Orchestrator Agent classifies the request as bug, feature, parameter
   decision, operations, research, trading, review, explanation, or docs.
2. The Orchestrator Agent classifies task weight as `tiny`, `standard`, or
   `heavy`, then selects the lead agent and supporting agents from the roster
   below.
3. The Orchestrator Agent decides whether independent work should be delegated
   to subagents. Standard and heavy tasks should use delegation when there are
   two or more bounded, non-blocking scopes with disjoint ownership.
4. The active agents read the project rules plus at least five files relevant to
   the affected area before code modification. For docs-only, review-only, or
   tiny no-edit tasks, the Orchestrator may use the smallest evidence set that
   still proves the claim.
5. The Orchestrator Agent states a short plan with scope, files likely to
   change, selected agents, delegated work if any, and verification.
6. The lead or assigned subagent makes exactly one focused change in its owned
   scope.
7. The Test and Verification Agent verifies with the narrowest meaningful
   command first.
8. If verification fails, switch to the Error Collaboration Protocol below
   before making further feature or cleanup changes.
9. The Orchestrator Agent reviews the integrated result, confirms the evidence,
   and reports changed files, verification result, agent roles used, delegated
   work if any, and remaining risk.

For review-only, audit, or no-edit requests, skip the patch step. Still classify
the request, read the relevant files, gather evidence, and verify the report with
read-back, search, or generated report checks.

## Active Orchestration Rules

These rules adapt the useful parts of `codex-active-orchestration-main` for
quntbot. They support the agent roster above; they do not replace the project
rules in `AGENTS.md`.

### Context Router

Use before broad reading or implementation.

- Classify the task weight as `tiny`, `standard`, or `heavy`.
- Classify the task shape as coding, review, research, assembly, measurement,
  delegation, explanation, or command.
- Load only the files needed for the next decision.
- If intent is unclear, ask the smallest question that affects correctness,
  safety, scope, or cost.
- For long logs, JSON, diffs, or search results, define the question first and
  slice the output instead of reading everything.

### Orchestrator Control Loop

Use for every task, including tiny work. This is the central project workflow.

```text
classify -> assign -> gather evidence -> plan -> delegate or execute -> verify
-> repair if needed -> final review -> report
```

- The Orchestrator Agent owns request classification, task weight, role
  selection, delegation decisions, final review, and user-facing claims.
- Specialist agents own domain evidence and implementation within their assigned
  scope. They do not expand scope, approve risk, or claim completion alone.
- Subagents should be used aggressively for standard and heavy tasks when their
  scopes are independent and useful: code owner inspection, test review, data
  checks, log slicing, docs consistency, or risk review.
- Tiny tasks may stay inline when delegation overhead would exceed the work, but
  the Orchestrator must still name the domain lead and verification path.
- The Orchestrator must not delegate the immediate blocker on the critical path
  if waiting for the result would stop all useful progress.
- The Orchestrator integrates subagent outputs, checks that evidence matches the
  final claim, and resolves contradictions before reporting to the user.

### Coding Operation Loop

Use for code, tests, scripts, setup, and repair work.

```text
understand -> locate -> inspect -> scope -> patch -> verify -> repair -> report
```

- Understand the success condition before reading broadly.
- Locate owners with `rg`, file lists, test names, symbols, script names, and
  documented entry points.
- Inspect owners, callers, tests, config, and nearby patterns only as needed.
- Scope writes to the smallest coherent surface.
- Patch in local style.
- Verify with the cheapest meaningful command.
- Repair only observed failures or clear omissions.
- Report changed files, behavior, verification, and remaining risk.

### Subagent Gate

The user has explicitly requested active agent use for quntbot work. Prefer
subagents when the current environment permits delegation and the task has two
or more independent non-blocking parts. Do not delegate the immediate blocker on
the critical path, and do not use subagents merely to add ceremony to a tiny
task.

Delegation by task weight:
- `tiny`: normally inline; use Orchestrator, domain lead, and Test and
  Verification only.
- `standard`: delegate at least one independent side task when a bounded support
  check can improve quality without blocking the main path.
- `heavy`: split into multiple assigned scopes unless the work is inherently
  serial or delegation would create shared-file conflicts.

Delegate only when the task is:
- bounded,
- independently useful,
- not the immediate blocker on the critical path,
- assigned to a disjoint file or responsibility scope.

Every delegated task must include:

```text
objective:
owned_scope:
excluded_scope:
required_output:
evidence_required:
maximum_report_shape:
```

The parent session remains responsible for final judgment, integration,
verification, and user-facing claims.

### Error Collaboration Protocol

Use whenever a command fails, a test fails, a runtime error appears, generated
output is malformed, or an agent reports uncertainty that affects correctness.

```text
stop expansion -> preserve failure -> Bug Investigator reproduces/localizes
-> failing agent provides context -> domain agent fixes root cause
-> Test and Verification proves the fix -> Orchestrator final review
```

- Stop feature expansion and unrelated cleanup until the failure is understood.
- Preserve the failing command, exit code, traceback, log line, report path, or
  malformed output slice.
- Assign Bug Investigator as the temporary lead for reproduction and
  localization.
- Keep the agent that hit the error involved as the context owner: it should
  provide changed files, assumptions, recent commands, and observed symptoms.
- Assign the relevant domain agent to fix only the root cause after Bug
  Investigator has localized the layer.
- Assign Test and Verification to prove the failing path changed with a targeted
  command first, then broaden only when shared contracts changed.
- The Orchestrator Agent performs the final review and reports whether the
  original task is complete, blocked, or narrowed after the repair.

### Final Review Gate

Use before every completion claim.

- Confirm the original user request and the final scope still match.
- Confirm changed files are limited to the planned scope.
- Confirm delegated outputs were integrated or explicitly rejected with a reason.
- Confirm verification command, result, and evidence locator are recorded.
- Confirm trading, parameter, and data decisions cite DB, report, or log facts.
- Confirm any error repair followed the Error Collaboration Protocol.
- Report remaining risk instead of implying certainty where evidence is missing.

### Source Fidelity and Evidence Ledger

Use when facts may be stale, contested, high-impact, niche, or parameter-related.

- Prefer repo files, DB rows, generated reports, logs, official docs, or primary
  sources.
- Mark important claims as verified, inferred, unresolved, or stale-risk.
- For quntbot parameter changes, record the measured evidence in the response or
  relevant doc before changing values.
- If later evidence changes a conclusion, add a correction instead of silently
  replacing the previous reasoning.

Compact evidence row shape:

```text
claim:
status:
evidence:
source_type:
source_date:
access_date:
locator:
confidence:
gap_or_correction:
```

### Output Slicing

Use when output is too large to read safely.

- Error slice: failing command, diagnostic code, stack frame, nearby lines.
- Diff slice: changed files, hunk headers, risky hunks, public API changes.
- Search slice: exact matches, file paths, nearby context.
- JSON slice: schema keys, counts, selected rows, anomalies.
- Source slice: imports, public interfaces, target function, callers, tests.

Expand slices only by an explicit reason, such as caller depth, fixture path,
config path, or runtime entry point.

### Efficiency Observer

Use when judging whether the roster is improving workflow.

- Do not claim speed or token savings without comparable before/after evidence.
- Treat fewer files read as useful only if verification quality is unchanged.
- Track whether the selected lead agent reduced backtracking, prevented unsafe
  edits, or found the right verification faster.
- If classification overhead exceeds the task itself, use only Planner, the
  domain lead, and Test and Verification.

## Engineering Discipline Rules

These rules adapt the useful parts of `agent-skills-main` for quntbot. They are
lightweight operating checks, not a requirement to load every external skill.

### Incremental Implementation

Use for any multi-file feature, bug fix, refactor, or script change.

- Build one thin slice at a time.
- Keep each slice working and testable before expanding.
- Prefer risk-first slices when the hardest part is uncertain.
- Avoid writing more than roughly 100 changed lines before a meaningful check.
- Do not mix feature work, refactoring, formatting, and config changes unless
  they are required for the same behavior.
- Use safe defaults for new operational behavior, especially anything near KIS,
  credentials, schedulers, or order paths.

### Debugging Discipline

Use whenever tests fail, scripts error, logs show unexpected behavior, or the bot
does not match expectations.

```text
reproduce -> localize -> reduce -> fix root cause -> guard -> verify
```

- Stop adding features once a failure appears.
- Preserve the failing command, exit code, traceback, log line, or report path.
- Reproduce with the smallest command or input that shows the issue.
- Localize the failing layer: config, DB, collector, factor engine, signal
  parser, backtest, trading client, scheduler, script, or test.
- Fix the root cause rather than masking symptoms.
- Add or update a regression test when behavior changed or a bug was confirmed.

### Test and Proof Discipline

Use for behavior changes and bug fixes.

- Write or identify the test that proves the behavior.
- For bug fixes, prefer a failing regression test before the fix.
- Test outcomes, not internal call sequences, unless the sequence is the public
  contract.
- Prefer real implementations or focused fakes over broad mocks.
- Run targeted tests first; broaden only when shared modules or contracts changed.
- Documentation-only changes may use read-back and required-section search
  instead of Python tests.

### Review Discipline

Use before claiming a non-trivial change is ready.

Review across five axes:
- Correctness: requirements, edge cases, error paths, regressions.
- Readability: names, control flow, comments that explain why, no cleverness for
  its own sake.
- Architecture: local patterns, module boundaries, no unnecessary abstraction.
- Security: secrets, untrusted inputs, external API responses, logs.
- Performance: unbounded loops, expensive DB queries, repeated external calls.

If the review finds unrelated cleanup, note it separately rather than folding it
into the current change.

### Security and Boundary Discipline

Use for KIS, Telegram, DART, pykrx, files, environment variables, SQLite, logs,
and any external data source.

- Treat third-party API responses, Telegram messages, downloaded files, and logs
  as untrusted input.
- Validate or normalize external data at the boundary before it reaches scoring,
  ranking, reports, or order decisions.
- Never commit secrets, tokens, sessions, account numbers, or raw credentials.
- Mask sensitive identifiers in logs and final reports.
- Ask before adding a new external service, credential category, or permission.
- Keep order execution behind existing PAPER, preflight, stale-report, quote
  failure, and fallback-price gates.
- Do not add external execution, copy-trading, auto-follow, or platform-token
  integrations without explicit user approval, a separate design note, and
  Trading Safety Agent review.

### Trading Pipeline Safety Patterns

These rules adapt only the safe operational patterns from `AI-Trader-main`.
They do not import automated execution, copy-trading, or third-party platform
control into quntbot.

- Market-intel layers are read-only context providers. They may enrich research,
  event review, and candidate generation, but must not trigger orders or mutate
  portfolio state.
- Every order-adjacent path needs a pre-order validation checklist covering
  trade mode, market hours, ticker eligibility, quantity, price source, trade
  value, available cash, holdings, stale report dates, fallback prices, quote
  failures, and skipped tickers.
- External data providers should have visible retry, timeout, cooldown, and
  degraded-mode behavior. A provider failure should be reported as evidence, not
  silently converted into a confident trading signal.
- Heartbeat or polling loops are for readiness and notification state only. They
  should record last checked time, missed states, provider errors, and next safe
  command; they must not bypass dry-run or preflight gates.
- Execution pipeline changes must be reviewed in this order: Research or signal
  evidence, Strategy or portfolio effect, Trading Safety gates, Test and
  Verification proof.

### Interface and Contract Discipline

Use when changing module boundaries, scripts, dataclasses, database models,
report JSON, or CLI arguments.

- Define the contract before implementation.
- Prefer additive fields and optional arguments over breaking existing callers.
- Keep error semantics consistent within a module or script family.
- Document observable behavior that downstream scripts, tests, or reports depend
  on.
- Update tests and report readers together when changing output formats.

### Decision Documentation Discipline

Use when a decision affects strategy, parameters, schema, operations, order
safety, or future agent work.

- Record the reason, evidence, alternatives, and consequence in `progress.md`,
  `HANDOFF_FOR_AGENTS.md`, a `docs/superpowers/specs/*.md` file, or a focused
  decision note.
- Do not document obvious code; document the why behind choices that would be
  expensive to rediscover.
- When a decision is superseded, add a correction rather than deleting history.

### Memory Governance Rules

These rules adapt only the governance patterns from `agentmemory-main`. They do
not require installing a memory server, MCP service, hooks, or external runtime.

- Treat project memory as curated operational evidence, not a transcript dump.
- Save only durable, useful knowledge: verified decisions, repeated failure
  modes, user-approved constraints, file-specific warnings, runbook outcomes,
  and lessons that would prevent future backtracking.
- Do not save secrets, API keys, account identifiers, raw credentials, private
  user data, unredacted logs, or unverified investment conclusions.
- Before relying on remembered strategy, parameter, data, or order-safety
  context, re-check the current repo, DB, report, or logs.
- Mark remembered items as `active`, `stale`, `superseded`, or
  `delete-candidate` when their status changes.
- Prefer correction over silent replacement. If a previous memory was wrong,
  record what changed, when it changed, and the current source of truth.
- Forgetting is a governed action. Show what would be removed, get explicit user
  confirmation, and record the reason in a handoff, progress note, or focused
  decision note.
- Use a small context budget: retrieve only memory relevant to the current
  request, affected files, or selected agent role.
- Review accumulated memory periodically for noise, stale assumptions, repeated
  low-value notes, and sensitive data leakage risk.

## Agent Roles

### Orchestrator Agent

Use for every task as the central coordinator.

Responsibilities:
- Classify request type, task weight, and task shape before broad reading or
  editing.
- Select the lead agent, supporting agents, and verification path.
- Decide whether subagents should be dispatched, and assign disjoint ownership
  scopes when they are useful.
- Keep the main critical path moving while delegated work runs in parallel.
- Switch to the Error Collaboration Protocol when any failure appears.
- Integrate specialist outputs, resolve contradictions, and perform the Final
  Review Gate before reporting completion.

Required context:
- `docs/agent-roster.md`
- `AGENTS.md`
- `CLAUDE.md`
- `HANDOFF_FOR_AGENTS.md`
- `progress.md` or the relevant current-status artifact
- The target files or reports named by the selected lead agent

Output:
- A short orchestration note with request classification, task weight, selected
  agents, delegated work if any, planned verification, and final review result.

### Planner Agent

Use for every non-trivial task before editing.

Responsibilities:
- Convert the user request into a bounded task.
- Identify affected modules and required reads.
- Prevent unrelated refactors.
- Decide whether a design doc or implementation plan is needed.

Required context:
- `AGENTS.md`
- `CLAUDE.md`
- `HANDOFF_FOR_AGENTS.md`
- Any relevant `docs/superpowers/specs/*.md`
- The target source or script files

Output:
- A short plan, including scope, likely files, and verification command.

### Bug Investigator Agent

Use when an error, failing test, traceback, bad report, or inconsistent runtime
behavior appears.

Responsibilities:
- Reproduce or locate the failure before proposing a fix.
- Inspect logs, test failures, and recent generated reports.
- Separate root cause from symptoms.
- Hand off a minimal fix scope to the Planner Agent.

Primary files and data:
- `logs/`
- `progress.md`
- Relevant `tests/**/test_*.py`
- Relevant `scripts/*.py`
- Relevant `src/**/*.py`

Verification:
- A targeted failing test that turns green, or a smoke/log check that proves the
  failure path changed.

### Data and DB Agent

Use for data sync, schema, repository, SQLite, coverage, or metric availability
work.

Responsibilities:
- Inspect actual DB state before data-related decisions.
- Check schema and repository behavior together.
- Confirm counts, date ranges, missingness, and latest available rows.

Primary files and data:
- `data/quntbot.db`
- `src/data/models.py`
- `src/data/database.py`
- `src/data/repositories.py`
- `src/data/collectors.py`
- `tests/data/`

Verification:
- Repository tests, sync script smoke tests, or SQLite queries showing before and
  after facts.

### Signal Agent

Use for Telegram or Busanstock collection, parsing, scoring inputs, and channel
archive behavior.

Responsibilities:
- Preserve raw-message parsing rules.
- Keep network/API calls isolated behind readers.
- Verify parser behavior with representative fixtures before live channel checks.

Primary files:
- `src/signals/telegram_parser.py`
- `src/signals/telegram_reader.py`
- `src/signals/busanstock_parser.py`
- `src/signals/busanstock_reader.py`
- `tests/signals/`

Verification:
- Parser tests first, then smoke scripts only when credentials and environment
  allow it.

### Strategy and Factor Agent

Use for factor scoring, ranking, quality metrics, investor flow overlays,
weights, and selection behavior.

Responsibilities:
- Keep live ranking and backtest ranking consistent.
- Use DB/report evidence before changing weights or thresholds.
- Check missing-data policy and score normalization effects.

Primary files:
- `config.py`
- `src/factors/engine.py`
- `src/factors/scoring.py`
- `src/factors/models.py`
- `src/backtest/engine.py`
- `tests/factors/`
- `tests/backtest/`

Verification:
- Targeted factor tests, backtest tests, and when changing parameters, a small
  report comparing old and new outputs.

### Backtest Agent

Use for simulations, metrics, historical execution rules, stop loss, trailing
stop, and cost assumptions.

Responsibilities:
- Match operational trading rules as closely as the historical data allows.
- Make cost, slippage, and execution timing assumptions explicit.
- Avoid changing strategy assumptions without measured comparison.

Primary files:
- `src/backtest/engine.py`
- `src/backtest/metrics.py`
- `src/backtest/models.py`
- `scripts/run_phase3_backtest.py`
- `scripts/run_backtest_matrix.py`
- `tests/backtest/`

Verification:
- Targeted backtest tests plus a generated comparison artifact when assumptions
  or parameters change.

### Trading Safety Agent

Use for KIS API, orders, rebalance execution, scheduler order paths, and anything
that could place PAPER or LIVE orders.

Responsibilities:
- Confirm `TRADE_MODE=PAPER` unless the user explicitly asks for LIVE analysis.
- Prefer no-order dry runs and preflight checks.
- Verify that fallback prices, stale reports, and quote failures block execution.
- Validate quantity, price source, trade value, available cash, holdings, market
  hours, stale dates, skipped tickers, and external provider status before any
  order-adjacent change is considered safe.
- Reject external execution, copy-trading, auto-follow, or platform-token flows
  unless the user explicitly requests that design and the safety gates are
  updated first.
- Mask credentials and account identifiers in logs and reports.

Primary files and data:
- `config.py`
- `src/trading/kis_client.py`
- `src/trading/rebalancer.py`
- `src/trading/engine.py`
- `src/trading/scheduler.py`
- `scripts/dry_run_rebalance.py`
- `scripts/prepare_rebalance_for_execution.py`
- `scripts/execute_rebalance_from_dry_run.py`
- `scripts/check_rebalance_readiness.py`
- `data/dry_run_rebalance_latest.json`
- `tests/trading/`

Verification:
- Trading unit tests first.
- `scripts/check_rebalance_readiness.py` for no-order readiness.
- Live KIS smoke tests only when credentials, market state, and user intent make
  them appropriate.

### Research Brief Agent

Use for morning notes, pre-market summaries, overnight event review, signal
summaries, and concise research brief drafts.

Responsibilities:
- Summarize material developments before the trading day.
- Separate actionable events from routine noise.
- Tie Telegram, Busanstock, DART, KRX, DB, and report facts back to source
  locators.
- Treat market-intel feeds as read-only context that supports human review, not
  as an order trigger or final recommendation.
- Make uncertainty explicit when news, filings, or market data are incomplete.
- Produce analyst work product for review, not final investment advice.

Primary files and data:
- `src/signals/telegram_parser.py`
- `src/signals/busanstock_parser.py`
- `scripts/smoke_test_telegram_signals.py`
- `scripts/smoke_test_busanstock_signals.py`
- `data/quntbot.db`
- `progress.md`
- `logs/`

Output:
- Short Markdown brief with top developments, affected tickers, source locators,
  expected relevance, and open verification gaps.

Verification:
- Parser tests or DB/log checks for any signal-derived claims.
- Source Fidelity and Evidence Ledger rows for stale-risk or high-impact claims.

### Catalyst Agent

Use for earnings dates, disclosure events, sector/macro events, regulatory dates,
and recurring event calendars that could affect the ranking or rebalance review.

Responsibilities:
- Maintain a forward-looking event view for the current universe or target list.
- Mark each catalyst by date, ticker or sector, type, expected impact, and source.
- Verify time-sensitive events against primary or reliable current sources before
  they influence parameters or trading plans.
- Archive actual outcomes when available so future reviews can compare expected
  and realized impact.

Primary files and data:
- `data/quntbot.db`
- `data/*rebalance*`
- `logs/`
- `scripts/prepare_and_review_rebalance.py`
- `scripts/review_rebalance_reports.py`
- `progress.md`

Output:
- Calendar-style Markdown or CSV-ready table with event date, ticker or sector,
  event type, impact, source, and follow-up action.

Verification:
- DB/report checks for covered tickers.
- Fresh source check for event dates that could plausibly have changed.

### Idea Generation Agent

Use for stock screens, thematic sweeps, candidate lists, and review of names that
surface from factor ranking.

Responsibilities:
- Treat screens as candidate generation, not conclusions.
- Start from quntbot's actual universe, factor scores, and available DB coverage.
- Document screen criteria and measured counts at each filter step.
- Highlight what the model may be missing and what evidence is still needed.
- Hand candidates to Strategy and Factor Agent for score impact review and
  Trading Safety Agent for order-path gating.

Primary files and data:
- `config.py`
- `src/factors/engine.py`
- `src/factors/scoring.py`
- `scripts/rank_phase2_factors.py`
- `data/quntbot.db`
- `data/*backtest*`
- `tests/factors/`

Output:
- Candidate shortlist with factor evidence, catalyst notes, risks, and required
  next research checks.

Verification:
- SQLite queries, ranking script output, or generated backtest/report artifacts
  showing the candidate universe and filter counts.

### Portfolio Review Agent

Use for pre-trade and post-trade review of dry-run rebalance plans, allocation
drift, sell/buy rationale, cash usage, and report quality.

Responsibilities:
- Review proposed rebalance trades before any execution path is considered.
- Check target list, holdings, cash, skipped tickers, fallback prices, quote
  failures, stale reports, and expected date alignment.
- Compare before/after portfolio exposure using generated dry-run reports.
- Document rationale and residual risks for human review.
- Never execute orders; all order-path decisions remain behind Trading Safety
  Agent gates.

Primary files and data:
- `data/dry_run_rebalance_latest.json`
- `data/dry_run_rebalance_latest.md`
- `data/rebalance_comparison_latest.md`
- `scripts/dry_run_rebalance.py`
- `scripts/compare_rebalance_reports.py`
- `scripts/check_rebalance_readiness.py`
- `src/trading/rebalancer.py`
- `tests/trading/`

Output:
- Pre-trade or post-trade review summary with blockers, clean checks, changed
  positions, and next safe command.

Verification:
- `scripts/check_rebalance_readiness.py` for no-order readiness.
- Report comparison or JSON slice checks for fallback prices, quote failures, and
  stale dates.

### Operations Agent

Use for daily runbooks, scheduler behavior, generated reports, readiness checks,
archives, and handoff updates.

Responsibilities:
- Keep operational commands copy-pastable for Windows PowerShell.
- Preserve generated reports and logs that explain trading decisions.
- For heartbeat or polling style checks, record last checked time, missed states,
  provider errors, and next safe command without triggering execution.
- Update progress or handoff docs when operational state changes.

Primary files and data:
- `scripts/prepare_and_review_rebalance.py`
- `scripts/print_rebalance_operations_checklist.py`
- `scripts/archive_rebalance_run_bundle.py`
- `logs/`
- `data/*rebalance*`
- `progress.md`
- `HANDOFF_FOR_AGENTS.md`

Verification:
- Smoke tests, report existence checks, and log inspection.

### Test and Verification Agent

Use before claiming completion.

Responsibilities:
- Choose the narrowest meaningful verification first.
- Escalate to broader tests when shared modules changed.
- Record exact command and result.

Verification ladder:
- Markdown/docs only: read-back and required-section search.
- Python syntax: `.\venv\Scripts\python.exe -m compileall src scripts tests`
- Targeted tests: `.\venv\Scripts\python.exe -m pytest <target> -q`
- Full suite: `.\venv\Scripts\python.exe -m pytest -q`
- Operations: smoke script or generated log/report check.

### Docs and Handoff Agent

Use when changing docs, plans, progress, operational notes, or agent rules.

Responsibilities:
- Keep docs concise and action-oriented.
- Do not let docs drift from code paths and script names.
- Apply Memory Governance Rules when preserving or removing cross-session
  context.
- Note when git is unavailable and commits cannot be made.

Primary files:
- `AGENTS.md`
- `CLAUDE.md`
- `HANDOFF_FOR_AGENTS.md`
- `progress.md`
- `docs/superpowers/`
- `docs/agent-roster.md`

Verification:
- Read the edited document back.
- Search for required sections and stale placeholders.

## Request Classification Matrix

| Request type | Lead agent | Supporting agents |
| --- | --- | --- |
| Error, traceback, failing command | Bug Investigator | Planner, Test and Verification |
| DB counts, missing data, sync issue | Data and DB | Bug Investigator, Test and Verification |
| Factor score or ranking change | Strategy and Factor | Data and DB, Backtest, Test and Verification |
| Backtest assumption or metric change | Backtest | Strategy and Factor, Test and Verification |
| Rebalance, KIS, order, scheduler | Trading Safety | Operations, Test and Verification |
| Morning note, signal brief, pre-market summary | Research Brief | Signal, Source Fidelity, Test and Verification |
| Earnings/event/catalyst calendar | Catalyst | Research Brief, Data and DB, Source Fidelity |
| Stock screen or candidate generation | Idea Generation | Strategy and Factor, Data and DB, Backtest |
| Dry-run rebalance review | Portfolio Review | Trading Safety, Operations, Test and Verification |
| Telegram or Busanstock signal issue | Signal | Data and DB, Test and Verification |
| Runbook, report, archive, handoff | Operations | Docs and Handoff, Test and Verification |
| Documentation-only change | Docs and Handoff | Planner, Test and Verification |

## Efficiency Test Cases

Use these quick dry runs to decide whether this roster is helping:

1. KIS quote failures during dry run
   - Lead: Bug Investigator
   - Support: Trading Safety, Operations, Test and Verification
   - Expected first reads: `progress.md`, `scripts/dry_run_rebalance.py`,
     `scripts/check_rebalance_readiness.py`, `src/trading/kis_client.py`,
     `tests/trading/test_dry_run_rebalance.py`
   - Good outcome: no order-path edits before the no-order failure is understood.

2. Factor weight adjustment request
   - Lead: Strategy and Factor
   - Support: Data and DB, Backtest, Test and Verification
   - Expected first action: query DB or inspect generated score/backtest reports.
   - Good outcome: no parameter edit without measured before/after evidence.

3. New signal parser rule
   - Lead: Signal
   - Support: Data and DB, Test and Verification
   - Expected first reads: parser, reader, signal tests, DB model, relevant script.
   - Good outcome: parser fixture test changes before reader/network behavior.

4. Morning research brief from current signals
   - Lead: Research Brief
   - Support: Signal, Data and DB, Source Fidelity
   - Expected first reads: signal parsers, signal smoke tests, latest DB rows,
     progress notes, and relevant logs.
   - Good outcome: concise brief with source locators and explicit uncertainty,
     without order recommendations.

5. Rebalance report review before execution
   - Lead: Portfolio Review
   - Support: Trading Safety, Operations, Test and Verification
   - Expected first reads: latest dry-run JSON/Markdown, readiness script,
     rebalancer, comparison report, trading tests.
   - Good outcome: blockers and clean checks are clear before any execution
     command is considered.

If a task takes longer to classify than to fix, use Planner, the domain lead, and
Test and Verification only.
