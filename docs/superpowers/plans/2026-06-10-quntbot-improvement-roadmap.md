# Quntbot Improvement Roadmap (Telegram Removal / 100-Point Scoring / Technical Filter / ETF)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> 이 문서는 4개 개선 과제의 **상위 로드맵**이다. 각 Phase는 구현 착수 전에
> `docs/superpowers/specs/`에 별도 설계 문서를 만들고 승인받은 뒤 진행한다 (기존 워크플로 동일).

**Goal:** 텔레그램 신호 팩터 제거 → 팩터 점수를 명시적 100점 배분 체계로 재설계 → 기술적 분석을 점수화·강화 → ETF 매매 지원. PAPER 안전 게이트(드라이런 프리플라이트, 일일 한도, 손실 한도)는 전 과정에서 유지한다.

**Architecture:** Phase 순서에 의존성이 있다. Phase 1(텔레그램 제거)이 `FactorScore` 시그니처와 가중치 합을 바꾸므로 Phase 2(100점 체계)보다 먼저 끝나야 한다. Phase 3(기술적 분석)은 Phase 2가 예약해둔 "기술 점수" 슬롯에 꽂는다. Phase 4(ETF)는 데이터/비용 모델이 독립적이지만 점수 체계 결정(Phase 2)에 의존하므로 마지막에 둔다.

**Tech Stack:** Python 3.10, pandas, SQLAlchemy/SQLite, pykrx, KIS API, pytest.

**공통 규칙:**
- 매매 동작을 바꾸는 모든 기본값 변경은 `scripts/run_backtest_matrix.py` 비교 리포트(변경 전/후)를 근거로 결정한다 (CLAUDE.md 데이터 기반 결정 원칙).
- 한 Phase 안에서도 Task 단위로 테스트 작성 → 실패 확인 → 구현 → 통과 → 커밋 순서를 지킨다.
- LIVE 동작 추가 금지. `REBALANCE_REQUIRE_DRY_RUN_PREFLIGHT` 제거 금지.

---

## Phase 1: 텔레그램 점수 시스템 삭제

**Goal:** MTProto 채널 리더 기반 텔레그램 *신호* 팩터를 코드베이스에서 제거한다.

**유지하는 것 (혼동 주의):**
- `TelegramNotifier` / `config.TELEGRAM` (주문·손절·긴급 **알림**) — 그대로 유지
- `python-telegram-bot` 의존성 — 알림용이므로 유지

**제거하는 것 (grep으로 확인된 접점):**

| 영역 | 파일 | 내용 |
|---|---|---|
| 설정 | `config.py` | `TelegramSignalConfig`/`TELEGRAM_SIGNAL`, `FACTOR.telegram_weight` |
| 신호 수집 | `src/signals/telegram_parser.py`, `src/signals/telegram_reader.py` | 파일 삭제 |
| 팩터 | `src/factors/engine.py` | `telegram_raw`/`telegram_score` 컬럼, `telegram_signals` 인자 |
| 모델 | `src/factors/models.py` | `FactorScore.telegram_score` 필드 (위치 인자 — 모든 생성처 영향) |
| DB | `src/data/models.py`, `src/data/repositories.py` | `TelegramSignal` 모델, `upsert/replace/get_latest_telegram_signals` |
| 스케줄러 | `src/trading/scheduler.py` | `_telegram_signal_job` + 잡 등록 |
| 스크립트 | `scripts/smoke_test_telegram_signals.py`(삭제), `scripts/generate_public_portfolio_snapshot.py`, `scripts/rank_phase2_factors.py`, `scripts/compare_research_report_factor_impact.py` | telegram 행/필드/로그 제거 |
| 의존성 | `requirements.txt` | `telethon` 제거 |
| 테스트 | `tests/signals/test_telegram_parser.py`, `test_telegram_reader.py`, `tests/notify/test_smoke_test_telegram_signals.py` 삭제 + `FactorScore`를 위치 인자로 생성하는 모든 테스트 수정 (`tests/factors/`, `tests/trading/`, `tests/data/`, `tests/test_config.py`, `tests/test_generate_public_portfolio_snapshot.py`) |

**결정 사항 (구현 전 확정):**
1. **가중치 재배분**: `telegram_weight=0.5`를 어디로 보낼지. 선례(배당 0.5→0.25 축소분을 핵심 3팩터에 `+0.25/3`씩 재배분)를 따르거나, Phase 2의 100점 재설계에서 한꺼번에 처리. **권고: Phase 1에서는 단순 제거만 하고 재배분은 Phase 2에서 처리** (두 번 백테스트할 필요 없음). 단, Phase 1 단독 배포 시에는 제거 전/후 백테스트 비교 필수.
2. **DB 테이블**: 기존 `telegram_signals` 테이블은 드롭하지 않고 고아 테이블로 남긴다 (파괴적 마이그레이션 회피). `create_tables`에서만 빠지면 신규 DB에는 생성 안 됨.

### Tasks

- [ ] **Task 1-1: 팩터 경로에서 텔레그램 제거** — `FactorScore.telegram_score` 필드 제거, `calculate_factor_scores*`의 telegram 인자/컬럼 제거, `FACTOR.telegram_weight` 제거. 검증: `pytest tests/factors tests/backtest -q`
- [ ] **Task 1-2: 신호 수집·스케줄러 제거** — reader/parser/스모크 스크립트 삭제, `_telegram_signal_job` 제거, `config.TELEGRAM_SIGNAL` 제거. 검증: `pytest tests/trading/test_scheduler.py tests/test_config.py -q`
- [ ] **Task 1-3: DB 모델·리포지토리 제거** — `TelegramSignal` 모델 + 리포지토리 함수 3개 제거. 검증: `pytest tests/data -q`
- [ ] **Task 1-4: 대시보드·리포트 스크립트 정리** — snapshot/rank/compare 스크립트에서 telegram 필드 제거 (스냅샷 JSON 스키마 변경은 대시보드 렌더러와 함께 수정). 검증: `pytest tests/test_generate_public_portfolio_snapshot.py tests/factors/test_rank_script.py -q`
- [ ] **Task 1-5: 의존성·문서 정리** — `telethon` 제거, `.env.example`의 TELEGRAM_API_* 제거, README/HANDOFF 갱신. 검증: `python -m compileall src scripts tests` + 전체 `pytest tests -q`
- [ ] **Task 1-6: 백테스트 전/후 비교 리포트 생성 후 커밋** — `scripts/run_backtest_matrix.py`로 제거 전(현 main)과 후의 CAGR/MDD/샤프 비교를 `data/`에 기록.

---

## Phase 2: 팩터 점수 100점 만점 체계로 세분화

**Goal:** 현재의 불투명한 가중치(`1.0 + 0.25/3 = 1.0833…`)를 **명시적 점수 예산**으로 바꾸고, 종목별 총점이 항상 0~100점이 되며 팩터·세부지표별 기여 점수를 그대로 읽을 수 있게 한다.

**현재 상태 (참고):** `combine_scores(scale_to=100.0)`이 이미 가중합을 100 스케일로 정규화하지만, 개별 팩터 기여도가 점수로 노출되지 않고 가중치 숫자의 의미를 알기 어렵다.

**설계 방향 (spec에서 확정할 점수 예산 초안):**

| 팩터 | 점수 예산 | 세부 지표 |
|---|---|---|
| 가치 | 30점 | PER 15 + PBR 15 |
| 퀄리티 | 25점 | ROE 10 + 영업이익률 8 + 부채비율 7 |
| 모멘텀 | 20점 | 6M 수익률 (Phase 3에서 세분화 여지) |
| 배당 | 5점 | DIV |
| 보조 신호 | 20점 | busanstock / 수급 / 리서치 / 기술점수(Phase 3 예약 슬롯) |

> 위 숫자는 초안이다. 최종 배분은 `run_backtest_matrix.py` 스윕 결과로 결정한다.
> rank 방식(백분위 0~1) × 점수 예산 = 지표별 획득 점수. 보조 신호처럼 음수가 가능한
> 오버레이는 [-예산, +예산] 범위로 클램프하는 규칙을 spec에서 정의한다.

**파일 접점:** `config.py`(FactorConfig → 점수 예산 구조 + `validate()`에 합계 100 검증), `src/factors/scoring.py`(`combine_scores` 재설계), `src/factors/engine.py`, `src/factors/models.py`(`FactorScore`에 지표별 점수 필드), `scripts/rank_phase2_factors.py`, `scripts/generate_public_portfolio_snapshot.py` + 대시보드(점수 분해 표시), 관련 테스트 전반.

### Tasks

- [ ] **Task 2-1: spec 작성** — 점수 예산표, 세부 지표 정의, 음수 오버레이 클램프 규칙, `FactorScore` 신규 스키마를 `docs/superpowers/specs/`에 작성하고 승인.
- [ ] **Task 2-2: scoring 코어 재설계 (TDD)** — `combine_scores`를 점수 예산 기반으로 교체. "예산 합=100이면 만점 100", "데이터 없는 팩터는 0점", "클램프 동작" 단위 테스트 선작성. 검증: `pytest tests/factors/test_scoring.py -q`
- [ ] **Task 2-3: 엔진·모델 연결** — `calculate_factor_scores_from_df`가 지표별 점수를 채우도록 수정, `FactorScore` 확장. 검증: `pytest tests/factors -q`
- [ ] **Task 2-4: 리포트·대시보드 점수 분해 노출** — rank 스크립트와 public snapshot에 팩터별 획득 점수 표시. 검증: `pytest tests/test_generate_public_portfolio_snapshot.py -q`
- [ ] **Task 2-5: 점수 예산 스윕 + 증거 기록** — 2~3개 배분안을 `run_backtest_matrix.py`로 비교, 채택안을 `progress.md`에 수치와 함께 기록 후 기본값 변경 커밋.

---

## Phase 3: 기술적 분석 개선

**Goal:** 현재 이진(pass/fail) 매수 필터인 기술적 분석을 (a) 점수화해 Phase 2의 보조 신호 슬롯에 편입하고 (b) 지표를 보강한다.

**현재 상태 (`src/factors/engine.py`):** MA20 상회 / MA60 기울기 상승 / RSI14 < 75 / 20일 변동성 < 5% 중 3개 이상 통과해야 매수 후보 유지. 통과 여부만 쓰고 강도는 버린다.

**개선 항목 (spec에서 채택 여부 확정):**
1. **점수화**: 4개 조건 통과 개수·강도를 0~N점으로 변환해 총점에 반영. 극단 조건(예: 변동성 > 8%)만 하드 필터로 유지.
2. **거래량 확인 지표 추가**: 20일 평균 거래량 대비 최근 거래량 비율 (`DailyPrice.volume`은 이미 수집·저장 중 — fast scorer가 volume을 로드하도록 확장 필요).
3. **추가 지표 후보**: MACD 시그널, 52주 신고가 근접도, 갭 필터 강화. 백테스트로 채택 결정.
4. **실거래/백테스트 경로 일치**: 현재 live `_load_factor_inputs`는 recent_closes 127개, fast scorer는 100개를 전달한다 — 동일 윈도 상수로 통일.

**파일 접점:** `src/factors/engine.py`(`_technical_filter_passes` → 점수 함수 + 하드 필터 분리), `src/backtest/engine.py`(`_make_fast_score_func`에 volume 로딩 추가), `config.py`(기술 지표 파라미터), `tests/factors/test_engine.py`, `tests/backtest/test_backtest_engine.py`.

### Tasks

- [ ] **Task 3-1: spec 작성** — 점수화 공식, 하드 필터 경계, 신규 지표 정의.
- [ ] **Task 3-2: 기술 점수 함수 구현 (TDD)** — `_technical_filter_passes`를 `technical_score()` + `technical_hard_filter()`로 분리. 기존 필터 동작을 보존하는 회귀 테스트 포함. 검증: `pytest tests/factors/test_engine.py -q`
- [ ] **Task 3-3: 거래량 지표 추가** — live/fast 양쪽 입력에 volume 시계열 추가, 윈도 길이 상수 통일. 검증: `pytest tests/factors tests/backtest -q`
- [ ] **Task 3-4: 파라미터 스윕 + 채택** — RSI 상한, 변동성 상한, 거래량 배수 등을 매트릭스로 비교해 수치 근거와 함께 기본값 결정.

---

## Phase 4: ETF 매매 지원

**Goal:** 코스피·코스닥 개별주 전용인 현재 봇이 ETF를 수집·점수화·주문할 수 있게 한다.

**현재 제약 (코드로 확인):**
- 유니버스: `pykrx stock.get_market_ticker_list`는 개별주만 반환 → ETF는 후보에 아예 없음 (`get_etf_ticker_list`/`get_etf_ohlcv_by_date` 별도 API 필요).
- 점수: ETF는 PER/PBR/DART 재무가 없어 3-팩터 점수 계산 불가 → **별도 점수 체계 필요** (모멘텀/거래대금 중심).
- 비용 모델: ETF는 매도 시 증권거래세 0% (개별주 0.20%) → `CostConfig`/`_sell_position`의 시장 기반 세율 분기에 상품 유형 분기 추가 필요. 국내주식형 외 ETF의 배당소득세는 backtest 단순화 범위에서 제외할지 spec에서 결정.
- 주문: KIS `order-cash` 엔드포인트는 ETF 티커도 동일하게 처리 (모의투자에서 스모크 테스트로 검증).

**전략 결정 (구현 전 사용자 확정 필요 — spec 단계):**
- **A안**: 미배분 현금을 벤치마크 ETF(069500 등)로 파킹 (가장 단순, 리스크 낮음)
- **B안**: 듀얼 모멘텀 ETF 슬리브를 별도 운용 (포트폴리오 일부를 ETF 전용 배분)
- **C안**: ETF를 개별주와 같은 포트폴리오에서 모멘텀 점수로 경쟁 편입 (점수 비교 가능성 문제로 난이도 최고)

**파일 접점:** `src/data/collectors.py`(ETF 유니버스/시세 수집), `src/data/models.py`(`Stock.market`에 "ETF" 또는 `instrument_type` 컬럼 — 마이그레이션 방식 spec에서 결정), `config.py`(ETF 설정), `src/factors/`(ETF 점수 경로), `src/backtest/engine.py`(세율 분기), `src/trading/rebalancer.py`/`scheduler.py`(슬리브 배분), `scripts/dry_run_rebalance.py`(ETF 행 표시), 스모크 테스트 신규.

### Tasks

- [ ] **Task 4-1: spec 작성 + 전략 A/B/C 결정** — 사용자 결정 필요. 세금 모델 단순화 범위 포함.
- [ ] **Task 4-2: ETF 데이터 수집 (TDD)** — `PykrxMarketDataProvider`에 ETF 유니버스·시세 수집 추가, `instrument_type` 저장. 검증: `pytest tests/data -q` + 수집 스모크.
- [ ] **Task 4-3: 비용 모델 분기** — `_sell_position` 세율을 instrument 기준으로 분기, ETF 세율 0 적용. 회귀 테스트: 개별주 세율 불변. 검증: `pytest tests/backtest -q`
- [ ] **Task 4-4: 선택한 전략 구현 + 백테스트** — 슬리브/파킹 로직을 rebalancer·backtest에 구현, 전/후 비교 리포트.
- [ ] **Task 4-5: PAPER 스모크** — 모의투자에서 ETF 1주 매수→매도 스모크 스크립트 (`scripts/smoke_test_order.py` 패턴), dry-run 프리플라이트에 ETF 행이 정상 포함되는지 확인.

---

## 실행 순서 요약

```
Phase 1 (텔레그램 제거)          ──→ Phase 2 (100점 체계)  ──→ Phase 3 (기술 점수 편입)
  의존: FactorScore 시그니처 변경      의존: 가중치 전면 재설계      의존: Phase 2의 보조 슬롯
                                                                        │
                                                          Phase 4 (ETF) ←┘
                                                            의존: 점수 체계 확정 후 ETF 점수 경로 설계
```

| Phase | 규모 추정 | 선행 결정 |
|---|---|---|
| 1. 텔레그램 제거 | 중 (접점 25파일, 대부분 삭제) | 가중치 재배분 시점 |
| 2. 100점 체계 | 중~대 (scoring 코어 + 전 리포트) | 점수 예산표 |
| 3. 기술 분석 | 중 | 점수화 공식, 신규 지표 채택 |
| 4. ETF | 대 (데이터~주문 전 구간) | 전략 A/B/C, 세금 모델 범위 |

## Final Review Checklist

- [ ] 텔레그램 *알림*(TelegramNotifier)은 모든 Phase 후에도 동작한다.
- [ ] 어느 시점에서든 `pytest tests -q` 전체 통과 상태로 커밋되어 있다.
- [ ] 점수 예산 합계는 `config.validate()`가 100점 검증한다.
- [ ] 매매 동작 기본값 변경은 모두 백테스트 비교 수치가 `progress.md`에 기록되어 있다.
- [ ] ETF 주문은 PAPER 스모크 테스트 통과 전에는 스케줄러에 연결하지 않는다.
- [ ] 드라이런 프리플라이트·일일 한도·일일 손실 한도 게이트는 변경되지 않았다.
