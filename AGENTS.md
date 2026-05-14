# quntbot Agent Instructions

This file keeps only the top-level operating rules. Use
`docs/agent-roster.md` as the source of truth for agent roles, delegation,
error collaboration, and final review.

## Required Rules

- At task start, read `docs/agent-roster.md` and classify the request through
  the Orchestrator Agent.
- The Orchestrator Agent chooses the request type, task weight, lead/support
  agents, subagent delegation, and verification path before implementation.
- Before modifying code, read at least five related files. For docs-only,
  review-only, or tiny no-edit tasks, follow the efficiency rule in
  `docs/agent-roster.md` and gather the smallest evidence set that still proves
  the claim.
- Do not answer from guesswork. If unsure, verify with `rg`, Grep, Read, DB
  queries, logs, or generated reports.
- Before implementation, state a short plan and intended scope.
- Make one focused change at a time. Do not mix unrelated refactors,
  formatting, or cleanup with the requested work.
- After a change, verify it with the narrowest meaningful path first: syntax or
  AST check, targeted tests, log inspection, or report read-back.
- Parameter, strategy, data, and trading decisions must cite actual DB, log, or
  report numbers before values change.
- Order, KIS, rebalance, and scheduler execution paths must keep PAPER safety,
  no-order dry runs, and readiness gates ahead of any execution path.

## Agent Operating Principles

- The Orchestrator Agent owns classification, assignment, integration review,
  final review, and user-facing reporting for every task.
- Specialist agents own evidence gathering, implementation, or analysis inside
  their assigned scope.
- Use subagents aggressively when there are two or more independent,
  non-blocking work items with disjoint ownership.
- If an error appears, stop expansion. Bug Investigator reproduces and
  localizes the failure. The agent that encountered the error provides context.
  The relevant domain agent fixes only the root cause.
- Test and Verification proves the repair, then Orchestrator reviews the final
  result before reporting completion.
