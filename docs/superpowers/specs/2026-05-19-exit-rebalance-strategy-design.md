# Exit, Rebalance, and Allocation Strategy Design

## Status

- Date: 2026-05-19
- Status: approved for implementation planning
- Scope: design only. No strategy parameters or order paths are changed by this
  document.

## Goal

Reduce unnecessary sell frequency while adding clearer risk and profit
management:

- Cut losing positions faster before losses deepen.
- Take partial profits when a position reaches a meaningful gain.
- Let a remaining winner continue with trailing-stop protection.
- Reduce rebalance churn by using a rank buffer and a short minimum holding
  period.
- Move from fixed equal cash allocation toward score-weighted allocation with
  explicit concentration limits.

## Current Baseline

The current baseline uses:

- Stop loss: sell all at `-8%` from entry.
- Trailing stop: sell all at `-10%` from post-entry peak.
- Rebalance frequency: weekly.
- Rebalance sell rule: sell held tickers that are no longer in the target list.
- Target holdings: `20`.
- Current config includes `weighting = "equal"` and a dormant
  `score_weighted` option.

## New Exit Strategy

### Pre-Profit-Take State

For each open position, track an exit state. Before any profit-taking has
occurred:

- If current return from average entry price is `<= -5%`, sell the full
  position.
- If current return from average entry price is `>= +20%`, sell `50%` of the
  current position and mark first profit-taking as completed.

The `+20%` first profit-taking action must run at most once per ticker for the
current open position.

### Post-Profit-Take State

After the first `+20%` profit-taking sale, the remaining position is divided into
two logical buckets:

- Trailing bucket: `50%` of the remaining shares.
- Breakeven bucket: `50%` of the remaining shares.

Given the first sale removes half the original position, each bucket is roughly
`25%` of the original entry quantity, subject to integer share rounding.

Post-profit-take exits:

- Trailing bucket: sell when current price is `<= 10%` below the post-entry
  peak price. This keeps the existing trailing stop threshold.
- Breakeven bucket: sell when current price is at or below the average entry
  price.

### Rounding

All live order quantities must be whole shares.

Recommended rounding policy:

- First profit take: sell `floor(current_qty * 0.50)`.
- If the computed sale quantity is zero, skip the partial sale.
- For the remaining quantity, allocate `floor(remaining_qty * 0.50)` to the
  trailing bucket and the rest to the breakeven bucket.
- Never create an order with quantity `<= 0`.

### Priority

For a single monitoring pass, evaluate exits in this order:

1. Full stop loss before profit-taking: `-5%`.
2. First profit take: `+20%`.
3. Post-profit-take trailing bucket.
4. Post-profit-take breakeven bucket.

This avoids conflicting full-stop and partial-profit orders in the same pass.

## New Rebalance Strategy

### Rank Buffer

Use a buy list and a wider sell threshold:

- Buy candidates: top `20` ranked tickers.
- Keep buffer: held tickers ranked `1` through `30` remain eligible to hold.
- Rebalance sell candidates: held tickers ranked outside top `30`.

This replaces immediate rebalance selling when a held ticker drops out of the
top `20`.

### Minimum Holding Period

Add a `2` trading-day minimum holding period for rebalance exits:

- A newly bought ticker cannot be sold by the rebalance rule until it has been
  held for at least `2` trading days.
- The minimum holding period only blocks rebalance exits.
- Risk exits and profit exits still run during the minimum holding period:
  `-5%` stop, `+20%` first profit take, post-profit trailing, and breakeven.

## New Allocation Strategy

Move target allocation from equal-weight to score-weighted with caps:

- Target holdings: `20`.
- Weighting mode: `score_weighted`.
- Minimum target weight per selected ticker: `3%`.
- Maximum target weight per selected ticker: `15%`.
- Weights must sum to no more than deployable cash.
- If a ticker cannot buy at least one share under its target allocation and the
  existing price filter is enabled, skip that buy.

### Score Weighting Rule

Use a transparent formula rather than discretionary manual weighting.

Recommended formula:

1. Convert the selected top `20` scores into positive score weights.
2. Normalize the score weights to sum to `100%`.
3. Clamp each ticker to `[3%, 15%]`.
4. Redistribute leftover or excess weight across unclamped tickers.
5. If all tickers are clamped and a residual remains, leave the residual as cash
   rather than forcing an unsafe overweight.

The implementation plan should decide whether to use raw positive scores,
rank-inverted scores, or shifted scores after checking current score
distribution in generated reports or DB-backed ranking output.

## State Requirements

The new exit strategy needs durable per-position state, not only in-memory
checks:

- Ticker.
- Entry price or average entry price used for exit thresholds.
- Entry date.
- Original entry quantity.
- Current logical bucket quantities.
- Whether first `+20%` profit take has completed.
- Peak price used by trailing bucket.
- Last updated date/time.

The design should support PAPER operation first. LIVE behavior is out of scope
unless explicitly approved later.

## Safety Requirements

- Keep all order paths behind existing PAPER, dry-run, preflight, quote failure,
  fallback price, stale-report, daily buy/sell limit, and daily loss gates.
- Do not bypass `REBALANCE_REQUIRE_DRY_RUN_PREFLIGHT`.
- Do not place orders from tests or design scripts.
- Do not use fallback prices for live order sizing.
- Log and notify partial exits with enough detail to distinguish first profit
  take, trailing bucket, breakeven bucket, full stop loss, and rebalance exit.

## Backtest Requirements

Before changing default live parameters, run a backtest comparison that includes
at least:

- Baseline current strategy.
- New exit strategy only.
- New rebalance buffer only.
- New allocation strategy only.
- Combined new strategy.

Compare:

- Total return.
- CAGR.
- Max drawdown.
- Sharpe ratio.
- Win rate.
- Average holding days.
- Trade count.
- Sell count by reason.
- Turnover or an equivalent churn proxy.

The final parameter decision must cite generated report numbers.

## Implementation Boundaries

Expected affected areas:

- `config.py`: new parameters for profit take, stop loss, rebalance buffer,
  minimum holding period, and allocation caps.
- `src/trading/engine.py`: live PAPER exit monitoring and order execution
  behavior.
- `src/trading/rebalancer.py`: rank-buffer sell rules and score-weighted target
  allocation.
- `src/backtest/engine.py`: historical simulation for partial exits,
  post-profit buckets, rebalance buffer, minimum holding period, and weighted
  allocation.
- `scripts/run_phase3_backtest.py` and `scripts/run_backtest_matrix.py`: CLI
  switches for strategy experiments.
- `tests/backtest/` and `tests/trading/`: regression coverage.

Out of scope:

- LIVE trading enablement.
- New external data providers.
- Changing factor scoring weights.
- Changing the universe filters.
- Removing dry-run or readiness gates.

## Open Implementation Decisions

These are intentionally deferred to implementation planning and must be resolved
with code and data inspection:

- Exact storage location for durable exit state.
- Whether backtest should model partial fills or assume full fills at the next
  available execution price.
- Whether live PAPER exit checks should run in the existing intraday stop job or
  a renamed generalized exit monitor.
- Whether weighted allocation should rebalance existing held quantities toward
  target weights or only size new buys initially.

## Acceptance Criteria

- Tests prove `-5%` stop sells the full pre-profit position.
- Tests prove `+20%` first profit take sells only once.
- Tests prove post-profit trailing bucket and breakeven bucket can exit
  independently.
- Tests prove held tickers ranked `21` through `30` are not sold by rebalance.
- Tests prove held tickers outside top `30` are sold only after the `2`
  trading-day minimum holding period.
- Tests prove risk/profit exits ignore the rebalance minimum holding period.
- Tests prove score-weighted allocation respects `3%` minimum and `15%` maximum
  target weights.
- Backtest/report output includes sell reasons detailed enough to compare churn
  and risk behavior against baseline.
