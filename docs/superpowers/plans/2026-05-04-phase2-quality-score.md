# Phase 2 Quality Score Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 현재 `src/factors/engine.py:39` 에서 `raw["quality_score"] = 0.0` 으로 비어있는 자리를 ROE / 영업이익률 / 부채비율 z-score 평균으로 채워, 3-팩터가 실제로 3-팩터로 동작하게 만든다.

**Prerequisites:**
- `docs/superpowers/plans/2026-05-03-environment-recovery.md` 의 모든 Task 가 완료되어 `.venv` 에서 `pytest` 가 정상 동작해야 함.
- `docs/superpowers/plans/2026-05-04-phase1-quality-fundamentals.md` 가 먼저 완료되어 `quality_metrics` 테이블이 존재하고, 일부 종목에 분기 데이터가 들어있어야 함.

**Plan dependencies:**
- Must run after: `docs/superpowers/plans/2026-05-03-environment-recovery.md`
- Must run after: `docs/superpowers/plans/2026-05-04-phase1-quality-fundamentals.md`
- Should run before: Phase 4 trading logic, because live candidate ranking must use the final 3-factor score.
- Independent from: `docs/superpowers/plans/2026-05-04-phase3-stops-simulation.md`
- Recommended commit scope: one commit for quality score spec/tests, one commit for factor engine implementation/logging.

**Architecture:**
- `_load_factor_inputs` 가 종목별로 `as_of_date` 이전 가장 최근 `QualityMetric` 한 행을 함께 조회해 `roe / operating_margin / debt_ratio` 컬럼을 raw DataFrame에 추가.
- `calculate_factor_scores` 에서 위 3개를 각각 `score_series` 로 점수화 (ROE/영업이익률은 higher_is_better=True, 부채비율은 higher_is_better=False).
- `quality_score = mean(roe_score, opm_score, debt_score)` — value_score 가 PER/PBR 평균이듯 같은 패턴.
- `roe`와 `operating_margin`은 Phase 1 quality plan에서 저장한 TTM 기준 값을 사용한다. 단일 분기 값은 계절성이 크므로 점수 계산에 직접 쓰지 않는다. `debt_ratio`는 최신 분기 재무상태표 스냅샷 값을 사용한다.
- 결측 처리: `pandas.DataFrame.mean(axis=1)` 이 NaN 자동 제외 → 3개 중 일부만 결측이면 사용 가능한 점수의 평균이 자동으로 산출됨. **3개 모두 결측이면 quality_score=NaN**.
- 최종 ranking 단계의 `dropna(subset=["value_score", "momentum_score", "total_score"])` 는 그대로 유지. quality_score 가 NaN 이면 total_score 도 NaN 이 되도록 동작 검증 필요(기존 `combine_scores` 가 `fillna(0.0)` 처리하므로 그렇지 않음 → 이 부분은 정책 결정 필요, Task 1 spec 에서 확정).

**자동 다운그레이드(quality_min_coverage)는 도입하지 않음:**
- mean(axis=1) 으로 부분 결측은 이미 우아하게 처리됨.
- 자동 fallback 은 동작이 암시적이 되어 "왜 점수가 이상하지" 디버깅이 어려워짐. 사용자가 데이터 부족을 모른 채 매매 결정하는 위험이 더 큼.
- 대신 **engine 시작 시 quality 커버리지를 명시 로그로 출력**해 사용자가 직접 인지하게 함 (Task 4).

**Decisions to record:**
- 부채비율 outlier: 1차 구현에서는 winsorize 하지 않고 z-score 그대로 사용한다. 단, z-score 는 평균과 표준편차를 사용하므로 극단적인 부채비율이 다른 종목들의 점수 분포를 압축하거나 왜곡할 수 있다. 이 리스크를 spec 에 명시하고, Task 2 테스트에 "극단값이 있어도 부채비율 낮은 종목이 높은 점수를 받는 최소 방향성"을 검증한다. winsorize/clip 은 실데이터 분포를 본 뒤 별도 후속 작업으로 결정한다.
- ROE/영업이익률 기간 정의: Phase 1에서 계산된 TTM 값만 사용한다. ROE는 `TTM 당기순이익 / 평균자본총계`, 영업이익률은 `TTM 영업이익 / TTM 매출액`이다. Phase 2는 이 값들을 재계산하지 않고 저장된 값을 점수화한다.
- ROE 음수: 그대로 z-score (낮은 점수). `require_positive` 사용 X — 적자 기업도 비교 대상.
- `as_of_date` 매칭: `published_at <= as_of_date` 인 가장 최근 한 행. published_at 이 NULL 이면 `fiscal_year/quarter` 분기 종료일 + 45일을 가상 published_at 으로 사용.
- 3개 모두 결측 종목: total_score 산출에서 quality_score 결측을 어떻게 다룰지 — Task 1 spec 단계에서 (a) NaN 으로 두고 ranking 에서 제외 또는 (b) `combine_scores` 가 0 처리(현 동작) 중 결정. 현재 `src/factors/scoring.py`의 `combine_scores`는 각 컴포넌트에 `fillna(0.0)`을 적용하므로, quality_score가 NaN이어도 total_score에는 중립점 0으로 반영된다. 이 현 동작을 유지할지 바꿀지 명시적으로 결정해야 한다.

**Tech Stack:** Python 3.12, pandas, SQLAlchemy, pytest, SQLite, loguru.

---

### Task 1: spec 보강 및 결측 정책 확정

**Files:**
- Read: `src/factors/engine.py`
- Read: `src/factors/scoring.py`
- Read: `tests/factors/test_engine.py`
- Read: `docs/superpowers/specs/2026-05-03-phase2-factor-engine-design.md`
- Create: `docs/superpowers/specs/2026-05-04-phase2-quality-score-design.md`

- [ ] **Step 1: 결측 정책 결정과 spec 작성**

위 Architecture / Decisions 절을 정리해 spec 문서로 저장. 특히 다음 두 결정을 명시:
1. quality 3개 모두 결측인 종목의 처리 방식 (NaN 유지 vs 0 fallback).
2. `as_of_date` 와 `published_at` 매칭 로직(45일 가상화 포함).
3. `combine_scores`의 `fillna(0.0)` 정책을 유지할지 변경할지. 유지한다면 "quality 데이터가 없는 종목은 quality 컴포넌트만 중립점 0으로 계산되고, value/momentum으로 계속 랭킹될 수 있다"는 의미를 spec과 테스트에 명시한다. 변경한다면 `combine_scores`를 건드리는 shared behavior 변경이므로 기존 value/momentum 결측 테스트까지 함께 갱신한다.

Expected: 후속 단계의 동작이 spec 한 군데서 확인 가능.

---

### Task 2: 실패 테스트 작성 (test_engine.py 보강)

**Files:**
- Edit: `tests/factors/test_engine.py`

- [ ] **Step 1: 기존 단언 변경**

`tests/factors/test_engine.py:53` 의 `assert all(score.quality_score == 0.0 for score in scores)` 를 제거하고, 대신 quality 데이터가 시드되지 않은 시나리오에서는 quality_score 가 Task 1 에서 정한 정책대로 (NaN 또는 0) 동작하는지 명시적으로 검증.

- [ ] **Step 2: 새 테스트 추가 — quality 시드 케이스**

`test_quality_score_ranks_high_roe_low_debt_higher`:
- 3종목 시드, ROE 15%/3%/-2%, 영업이익률 10%/5%/0%, 부채비율 50%/120%/300% 로 차등.
- ROE와 영업이익률 fixture 값은 TTM 계산이 이미 끝난 결과값으로 취급한다. Phase 2 테스트는 TTM 환산 자체를 검증하지 않는다.
- 우량 종목이 가장 높은 quality_score 를 받는지 단언.
- value/momentum 데이터를 동일하게 두면 total ranking 도 quality_score 순으로 결정되는지 단언.

`test_quality_score_partial_metrics_uses_available_subset`:
- ROE 만 있고 나머지는 NULL 인 케이스 → 해당 종목 quality_score = roe_score (다른 두 점수의 평균이 아니라 사용 가능한 점수의 평균).

`test_quality_score_debt_ratio_outlier_preserves_direction`:
- 부채비율 50% / 120% / 3000% 같이 극단값이 있는 케이스를 시드한다.
- z-score 분포가 압축될 수 있다는 점은 허용하되, `higher_is_better=False` 적용 후 부채비율이 낮은 종목의 `debt_score`가 높은 종목보다 커야 한다는 최소 방향성을 단언한다.
- 이 테스트는 winsorize 를 도입하지 않는 1차 구현의 안전장치이며, outlier 영향을 제거한다는 의미는 아니다.

`test_quality_score_all_missing_follows_policy`:
- quality_metrics 테이블에 데이터 없음 → Task 1 spec에서 정한 정책대로 동작.
- 현 `combine_scores(fillna(0.0))` 정책을 유지하기로 결정했다면, quality 3개가 모두 결측이어도 total_score가 NaN이 되지 않고 quality 컴포넌트만 0점으로 처리되는지 단언한다.
- 반대로 NaN 유지 정책을 선택했다면, 이 테스트는 해당 종목이 ranking에서 제외되는지 단언해야 한다.

- [ ] **Step 3: 실패 확인**

Run: `.\.venv\Scripts\python.exe -m pytest tests/factors/test_engine.py -q -p no:cacheprovider`

Expected: 새 테스트 3건 FAIL (현재 quality_score=0.0 하드코딩이라 차등 비교 못 함), 기존 테스트 변경분 일부 FAIL.

---

### Task 3: engine.py 구현

**Files:**
- Edit: `src/factors/engine.py`

- [ ] **Step 1: `_load_factor_inputs` 에 quality_metrics 조회 추가**

각 종목마다 `as_of_date` 이전 가장 최근 `QualityMetric` 한 행을 가져와 `roe / operating_margin / debt_ratio` 컬럼으로 raw DataFrame 에 추가. 결측은 그대로 NaN 유지.

```python
quality = session.scalars(
    select(QualityMetric)
    .where(QualityMetric.ticker == stock.ticker)
    .where(
        (QualityMetric.published_at.is_(None))
        | (QualityMetric.published_at <= as_of_date)
    )
    .order_by(QualityMetric.fiscal_year.desc(), QualityMetric.fiscal_quarter.desc())
).first()
```

published_at NULL 처리(45일 가상화)는 Task 1 결정 따라 위 where 절을 보강.

- [ ] **Step 2: `calculate_factor_scores` 에서 quality 3종 점수화 후 평균**

```python
raw["roe_score"] = score_series(raw["roe"], higher_is_better=True, method=FACTOR.scoring_method)
raw["opm_score"] = score_series(raw["operating_margin"], higher_is_better=True, method=FACTOR.scoring_method)
raw["debt_score"] = score_series(raw["debt_ratio"], higher_is_better=False, method=FACTOR.scoring_method)
raw["quality_score"] = raw[["roe_score", "opm_score", "debt_score"]].mean(axis=1)
```

`mean(axis=1)` 은 NaN 을 자동 제외하므로 부분 결측 시 사용 가능한 점수의 평균이 됨 — Task 2 의 partial 테스트가 이 동작을 가정.

- [ ] **Step 3: 통과 확인**

Run: `.\.venv\Scripts\python.exe -m pytest tests/factors/test_engine.py -q -p no:cacheprovider`

Expected: PASS.

---

### Task 4: quality 커버리지 로깅

**Files:**
- Edit: `src/factors/engine.py`

- [ ] **Step 1: loguru 로 커버리지 출력**

`calculate_factor_scores` 마지막 직전(ranking 후) 다음 한 줄 추가:

```python
from loguru import logger
covered = raw["quality_score"].notna().sum()
total = len(raw)
logger.info(f"quality_score covered {covered}/{total} ({covered/total:.0%}) on {as_of_date}")
```

DART 데이터가 적게 들어왔을 때 사용자가 즉시 인지 가능. 자동 fallback 없음 — 사용자 의사결정에 맡김.

- [ ] **Step 2: 로그 출력이 테스트 흐름을 깨지 않는지 확인**

Run: `.\.venv\Scripts\python.exe -m pytest tests/factors -q -p no:cacheprovider`

Expected: PASS. loguru 기본 sink는 일반적으로 stderr이므로 stdout 기반 출력 단언에는 영향을 주지 않아야 한다. 테스트가 stderr를 엄격히 캡처하는 경우에는 로그 레벨/캡처 설정을 명시적으로 조정한다.

---

### Task 5: rank 스크립트 회귀 검증

**Files:**
- Read: `scripts/rank_phase2_factors.py`
- Read: `tests/factors/test_rank_script.py`

- [ ] **Step 1: 기존 rank 스크립트 테스트가 깨지지 않는지 확인**

Run: `.\.venv\Scripts\python.exe -m pytest tests/factors -q -p no:cacheprovider`

Expected: PASS.

- [ ] **Step 2: AST 신택스 체크**

Run: `.\.venv\Scripts\python.exe -m py_compile config.py src/factors/engine.py src/factors/scoring.py src/factors/models.py scripts/rank_phase2_factors.py`

Expected: 종료 코드 0.

- [ ] **Step 3: 실 데이터로 1회 실행 (옵션, 데이터 시드 후)**

Run: `.\.venv\Scripts\python.exe scripts/rank_phase2_factors.py --as-of 2026-05-01 --top 20`

Expected: 상위 20개 출력에서 `quality_score` 값이 0이 아닌 차등 분포가 보이고, 콘솔에 quality 커버리지 로그 1줄이 출력됨.
