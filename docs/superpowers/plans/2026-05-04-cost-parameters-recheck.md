# Cost Parameters Recheck Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `config.COST` 의 `commission_rate / tax_rate_kospi / tax_rate_kosdaq / slippage_rate` 값을 **실제 자료 출처 기반**으로 재검증·재조정. CLAUDE.md "데이터 기반 결정" 원칙을 직접 적용하는 작업.

**Prerequisite:** `docs/superpowers/plans/2026-05-03-environment-recovery.md` 의 모든 Task 가 완료되어 `.venv` 에서 `pytest` 가 정상 동작해야 함. (config 패치 후 회귀 테스트와 백테스트 비교 단계가 모두 `.venv` 에 의존.)

**Plan dependencies:**
- Must run after: `docs/superpowers/plans/2026-05-03-environment-recovery.md`
- Should run before: `docs/superpowers/plans/2026-05-04-phase3-stops-simulation.md`, so stop simulation uses corrected tax assumptions.
- Independent from: `docs/superpowers/plans/2026-05-04-phase1-quality-fundamentals.md`
- Independent from: `docs/superpowers/plans/2026-05-04-phase2-quality-score.md`
- Recommended commit scope: one commit for cost decision spec/config/test, and a separate commit only if real-data backtest comparison output is added later.

**Background — 사전 조사로 확인된 사실 (2026-05-04 시점):**
- 한국 정부는 2026년 1월 1일부터 **증권거래세율을 변경**.
  - **코스피**: 거래세 0% → 0.05%, 농어촌특별세 0.15% 유지 → **합계 0.20%**.
  - **코스닥**: 합계 0.15% → **0.20%** (농특세 없음, 거래세만 0.20%).
  - 출처: 네이트 뉴스 (2025-12-01, "내년부터 증권거래세 인상…코스피 0.05%·코스닥 0.20%"), 머니투데이, 헤럴드경제, 삼일회계법인 12월 commentary.
- 즉 현재 `tax_rate_kospi = tax_rate_kosdaq = 0.0018` (= 0.18%) **두 값 모두 잘못된 옛 수치**. 새 값은 **0.0020 (=0.20%)**.
- KIS 영웅문/KIS Developers 수수료는 계좌 종류·이벤트 따라 다름 → 실제 사용자 계좌의 수수료표를 1차 자료로 삼아야 함.
- 슬리피지 0.1% (0.001) 는 추정치 — 백테스트에서는 검증 불가, Phase 4 모의투자 체결 로그가 누적되면 실측 가능.

**Architecture:**
이 plan은 코드 변경량이 작지만 **결정 기록 → 패치 → 회귀 비교** 절차를 그대로 따르는 데 핵심이 있다.
1. spec 형태의 결정 문서 작성 (출처와 결정값 명시).
2. `config.py: CostConfig` 패치.
3. 패치 전/후 동일 백테스트 실행 → final_equity / total_return 차이 기록.
4. README의 "안전장치" / 매매 전략 섹션 거래세 표기 업데이트 (있는 경우).

**Tech Stack:** Python 3.12, pytest, requests (또는 수동 검증), 기존 backtest 엔진.

---

### Task 1: 자료 수집과 결정 기록

**Files:**
- Create: `docs/superpowers/specs/2026-05-04-cost-parameters-decision.md`
- Read: `config.py`
- Read: `src/backtest/engine.py`

- [ ] **Step 1: 거래세 출처 확정**

위 Background 의 4개 출처 중 가장 권위 있는 1차 자료 1건 선택 — 우선순위: 기획재정부/국세청 보도자료 > PwC/Samil 회계법인 commentary > 일간지 > 블로그/Threads.

Run (옵션): WebFetch 로 PwC 12월 commentary PDF 본문 확인하여 정확한 비율과 시행일을 인용.

기록할 내용:
- 코스피 매도 시 거래세 0.20% (= 거래세 0.05% + 농어촌특별세 0.15%), 시행 2026-01-01.
- 코스닥 매도 시 거래세 0.20%, 시행 2026-01-01.

- [ ] **Step 2: 수수료 결정 — 0.015% 유지**

사용자 결정: **`commission_rate = 0.00015` (=0.015%) 를 일단 유지.** 비대면 개설 일반 계좌의 보수적 기본값. 이 값은 KIS 영웅문 표준 수수료에 해당하며 이벤트 우대(0.0036265%, 0.011% 등) 적용 여부는 사용자 본인이 Phase 4 진입 전에 KIS 모바일 앱 → 고객센터 → 수수료 안내 또는 KIS Developers 콘솔에서 확인하기로 함.

→ Task 2 의 config 패치에서 `commission_rate` 는 변경 없이 0.00015 유지.

→ Task 5 의 후속 TODO 에 "사용자 KIS 계좌 실 적용 수수료 확인 후 갱신" 항목으로 명시 등록.

- [ ] **Step 3: 슬리피지 가정 정리**

현재 0.001 (=0.1%) 는 시장가 평균 추정치. 결정 문서에 다음 명시:
- 백테스트 단계에서는 0.001 유지.
- Phase 4 모의투자 체결 로그가 50건 이상 쌓이면 (체결가 - 호가)/호가 평균으로 재캘리브레이션.

- [ ] **Step 4: 결정 문서 작성**

`docs/superpowers/specs/2026-05-04-cost-parameters-decision.md` 에 다음 섹션으로 기록:
- 1차 자료 인용(URL과 발표일).
- 결정값과 변경 사유.
- 변경 후 영향 (Task 4 결과 채워 넣기 자리).

Expected: spec 문서 생성, 검토 가능 상태.

---

### Task 2: config.py 패치

**Files:**
- Edit: `config.py`

- [ ] **Step 1: 거래세 갱신**

```python
@dataclass(frozen=True)
class CostConfig:
    commission_rate: float = 0.00015     # KIS 영웅문 비대면 일반계좌 표준값. 사용자 계좌 우대수수료 확인 후 Phase 4 전 갱신 (Task 5 TODO).
    tax_rate_kospi: float = 0.0020       # 2026-01-01 시행: 거래세 0.05% + 농어촌특별세 0.15%
    tax_rate_kosdaq: float = 0.0020      # 2026-01-01 시행: 거래세 0.20% (농특세 없음)
    slippage_rate: float = 0.0010        # Phase 4 모의투자 체결 로그 50건 누적 후 재캘리 (Task 5 TODO).
```

핵심 변경: 기존 `tax_rate_kospi=0.0018, tax_rate_kosdaq=0.0018` 두 줄을 **0.0020 으로 교체**. `commission_rate` 와 `slippage_rate` 는 값 유지하되 주석으로 출처/후속 일정 명시.

- [ ] **Step 2: 주석 보강**

각 라인에 출처와 시행일을 1줄 주석으로 남겨 "왜 이 숫자인지" 가 코드에서 즉시 보이도록.

- [ ] **Step 3: AST 신택스 체크**

Run: `.\.venv\Scripts\python.exe -m py_compile config.py`

Expected: 종료 코드 0.

- [ ] **Step 4: config 출력 확인**

Run: `.\.venv\Scripts\python.exe config.py`

Expected: JSON snapshot 의 `COST` 섹션이 새 값으로 출력, `[OK] 설정 일관성 통과` 또는 의도된 경고만 노출.

---

### Task 3: 회귀 테스트 (코스피/코스닥 분기 검증)

**Files:**
- Edit: `tests/backtest/test_backtest_engine.py`

- [ ] **Step 1: 매도 비용이 시장별 거래세를 정확히 반영하는지 단언**

`test_sell_uses_kospi_tax_rate` / `test_sell_uses_kosdaq_tax_rate` 추가:
- 1종목씩 시드 (KOSPI / KOSDAQ).
- commission_rate=0, slippage_rate=0, tax_rate_kospi=0.0020, tax_rate_kosdaq=0.0020.
- 매도 1회 발생시키고 `trade.cost == quantity * price * 0.0020` 인지 단언.

- [ ] **Step 2: 통과 확인**

Run: `.\.venv\Scripts\python.exe -m pytest tests/backtest/test_backtest_engine.py -q -p no:cacheprovider`

Expected: PASS.

---

### Task 4: 변경 전/후 백테스트 비교 (영향 측정)

**Files:**
- Read: `scripts/run_phase3_backtest.py`
- Edit: `docs/superpowers/specs/2026-05-04-cost-parameters-decision.md`

- [ ] **Step 1: Phase 1 데이터 시드 확인**

거래세 0.18% → 0.20% 변경 영향은 매도 거래가 실제로 발생하는 백테스트 데이터가 있어야 측정 가능하다. 따라서 비교 전에 다음 prerequisite 을 확인한다.

1. `data/quntbot.db` 존재 여부 확인.
2. `stocks`, `daily_prices`, `fundamentals` 테이블에 백테스트 기간을 커버하는 데이터가 있는지 확인.
3. 데이터가 없으면 Phase 1 sync 를 먼저 실행한다.

현재 `scripts/sync_phase1_data.py` 의 실제 인자는 `--start-date` / `--end-date` 이다. 예:

```powershell
.\venv\Scripts\python.exe scripts\sync_phase1_data.py --start-date 2024-01-01 --end-date 2025-12-31
```

네트워크/API 문제로 pykrx 실데이터 sync 가 실패하면 Task 4 비교는 "실데이터 미시드로 보류"로 기록하고, 대신 단위 테스트에서 매도 비용 계산만 검증한다. 빈 DB로 `run_phase3_backtest.py` 를 실행한 결과는 비용 변경 영향 측정값으로 사용하지 않는다.

- [ ] **Step 2: 변경 전 값으로 1회 백테스트**

config 의 0.0020 자리에 임시로 0.0018 을 넣고 (또는 `--tax-rate` CLI 인자가 있으면 그걸 사용) `scripts/run_phase3_backtest.py` 1회 실행. `final_equity / total_return / 전체 매도 비용 합` 기록.

- [ ] **Step 3: 변경 후 값으로 1회 백테스트**

config 원복(0.0020) 후 동일 기간/시드로 다시 실행. 같은 지표 기록.

- [ ] **Step 4: 결정 문서 업데이트**

Task 1 의 결정 문서 "변경 후 영향" 섹션에 두 백테스트 차이를 표로 채움. 예: "기간 2024-01-01 ~ 2025-12-31, 매도 N회, 0.18% → 0.20% 변경 시 final_equity Y원 감소 (= -Z%)".

Expected: 0.02% × 매도 횟수만큼 비용이 늘어남이 수치로 확인됨.

---

### Task 5: 후속 TODO 등록

- [ ] **Step 1: 사용자 계좌 실 수수료 확인 TODO**

Task 1 의 결정 문서 상단에 다음 TODO 박스를 추가 (눈에 잘 띄게):

```
TODO (Phase 4 진입 전):
- [ ] 사용자가 KIS 계좌의 실 적용 수수료를 확인 (KIS 모바일 앱 또는 Developers 콘솔)
- [ ] 우대수수료가 적용되어 있다면 config.COST.commission_rate 갱신
  - 비대면 일반: 0.00015 (현재 값, 변경 불필요)
  - 우대 케이스 예: 0.011% → 0.00011, 0.0036265% → 0.0000036265
```

- [ ] **Step 2: Phase 4 슬리피지 재캘리 TODO**

같은 문서에 다음 추가:

```
TODO (Phase 4 모의투자 1~2개월 운용 후):
- [ ] 체결 로그 50건 이상 누적되면 (체결가 - 호가)/호가 평균 계산
- [ ] config.COST.slippage_rate 갱신 (현재 0.0010 = 0.1% 추정값)
```

Expected: 사용자가 한 눈에 미해결 항목과 갱신 시점을 알 수 있음.
