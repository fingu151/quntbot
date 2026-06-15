# quntbot Handoff For Agents

## 2026-06-15 cleanup status

- MTProto Telegram stock-signal scoring is removed. Telegram is now used only
  for Bot API notifications through `src\notify\notifier.py` and
  `scripts\smoke_test_telegram.py`.
- The legacy SQLite table `telegram_signals` was archived to
  `data\legacy_telegram_signals_archive.csv` and
  `data\legacy_telegram_signals_archive.md`, then dropped from
  `data\quntbot.db` by `scripts\cleanup_legacy_telegram_signals.py --apply`.
- The unconnected KWR experiment was removed because it had no runtime or
  backtest runner entry point outside its own tests.
- Current factor output uses the 100-point budget fields:
  `value_score`, `quality_score`, `momentum_score`, `yield_score`,
  `technical_score`, `auxiliary_score`, and `total_score`.

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
# Hankyung consensus metadata + PDF body analysis.
.\venv\Scripts\python.exe scripts\sync_korean_research_reports.py --url https://consensus.hankyung.com/ --source hankyung_consensus --broker "한경 컨센서스" --include-pdf-text --pages 15 --start-date 2026-01-01 --end-date 2026-01-31

# Mirae Asset research metadata + PDF body analysis.
# Use --pages N to collect multiple public list pages.
.\venv\Scripts\python.exe scripts\sync_korean_research_reports.py --url https://securities.miraeasset.com/bbs/board/message/list.do?categoryId=1533 --source mirae_asset --broker "미래에셋증권" --include-pdf-text --pages 2

# Mirae Asset 2026 YTD collection should be run in date chunks because broad
# provider searches return a capped recent slice.
.\venv\Scripts\python.exe scripts\sync_korean_research_reports.py --url https://securities.miraeasset.com/bbs/board/message/list.do?categoryId=1533 --source mirae_asset --broker "미래에셋증권" --include-pdf-text --pages 80 --start-date 2026-01-01 --end-date 2026-01-31

# Re-analyze already stored Mirae Asset report rows with the current rule-v1 analyzer.
.\venv\Scripts\python.exe scripts\reanalyze_research_report_bodies.py --source mirae_asset --broker "미래에셋증권"

# Generate a human-readable Mirae Asset research summary Markdown report.
.\venv\Scripts\python.exe scripts\generate_mirae_research_summary.py --output data\mirae_research_summary_latest.md --limit 1000

# Compare factor rankings with and without Mirae Asset research overlay.
.\venv\Scripts\python.exe scripts\compare_research_report_factor_impact.py --as-of-date 2026-05-14 --research-start-date 2026-01-01 --top-n 100

# One-command Mirae Asset read-only research pipeline:
# collect metadata/PDF text, reanalyze bodies, refresh summary, refresh factor impact.
.\venv\Scripts\python.exe scripts\run_mirae_research_readonly_pipeline.py --start-date 2026-01-01 --as-of-date 2026-05-14 --pages 80 --limit 1000 --top-n 100

# One-command Hankyung consensus read-only research pipeline:
# collect public metadata, attempt linked PDF body text, refresh summary, refresh factor impact.
.\venv\Scripts\python.exe scripts\run_hankyung_research_readonly_pipeline.py --start-date 2026-01-01 --end-date 2026-05-14 --as-of-date 2026-05-14 --pages 60 --limit 3000 --top-n 100

# Discover usable public URLs from supplemental candidate searches and write
# an ingest-ready draft. This is read-only market-intel work and submits no
# orders. Provider list pages are checked for reachability only; unrelated list
# PDFs are not promoted into the draft.
.\venv\Scripts\python.exe -m scripts.discover_supplemental_research_sources --candidates data\supplemental_source_candidates.json --discovery-output data\supplemental_source_discovery_results.json --source-draft-output data\supplemental_research_sources_draft.json --max-candidates 112 --max-urls-per-candidate 8 --report-date 2026-05-16

# Verify discovered PDF candidates by fetching text and requiring the ticker in
# the body before ingest. This prevents search-result false positives.
.\venv\Scripts\python.exe -m scripts.verify_supplemental_research_sources --input data\supplemental_research_sources_draft.json --verified-output data\supplemental_research_sources_verified.json --rejected-output data\supplemental_research_sources_rejected.json

# Ingest only verified supplemental sources.
.\venv\Scripts\python.exe -m scripts.ingest_supplemental_research_sources --input data\supplemental_research_sources_verified.json

# One-command dashboard artifact refresh with supplemental discovery enabled.
# This can call public search/PDF URLs, verifies ticker text before ingest, and
# still submits no orders.
.\venv\Scripts\python.exe -m scripts.refresh_public_dashboard_artifacts --refreshed-through 2026-05-15 --include-supplemental-discovery
```

Current verified provider behavior:
- Hankyung must use `https://consensus.hankyung.com/`, not
  `https://markets.hankyung.com/consensus`. The working PDF path is
  `/analysis/downpdf?report_idx=...`.
- Hankyung blocks Python's default requests user-agent with `Block access. 0001`,
  but serves PDFs with a browser-style user-agent. The reader sends a browser
  user-agent for list and PDF fetches.
- Latest Hankyung 2026 YTD collection stored `2012` rows dated `2026-01-02` to
  `2026-05-14`; body statuses are `extracted=2010`, `empty=2`.
- Latest Hankyung factor-impact report wrote
  `data\hankyung_research_factor_impact_latest.md`: `score_count=198`,
  `research_signal_count=478`, `impacted_count=131`.
- Mirae Asset category `1533` stores metadata and extracts linked PDFs. Latest
  multi-page smoke used `--pages 2` and stored 20 rows with
  `pdf_text_extracted=20`.
- Latest read-only pipeline verification used `venv\Scripts\python.exe` with
  `pypdf 5.1.0`: `pdf_text_attempted=323`, `pdf_text_extracted=323`,
  `pdf_text_length=1020335`, `analysis_success_count=323`.
- Latest factor-impact report wrote
  `data\mirae_research_factor_impact_latest.md`: `score_count=198`,
  `research_signal_count=115`, `impacted_count=48`.
- Latest 2026 YTD Mirae collection was run in monthly chunks:
  `2026-01=70`, `2026-02=95`, `2026-03=36`, `2026-04=63`,
  `2026-05=59`, total `323` reports, all `body_text_status=extracted`.
- Every sync command prints `orders_submitted=0`.
- Latest supplemental discovery replaced Google web search URLs with Bing/Naver
  web-search URLs and checked `112` candidates / `896` URLs:
  `usable_source_count=5`, `source_draft_count=5`, `orders_submitted=0`.
  Status counts were `reference_url_reachable=111`,
  `provider_list_reachable=224`, `reachable_html=556`,
  `search_result_pdf_found=4`, `fetch_failed=1`.
- Latest supplemental source verification fetched the 5 draft PDFs and required
  the ticker in extracted body text: `verified_count=1`, `rejected_count=4`.
  The verified row was ticker `042520`, report date `2026-04-09`, source
  `yuanta_pdf_naver`; rejected rows had `ticker_not_found_in_body`.
- Ingesting `data\supplemental_research_sources_verified.json` stored
  `signal_rows=1`, `analysis_rows=1`, `brief_rows=1`, `orders_submitted=0`.
  Refreshing ticker briefs then moved `complete_count` from `406` to `407` and
  `needs_review_count` from `112` to `111`.
- `scripts.refresh_public_dashboard_artifacts` now supports
  `--include-supplemental-discovery`. When enabled, it runs
  export candidates -> discover URLs -> verify ticker text -> ingest verified
  sources -> rebuild ticker briefs/queues/candidates before writing the QA
  sample. The PowerShell refresh loop also accepts
  `-IncludeSupplementalDiscovery`.

Relevant files:
- `src\signals\research_report_analysis.py`
- `src\signals\research_report_parser.py`
- `src\signals\research_report_reader.py`
- `src\data\models.py`
- `src\data\repositories.py`
- `scripts\sync_korean_research_reports.py`
- `scripts\reanalyze_research_report_bodies.py`
- `scripts\generate_mirae_research_summary.py`
- `scripts\compare_research_report_factor_impact.py`
- `scripts\run_mirae_research_readonly_pipeline.py`
- `scripts\run_hankyung_research_readonly_pipeline.py`
- `scripts\discover_supplemental_research_sources.py`
- `tests\signals\test_research_report_analysis.py`
- `tests\signals\test_research_report_parser.py`
- `tests\signals\test_research_report_reader.py`
- `tests\signals\test_sync_korean_research_reports.py`
- `tests\signals\test_reanalyze_research_report_bodies.py`
- `tests\signals\test_generate_mirae_research_summary.py`
- `tests\signals\test_run_mirae_research_readonly_pipeline.py`
- `tests\signals\test_run_hankyung_research_readonly_pipeline.py`
- `tests\signals\test_discover_supplemental_research_sources.py`
- `tests\factors\test_compare_research_report_factor_impact.py`
- `data\mirae_research_summary_latest.md`
- `data\mirae_research_factor_impact_latest.md`
- `data\hankyung_research_summary_latest.md`
- `data\hankyung_research_factor_impact_latest.md`
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
                              SyncRun
    database.py               get_engine(), create_tables(), session_scope()
    repositories.py           upsert_*/get_* 함수 (SQLite upsert)
    collectors.py             PykrxMarketDataProvider, sync_phase1_data
  factors/
    models.py                 FactorScore dataclass
    scoring.py                score_series(), combine_scores(), _zscore()
    engine.py                 calculate_factor_scores(), _load_factor_inputs()
  signals/
    busanstock_parser.py      Busanstock news/consensus parser
    research_report_reader.py Broker research report metadata/PDF reader
  trading/
    kis_client.py             KIS REST API 래퍼
    engine.py                 TradingEngine (stop-loss, trailing-stop, 잔고조회)
    rebalancer.py             compute_rebalance_orders(), execute_rebalance()
    scheduler.py              APScheduler 루프
  backtest/
    engine.py                 run_backtest()
    models.py                 BacktestResult, Trade
  notify/
    notifier.py               Telegram Bot API alerts via requests
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
| `research_report_signals` | id / (report_date, ticker, source, title) | rating, target_price, raw_score, source_url |
| `sync_runs` | id | started_at, finished_at, status, universe/price/fundamental_count |

---

## 팩터 점수 구조

`FactorScore` fields:
```python
ticker, name, market, as_of_date,
value_score,             # up to 25 points
quality_score,           # up to 25 points
momentum_score,          # up to 20 points
yield_score,             # up to 5 points
technical_score,         # up to 15 points
auxiliary_score,         # up to 10 points
busanstock_score,
investor_flow_score,
research_report_score,
total_score,             # 100-point budget total
rank                     # 1 = best
```

`config.py` point budget:
```python
value_points     = 25
quality_points   = 25
momentum_points  = 20
yield_points     = 5
technical_points = 15
auxiliary_points = 10
```

Missing-data policy is implemented in `src/factors/engine.py`: critical value
or momentum gaps exclude candidates, while optional auxiliary inputs contribute
zero when absent.

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

## Telegram notifications

Telegram is notification-only now. The removed MTProto stock-signal scorer no
longer contributes to factor scores, scheduler polling, or DB schemas. Use
`scripts\smoke_test_telegram.py` only to verify Bot API alert delivery; it does
not submit orders.

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
  - `scripts/daily_paper_run.py` 기본 `--top-n`은 `PORTFOLIO.n_holdings` (`30`)를 따른다.
  - `SAFETY.max_daily_buys`는 `10`으로 유지한다. 목표 리스트는 30종목으로 만들되, 신규 매수는 하루 최대 10건씩 단계적으로 채운다.
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

### 2026-05-09: Removed stock-signal history

The former MTProto Telegram stock-signal path was superseded by the
2026-06-11 improvement-roadmap cleanup. Telegram remains notification-only.

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

### 2026-05-06: Removed stock-signal integration

This historical stock-signal integration was removed in the 2026-06-11
improvement-roadmap cleanup. Current Telegram support is notification-only.

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
.\venv\Scripts\pytest.exe tests/signals/ -v          # signal parsers/readers
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

3. **Telegram 알림 권한**: 알림은 Bot API만 사용한다. `TELEGRAM_BOT_TOKEN`과 `TELEGRAM_CHAT_ID`가 맞고 봇이 대상 채팅에 접근할 수 있어야 한다.

4. **FactorScore 위치 인자 순서**: `technical_score`, `auxiliary_score`, `busanstock_score`, `investor_flow_score`, `research_report_score`는 후행 필드다.

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
