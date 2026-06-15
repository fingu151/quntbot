# Handoff — 전략 개선 Step 1 (청산 ATR 단일 스톱)

작성: 2026-06-15 / 브랜치: `codex/exit-rebalance-strategy` / 상태: **검증 완료, config 기본 OFF 유지, 커밋 준비**

## 1. 무엇을 하고 있었나
매수·매도 전략 성능 개선. 전체 설계는 아래 문서에 있음(반드시 먼저 읽을 것):
`docs/superpowers/plans/2026-06-15-strategy-improvement-design.md`
(Step1 청산 → Step2 진입필터 → Step3 팩터 재최적화 → Step4 사이징, 각 단계 검증 게이트 포함)

근거 데이터: `data/actual_exit_strategy_stress_matrix_2026-05-19.csv`
→ 동일 구간에서 stops-OFF가 stops-ON보다 수익 88%→166%, Sharpe 1.40→1.53, 거래수 절반.
즉 고정 -7% 손절 + -8% 트레일링이 승자를 조기 청산(whipsaw). Step1은 이를 ATR 단일 스톱으로 완화.

## 2. 이미 적용된 코드 변경 (게이트, 기본 OFF = 현행 동작 유지)
`atr_only_stop` 플래그 추가. True면 ATR 스톱 가용 종목은 고정 stop_loss_pct를 적용하지 않고
ATR 스톱만으로 하방 통제. ATR 없으면 고정 손절 폴백 유지.

- `config.py` — `ExitRulesConfig.atr_only_stop: bool = False`
- `src/backtest/engine.py` — `run_backtest(atr_only_stop=...)` 파라미터 + 고정손절 elif 게이트
- `src/trading/engine.py` — `check_exit_rules` 고정손절 블록 동일 게이트 (라이브/백테 일관성)
- `src/strategies/adaptive_alpha.py` — `AdaptiveAlphaConfig.atr_only_stop` + params 전달
- `scripts/run_backtest_matrix.py` — `--atr-only-stop` CLI 플래그 + 전달
- `tests/backtest/test_backtest_engine.py` — 단위테스트 2개 추가:
  `test_run_backtest_atr_only_stop_skips_fixed_stop_when_atr_available`,
  `test_run_backtest_default_keeps_fixed_stop_alongside_atr`
- `tests/trading/test_engine.py` — 라이브 게이트 회귀테스트 1개 추가:
  `test_check_exit_rules_atr_only_stop_keeps_static_stop_when_atr_stop_disabled`

`atr_multiplier`는 2.2 그대로 (튜닝은 아래 검증에서 결정).

## 3. 검증 결과
### (a) 검증 — 최우선
```bash
pytest tests/backtest/test_backtest_engine.py -k "atr_only or default_keeps or stop_loss or atr_stop"
python -m compileall config.py src/backtest/engine.py src/trading/engine.py \
  src/strategies/adaptive_alpha.py scripts/run_backtest_matrix.py
```

2026-06-15 로컬 검증:
- `pytest tests/backtest/test_backtest_engine.py -k "atr_only or default_keeps or stop_loss or atr_stop"` → 5 passed.
- `pytest tests/trading/test_engine.py -k "atr_stop or atr_only"` → 2 passed.
- `python -m compileall config.py src/backtest/engine.py src/trading/engine.py src/strategies/adaptive_alpha.py scripts/run_backtest_matrix.py` → passed.
- 최종 묶음 검증:
  `python -m pytest tests/backtest/test_backtest_engine.py tests/trading/test_engine.py tests/strategies/test_adaptive_alpha.py tests/test_strategy_defaults.py tests/backtest/test_run_script.py -q` → 107 passed.

### (b) ATR 배수 그리드 + A/B (오버레이 ON, 표준 구간 2020-2025)
```bash
python scripts/run_backtest_matrix.py --start-date 2020-01-01 --end-date 2025-12-31 \
  --top-ns 20 --rebalance-frequencies weekly --no-atr-only-stop --output-md data/step1_baseline.md
# atr_only ON, 배수 2.5 / 2.8 / 3.0 / 3.5 각각:
python scripts/run_backtest_matrix.py --start-date 2020-01-01 --end-date 2025-12-31 \
  --top-ns 20 --rebalance-frequencies weekly --atr-only-stop --atr-multiplier 2.8 \
  --output-md data/step1_atr_only_28.md
```
채택 기준(설계 문서): Sharpe↑ AND 거래수↓ AND MDD ≤ baseline. 충족 조합으로
`config.py`의 `atr_only_stop=True` + `atr_multiplier` 확정.

2026-06-15 로컬 A/B 결과(`data/step1_*.csv`, top_n=20, weekly, custom):

| scenario | total_return | CAGR | MDD | Sharpe | win_rate | avg_hold_days | trades |
|---|---:|---:|---:|---:|---:|---:|---:|
| baseline (`--no-atr-only-stop`) | 75.32% | 9.80% | -19.35% | 0.8194 | 54.55% | 54.69 | 2616 |
| atr_only 2.5 | 72.71% | 9.53% | -22.52% | 0.7660 | 59.22% | 62.68 | 2422 |
| atr_only 2.8 | 75.31% | 9.80% | -21.96% | 0.7833 | 59.06% | 63.33 | 2318 |
| atr_only 3.0 | 78.03% | 10.09% | -22.08% | 0.7990 | 60.15% | 65.12 | 2293 |
| atr_only 3.5 | 78.81% | 10.17% | -23.30% | 0.7964 | 60.19% | 67.24 | 2191 |

판단: 모든 atr_only 후보가 거래수는 줄였지만 Sharpe가 baseline보다 낮고 MDD가 더 깊어져 채택 기준을 충족하지 못함.
따라서 `config.py`는 `atr_only_stop=False`, `atr_multiplier=2.2`를 유지한다.

### (c) 그 다음 단계: 설계 문서의 Step2(진입 타이밍 필터) → Step3 → Step4 순서로 진행.

## 4. 정리 필요 (이전 세션 잔여물)
- 임시 스크립트 삭제: `scripts/_tmp_atr_grid.py _tmp_grid_run.py _tmp_one_bt.py _tmp_precompute.py _tmp_profile*.py` (8개, 커밋 금지)
- 작업트리에 본 작업과 무관한 기존 수정 다수 존재(HANDOFF/README/progress/scheduler 등) → Step1 커밋은 2절 파일만 선택 스테이징할 것.

## 5. 커밋 가이드 (검증 통과 후)
```bash
rm scripts/_tmp_*.py
git add config.py src/backtest/engine.py src/trading/engine.py \
  src/strategies/adaptive_alpha.py scripts/run_backtest_matrix.py \
  tests/backtest/test_backtest_engine.py tests/trading/test_engine.py \
  docs/superpowers/plans/2026-06-15-strategy-improvement-design.md \
  docs/superpowers/2026-06-15-handoff-strategy-step1.md
git commit -m "feat(exit): add atr_only_stop gate (default off) to relax fixed stop when ATR available"
```

## 6. 프로젝트 규칙 리마인더 (CLAUDE.md)
코드 수정 전 관련 파일 5개+ 읽기 / 추측 금지(Grep·Read 확인) / 변경 후 반드시 검증 /
한 번에 하나씩 / 구현 전 Plan(설계) 먼저 / 데이터 기반 결정.
