# Exit Rebalance Strategy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the approved staged exit, rebalance buffer, minimum holding period, and score-weighted allocation strategy while preserving PAPER safety gates.

**Architecture:** Add explicit configuration and small pure helpers first, then wire them into rebalancing, backtesting, and PAPER trading in separate slices. Backtest support comes before changing operational defaults, and live/PAPER order paths remain behind existing daily limit, dry-run, preflight, quote failure, and stale-report gates.

**Tech Stack:** Python 3, dataclasses, pytest, SQLite/SQLAlchemy, existing quntbot trading/backtest modules.

---

## File Structure

- Modify `config.py`: add strategy parameters with conservative validation.
- Create `src/trading/allocation.py`: pure score-weight allocation helper.
- Create `src/trading/exit_state.py`: durable JSON-backed PAPER exit state.
- Modify `src/trading/rebalancer.py`: add rank-buffer sell eligibility and weighted buy sizing.
- Modify `src/trading/engine.py`: add staged PAPER exit monitor using durable state.
- Modify `src/trading/scheduler.py`: call the generalized exit monitor from the existing intraday stop job.
- Modify `src/backtest/engine.py`: simulate staged exits, rank buffer, minimum holding period, and score weighting.
- Modify `scripts/dry_run_rebalance.py`: pass target scores/rank buffer data into rebalancer and include allocation details in reports.
- Modify `scripts/run_phase3_backtest.py` and `scripts/run_backtest_matrix.py`: expose new strategy switches.
- Add/modify tests in `tests/trading/` and `tests/backtest/`.

## Implementation Notes

- Keep default trading mode PAPER-safe. Do not add LIVE execution behavior.
- Do not remove `REBALANCE_REQUIRE_DRY_RUN_PREFLIGHT`.
- The first implementation should use score-shifted weights for allocation:
  `weight_score = max(score - min_score, 0) + 1.0`. This is stable when scores are all positive, equal, or tightly clustered.
- Existing Korean comments in some files are mojibake in the current checkout. New code and comments should be ASCII unless surrounding text already requires Korean.
- Backtest can use fractional shares as it does today; PAPER order paths must use integer shares.

---

### Task 1: Add Config and Score-Weighted Allocation Helper

**Files:**
- Modify: `config.py`
- Create: `src/trading/allocation.py`
- Create: `tests/trading/test_allocation.py`

- [ ] **Step 1: Write allocation helper tests**

Create `tests/trading/test_allocation.py`:

```python
import pytest

from src.trading.allocation import compute_score_weights


def test_compute_score_weights_respects_min_and_max_caps():
    scores = [
        ("AAA", 100.0),
        ("BBB", 80.0),
        ("CCC", 60.0),
        ("DDD", 40.0),
    ]

    weights = compute_score_weights(scores, min_weight=0.03, max_weight=0.15)

    assert set(weights) == {"AAA", "BBB", "CCC", "DDD"}
    assert all(0.03 <= value <= 0.15 for value in weights.values())
    assert weights["AAA"] >= weights["BBB"] >= weights["CCC"] >= weights["DDD"]
    assert sum(weights.values()) == pytest.approx(0.60)


def test_compute_score_weights_normalizes_when_caps_do_not_bind():
    scores = [("AAA", 3.0), ("BBB", 2.0), ("CCC", 1.0)]

    weights = compute_score_weights(scores, min_weight=0.01, max_weight=0.80)

    assert sum(weights.values()) == pytest.approx(1.0)
    assert weights["AAA"] > weights["BBB"] > weights["CCC"]


def test_compute_score_weights_handles_equal_scores():
    scores = [("AAA", 5.0), ("BBB", 5.0), ("CCC", 5.0)]

    weights = compute_score_weights(scores, min_weight=0.03, max_weight=0.50)

    assert weights == pytest.approx({"AAA": 1 / 3, "BBB": 1 / 3, "CCC": 1 / 3})


def test_compute_score_weights_rejects_invalid_caps():
    with pytest.raises(ValueError, match="min_weight"):
        compute_score_weights([("AAA", 1.0)], min_weight=-0.01, max_weight=0.15)

    with pytest.raises(ValueError, match="max_weight"):
        compute_score_weights([("AAA", 1.0)], min_weight=0.03, max_weight=0.0)
```

- [ ] **Step 2: Run allocation tests and verify they fail**

Run:

```powershell
.\venv\Scripts\python.exe -m pytest tests\trading\test_allocation.py -q
```

Expected: fail because `src.trading.allocation` does not exist.

- [ ] **Step 3: Add config fields**

In `config.py`, update `PortfolioConfig`, `ExitRulesConfig`, and `RebalanceConfig`:

```python
@dataclass(frozen=True)
class PortfolioConfig:
    initial_capital: float = 100_000_000
    n_holdings: int = 20
    weighting: Literal["equal", "score_weighted"] = "score_weighted"
    min_position_weight: float = 0.03
    max_position_weight: float = 0.15
    enforce_price_filter: bool = True
    max_abs_open_gap_pct: float = 0.20
```

```python
@dataclass(frozen=True)
class ExitRulesConfig:
    stop_loss_pct: float = -0.05
    trailing_stop_pct: float = -0.10
    stop_cooldown_days: int = 0
    profit_take_pct: float = 0.20
    profit_take_sell_fraction: float = 0.50
    breakeven_stop_pct: float = 0.0
    use_rebalance_exit: bool = True
```

```python
@dataclass(frozen=True)
class RebalanceConfig:
    frequency: Literal["daily", "weekly", "monthly"] = "weekly"
    sell_rank_buffer: int = 30
    min_holding_trading_days: int = 2
```

Extend `validate_config()` with:

```python
if not 0 < PORTFOLIO.min_position_weight <= PORTFOLIO.max_position_weight <= 1:
    warnings.append("PORTFOLIO position weights must satisfy 0 < min <= max <= 1.")
if EXIT_RULES.profit_take_pct <= 0:
    warnings.append("EXIT_RULES.profit_take_pct must be positive.")
if not 0 < EXIT_RULES.profit_take_sell_fraction < 1:
    warnings.append("EXIT_RULES.profit_take_sell_fraction must be between 0 and 1.")
if REBALANCE.sell_rank_buffer < PORTFOLIO.n_holdings:
    warnings.append("REBALANCE.sell_rank_buffer must be >= PORTFOLIO.n_holdings.")
if REBALANCE.min_holding_trading_days < 0:
    warnings.append("REBALANCE.min_holding_trading_days must be zero or greater.")
```

- [ ] **Step 4: Implement allocation helper**

Create `src/trading/allocation.py`:

```python
from __future__ import annotations

from collections.abc import Iterable


def compute_score_weights(
    scores: Iterable[tuple[str, float]],
    *,
    min_weight: float,
    max_weight: float,
) -> dict[str, float]:
    items = [(ticker, float(score)) for ticker, score in scores]
    if not items:
        return {}
    if min_weight <= 0:
        raise ValueError("min_weight must be positive")
    if max_weight <= 0 or max_weight < min_weight:
        raise ValueError("max_weight must be >= min_weight and positive")
    if min_weight * len(items) > 1.0:
        raise ValueError("min_weight is too high for the number of scores")

    min_score = min(score for _, score in items)
    raw = {ticker: max(score - min_score, 0.0) + 1.0 for ticker, score in items}
    total_raw = sum(raw.values())
    weights = {ticker: value / total_raw for ticker, value in raw.items()}

    clamped: dict[str, float] = {}
    flexible = set(weights)
    remaining = 1.0

    while flexible:
        changed = False
        flexible_total = sum(weights[ticker] for ticker in flexible)
        if flexible_total <= 0:
            share = remaining / len(flexible)
            proposed = {ticker: share for ticker in flexible}
        else:
            proposed = {
                ticker: remaining * (weights[ticker] / flexible_total)
                for ticker in flexible
            }

        for ticker, weight in list(proposed.items()):
            if weight < min_weight:
                clamped[ticker] = min_weight
                remaining -= min_weight
                flexible.remove(ticker)
                changed = True
            elif weight > max_weight:
                clamped[ticker] = max_weight
                remaining -= max_weight
                flexible.remove(ticker)
                changed = True

        if not changed:
            clamped.update(proposed)
            flexible.clear()

        if remaining <= 0:
            break

    return {ticker: round(weight, 12) for ticker, weight in clamped.items() if weight > 0}
```

- [ ] **Step 5: Run allocation tests**

Run:

```powershell
.\venv\Scripts\python.exe -m pytest tests\trading\test_allocation.py -q
```

Expected: pass.

- [ ] **Step 6: Commit Task 1**

```powershell
git add config.py src\trading\allocation.py tests\trading\test_allocation.py
git commit -m "Add score weighted allocation settings"
```

---

### Task 2: Add Rebalance Rank Buffer and Weighted Buy Sizing

**Files:**
- Modify: `src/trading/rebalancer.py`
- Modify: `scripts/dry_run_rebalance.py`
- Modify: `tests/trading/test_rebalancer.py`
- Modify: relevant dry-run tests if failures identify report contract changes

- [ ] **Step 1: Write rebalancer tests**

Append to `tests/trading/test_rebalancer.py`:

```python
def test_rank_buffer_keeps_held_ticker_outside_buy_list_but_inside_sell_buffer():
    holdings = [
        {"ticker": "HELD", "name": "Held", "qty": 10, "avg_price": 1000, "current_price": 1000},
    ]

    sells, buys = compute_rebalance_orders(
        holdings=holdings,
        target_tickers=["NEW"],
        prices={"NEW": 1000},
        cash=10_000,
        portfolio=_portfolio(n=1),
        sell_eligible_tickers=[],
    )

    assert sells == []
    assert [order.ticker for order in buys] == ["NEW"]


def test_rank_buffer_sells_held_ticker_outside_sell_buffer():
    holdings = [
        {"ticker": "OLD", "name": "Old", "qty": 10, "avg_price": 1000, "current_price": 1000},
    ]

    sells, _ = compute_rebalance_orders(
        holdings=holdings,
        target_tickers=["NEW"],
        prices={"NEW": 1000},
        cash=10_000,
        portfolio=_portfolio(n=1),
        sell_eligible_tickers=["OLD"],
    )

    assert [order.ticker for order in sells] == ["OLD"]


def test_score_weighted_buy_sizing_uses_target_weights():
    holdings = []
    target = ["AAA", "BBB"]
    prices = {"AAA": 1000, "BBB": 1000}

    _, buys = compute_rebalance_orders(
        holdings=holdings,
        target_tickers=target,
        prices=prices,
        cash=100_000,
        portfolio=_portfolio(n=2),
        target_weights={"AAA": 0.70, "BBB": 0.30},
    )

    assert [(order.ticker, order.qty) for order in buys] == [("AAA", 70), ("BBB", 30)]
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
.\venv\Scripts\python.exe -m pytest tests\trading\test_rebalancer.py -q
```

Expected: fail because `compute_rebalance_orders()` has no `sell_eligible_tickers` or `target_weights` arguments.

- [ ] **Step 3: Extend rebalancer signature and sell logic**

In `src/trading/rebalancer.py`, change the signature:

```python
def compute_rebalance_orders(
    *,
    holdings: list[dict[str, Any]],
    target_tickers: list[str],
    prices: dict[str, int],
    previous_closes: dict[str, int | float] | None = None,
    cash: int,
    portfolio: PortfolioConfig = PORTFOLIO,
    sell_eligible_tickers: list[str] | set[str] | None = None,
    target_weights: dict[str, float] | None = None,
) -> tuple[list[RebalanceOrder], list[RebalanceOrder]]:
```

Replace the current `target_set` sell test with:

```python
    held_tickers = {h["ticker"] for h in holdings}
    target_set = set(target_tickers)
    sell_set = set(sell_eligible_tickers) if sell_eligible_tickers is not None else held_tickers - target_set

    sells: list[RebalanceOrder] = []
    expected_sell_proceeds = 0
    for h in holdings:
        if h["ticker"] in sell_set:
            sells.append(RebalanceOrder(
                ticker=h["ticker"],
                side="SELL",
                qty=h["qty"],
                reason=f"rebalance sell buffer exit (holding {h['qty']} shares)",
            ))
            expected_sell_proceeds += int(h.get("current_price", 0) or 0) * int(h["qty"])
```

- [ ] **Step 4: Extend buy sizing**

Replace equal `per_position` sizing with:

```python
    available_cash = cash + expected_sell_proceeds
    weights = target_weights or {}

    buys: list[RebalanceOrder] = []
    for ticker in buy_targets:
        price = prices.get(ticker, 0)
        if price <= 0:
            logger.warning(f"[rebalancer] {ticker} current price unavailable; buy skipped")
            continue

        previous_close = (previous_closes or {}).get(ticker)
        if is_execution_gap_too_large(
            execution_price=price,
            previous_close=previous_close,
            max_abs_gap_pct=portfolio.max_abs_open_gap_pct,
        ):
            gap_pct = (float(price) / float(previous_close)) - 1.0
            logger.warning(
                f"[rebalancer] {ticker} execution gap {gap_pct:.2%} exceeds "
                f"{portfolio.max_abs_open_gap_pct:.0%}; buy skipped"
            )
            continue

        if weights:
            budget = available_cash * max(weights.get(ticker, 0.0), 0.0)
        else:
            budget = available_cash / len(buy_targets)
        qty = math.floor(budget / price)
        if portfolio.enforce_price_filter and qty <= 0:
            logger.warning(
                f"[rebalancer] {ticker} price {price:,} exceeds budget {budget:,.0f}; buy skipped"
            )
            continue

        buys.append(RebalanceOrder(
            ticker=ticker,
            side="BUY",
            qty=qty,
            reason=f"target portfolio entry (budget {budget:,.0f} / {price:,} = {qty} shares)",
        ))
```

- [ ] **Step 5: Update dry-run script to compute buffer and weights**

In `scripts/dry_run_rebalance.py`:

Import:

```python
from config import KIS, PORTFOLIO, REBALANCE
from src.trading.allocation import compute_score_weights
```

After `scores = score_func(...)`, compute:

```python
    target_scores = scores[:args.top_n]
    buffer_scores = scores[:max(args.top_n, REBALANCE.sell_rank_buffer)]
    target_tickers = [score.ticker for score in target_scores]
    buffer_tickers = {score.ticker for score in buffer_scores}
```

Before calling `compute_rebalance_orders()`:

```python
    held_tickers = {holding["ticker"] for holding in holdings}
    sell_eligible_tickers = sorted(held_tickers - buffer_tickers)
    target_weights = {}
    if PORTFOLIO.weighting == "score_weighted":
        target_weights = compute_score_weights(
            [(score.ticker, score.total_score) for score in target_scores],
            min_weight=PORTFOLIO.min_position_weight,
            max_weight=PORTFOLIO.max_position_weight,
        )
```

Pass:

```python
    sells, buys = compute_rebalance_orders(
        holdings=holdings,
        target_tickers=target_tickers,
        prices=prices,
        previous_closes=previous_closes,
        cash=cash,
        sell_eligible_tickers=sell_eligible_tickers,
        target_weights=target_weights,
    )
```

- [ ] **Step 6: Add allocation details to reports**

Extend `_format_markdown_report()` and `_format_json_report()` with a `target_weights` argument. Markdown should add a `target_weight` column to target portfolio rows. JSON target rows should include `"target_weight": target_weights.get(score.ticker, 0.0)`.

- [ ] **Step 7: Run rebalancer and dry-run tests**

Run:

```powershell
.\venv\Scripts\python.exe -m pytest tests\trading\test_rebalancer.py tests\test_generate_agent_ops_dashboard.py -q
```

Expected: pass after updating report assertions only where they depend on exact order reason text or target schema.

- [ ] **Step 8: Commit Task 2**

```powershell
git add src\trading\rebalancer.py scripts\dry_run_rebalance.py tests\trading\test_rebalancer.py tests\test_generate_agent_ops_dashboard.py
git commit -m "Add rebalance buffer and weighted buy sizing"
```

---

### Task 3: Implement Backtest Strategy Simulation

**Files:**
- Modify: `src/backtest/engine.py`
- Modify: `tests/backtest/test_backtest_engine.py`
- Modify: `scripts/run_phase3_backtest.py`
- Modify: `scripts/run_backtest_matrix.py`
- Modify: `tests/backtest/test_run_script.py`

- [ ] **Step 1: Write backtest staged exit tests**

Append to `tests/backtest/test_backtest_engine.py`:

```python
def test_run_backtest_takes_half_profit_at_twenty_percent_next_open():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    seed_single_stock_prices(
        engine,
        [
            (date(2026, 1, 1), 100, 100),
            (date(2026, 1, 2), 100, 121),
            (date(2026, 1, 3), 122, 122),
        ],
    )

    result = run_backtest(
        engine,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 3),
        scoring_func=score_always_aaa,
        initial_capital=10_000,
        top_n=1,
        commission_rate=0.0,
        tax_rate_kospi=0.0,
        tax_rate_kosdaq=0.0,
        slippage_rate=0.0,
        stop_loss_pct=-0.05,
        profit_take_pct=0.20,
        profit_take_sell_fraction=0.50,
    )

    sells = [trade for trade in result.trades if trade.side == "SELL"]
    assert len(sells) == 1
    assert sells[0].reason == "profit_take_20"
    assert sells[0].date == date(2026, 1, 3)
    assert sells[0].quantity == pytest.approx(50.0)


def test_run_backtest_post_profit_trailing_bucket_sells_independently():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    seed_single_stock_prices(
        engine,
        [
            (date(2026, 1, 1), 100, 100),
            (date(2026, 1, 2), 100, 121),
            (date(2026, 1, 3), 122, 130),
            (date(2026, 1, 4), 116, 116),
            (date(2026, 1, 5), 115, 118),
        ],
    )

    result = run_backtest(
        engine,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 5),
        scoring_func=score_always_aaa,
        initial_capital=10_000,
        top_n=1,
        commission_rate=0.0,
        tax_rate_kospi=0.0,
        tax_rate_kosdaq=0.0,
        slippage_rate=0.0,
        stop_loss_pct=-0.05,
        profit_take_pct=0.20,
        trailing_stop_pct=-0.10,
    )

    reasons = [trade.reason for trade in result.trades if trade.side == "SELL"]
    assert reasons == ["profit_take_20", "post_profit_trailing_stop"]


def test_run_backtest_post_profit_breakeven_bucket_sells_at_entry():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    seed_single_stock_prices(
        engine,
        [
            (date(2026, 1, 1), 100, 100),
            (date(2026, 1, 2), 100, 121),
            (date(2026, 1, 3), 122, 130),
            (date(2026, 1, 4), 101, 101),
            (date(2026, 1, 5), 99, 100),
        ],
    )

    result = run_backtest(
        engine,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 5),
        scoring_func=score_always_aaa,
        initial_capital=10_000,
        top_n=1,
        commission_rate=0.0,
        tax_rate_kospi=0.0,
        tax_rate_kosdaq=0.0,
        slippage_rate=0.0,
        stop_loss_pct=-0.05,
        profit_take_pct=0.20,
    )

    reasons = [trade.reason for trade in result.trades if trade.side == "SELL"]
    assert reasons == ["profit_take_20", "post_profit_breakeven_stop"]
```

- [ ] **Step 2: Write rebalance buffer/min-holding backtest tests**

Append:

```python
def test_rebalance_buffer_keeps_rank_just_outside_top_n():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    seed_prices_for_tickers(engine, ["AAA", "BBB"], start=date(2026, 1, 1), days=5, price=100)

    def score_func(_engine, *, as_of_date):
        if as_of_date <= date(2026, 1, 2):
            return [
                FactorScore("AAA", "AAA", "KOSPI", as_of_date, 1, 0, 1, 0, 0, 10.0, 1),
                FactorScore("BBB", "BBB", "KOSPI", as_of_date, 1, 0, 1, 0, 0, 9.0, 2),
            ]
        return [
            FactorScore("BBB", "BBB", "KOSPI", as_of_date, 1, 0, 1, 0, 0, 10.0, 1),
            FactorScore("AAA", "AAA", "KOSPI", as_of_date, 1, 0, 1, 0, 0, 9.0, 2),
        ]

    result = run_backtest(
        engine,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 5),
        scoring_func=score_func,
        initial_capital=10_000,
        top_n=1,
        sell_rank_buffer=2,
        rebalance_frequency="daily",
        commission_rate=0.0,
        tax_rate_kospi=0.0,
        tax_rate_kosdaq=0.0,
        slippage_rate=0.0,
    )

    assert [trade.reason for trade in result.trades if trade.side == "SELL"] == []


def test_rebalance_min_holding_blocks_early_rebalance_sell():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    seed_prices_for_tickers(engine, ["AAA", "BBB"], start=date(2026, 1, 1), days=6, price=100)

    def score_func(_engine, *, as_of_date):
        if as_of_date <= date(2026, 1, 2):
            return [FactorScore("AAA", "AAA", "KOSPI", as_of_date, 1, 0, 1, 0, 0, 10.0, 1)]
        return [FactorScore("BBB", "BBB", "KOSPI", as_of_date, 1, 0, 1, 0, 0, 10.0, 1)]

    result = run_backtest(
        engine,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 6),
        scoring_func=score_func,
        initial_capital=10_000,
        top_n=1,
        sell_rank_buffer=1,
        min_holding_trading_days=2,
        rebalance_frequency="daily",
        commission_rate=0.0,
        tax_rate_kospi=0.0,
        tax_rate_kosdaq=0.0,
        slippage_rate=0.0,
    )

    sells = [trade for trade in result.trades if trade.side == "SELL" and trade.reason == "rebalance"]
    assert sells[0].date >= date(2026, 1, 5)
```

If `seed_prices_for_tickers` does not exist, add this helper near existing test seed helpers and ensure `timedelta` is imported from `datetime`:

```python
def seed_prices_for_tickers(engine, tickers, *, start: date, days: int, price: int) -> None:
    with session_scope(engine) as session:
        upsert_stocks(session, [{"ticker": ticker, "name": ticker, "market": "KOSPI"} for ticker in tickers])
        rows = []
        for offset in range(days):
            price_date = start + timedelta(days=offset)
            for ticker in tickers:
                rows.append({"ticker": ticker, "date": price_date, "open": price, "close": price})
        upsert_daily_prices(session, rows)
```

- [ ] **Step 3: Run backtest tests and verify failures**

Run:

```powershell
.\venv\Scripts\python.exe -m pytest tests\backtest\test_backtest_engine.py -q
```

Expected: fail because `run_backtest()` does not accept `profit_take_pct`, `sell_rank_buffer`, or `min_holding_trading_days`.

- [ ] **Step 4: Extend `run_backtest()` signature**

In `src/backtest/engine.py` add arguments:

```python
    profit_take_pct: float = EXIT_RULES.profit_take_pct,
    profit_take_sell_fraction: float = EXIT_RULES.profit_take_sell_fraction,
    breakeven_stop_pct: float = EXIT_RULES.breakeven_stop_pct,
    sell_rank_buffer: int = REBALANCE.sell_rank_buffer,
    min_holding_trading_days: int = REBALANCE.min_holding_trading_days,
    weighting: str = PORTFOLIO.weighting,
    min_position_weight: float = PORTFOLIO.min_position_weight,
    max_position_weight: float = PORTFOLIO.max_position_weight,
```

Add dictionaries:

```python
    profit_taken: set[str] = set()
    trailing_bucket_qty: dict[str, float] = {}
    breakeven_bucket_qty: dict[str, float] = {}
    trading_day_index_by_date = {value: idx for idx, value in enumerate(trading_dates)}
```

- [ ] **Step 5: Implement pending partial exits**

Change `pending_stops` to:

```python
    pending_exits: list[tuple[str, str, float | None]] = []
```

Use `None` quantity for full exits. For partial exits, pass a quantity. When a partial sell executes, subtract the sold quantity from `positions[ticker]` instead of popping the whole position. Only pop entry/peak/bucket state when the remaining position is `<= 1e-9`.

- [ ] **Step 6: Implement close-based trigger checks**

Replace the current stop check block with:

```python
        if enable_stops:
            for ticker in list(positions):
                if ticker not in close_prices:
                    continue
                close = close_prices[ticker]
                peak_prices[ticker] = max(peak_prices.get(ticker, close), close)
                entry = entry_prices.get(ticker)
                if entry is None:
                    continue
                return_from_entry = (close / entry) - 1.0
                loss_from_peak = (close / peak_prices[ticker]) - 1.0
                if ticker not in profit_taken:
                    if return_from_entry <= stop_loss_pct:
                        pending_exits.append((ticker, "stop_loss", None))
                    elif return_from_entry >= profit_take_pct:
                        sell_qty = positions[ticker] * profit_take_sell_fraction
                        if sell_qty > 0:
                            pending_exits.append((ticker, "profit_take_20", sell_qty))
                            profit_taken.add(ticker)
                            remaining_qty = positions[ticker] - sell_qty
                            trailing_bucket_qty[ticker] = remaining_qty * 0.50
                            breakeven_bucket_qty[ticker] = remaining_qty - trailing_bucket_qty[ticker]
                else:
                    trail_qty = trailing_bucket_qty.get(ticker, 0.0)
                    breakeven_qty = breakeven_bucket_qty.get(ticker, 0.0)
                    if trail_qty > 0 and loss_from_peak <= trailing_stop_pct:
                        pending_exits.append((ticker, "post_profit_trailing_stop", trail_qty))
                        trailing_bucket_qty[ticker] = 0.0
                    if breakeven_qty > 0 and return_from_entry <= breakeven_stop_pct:
                        pending_exits.append((ticker, "post_profit_breakeven_stop", breakeven_qty))
                        breakeven_bucket_qty[ticker] = 0.0
```

- [ ] **Step 7: Implement rebalance buffer and minimum holding in backtest**

When scores are available:

```python
            ranked_tickers = [
                score.ticker
                for score in scores
                if score.ticker in open_prices and score.ticker not in forbidden_today
                and cooldown_until.get(score.ticker, date.min) < trading_date
                and not is_execution_gap_too_large(
                    execution_price=open_prices[score.ticker],
                    previous_close=previous_close_prices.get(score.ticker),
                    max_abs_gap_pct=PORTFOLIO.max_abs_open_gap_pct,
                )
            ]
            target_tickers = ranked_tickers[:target_count]
            keep_tickers = set(ranked_tickers[:max(target_count, sell_rank_buffer)])
```

When selling existing positions for rebalance:

```python
            held_days = trading_day_index_by_date[trading_date] - trading_day_index_by_date[entry_dates[ticker]]
            if ticker not in keep_tickers and held_days >= min_holding_trading_days and ticker in open_prices:
                ...
```

- [ ] **Step 8: Implement weighted allocation in backtest buys**

Import `compute_score_weights`. If `weighting == "score_weighted"`, compute weights from `scores[:target_count]` and set `target_value = equity_before_buys * weights.get(ticker, 0.0)`. Otherwise preserve equal-weight behavior.

- [ ] **Step 9: Add CLI flags**

In both backtest scripts add parser arguments:

```python
parser.add_argument("--profit-take-pct", type=float, default=EXIT_RULES.profit_take_pct)
parser.add_argument("--profit-take-sell-fraction", type=float, default=EXIT_RULES.profit_take_sell_fraction)
parser.add_argument("--breakeven-stop-pct", type=float, default=EXIT_RULES.breakeven_stop_pct)
parser.add_argument("--sell-rank-buffer", type=int, default=REBALANCE.sell_rank_buffer)
parser.add_argument("--min-holding-trading-days", type=int, default=REBALANCE.min_holding_trading_days)
parser.add_argument("--weighting", choices=("equal", "score_weighted"), default=PORTFOLIO.weighting)
```

Pass the values into `run_backtest_func(...)`.

- [ ] **Step 10: Run targeted backtest tests**

Run:

```powershell
.\venv\Scripts\python.exe -m pytest tests\backtest\test_backtest_engine.py tests\backtest\test_run_script.py -q
```

Expected: pass.

- [ ] **Step 11: Commit Task 3**

```powershell
git add src\backtest\engine.py scripts\run_phase3_backtest.py scripts\run_backtest_matrix.py tests\backtest\test_backtest_engine.py tests\backtest\test_run_script.py
git commit -m "Simulate staged exits and buffered rebalance"
```

---

### Task 4: Add PAPER Exit State and Generalized Exit Monitor

**Files:**
- Create: `src/trading/exit_state.py`
- Modify: `src/trading/engine.py`
- Modify: `src/trading/scheduler.py`
- Modify: `tests/trading/test_engine.py`
- Modify: `tests/trading/test_scheduler.py`

- [ ] **Step 1: Write exit state tests**

Create `tests/trading/test_exit_state.py`:

```python
from pathlib import Path

from src.trading.exit_state import ExitStateStore


def test_exit_state_store_round_trips_position_state(tmp_path: Path):
    store = ExitStateStore(tmp_path / "exit_state.json")

    state = store.get_or_create(
        ticker="005930",
        entry_price=100_000,
        qty=10,
        entry_date="2026-05-19",
    )
    state.profit_take_done = True
    state.trailing_qty = 2
    state.breakeven_qty = 3
    state.peak_price = 125_000
    store.save_position(state)

    loaded = store.load()["005930"]
    assert loaded.profit_take_done is True
    assert loaded.trailing_qty == 2
    assert loaded.breakeven_qty == 3
    assert loaded.peak_price == 125_000
```

- [ ] **Step 2: Implement exit state store**

Create `src/trading/exit_state.py`:

```python
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class PositionExitState:
    ticker: str
    entry_price: float
    entry_date: str
    original_qty: int
    profit_take_done: bool = False
    trailing_qty: int = 0
    breakeven_qty: int = 0
    peak_price: float = 0.0


class ExitStateStore:
    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> dict[str, PositionExitState]:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        return {
            ticker: PositionExitState(**payload)
            for ticker, payload in raw.items()
        }

    def save(self, states: dict[str, PositionExitState]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps({ticker: asdict(state) for ticker, state in states.items()}, indent=2),
            encoding="utf-8",
        )

    def get_or_create(
        self,
        *,
        ticker: str,
        entry_price: float,
        qty: int,
        entry_date: str,
    ) -> PositionExitState:
        states = self.load()
        state = states.get(ticker)
        if state is None or state.original_qty != qty or abs(state.entry_price - entry_price) > 1e-9:
            state = PositionExitState(
                ticker=ticker,
                entry_price=entry_price,
                entry_date=entry_date,
                original_qty=qty,
                peak_price=entry_price,
            )
            states[ticker] = state
            self.save(states)
        return state

    def save_position(self, state: PositionExitState) -> None:
        states = self.load()
        states[state.ticker] = state
        self.save(states)

    def prune(self, held_tickers: set[str]) -> None:
        states = {
            ticker: state
            for ticker, state in self.load().items()
            if ticker in held_tickers
        }
        self.save(states)
```

- [ ] **Step 3: Write engine staged exit tests**

Append to `tests/trading/test_engine.py`:

```python
def test_check_exit_rules_takes_half_profit_once(tmp_path):
    engine = _make_engine(stop_loss_pct=-0.05)
    engine._exit_state_store = ExitStateStore(tmp_path / "exit_state.json")
    engine._client.get_holdings.return_value = [
        {"ticker": "005930", "name": "Samsung", "qty": 10, "avg_price": 100_000, "current_price": 121_000}
    ]

    first = engine.check_exit_rules()
    second = engine.check_exit_rules()

    assert first == ["005930"]
    assert second == []
    engine._client.place_order.assert_called_once_with("005930", qty=5, price=0, side="SELL")


def test_check_exit_rules_full_stops_before_profit_take(tmp_path):
    engine = _make_engine(stop_loss_pct=-0.05)
    engine._exit_state_store = ExitStateStore(tmp_path / "exit_state.json")
    engine._client.get_holdings.return_value = [
        {"ticker": "005930", "name": "Samsung", "qty": 10, "avg_price": 100_000, "current_price": 94_000}
    ]

    triggered = engine.check_exit_rules()

    assert triggered == ["005930"]
    engine._client.place_order.assert_called_once_with("005930", qty=10, price=0, side="SELL")
```

Add import:

```python
from src.trading.exit_state import ExitStateStore
```

- [ ] **Step 4: Wire state store into `TradingEngine`**

In `src/trading/engine.py` import:

```python
import math
from src.trading.exit_state import ExitStateStore
```

Extend `__init__`:

```python
        exit_state_path: Path | None = None,
```

Set:

```python
        self._exit_state_store = ExitStateStore(exit_state_path or (DATA_DIR / "exit_state.json"))
```

- [ ] **Step 5: Add `check_exit_rules()`**

Add a method that:

1. Calls `_reset_if_new_day()` and `_check_halted()`.
2. Loads holdings.
3. Prunes exit state to held tickers.
4. For each holding, creates/loads state from `avg_price`, `qty`, and `self._today.isoformat()`.
5. Evaluates `-5%` full stop before profit-taking.
6. Evaluates `+20%` first profit take with `math.floor(qty * 0.50)`.
7. After first profit take, updates peak and sells trailing bucket at `-10%`.
8. Sells breakeven bucket when current price is `<= avg_price`.
9. Saves state after every successful state change.

Use reason-specific log text, but route all orders through `self.sell(...)` so daily sell limits and halt checks still apply.

- [ ] **Step 6: Keep old stop methods as compatibility wrappers**

Change `check_stop_loss()` and `check_trailing_stop()` only if needed for compatibility. Prefer leaving them in place for tests, and have scheduler use `check_exit_rules()` instead.

- [ ] **Step 7: Update scheduler**

In `src/trading/scheduler.py`, change `_stop_loss_job()` body to:

```python
def _stop_loss_job(engine: TradingEngine) -> None:
    """Intraday staged exit monitor."""
    try:
        if engine.check_daily_loss_limit():
            logger.error("Daily loss limit exceeded. Trading is halted today.")
            return
        triggered = engine.check_exit_rules()
        if triggered:
            logger.warning(f"[Intraday exits] sells executed: {triggered}")
    except Exception as exc:
        logger.exception(f"Exit monitor failed: {exc}")
```

Keep the scheduler job id `intraday_stop_loss` for backward compatibility unless tests require a rename.

- [ ] **Step 8: Run trading tests**

Run:

```powershell
.\venv\Scripts\python.exe -m pytest tests\trading\test_exit_state.py tests\trading\test_engine.py tests\trading\test_scheduler.py -q
```

Expected: pass.

- [ ] **Step 9: Commit Task 4**

```powershell
git add src\trading\exit_state.py src\trading\engine.py src\trading\scheduler.py tests\trading\test_exit_state.py tests\trading\test_engine.py tests\trading\test_scheduler.py
git commit -m "Add staged paper exit monitor"
```

---

### Task 5: Run Strategy Comparison Reports and Final Verification

**Files:**
- Generated: `data/backtest_exit_rebalance_strategy_2026-05-19.csv`
- Generated: `data/backtest_exit_rebalance_strategy_2026-05-19.md`
- Modify if useful: `progress.md`

- [ ] **Step 1: Run targeted test suite**

Run:

```powershell
.\venv\Scripts\python.exe -m pytest tests\trading tests\backtest -q
```

Expected: pass.

- [ ] **Step 2: Run compile check**

Run:

```powershell
.\venv\Scripts\python.exe -m compileall src scripts tests
```

Expected: command exits `0`.

- [ ] **Step 3: Generate comparison matrix**

Run:

```powershell
.\venv\Scripts\python.exe scripts\run_backtest_matrix.py --top-ns 20 --rebalance-frequencies weekly --cost-scenarios custom --stop-loss-pct -0.05 --trailing-stop-pct -0.10 --profit-take-pct 0.20 --profit-take-sell-fraction 0.50 --sell-rank-buffer 30 --min-holding-trading-days 2 --weighting score_weighted --output-csv data\backtest_exit_rebalance_strategy_2026-05-19.csv --output-md data\backtest_exit_rebalance_strategy_2026-05-19.md
```

Expected: writes both report files and exits `0`.

- [ ] **Step 4: Generate no-order dry-run report**

Run:

```powershell
.\venv\Scripts\python.exe scripts\dry_run_rebalance.py --as-of-date 2026-05-19 --top-n 20 --output-json data\dry_run_rebalance_latest.json --output-md data\dry_run_rebalance_latest.md --quote-retries 4 --quote-delay-sec 0.5
```

Expected: `dry_run=true`, no order-execution function is called, and the report includes `target_weight` per target.

- [ ] **Step 5: Run readiness check**

Run:

```powershell
.\venv\Scripts\python.exe scripts\check_rebalance_readiness.py --dry-run-json data\dry_run_rebalance_latest.json --expected-date 2026-05-19
```

Expected: no orders are submitted. If market time is closed, `market_time_status=blocked` is acceptable as long as preflight checks are clean.

- [ ] **Step 6: Record measured decision evidence**

If backtest and dry-run reports are clean, append a concise entry to `progress.md`:

```markdown
## 2026-05-19 Exit/Rebalance Strategy Implementation Evidence

- Implemented staged exits: -5% full stop, +20% 50% profit take, post-profit trailing and breakeven buckets.
- Implemented rebalance buffer: top 20 buy list, top 30 sell buffer, 2 trading-day minimum holding period.
- Implemented score-weighted allocation with 3% minimum and 15% maximum target weights.
- Backtest report: `data/backtest_exit_rebalance_strategy_2026-05-19.md`.
- Dry-run report: `data/dry_run_rebalance_latest.json`.
- Readiness command: `.\venv\Scripts\python.exe scripts\check_rebalance_readiness.py --dry-run-json data\dry_run_rebalance_latest.json --expected-date 2026-05-19`.
```

- [ ] **Step 7: Commit final verification artifacts**

```powershell
git add data\backtest_exit_rebalance_strategy_2026-05-19.csv data\backtest_exit_rebalance_strategy_2026-05-19.md data\dry_run_rebalance_latest.json data\dry_run_rebalance_latest.md progress.md
git commit -m "Record exit rebalance strategy evidence"
```

If any generated report contains secrets, account identifiers, or raw credentials, do not stage it. Redact or omit it and document the omission in the final response.

---

## Final Review Checklist

- [ ] `-5%` full stop is proven in backtest and PAPER engine tests.
- [ ] `+20%` first profit take runs once per open position.
- [ ] Post-profit trailing and breakeven buckets can exit independently.
- [ ] Rebalance keeps held tickers ranked `21` through `30`.
- [ ] Rebalance sell waits for `2` trading days unless a risk/profit exit fires.
- [ ] Score-weighted allocation respects `3%` and `15%` caps.
- [ ] Dry-run/preflight gates still block fallback prices, quote failures, stale reports, and daily order limit violations.
- [ ] Backtest comparison report numbers are cited before claiming the new strategy is better.
