# quntbot Handoff For Agents

## Agent work continuity dashboard

The local agent work continuity dashboard helps recover context after switching
work environments. It reads local artifacts only and shows current safety state,
latest progress, completed work, verification notes, evidence, timeline, and
the next safe command. It must not call KIS, place orders, mutate the DB, or run
readiness checks automatically.

```powershell
# Generate or refresh the Markdown handoff dashboard.
.\venv\Scripts\python.exe scripts\generate_agent_ops_dashboard.py --expected-date 2026-05-13

# Open the local Streamlit work continuity dashboard.
.\venv\Scripts\python.exe -m streamlit run scripts\agent_ops_streamlit_dashboard.py
```

Relevant files:
- `scripts\generate_agent_ops_dashboard.py`
- `scripts\agent_ops_streamlit_dashboard.py`
- `tests\test_generate_agent_ops_dashboard.py`
- `tests\test_agent_ops_streamlit_dashboard.py`
- `data\agent_ops_dashboard_latest.md`
- `docs\superpowers\specs\2026-05-13-agent-work-continuity-dashboard-design.md`
- `docs\superpowers\plans\2026-05-13-agent-work-continuity-dashboard.md`

---

## Public portfolio dashboard

The local public portfolio dashboard uses a manual snapshot flow. The snapshot
generator may call KIS PAPER read endpoints, but the Streamlit dashboard reads
only `data\public_portfolio_snapshot.json` and must not call KIS or any order
execution path.

```powershell
# Generate or refresh the public read-only snapshot.
.\venv\Scripts\python.exe scripts\generate_public_portfolio_snapshot.py --output data\public_portfolio_snapshot.json

# Open the local Streamlit dashboard.
.\venv\Scripts\python.exe -m streamlit run scripts\public_portfolio_dashboard.py
```

Relevant files:
- `scripts\generate_public_portfolio_snapshot.py`
- `scripts\public_portfolio_dashboard.py`
- `tests\test_generate_public_portfolio_snapshot.py`
- `tests\test_public_portfolio_dashboard.py`
- `docs\superpowers\specs\2026-05-12-public-portfolio-dashboard-design.md`
- `docs\superpowers\plans\2026-05-12-public-portfolio-dashboard.md`

---

## Research report body analysis

The research-report layer is read-only market intelligence. It stores analyst
report metadata plus compact body-analysis summaries for agent review. It must
not place orders or bypass PAPER dry-run/readiness gates.

```powershell
# Hankyung consensus metadata + body-analysis attempt.
.\venv\Scripts\python.exe scripts\sync_korean_research_reports.py --url https://markets.hankyung.com/consensus --source hankyung_consensus --broker "한경 컨센서스" --include-pdf-text

# Mirae Asset research metadata + PDF body analysis.
.\venv\Scripts\python.exe scripts\sync_korean_research_reports.py --url https://securities.miraeasset.com/bbs/board/message/list.do?categoryId=1533 --source mirae_asset --broker "미래에셋증권" --include-pdf-text
```

Current verified provider behavior:
- Hankyung consensus stores metadata and analysis rows, but linked report PDFs
  redirect to a login flow in this environment. Those analysis rows should show
  `body_text_status=login_required`.
- Mirae Asset category `1533` stores metadata and extracts linked PDFs. Latest
  smoke stored 10 rows with `pdf_text_extracted=10`.
- Every sync command prints `orders_submitted=0`.

Relevant files:
- `src\signals\research_report_analysis.py`
- `src\signals\research_report_parser.py`
- `src\signals\research_report_reader.py`
- `src\data\models.py`
- `src\data\repositories.py`
- `scripts\sync_korean_research_reports.py`
- `tests\signals\test_research_report_analysis.py`
- `tests\signals\test_research_report_parser.py`
- `tests\signals\test_research_report_reader.py`
- `tests\signals\test_sync_korean_research_reports.py`
- `docs\superpowers\specs\2026-05-14-research-report-body-analysis-design.md`
- `docs\superpowers\plans\2026-05-14-research-report-body-analysis.md`

> **마지막 업데이트**: 2026-05-12  
> **테스트 상태**: 전체 `339 passed`, daily runner/scheduler targeted `19 passed`, KIS/dry-run parser targeted `44 passed`, agent dashboard targeted `11 passed`  
> **운영 모드**: `TRADE_MODE=PAPER` — LIVE 주문 금지

---

## 프로젝트 개요

한국 주식 퀀트 트레이딩 봇. KRX 데이터(pykrx)를 수집하고, 멀티팩터 점수(가치·퀄리티·모멘텀·배당수익률·텔레그램신호·Busanstock·투자자별 수급)로 종목을 랭킹한 뒤, KIS(한국투자증권) API로 모의투자 자동 리밸런싱한다.

### 하루 운영 흐름

```
06:00–09:00  텔레그램 채널 폴링 (15분마다, 오늘 모닝 브리핑 신호 저장)
08:40        Phase 1 데이터 동기화 (최근 30일, 유동성 상위 KOSPI 400 + KOSDAQ 200)
09:05        팩터 점수 계산 → PAPER 리밸런싱 주문
09:00–15:00  손절/트레일링 스탑 모니터링 (10분마다)
```

---

## 아키텍처 지도

```
config.py                     전역 설정 (dataclass, .env 읽기)
src/
  data/
    models.py                 SQLAlchemy ORM: Stock, DailyPrice, Fundamental,
                              TelegramSignal, SyncRun
    database.py               get_engine(), create_tables(), session_scope()
    repositories.py           upsert_*/get_* 함수 (SQLite upsert)
    collectors.py             PykrxMarketDataProvider, sync_phase1_data
  factors/
    models.py                 FactorScore dataclass
    scoring.py                score_series(), combine_scores(), _zscore()
    engine.py                 calculate_factor_scores(), _load_factor_inputs()
  signals/
    telegram_parser.py        모닝 브리핑 메시지 파서
    telegram_reader.py        telethon 채널 폴링 → DB 저장
  trading/
    kis_client.py             KIS REST API 래퍼
    engine.py                 TradingEngine (stop-loss, trailing-stop, 잔고조회)
    rebalancer.py             compute_rebalance_orders(), execute_rebalance()
    scheduler.py              APScheduler 루프
  backtest/
    engine.py                 run_backtest()
    models.py                 BacktestResult, Trade
  notify/
    notifier.py               텔레그램 봇 알림 (python-telegram-bot)
scripts/
  run_bot.py                  메인 진입점
  sync_phase1_data.py         수동 데이터 동기화
  rank_phase2_factors.py      팩터 점수 조회
  smoke_test_kis.py           KIS API 연결 확인
  smoke_test_telegram.py      Telegram 알림 설정/발송 확인 (주문 없음)
  smoke_test_investor_flows.py
                              투자자별 수급 DB 적재/점수화 readiness 확인 (주문 없음)
  smoke_test_order.py         PAPER 주문 테스트 (시장시간 가드 포함)
  dry_run_rebalance.py        PAPER 리밸런싱 주문 없는 계획/리포트 생성
  prepare_rebalance_for_execution.py
                              실주문 전 드라이런 생성 + preflight 검증
  prepare_and_review_rebalance.py
                              주문 없이 드라이런 준비 + 리포트 리뷰
  check_rebalance_readiness.py
                              주문 없이 정규장/clean dry-run 실행 가능 상태 확인
  print_rebalance_operations_checklist.py
                              오늘 날짜 기준 안전 운영 명령 순서 출력
  smoke_rebalance_operations_checklist.py
                              체크리스트 참조 스크립트 존재 여부 점검
  archive_rebalance_operations_checklist.py
                              체크리스트 smoke 출력 로그 보관
  cleanup_rebalance_checklist_logs.py
                              오래된 체크리스트 로그 정리
  execute_rebalance_from_dry_run.py
                              검증된 드라이런 JSON에서 PAPER 주문 실행
  review_rebalance_reports.py 드라이런/실행 JSON 리포트 요약 점검
  compare_rebalance_reports.py 두 dry-run JSON 리포트의 목표/매수 변화 비교
  archive_rebalance_run_bundle.py
                              운영일별 dry-run/readiness/review/checklist 산출물 보관
  daily_paper_run.py          동기화→드라이런→readiness→PAPER 실행→리뷰→장중 손절/트레일링 감시
tests/                        pytest, 각 src 모듈 1:1 대응
```

---

## DB 스키마 (SQLite: `data/quntbot.db`)

| 테이블 | 기본키 / 유일키 | 주요 컬럼 |
|--------|----------------|-----------|
| `stocks` | `ticker` | name, market, is_active |
| `daily_prices` | id / (ticker, date) | open/high/low/close/volume/trading_value |
| `fundamentals` | id / (ticker, date) | bps, per, pbr, eps, div, dps |
| `telegram_signals` | id / (message_date, ticker) | signal_type, star_rating, raw_score, target_price, message_id |
| `sync_runs` | id | started_at, finished_at, status, universe/price/fundamental_count |

---

## 팩터 점수 구조

`FactorScore` 필드 (순서):
```python
ticker, name, market, as_of_date,
value_score,     # PER·PBR zscore (낮을수록 ↑)
quality_score,   # ROE = EPS/BPS zscore
momentum_score,  # 모멘텀 수익률 zscore
yield_score,     # 배당수익률 zscore
telegram_score,  # 텔레그램 신호 raw_score zscore
total_score,     # 가중합 (config.py FACTOR 가중치)
rank             # 1 = 최고
```

`config.py` 기본 가중치:
```python
value_weight    = 1.0
quality_weight  = 1.0
momentum_weight = 1.0
yield_weight    = 0.5
telegram_weight = 0.5
```

NaN 처리: `quality_score`, `yield_score`, `telegram_score`는 데이터 없으면 0.0으로 채움.  
`value_score`, `momentum_score` 중 하나라도 NaN이면 랭킹에서 제외.

---

## 유니버스 필터 (config.py UNIVERSE)

```
전체 KOSPI + KOSDAQ 종목
→ 우선주 제외 (ticker 끝자리 != '0')
→ KRX 관리·경고·거래정지 종목 제외
→ 최근 5영업일 평균 거래대금 < 50억원 제외
→ KOSPI 상위 400, KOSDAQ 상위 200 선택
```

상태 확인 실패 시: `exclude_unverifiable_status=True` → 보수적으로 전체 제외.

---

## 텔레그램 신호 (src/signals/)

### 설정 (.env)
```env
TELEGRAM_API_ID=12345678        # my.telegram.org 에서 발급 (MTProto)
TELEGRAM_API_HASH=abcdef...
TELEGRAM_SIGNAL_CHANNEL=채널명  # username 또는 초대링크
TELEGRAM_SIGNAL_WEIGHT=0.5      # 팩터 가중치 (선택, 기본 0.5)
```

### 동작 방식
- `telethon` MTProto User API로 채널 메시지 폴링 (Bot API 아님, 읽기 전용)
- 오전 6–9시 15분마다 `fetch_and_store_signals()` 실행
- 첫 실행 시 전화번호 + OTP 입력 → `data/telegram_signal.session` 생성

### 파서 (`telegram_parser.py`)
모닝 브리핑 메시지 포맷:
```
주식 요약 · 모닝 · YYYY-MM-DD
━━━━━━━━━━━━━━━
수혜 종목
005930 삼성전자 ★★★ - 설명
주의 종목
035420 NAVER ★
━━━━━━━━━━━━━━━
| 종목 | 커버 | TP | 핵심 1줄 |
| 005930 삼성전자 | ★★★ | 90000 | AI 서버 |
```

raw_score 계산:
- 표 행(TP 있음) → 항상 `수혜`, stars만큼 점수 (1~3)
- 섹션 내 수혜 라인 → ★ 수만큼 점수 (최소 1.0)
- 주의 라인 → -1.0
- 표 행이 섹션보다 우선 (먼저 처리, 섹션은 skip)

---

## .env 필수 항목

```env
# 매매 모드
TRADE_MODE=PAPER

# KIS API
KIS_APP_KEY=...
KIS_APP_SECRET=...
KIS_ACCOUNT_NO=...
KIS_ACCOUNT_PRODUCT_CODE=01

# KRX 로그인 (pykrx 데이터 수집용)
KRX_ID=...
KRX_PW=...

# 텔레그램 봇 알림 (선택)
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...

# 텔레그램 신호 채널 (선택, MTProto)
TELEGRAM_API_ID=...
TELEGRAM_API_HASH=...
TELEGRAM_SIGNAL_CHANNEL=...
```

---

## 최근 주요 변경 이력

### 2026-05-12: PAPER 리밸런싱 실운영 리허설 성공

- Phase 1 동기화 명령:
  - `.\venv\Scripts\python.exe scripts\sync_phase1_data.py --start-date 2026-05-01 --end-date 2026-05-12 --workers 1`
- 결과:
  - `universe_count=470`
  - `price_count=2816`
  - `fundamental_count=2804`
  - fundamental 누락 2개: `088980`, `950160`
- 준비/리뷰 명령:
  - `.\venv\Scripts\python.exe scripts\prepare_and_review_rebalance.py --as-of-date 2026-05-12 --top-n 10 --output-json data\dry_run_rebalance_latest.json --output-md data\dry_run_rebalance_latest.md --quote-retries 4 --quote-delay-sec 0.5`
- dry-run 결과:
  - `dry_run_status=clean`
  - `buy_count=10`
  - `price_fallback_count=0`
  - `price_lookup_failed_count=0`
  - `price_retry_success_count=8`, `price_retry_failed_count=0`
- readiness 결과:
  - `market_time_status=ready`
  - `preflight_status=clean`
  - `execution_ready=true`
- PAPER 실행 결과:
  - `sold=0,bought=10,failed=0`
  - `data\rebalance_execution_2026-05-12.json`
  - `execution_match_status=matched`
- 현재 안전 운영 기준:
  - 실행 전 `--top-n 10` 사용 권장. `SAFETY.max_daily_buys`가 10이라 `--top-n 20`은 사전 차단될 수 있다.
  - KIS 현재가 조회의 일시적 `500`은 `price_retry,...,success`이면 복구된 조회 실패 기록이다. `price_retry_failed_count`, `price_lookup_failed_count`, `price_fallback_count`가 0인지 확인한다.

### 2026-05-12: Agent operations dashboard

- 추가/변경 파일:
  - `scripts/generate_agent_ops_dashboard.py`
  - `tests/test_generate_agent_ops_dashboard.py`
  - `data/agent_ops_dashboard_latest.md`
  - `docs/superpowers/specs/2026-05-12-agent-ops-dashboard-design.md`
  - `docs/superpowers/plans/2026-05-12-agent-ops-dashboard.md`
- 로컬 파일만 읽는 Markdown 대시보드 생성기를 추가했다.
- KIS 호출, 주문 실행, readiness 실행, 전략 파라미터 변경은 하지 않는다.
- malformed dry-run JSON은 `blocked`, 날짜 불일치는 `stale-risk` 및 overall `blocked`로 표시한다.

### 2026-05-12: Daily PAPER one-command runner

- 추가 파일:
  - `scripts/daily_paper_run.py`
  - `tests/trading/test_daily_paper_run.py`
- 매일 아침 운영 플로우를 한 명령으로 묶었다:
  - Phase 1 sync
  - dry-run prepare/review
  - readiness check
  - PAPER execution
  - post execution report review
  - intraday stop-loss/trailing-stop monitor
- 안전 경계:
  - `--confirm EXECUTE_PAPER_REBALANCE` 없이는 시작하지 않는다.
  - `TRADE_MODE=PAPER`가 아니면 시작하지 않는다.
  - readiness 실패, 실행 실패, post-review 실패 시 감시 프로세스를 시작하지 않는다.
  - 매수 실행 후에는 전체 `run_bot.py` 스케줄러가 아니라 손절/트레일링 감시 전용 스케줄러만 켠다. 이는 09:05 daily rebalance job 중복 등록을 피하기 위한 보수적 선택이다.

### 2026-05-09: Investor flow overlay

Added/changed files:
- `src/data/models.py`
- `src/data/repositories.py`
- `src/data/collectors.py`
- `src/factors/models.py`
- `src/factors/engine.py`
- `scripts/rank_phase2_factors.py`
- `scripts/smoke_test_investor_flows.py`
- `tests/data/test_repositories.py`
- `tests/data/test_collectors.py`
- `tests/data/test_smoke_test_investor_flows.py`
- `tests/factors/test_engine.py`

Summary:
- Added `investor_flows` table for ticker/date individual, foreign, and institution net-buy data.
- Phase1 sync now asks the market data provider for investor flows and stores them with prices/fundamentals.
- `PykrxMarketDataProvider.get_investor_flows()` uses `get_market_trading_value_by_date(..., on="순매수")`.
- Added recent investor flow scoring:
  - foreign + institution both net buying: `+0.6`
  - one of foreign/institution net buying: `+0.3`
  - individual net buying while both foreign/institution sell: `-0.7`
  - strong retail-only buying against foreign/institution selling: `-1.0`
- `investor_flow_score` is added as a low-weight overlay with `FACTOR.investor_flow_weight = 0.3`.
- Ranking output now includes `investor_flow_scored_count`, `investor_flow_coverage`, and per-row `investor_flow=...`.
- Added `scripts/smoke_test_investor_flows.py` to verify stored investor flow rows, latest flow date/count, scored ticker count, retail-only penalty count, and smart-money positive count without placing orders.

### 2026-05-09: Busanstock news/consensus overlay

Added/changed files:
- `src/data/models.py`
- `src/data/repositories.py`
- `src/signals/busanstock_parser.py`
- `src/signals/busanstock_reader.py`
- `src/factors/models.py`
- `src/factors/engine.py`
- `src/trading/scheduler.py`
- `scripts/smoke_test_busanstock_signals.py`
- `scripts/rank_phase2_factors.py`
- `tests/signals/test_busanstock_parser.py`
- `tests/signals/test_busanstock_reader.py`
- `tests/signals/test_smoke_test_busanstock_signals.py`

Summary:
- Added `busanstock_signals` table for site-derived news/consensus overlay signals.
- Parser extracts `종목 한눈에` buy/warning names and `컨센서스 변경` TP up/down rows from the site HTML.
- Signals are mapped by Korean stock name through active `stocks` DB rows.
- `busanstock_score` is added as a same-day-only raw overlay with `FACTOR.busanstock_weight = 0.3`.
- Ranking output now includes `busanstock_scored_count`, `busanstock_coverage`, and per-row `busanstock=...`.
- Same-day rule prevents old Busanstock news from carrying into later trading dates.
- Scheduler polls Busanstock every 15 minutes from 06:00-09:00 KST on weekdays.

### 2026-05-09: Telegram stock score stabilization

Added/changed files:
- `src/signals/telegram_parser.py`
- `scripts/smoke_test_telegram_signals.py`
- `tests/signals/test_telegram_parser.py`
- `tests/signals/test_telegram_reader.py`
- `tests/signals/test_smoke_test_telegram_signals.py`
- `tests/data/test_repositories.py`
- `tests/factors/test_rank_script.py`

Summary:
- Fixed `telegram_signals` upsert for models that do not have `updated_at`.
- Replaced garbled Telegram morning-brief parser rules with UTF-8 Korean parsing.
- Parser now emits canonical `signal_type`: `positive` / `warning`.
- Table rows parse star rating and TP; section-only warning rows become negative raw scores.
- Parser resolves Korean stock names to tickers using active `stocks` DB rows.
- Telegram signal fetch now scans 20 recent messages by default via `TELEGRAM_SIGNAL_FETCH_LIMIT`.
- Telegram signal storage now replaces rows for the same message date to remove stale false matches.
- Parser ignores URL digits and markdown source-link names to avoid false ticker matches.
- Added reader integration test for Telegram message -> parser -> DB storage.
- Added `scripts/smoke_test_telegram_signals.py` for signal fetch diagnostics without orders.
- `rank_phase2_factors.py` now prints `score_count`, `telegram_scored_count`, `telegram_coverage`, and per-row `telegram=...`.

### 2026-05-09: PAPER 리밸런싱 실행 안전 흐름

추가한 파일:
- `scripts/dry_run_rebalance.py`
- `scripts/prepare_rebalance_for_execution.py`
- `scripts/prepare_and_review_rebalance.py`
- `scripts/check_rebalance_readiness.py`
- `scripts/print_rebalance_operations_checklist.py`
- `scripts/smoke_rebalance_operations_checklist.py`
- `scripts/archive_rebalance_operations_checklist.py`
- `scripts/cleanup_rebalance_checklist_logs.py`
- `scripts/execute_rebalance_from_dry_run.py`
- `scripts/review_rebalance_reports.py`
- `tests/trading/test_dry_run_rebalance.py`
- `tests/trading/test_prepare_rebalance_for_execution.py`
- `tests/trading/test_execute_rebalance_from_dry_run.py`

핵심 동작:
- 드라이런은 계좌 잔고와 실시간 호가를 조회해 매도/매수 계획을 만들지만 주문 메서드는 호출하지 않는다.
- `prepare_rebalance_for_execution.py`는 `--price-fallback none`, `--quote-retries 4`, `--quote-delay-sec 0.5`로 드라이런을 만들고 같은 JSON을 즉시 preflight 검증한다.
- `prepare_and_review_rebalance.py`는 위 준비 단계가 성공했을 때 바로 `review_rebalance_reports.py`를 실행하며, 주문은 내지 않는다.
- `check_rebalance_readiness.py`는 현재 시간이 평일 09:00-15:20 KST인지와 dry-run preflight가 clean인지 확인하지만 주문은 내지 않는다.
- `print_rebalance_operations_checklist.py`는 날짜별 prepare/review/readiness/execute/post-review 명령 순서를 출력하지만 주문은 내지 않는다.
- `smoke_rebalance_operations_checklist.py`는 체크리스트를 생성하고 참조된 `scripts\*.py` 파일들이 실제 존재하는지 확인하지만 주문은 내지 않는다.
- `archive_rebalance_operations_checklist.py`는 체크리스트 smoke 결과를 화면에 출력하고 날짜별 `logs\rebalance_operations_checklist_YYYY-MM-DD.log`에 보관하지만 주문은 내지 않는다.
- `cleanup_rebalance_checklist_logs.py`는 오래된 체크리스트 로그 정리 후보를 출력한다. 실제 삭제는 `--apply`가 있을 때만 수행한다.
- `execute_rebalance_from_dry_run.py`는 확인 토큰 `EXECUTE_PAPER_REBALANCE`가 있어야 동작하며, 평일 09:00-15:20 KST 밖에서는 기본적으로 주문을 막는다.
- `--review-before-execute`를 사용하면 주문 직전에 dry-run 리포트 요약을 다시 출력하고, 리뷰가 blocked이면 주문 전에 멈춘다.
- `execute_rebalance_from_dry_run.py`는 실행 리포트 JSON이 이미 있으면 기본 차단한다. 의도적으로 덮어쓸 때만 `--force-overwrite-report`를 사용한다.
- 실제 주문 직전에도 `execute_rebalance(..., preflight_report_path=..., expected_preflight_date=...)`가 fallback 가격, 실시간 호가 실패, 날짜 불일치를 다시 차단한다.
- `review_rebalance_reports.py`는 KIS/DB에 접속하지 않고 드라이런 JSON과 실행 결과 JSON만 읽어서 사람이 확인할 요약을 출력한다.

### 2026-05-06: 텔레그램 신호 통합

추가한 파일:
- `src/signals/__init__.py`
- `src/signals/telegram_parser.py`
- `src/signals/telegram_reader.py`
- `tests/signals/test_telegram_parser.py`

수정한 파일:
- `requirements.txt` — `telethon==1.38.1` 추가
- `config.py` — `TelegramSignalConfig`, `FactorConfig.telegram_weight` 추가
- `src/data/models.py` — `TelegramSignal` 테이블 추가
- `src/data/repositories.py` — `upsert_telegram_signals`, `get_latest_telegram_signals` 추가
- `src/factors/models.py` — `FactorScore.telegram_score` 필드 추가 (yield_score와 total_score 사이)
- `src/factors/engine.py` — 텔레그램 신호 로드 및 팩터 반영
- `src/trading/scheduler.py` — `_telegram_signal_job` 추가, 오전 6–9시 15분 폴링

### 2026-05-06 이전: 네이버 뉴스 API 전면 삭제

다른 AI 에이전트가 추가했던 Naver News 관련 코드 전체 제거:
- 삭제된 모델: `NewsItemRecord`, `NewsSignalScoreRecord`, `ThemeStockMapping`
- 삭제된 파일: `src/signals/` (이전 구조), `scripts/smoke_test_naver_news.py`, `scripts/import_theme_stock_mappings.py`, `tests/signals/` (이전 구조), `tests/data/test_import_theme_stock_mappings_script.py`
- `FactorScore`에서 `news_score` 필드 제거

### 2026-05-05~06: 유니버스 방식 변경

기존: KOSPI200/KOSDAQ150 인덱스 종목  
변경: 전체 시장에서 유동성(거래대금) 기준 상위 종목 직접 선발

`collectors.py` 핵심 로직:
```python
_build_market_universe(market, target_date, top_n, lookback_days)
  → get_market_ticker_list()  # 우선주 제외
  → _filter_status_eligible_tickers()  # 관리/경고/정지 제외
  → get_market_ohlcv_by_ticker()  # 최근 5영업일 거래대금 평균
  → 상위 top_n 반환
```

### 2026-05-04~05: 핵심 버그 수정

1. **리밸런싱 매수 예산**: 매도 예상 대금 미포함 버그 수정
2. **일일 손실 한도**: 보유 시작 기준점 없이 누적 손실 계산하던 버그 수정
3. **동시 손절/트레일링**: 같은 사이클에서 같은 종목 이중 매도 방지
4. **pre-market sync 실패 시 리밸런싱 블록**: `require_pre_market_sync=True`

---

## 테스트 실행

```powershell
.\venv\Scripts\pytest.exe tests/ -q
```

최근 전체 결과: `339 passed`
daily runner/scheduler targeted 결과: `19 passed`
KIS/dry-run parser targeted 결과: `44 passed`
대시보드 targeted 결과: `11 passed`

특정 모듈만:
```powershell
.\venv\Scripts\pytest.exe tests/signals/ -v          # 텔레그램 파서 8개
.\venv\Scripts\pytest.exe tests/factors/ -v          # 팩터 엔진
.\venv\Scripts\pytest.exe tests/data/ -v             # DB/수집기
.\venv\Scripts\pytest.exe tests/trading/ -v          # 트레이딩 엔진
```

---

## 유용한 명령어

```powershell
# 설정 검증
.\venv\Scripts\python.exe config.py

# KIS API 연결 확인
.\venv\Scripts\python.exe scripts\smoke_test_kis.py

# 매일 아침 원클릭 PAPER 운영: 매수/리밸런싱 후 장중 손절/트레일링 감시 전용 스케줄러 시작
.\venv\Scripts\python.exe scripts\daily_paper_run.py --confirm EXECUTE_PAPER_REBALANCE

# PAPER 리밸런싱 준비: 주문 없이 최신 드라이런 JSON/Markdown 생성 후 preflight 검증
.\venv\Scripts\python.exe scripts\prepare_rebalance_for_execution.py --as-of-date 2026-05-12 --top-n 10

# PAPER 리밸런싱 준비 + 리뷰: 주문 없이 준비 상태까지 한 번에 확인
.\venv\Scripts\python.exe scripts\prepare_and_review_rebalance.py --as-of-date 2026-05-12 --top-n 10 --output-json data\dry_run_rebalance_latest.json --output-md data\dry_run_rebalance_latest.md --quote-retries 4 --quote-delay-sec 0.5

# PAPER 리밸런싱 운영 체크리스트: 날짜별 안전 명령 순서 출력
.\venv\Scripts\python.exe scripts\print_rebalance_operations_checklist.py --as-of-date 2026-05-12 --top-n 10

# PAPER 리밸런싱 체크리스트 smoke: 참조 스크립트 파일 존재 확인
.\venv\Scripts\python.exe scripts\smoke_rebalance_operations_checklist.py --as-of-date 2026-05-12 --top-n 10

# PAPER 리밸런싱 체크리스트 로그 아카이브: smoke 결과를 logs/에 저장
.\venv\Scripts\python.exe scripts\archive_rebalance_operations_checklist.py --as-of-date 2026-05-12 --top-n 10

# PAPER 리밸런싱 체크리스트 로그 정리: 기본은 dry-run, 실제 삭제는 --apply 필요
.\venv\Scripts\python.exe scripts\cleanup_rebalance_checklist_logs.py --keep 20

# PAPER 리밸런싱 실행 가능 상태 체크: 주문 없이 정규장/clean JSON 여부 확인
.\venv\Scripts\python.exe scripts\check_rebalance_readiness.py --dry-run-json data\dry_run_rebalance_latest.json --expected-date 2026-05-12

# PAPER 리밸런싱 실행: 정규장 중, 같은 날짜의 clean JSON일 때만 사용
.\venv\Scripts\python.exe scripts\execute_rebalance_from_dry_run.py --dry-run-json data\dry_run_rebalance_latest.json --expected-date 2026-05-12 --confirm EXECUTE_PAPER_REBALANCE --review-before-execute --execution-report-json data\rebalance_execution_2026-05-12.json

# PAPER 리밸런싱 리포트 리뷰: KIS/DB 접속 없이 JSON 결과만 요약
.\venv\Scripts\python.exe scripts\review_rebalance_reports.py --dry-run-json data\dry_run_rebalance_latest.json --execution-report-json data\rebalance_execution_2026-05-12.json

# PAPER rebalance run bundle archive: dry-run/readiness/review/checklist artifacts into logs/rebalance_run_YYYY-MM-DD
.\venv\Scripts\python.exe scripts\archive_rebalance_run_bundle.py --as-of-date 2026-05-12 --top-n 10 --dry-run-json data\dry_run_rebalance_latest.json --dry-run-md data\dry_run_rebalance_latest.md --execution-report-json data\rebalance_execution_2026-05-12.json

# PAPER dry-run comparison: compare two JSON reports and optionally write Markdown
.\venv\Scripts\python.exe scripts\compare_rebalance_reports.py --before-json data\dry_run_rebalance_retry_strict.json --after-json data\dry_run_rebalance_latest.json --output-md data\rebalance_comparison_latest.md

# 수동 데이터 동기화
.\venv\Scripts\python.exe scripts\sync_phase1_data.py --start-date 2026-05-01 --end-date 2026-05-12 --workers 1

# 팩터 점수 확인
.\venv\Scripts\python.exe scripts\rank_phase2_factors.py --as-of-date 2026-05-12 --top-n 10

# 에이전트 운영 대시보드 생성: 로컬 파일만 읽고 주문/API 호출 없음
.\venv\Scripts\python.exe scripts\generate_agent_ops_dashboard.py --expected-date 2026-05-12

# Telegram stock-score signal smoke test (orders are never submitted)
.\venv\Scripts\python.exe scripts\smoke_test_telegram_signals.py --as-of-date 2026-05-06

# Busanstock news/consensus overlay smoke test (orders are never submitted)
.\venv\Scripts\python.exe scripts\smoke_test_busanstock_signals.py --as-of-date 2026-05-06

# Investor flow readiness smoke test (orders are never submitted)
.\venv\Scripts\python.exe scripts\smoke_test_investor_flows.py --as-of-date 2026-05-06

# 봇 시작 (08:40 전에 시작)
.\venv\Scripts\python.exe scripts\run_bot.py
```

---

## 현재 알려진 제약사항

1. **SQLite 잠금**: 다른 Python 프로세스가 `data/quntbot.db`를 열고 있으면 sync가 `OperationalError: database is locked`으로 실패. 봇 시작 전 다른 Python 터미널 닫을 것.

2. **KRX 로그인**: `KRX_ID`/`KRX_PW` 없으면 pykrx가 빈 JSON 반환 → `RuntimeError: no market data rows collected`. `.env`에 KRX 계정 필수.

3. **텔레그램 신호 첫 실행**: `telethon` 최초 실행 시 전화번호 + OTP 필요. 인터랙티브 환경에서 한 번 실행해 `data/telegram_signal.session` 생성 후 봇에서 사용.

4. **FactorScore 위치 인자 순서**: `telegram_score`가 `yield_score`와 `total_score` 사이 9번째 필드. `busanstock_score`, `investor_flow_score`는 기본값이 있는 후행 필드다.

5. **PAPER 리밸런싱 실행 조건**: 같은 날짜의 clean dry-run JSON이 필요하다. fallback 가격이나 실시간 호가 실패가 있으면 preflight가 주문 전 차단한다. 수동 실행 스크립트는 기본적으로 평일 09:00-15:20 KST에서만 주문을 허용한다.

6. **실행 리포트 보존**: `--execution-report-json` 경로에 파일이 이미 있으면 실행 스크립트가 주문 전에 차단한다. 같은 파일을 의도적으로 덮어쓸 때만 `--force-overwrite-report`를 추가한다.

---

## 미구현 / 다음 우선순위

설계 문서는 `docs/superpowers/specs/` 참고.

1. **DART quality 지표**: `src/data/collectors.py`에 ROE(TTM), 영업이익률(TTM), 부채비율 수집 추가. 현재 quality_score는 EPS/BPS 단순 계산만 함.

2. **매수 필터 구현**: `docs/superpowers/specs/2026-05-04-buy-filter-policy-design.md` 참고.
   - PER/PBR 음수 제외 (요건 확정)
   - 최근 2분기 연속 적자 제외
   - 상장 1년 미만 제외
   - 유동성 필터는 유니버스 단계에서 이미 적용됨

3. **기술적 진입 필터**: `docs/superpowers/specs/2026-05-04-technical-entry-filter-policy-design.md` 참고.
   - MA20 돌파, MA60 상승, RSI < 75, 20일 변동성 < 5%
   - 4개 중 3개 이상 만족 시 매수 허용

4. **백테스트 손절/트레일링**: 백테스트 엔진에 stop-loss(-8%), trailing-stop(-10%) 미반영.

5. **백테스트 look-ahead bias 수정**: B안 확정 — T-1 데이터로 신호 계산, T일 시가 체결.

---

## CLAUDE.md 핵심 규칙 요약

- 코드 수정 전 관련 파일 최소 5개 이상 읽기
- 추측 금지, 모르면 Grep/Read로 확인
- 변경 후 반드시 테스트 실행으로 검증
- 구현 전 Plan 모드로 설계 먼저
- 단순함 우선, 요청 이상의 기능 추가 금지
- 수술적 변경: 관련 없는 코드 리팩토링 금지
