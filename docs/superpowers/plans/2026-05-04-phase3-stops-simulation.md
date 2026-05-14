# Phase 3 Stop-Loss / Trailing-Stop Simulation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 백테스트 엔진(`src/backtest/engine.py`)에 손절(`EXIT_RULES.stop_loss_pct = -0.08`)과 트레일링 스톱(`EXIT_RULES.trailing_stop_pct = -0.10`)을 추가해, 실제 운영 룰과 백테스트 결과를 일치시킨다.

**Prerequisite:** `docs/superpowers/plans/2026-05-03-environment-recovery.md` 의 모든 Task 가 완료되어 `.venv` 에서 `pytest` 가 정상 동작해야 함.

**Plan dependencies:**
- Must run after: `docs/superpowers/plans/2026-05-03-environment-recovery.md`
- Should run after: `docs/superpowers/plans/2026-05-04-cost-parameters-recheck.md`, so stop simulation uses the corrected tax assumptions from the start.
- Independent from: `docs/superpowers/plans/2026-05-04-phase1-quality-fundamentals.md`
- Independent from: `docs/superpowers/plans/2026-05-04-phase2-quality-score.md`, except that better rankings will later change backtest inputs.
- Recommended commit scope: one commit for stop/trailing tests, one commit for backtest engine implementation, one commit for CLI/spec updates.

**Background:** 기존 spec(`2026-05-03-phase3-backtest-engine-design.md`) 은 "baseline rebalancing 동작 후 stop 추가"라고 명시. 이 plan이 그 후속.

**Architecture:**
- `positions: dict[str, float]` 외에 다음 두 dict 추가:
  - `entry_prices: dict[str, float]` — 매수 시 단위가 (수수료/슬리피지 포함 평균 단가)
  - `peak_prices: dict[str, float]` — 매 trading_date 마다 max(close) 갱신
- 매 trading_date 의 흐름:
  1. 모든 보유 종목의 close 로 `peak_prices` 갱신
  2. **이전 영업일에 트리거된 stop 매도(pending_stops)** 를 **오늘 시가**로 체결 (보수적·실현 가능 가정).
  3. **오늘 종가 기준**으로 새로운 stop 트리거 판정 → `pending_stops` 큐에 추가 (체결은 다음 영업일 시가).
  4. 리밸런싱 매도/매수.

**일중 체크 한계와 트리거→체결 분리 결정:**
- 우리는 일봉만 가짐. 장중 -8% 도달 후 -3% 회복 같은 시나리오는 시뮬 불가.
- **결정**: 트리거 비교는 **종가 기준**, 체결가는 **다음 영업일 시가**. 이는 실제 봇이 "장 마감 후 종가 신호 → 다음날 개장 시 시가 매도" 흐름과 일치하므로 운영-백테스트 일관성을 우선.
- 마지막 영업일에 트리거된 경우 다음날 데이터가 없으므로 **같은 날 종가로 fallback 매도** + `BacktestTrade.reason="stop_loss_close_fallback"` (또는 `"trailing_stop_close_fallback"`).
- `daily_prices.open` 컬럼이 필요 — 기존 `_load_close_prices` 를 확장해 close + open 둘 다 로딩.
- **재진입 금지**: 같은 날 stop 매도된 종목은 그날 리밸런싱 매수에서 제외(현실적 제약: 같은 날 손절 후 즉시 재매수는 의미 없음). `forbidden_today: set[str]` 로 표현. pending → 체결도 체결 당일 재진입 금지.
- **동시 트리거 우선순위**: 같은 종목에서 stop_loss와 trailing_stop이 같은 종가에 동시에 충족되면 `stop_loss`를 우선한다. 손절은 최초 매수가 대비 원금 방어 규칙이고, 트레일링은 수익 보호 규칙이므로 리스크 관리상 손절 reason을 남긴다. 코드에서는 `loss_from_entry <= stop_loss_pct` 조건을 먼저 검사하고, 그 조건이 거짓일 때만 `loss_from_peak <= trailing_stop_pct` 조건을 검사한다.
- **재진입 금지 범위**: 1차 구현에서는 "체결 당일만" 재진입 금지한다. N영업일 cooldown은 도입하지 않는다. cooldown은 성과와 거래 빈도에 큰 영향을 주는 별도 전략 파라미터이므로, 실데이터 백테스트 결과를 본 뒤 후속 plan으로 결정한다.

**Trade reason 확장:** 기존 "rebalance" 외에 "stop_loss", "trailing_stop", "stop_loss_close_fallback", "trailing_stop_close_fallback" 추가. `BacktestTrade.reason` 은 이미 자유 문자열이므로 모델 변경 없음.

**Toggle:** 운영 룰 비활성 백테스트도 비교용으로 가능하게 `run_backtest(enable_stops: bool = True)` 매개변수 추가. 기본은 True.

**Tech Stack:** Python 3.12, SQLAlchemy, pandas, pytest, SQLite.

---

### Task 1: open 컬럼 로딩 추가 + 회귀 보장

**Files:**
- Edit: `src/backtest/engine.py`
- Read: `src/data/models.py`
- Read: `tests/backtest/test_backtest_engine.py`

- [ ] **Step 1: 가격 로더 확장**

기존 `_load_close_prices` 를 `_load_prices(engine, *, start_date, end_date) -> dict[(ticker, date), dict[str, float]]` 형태로 확장한다. 예를 들어 `("005930", date(2026, 5, 1))` 키의 값은 `{"open": 70000.0, "close": 71000.0}` 형태가 되어야 한다.

- [ ] **Step 2: 호출부 회귀 통과 보장**

기존 리밸런싱 로직은 close 만 사용한다. `_load_prices` 반환값을 `float` 에서 `{"open": 70000.0, "close": 71000.0}` 같은 dict 로 바꾸면 다음 호출부 3곳을 함께 고쳐야 한다.

1. `trading_date` 루프 초반의 `available_prices` 생성부
   - 기존: `{ticker: price for (ticker, price_date), price in prices.items() if price_date == trading_date}`
   - 변경 후: close 전용 dict 를 만들거나, `today_prices` dict 에서 `p["close"]` 를 꺼내 리밸런싱 로직에 전달해야 한다.
2. 리밸런싱 매수 전 equity 계산부
   - 기존: `_positions_value(positions, available_prices)`
   - 변경 후: `_positions_value` 가 close dict 를 받도록 호출부에서 close 값만 넘기거나, `_positions_value` 내부에서 `prices[ticker]["close"]` 를 읽도록 바꿔야 한다.
3. equity_curve 기록부
   - 기존: `positions_value = _positions_value(positions, available_prices)`
   - 변경 후: 위 2번과 같은 방식으로 close 기준 평가액을 유지해야 한다.

회귀 기준: stop 기능을 켜기 전에도 기존 리밸런싱 테스트가 그대로 통과해야 하며, 기존 buy/sell 가격은 모두 close 기준으로 동일해야 한다.

Run: `.\.venv\Scripts\python.exe -m pytest tests/backtest -q -p no:cacheprovider`

Expected: 기존 테스트 그대로 PASS. 회귀 없음.

---

### Task 2: 실패 테스트 작성

**Files:**
- Edit: `tests/backtest/test_backtest_engine.py`

- [ ] **Step 1: seed_prices 헬퍼에 open 추가**

기존 `seed_prices` 의 `upsert_daily_prices` 호출에 `"open": 100.0`처럼 명시적인 open 값을 추가한다. 기존 테스트는 open 값을 직접 assert 하지 않으므로, 회귀용 fixture에서는 close와 같은 값으로 두고 stop 테스트 fixture에서만 의도된 open 값을 따로 둔다.

- [ ] **Step 2: 손절 시나리오 테스트 추가**

`test_run_backtest_triggers_stop_loss_and_executes_next_open`:
- 1종목(AAA), 5일치. 1일차 매수가 100, 2~3일차 close 95→90, 4일차 close 88, 4일차 open 89, 5일차 open 86.
- top_n=1, scoring_func 항상 AAA 1위, `stop_loss_pct=-0.10` (단순화).
- 4일차 close 88 → 매수가 100 대비 -12% → stop_loss 트리거.
- **5일차 open 86 으로 SELL 체결**, reason="stop_loss".
- 5일차에는 보유가 없어야 함 (재진입 금지).

- [ ] **Step 3: 트레일링 스톱 시나리오 테스트 추가**

`test_run_backtest_triggers_trailing_stop_after_peak_drop`:
- 1종목(AAA), 5일치. close 100 → 110 → 120 → 105 (peak=120 시점에 105 = -12.5%).
- 4일차 close 105 → trailing_stop 트리거. **5일차 open 으로 SELL 체결**.

- [ ] **Step 4: 손절과 트레일링 동시 트리거 우선순위 테스트**

`test_run_backtest_prefers_stop_loss_when_both_stops_trigger`:
- 1종목(AAA), 5일치.
- 매수가 100, 이후 peak 130, 트리거일 close 88.
- 매수가 대비 -12%이므로 stop_loss 조건 충족, peak 대비 약 -32%이므로 trailing_stop 조건도 충족.
- 다음 영업일 open 으로 SELL 체결하되 `reason=="stop_loss"` 여야 한다.

- [ ] **Step 5: 마지막 영업일 fallback 테스트**

`test_run_backtest_triggers_stop_on_last_day_uses_close_fallback`:
- 1종목, 마지막 영업일 close 가 -10% 이상 빠짐. 다음날 데이터 없음 → 같은날 close 로 SELL, reason 끝에 "_close_fallback" 포함.

- [ ] **Step 6: 체결 당일 재진입 금지 테스트**

`test_run_backtest_does_not_reenter_stopped_ticker_same_day`:
- stop 매도가 오늘 open에 체결된 종목이 같은 날 scoring_func에서 계속 1위로 나오더라도, 그날 리밸런싱 매수에서는 제외되는지 검증한다.
- 다음 영업일부터는 별도 cooldown이 없으므로 다시 후보가 될 수 있다. 이 동작은 1차 구현의 명시 정책이다.

- [ ] **Step 7: enable_stops=False 회귀 테스트**

`test_run_backtest_disable_stops_keeps_old_behavior`:
- 위 손절 시나리오와 같은 데이터에서 `enable_stops=False` → stop SELL 발생하지 않음.

- [ ] **Step 8: 실패 확인**

Run: `.\.venv\Scripts\python.exe -m pytest tests/backtest/test_backtest_engine.py -q -p no:cacheprovider`

Expected: 새 테스트들이 FAIL — engine 미구현.

---

### Task 3: engine.py 에 stop 트래킹 + 다음날 시가 체결 도입

**Files:**
- Edit: `src/backtest/engine.py`

- [ ] **Step 1: 시그니처 확장**

```python
def run_backtest(
    engine: Engine,
    *,
    start_date: date,
    end_date: date,
    scoring_func: ScoreFunction = calculate_factor_scores,
    initial_capital: float | None = None,
    top_n: int | None = None,
    commission_rate: float = COST.commission_rate,
    tax_rate_kospi: float = COST.tax_rate_kospi,
    tax_rate_kosdaq: float = COST.tax_rate_kosdaq,
    slippage_rate: float = COST.slippage_rate,
    enable_stops: bool = True,
    stop_loss_pct: float = EXIT_RULES.stop_loss_pct,
    trailing_stop_pct: float = EXIT_RULES.trailing_stop_pct,
) -> BacktestResult:
```

`from config import EXIT_RULES` 추가.

- [ ] **Step 2: 매수 시 entry_price/peak_price 기록**

기존 매수 블록에서:
```python
entry_prices[ticker] = (gross_amount + cost) / quantity
peak_prices[ticker] = price
```

(주의: 기존 `entry_values[ticker]` 는 청산 시 trade_return 계산에 쓰이므로 유지. 새 dict 둘은 별도.)

- [ ] **Step 3: trading_date 흐름 재배치**

```python
pending_stops: list[tuple[str, str]] = []  # (ticker, reason) — 이전 영업일에 트리거된 stop, 오늘 open 으로 체결

for trading_date in trading_dates:
    today_prices = {t: prices[(t, trading_date)] for (t, d) in prices if d == trading_date}
    if not today_prices:
        continue

    forbidden_today: set[str] = set()

    # 1) pending_stops 를 오늘 시가로 체결
    if enable_stops:
        for ticker, reason in pending_stops:
            if ticker not in today_prices or ticker not in positions:
                continue
            open_price = today_prices[ticker]["open"]
            cash, trade, trade_return, holding_days = _sell_position(
                ticker=ticker,
                quantity=positions.pop(ticker),
                price=open_price,
                trade_date=trading_date,
                cash=cash,
                market=markets.get(ticker, ""),
                entry_date=entry_dates.pop(ticker),
                entry_value=entry_values.pop(ticker),
                commission_rate=commission_rate,
                tax_rate_kospi=tax_rate_kospi,
                tax_rate_kosdaq=tax_rate_kosdaq,
                slippage_rate=slippage_rate,
                reason=reason,
            )
            entry_prices.pop(ticker, None)
            peak_prices.pop(ticker, None)
            trades.append(trade)
            closed_trade_returns.append(trade_return)
            closed_holding_days.append(holding_days)
            forbidden_today.add(ticker)
        pending_stops.clear()

    # 2) 오늘 종가로 새 stop 트리거 판정 → pending_stops 추가 (다음날 체결)
    available_close = {t: p["close"] for t, p in today_prices.items()}
    if enable_stops:
        for ticker in list(positions):
            if ticker not in available_close:
                continue
            close = available_close[ticker]
            peak_prices[ticker] = max(peak_prices.get(ticker, close), close)
            entry = entry_prices.get(ticker)
            if entry is None:
                continue
            loss_from_entry = (close / entry) - 1.0
            loss_from_peak = (close / peak_prices[ticker]) - 1.0
            if loss_from_entry <= stop_loss_pct:
                pending_stops.append((ticker, "stop_loss"))
            elif loss_from_peak <= trailing_stop_pct:
                pending_stops.append((ticker, "trailing_stop"))

    # 3) 리밸런싱 매도/매수 (기존 로직). 단, forbidden_today 종목은 매수에서 제외.
    scores = scoring_func(engine, as_of_date=trading_date)
    target_tickers = [
        score.ticker
        for score in scores
        if score.ticker in available_close and score.ticker not in forbidden_today
    ][:target_count]

    # 기존 리밸런싱 매도 블록은 available_close를 가격 dict로 사용한다.
    # 기존 리밸런싱 매수 블록도 price = available_close[ticker] 를 사용한다.
    # 즉 stop 도입 후에도 리밸런싱 가격 기준은 close로 유지한다.
```

- [ ] **Step 4: 마지막 영업일 fallback 처리**

루프 종료 후, `pending_stops` 가 남아있으면 마지막 trading_date 의 close 로 강제 매도하고 reason 에 `"_close_fallback"` suffix.

- [ ] **Step 5: 통과 확인**

Run: `.\.venv\Scripts\python.exe -m pytest tests/backtest/test_backtest_engine.py -q -p no:cacheprovider`

Expected: PASS.

---

### Task 4: 비용 인터랙션 회귀 테스트

**Files:**
- Edit: `tests/backtest/test_backtest_engine.py`

- [ ] **Step 1: stops + costs 결합 테스트**

`test_stops_with_costs_reduces_equity_more_than_no_stop`:
- 같은 가격 시퀀스에서 enable_stops=True 가 enable_stops=False 보다 거래 횟수가 더 많고, 비용 비율 0이 아닐 때 final_equity 가 다르게 나오는지 검증.

- [ ] **Step 2: 통과 확인**

Run: `.\.venv\Scripts\python.exe -m pytest tests/backtest/test_backtest_engine.py -q -p no:cacheprovider`

Expected: PASS.

---

### Task 5: spec 문서 보강

**Files:**
- Create: `docs/superpowers/specs/2026-05-04-phase3-stops-simulation-design.md`

- [ ] **Step 1: 결정 기록**

위 Architecture 절(일중 체크 한계, 종가 트리거 + 다음날 시가 체결, 마지막 영업일 fallback, 재진입 금지, enable_stops 토글)을 정리해 spec 문서로 저장. 향후 분봉 데이터로 업그레이드할 경우 무엇을 바꿔야 하는지 한 문단 추가.

Expected: spec 문서 생성.

---

### Task 6: 전체 검증

- [ ] **Step 1: 전체 테스트**

Run: `.\.venv\Scripts\python.exe -m pytest tests/data tests/factors tests/backtest -q -p no:cacheprovider`

Expected: PASS.

- [ ] **Step 2: AST 체크**

Run: `.\.venv\Scripts\python.exe -m py_compile config.py src/backtest/engine.py src/backtest/models.py src/backtest/metrics.py scripts/run_phase3_backtest.py`

Expected: 종료 코드 0.

- [ ] **Step 3: 스크립트 help 확인**

Run: `.\.venv\Scripts\python.exe scripts/run_phase3_backtest.py --help`

Expected: 도움말 출력. `--enable-stops / --disable-stops` 플래그도 추가하고 도움말에 노출.
