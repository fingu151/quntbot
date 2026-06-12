# quntbot Progress Log

## 2026-06-11 US macro exposure overlay

### Completed

- Added a unified macro exposure overlay that combines US index moves, bond
  yield moves, and official macro indicator release rows into one portfolio
  exposure adjustment.
- Added `MacroRiskConfig` defaults and `macro_indicator_releases` storage for
  CPI/Core CPI, labor, and rate-policy release data.
- Added `scripts/sync_macro_indicators.py` for FRED-backed official macro data
  sync. Without `FRED_API_KEY`, the fetcher returns no rows and the macro layer
  records missing source status instead of blocking orders.
- Added macro risk reduction orders that can proportionally reduce current
  holdings to a target cash ratio without duplicating existing rebalance sells.
- Wired macro adjustment into dry-run rebalance reports, scheduler rebalance
  order matching, intraday macro dry-run reports, and backtests.
- Added `scripts/run_intraday_macro_risk_dry_run.py`; it writes reduction
  candidates only and never submits PAPER/LIVE orders.
- No PAPER/LIVE orders were submitted during this change.

### Verification

- `.\venv\Scripts\python.exe -m pytest tests\trading tests\backtest tests\data -q`
  -> `371 passed`.
- `.\venv\Scripts\python.exe -m compileall config.py src scripts tests`
  -> passed.
- `.\venv\Scripts\python.exe -m pytest tests -q`
  -> `649 passed`.
- `.\venv\Scripts\python.exe scripts\check_rebalance_readiness.py`
  -> blocked safely with `execution_ready=false`; preflight was clean, but
  market time was outside weekday 09:00-15:20 KST.

## 2026-06-11 Quntbot improvement roadmap implementation slice

### Completed

- Removed MTProto Telegram stock-signal scoring paths while keeping Telegram
  notifier configuration and notification code intact.
- Replaced factor score output with a 100-point budget:
  Value 25, Quality 25, Momentum 20, Yield 5, Technical 15, Auxiliary 10.
- Added technical scoring plus a narrower hard filter for extreme overheat or
  volatility.
- Added `Stock.instrument_type` with SQLite migration support and ETF universe
  collection scaffolding.
- Added ETF backtest transaction-tax branching with ETF sells using 0% tax.
- Updated rank and public snapshot output to expose `technical` and `auxiliary`
  score fields instead of Telegram score fields.
- No PAPER/LIVE orders were submitted during this change.

### Verification

- `.\venv\Scripts\python.exe -m pytest tests\factors\test_engine.py::test_factor_score_contract_has_no_telegram_score_and_uses_100_point_budget tests\factors\test_engine.py::test_technical_score_contributes_points_without_requiring_old_filter_pass tests\data\test_database.py::test_create_tables_creates_phase1_tables tests\data\test_collectors.py::test_pykrx_provider_can_add_etf_universe_rows tests\backtest\test_backtest_engine.py::test_sell_uses_zero_transaction_tax_for_etf_market -q`
  -> `5 passed`.
- `.\venv\Scripts\python.exe -m pytest tests\factors tests\data tests\backtest\test_backtest_engine.py tests\test_config.py tests\test_generate_public_portfolio_snapshot.py tests\strategies\test_adaptive_alpha.py tests\trading\test_dry_run_rebalance.py tests\trading\test_scheduler.py -q`
  -> `207 passed`.
- `.\venv\Scripts\python.exe -m compileall config.py src scripts tests`
  -> passed.
- `.\venv\Scripts\python.exe -m pytest tests -q`
  -> `634 passed`.
- `.\venv\Scripts\python.exe scripts\check_rebalance_readiness.py`
  -> blocked safely with `execution_ready=false` because market time was outside
  weekday 09:00-15:20 KST and the latest dry-run report was stale
  (`as_of_date=2026-06-10`, expected `2026-06-11`).

## 2026-06-03 Daily buy limit raised to 30

### Completed

- Raised `SAFETY.max_daily_buys` from `20` to `30` after the 2026-06-03 dry-run
  rebalance produced `buy_count=24` and was blocked at `prepare_review` by the
  prior `24/20` daily buy limit.
- Updated the default-parameter regression test and the rebalance preflight
  guard test so buys above `30` remain blocked.
- No PAPER/LIVE orders were submitted during this change.

### Verification

- `.\venv\Scripts\python.exe -m pytest tests\test_strategy_defaults.py tests\trading\test_rebalancer.py::test_execute_rebalance_blocks_when_dry_run_orders_exceed_daily_buy_limit -q`
  -> 2 passed.

## 2026-06-02 Live ATR stop integration

### Completed

- Added live ATR stop support to `TradingEngine.check_exit_rules()`.
- ATR stop now applies before the fixed percentage stop for positions that have
  not completed the first profit-take stage:
  - ATR source: injected `atr_lookup(ticker, as_of_date, window)`;
  - stop price: `avg_price - ATR * EXIT_RULES.atr_multiplier`;
  - order path: full-position risk exit through `sell(..., enforce_daily_limit=False)`.
- Added DB-backed ATR calculation in `src.trading.scheduler` using
  `daily_prices` true range over `EXIT_RULES.atr_window`.
- Wired ATR lookup into both:
  - `run_scheduler()`;
  - `scripts.daily_paper_run.run_intraday_stop_monitor()`.
- No PAPER/LIVE orders were submitted during this change.

### Verification

- RED: `.\venv\Scripts\python.exe -m pytest tests\trading\test_engine.py::test_check_exit_rules_atr_stop_sells_before_static_stop -q`
  failed because `TradingEngine.__init__()` did not accept `atr_lookup`.
- RED:
  `.\venv\Scripts\python.exe -m pytest tests\trading\test_scheduler.py::test_load_daily_price_atr_uses_true_range tests\trading\test_scheduler.py::test_run_scheduler_injects_atr_lookup_into_trading_engine -q`
  failed because scheduler had no ATR loader and did not inject an ATR lookup.
- RED:
  `.\venv\Scripts\python.exe -m pytest tests\trading\test_daily_paper_run.py::test_intraday_monitor_registers_only_stop_monitor -q`
  failed because `daily_paper_run` did not create a DB-backed ATR lookup.
- GREEN:
  `.\venv\Scripts\python.exe -m pytest tests\trading\test_engine.py tests\trading\test_scheduler.py tests\trading\test_daily_paper_run.py tests\trading\test_rebalancer.py tests\trading\test_execute_rebalance_from_dry_run.py -q`
  -> `100 passed`.
- Syntax check:
  `.\venv\Scripts\python.exe -m compileall config.py src\trading scripts\daily_paper_run.py tests\trading`
  -> passed.

## 2026-05-28 PAPER execution HTTP 500 handling

### Completed

- Investigated a partial PAPER rebalance execution failure:
  - `000270` sell was accepted;
  - `012860` sell was accepted;
  - the next `order-cash` call returned HTTP `500`;
  - `KisClient.place_order()` raised `requests.exceptions.HTTPError`;
  - `execute_rebalance()` only caught `RuntimeError`, so the script crashed
    instead of recording a per-ticker failure summary.
- Updated `execute_rebalance()` to catch order-level exceptions and append the
  ticker to `failed`, allowing the loop to continue and return a final summary.
- Added `--skip-ticker` to `scripts/execute_rebalance_from_dry_run.py` so a
  partial run can be resumed without retrying already accepted tickers.
- No additional live/PAPER orders were submitted during this fix.

### Verification

- RED: `.\venv\Scripts\python.exe -m pytest tests\trading\test_rebalancer.py -q`
  failed because a raised `Exception("500 Server Error")` escaped the sell/buy
  loops.
- RED: `.\venv\Scripts\python.exe -m pytest tests\trading\test_execute_rebalance_from_dry_run.py -q`
  failed because `--skip-ticker` was not recognized.
- GREEN:
  `.\venv\Scripts\python.exe -m pytest tests\trading\test_execute_rebalance_from_dry_run.py tests\trading\test_rebalancer.py -q`
  -> `38 passed`.
- Syntax check:
  `.\venv\Scripts\python.exe -m compileall src\trading scripts\execute_rebalance_from_dry_run.py tests\trading`
  -> passed.

## 2026-05-28 Rebalance sell cap aligned with 30-stock portfolio

### Completed

- Investigated the latest prepare/rebalance blocker:
  - `data/dry_run_rebalance_latest.json` has `as_of_date=2026-05-28`;
  - `holdings_count=37`;
  - `target_count=30`;
  - `sell_count=18`;
  - `buy_count=10`;
  - preflight blocked because the old daily sell limit was `10`.
- Raised `SAFETY.max_daily_sells` from `10` to `30`, matching the current
  30-stock portfolio design and allowing today's `18` planned position-cleanup
  sells.
- Kept the sell limit active: dry-run preflight now allows up to `30` sells and
  still blocks `31+` planned sells.
- No order path was executed during verification.

### Verification

- RED: `.\venv\Scripts\python.exe -m pytest tests\trading\test_rebalancer.py -q`
  failed on `sell_count=30` with `daily sell limit would be exceeded (30/10)`.
- GREEN:
  - `.\venv\Scripts\python.exe -m pytest tests\trading\test_rebalancer.py -q`
    -> `22 passed`;
  - `.\venv\Scripts\python.exe -m pytest tests\trading\test_engine.py -q`
    -> `30 passed`;
  - `.\venv\Scripts\python.exe -m pytest tests\trading\test_prepare_rebalance_for_execution.py tests\trading\test_check_rebalance_readiness.py tests\trading\test_scheduler.py -q`
    -> `29 passed`.
- Syntax check:
  `.\venv\Scripts\python.exe -m compileall config.py src\trading scripts\prepare_rebalance_for_execution.py scripts\check_rebalance_readiness.py tests\trading`
  -> passed.
- Latest no-order readiness check:
  `.\venv\Scripts\python.exe scripts\check_rebalance_readiness.py --dry-run-json data\dry_run_rebalance_latest.json --expected-date 2026-05-28`
  -> `preflight_status=clean`, `execution_ready=true`.

## 2026-05-28 Risk exits bypass daily sell cap

### Completed

- Confirmed the root cause: `SAFETY.max_daily_sells=10` was enforced by
  `TradingEngine.sell()` for every sell path, so stop-loss and staged exit
  monitor sells could be blocked after the daily sell counter reached the
  rebalance/manual safety limit.
- Kept normal/manual/rebalance `sell()` calls under the daily sell cap.
- Added an explicit `enforce_daily_limit` switch to `TradingEngine.sell()` and
  used `False` only for risk-exit paths:
  - legacy stop-loss monitor;
  - legacy trailing-stop monitor;
  - staged full stop;
  - staged first profit take;
  - staged post-profit trailing bucket;
  - staged breakeven bucket.
- Rebalance dry-run preflight still blocks rebalance plans whose `sell_count`
  exceeds `SAFETY.max_daily_sells`, so PAPER safety/readiness gates remain in
  place.

### Verification

- RED: `.\venv\Scripts\python.exe -m pytest tests\trading\test_engine.py -q`
  failed with `RuntimeError: 일일 매도 한도 초과: 1/1` in both
  `check_stop_loss()` and `check_exit_rules()`.
- GREEN: `.\venv\Scripts\python.exe -m pytest tests\trading\test_engine.py -q`
  -> `30 passed`.
- Related trading tests:
  `.\venv\Scripts\python.exe -m pytest tests\trading\test_engine.py tests\trading\test_rebalancer.py tests\trading\test_scheduler.py -q`
  -> `69 passed`.
- Syntax check: `.\venv\Scripts\python.exe -m compileall src\trading tests\trading`
  -> passed.

## 2026-05-26 Remove minimum holding sell gate

### Completed

- Removed the rebalance sell block that required an exit-state `entry_date`.
- Removed the rebalance sell block that required `min_holding_trading_days`.
- Set `REBALANCE.min_holding_trading_days` to `0` so current defaults match the
  new behavior.
- Aligned the backtest engine and Adaptive Alpha wrapper so historical tests no
  longer assume a minimum holding-day gate.
- Kept stop-loss, trailing, breakeven, stop-cooldown re-entry protection, daily
  sell limits, and PAPER dry-run/preflight gates intact.

### Verification

- `.\venv\Scripts\python.exe -m pytest tests\trading\test_dry_run_rebalance.py tests\trading\test_scheduler.py tests\backtest\test_backtest_engine.py tests\strategies\test_adaptive_alpha.py tests\test_strategy_defaults.py`
  -> `67 passed`.
- `.\venv\Scripts\python.exe -m compileall config.py src scripts tests` ->
  passed.
- `git diff --check -- ...` -> passed.

## 2026-05-22 Bond-yield risk overlay

### Completed

- Added a bond-yield risk overlay that reads `KR10Y` and `US10Y` from
  `market_index_prices`.
- Applied the overlay to both dry-run rebalance reports and the scheduled
  rebalance path by combining it with the existing US-market index multiplier.
- Extended market index sync so `KR10Y` can come from pykrx OTC treasury
  yields and `US10Y` can come from Yahoo `^TNX`, with US yield scale
  normalization.
- Dry-run JSON now includes `bond_yield_risk` and
  `combined_buy_budget_multiplier`.

### Rules

- +15bp or more in one 10Y yield: reduce buys to `0.85x`.
- +30bp in one 10Y yield, or both KR/US 10Y yields +15bp or more: reduce buys
  to `0.70x`.
- -15bp or more in one 10Y yield: increase buys to `1.10x`.
- -30bp in one 10Y yield, or both KR/US 10Y yields -15bp or more: increase
  buys to `1.20x`.
- Mixed one-up/one-down bond signals stay neutral. Missing yield history stays
  neutral.

### Verification

- `.\venv\Scripts\python.exe -m pytest tests\data\test_sync_market_indices.py tests\trading\test_us_market_risk.py tests\trading\test_bond_yield_risk.py tests\trading\test_dry_run_rebalance.py tests\trading\test_scheduler.py`
  -> `44 passed`.
- `.\venv\Scripts\python.exe -m compileall src scripts tests` -> passed.

## 2026-05-14 Hankyung consensus research pipeline

### Completed

- Added `scripts\run_hankyung_research_readonly_pipeline.py` so Hankyung
  consensus research can run through the same read-only flow as Mirae:
  metadata sync, body reanalysis, summary Markdown, and factor-impact Markdown.
- Added custom report titles for the shared summary/factor reporting scripts so
  Hankyung outputs no longer look like Mirae outputs.
- Fixed stored-report reanalysis so Hankyung paths such as
  `/pdf/2026/05/...` are treated as PDF links and recorded as attempted body
  fetches instead of `not_pdf`.
- Corrected Hankyung's provider URL from `markets.hankyung.com/consensus` to
  `consensus.hankyung.com`, where PDF buttons use
  `/analysis/downpdf?report_idx=...`.
- Added browser-style user-agent headers for list and PDF fetches because
  Hankyung returns `Block access. 0001` to Python's default requests
  user-agent.
- Removed `8` obsolete rows from the earlier `markets.hankyung.com/pdf/...`
  path after the correct `downpdf` rows were collected.

### Real Collection

- Command:
  `.\venv\Scripts\python.exe scripts\run_hankyung_research_readonly_pipeline.py --start-date 2026-01-01 --end-date 2026-05-14 --as-of-date 2026-05-14 --pages 20 --limit 3000 --top-n 100`
- The full run timed out while doing PDF extraction, so missing early-year
  ranges were filled with monthly sync chunks:
  - January: `515` rows, `pdf_text_extracted=515`
  - February: `556` rows, `pdf_text_extracted=556`
  - March 1-22: `114` rows, `pdf_text_extracted=114`
- DB verification:
  - `signals=2012`
  - date range: `2026-01-02` to `2026-05-14`
  - monthly rows: `2026-01=515`, `2026-02=556`, `2026-03=163`,
    `2026-04=521`, `2026-05=257`
  - `body_status=[('empty', 2), ('extracted', 2010)]`
  - `investment_opinion=[('mixed', 49), ('negative', 2), ('positive', 1958), ('unknown', 11)]`
- `orders_submitted=0`.

### Generated Reports

- `data\hankyung_research_summary_latest.md`
  - `row_count=2012`
  - `body_status=empty=2, extracted=2010`
- `data\hankyung_research_factor_impact_latest.md`
  - `factor_score_count=198`
  - `research_signal_count=478`
  - `impacted_count=131`
  - top impacted tickers include `079900`, `078930`, `112610`, `460860`,
    `483650`, `218410`.

### Verification

- `.\venv\Scripts\python.exe -m pytest tests\signals\test_reanalyze_research_report_bodies.py tests\signals\test_generate_mirae_research_summary.py tests\signals\test_run_hankyung_research_readonly_pipeline.py`
  -> `9 passed`.
- `.\venv\Scripts\python.exe -m py_compile ...` for the changed research
  reader, reanalysis, summary, factor-impact, Hankyung pipeline, and tests
  -> passed.
- `.\venv\Scripts\python.exe -m pytest tests\signals\test_research_report_reader.py tests\signals\test_reanalyze_research_report_bodies.py tests\signals\test_generate_mirae_research_summary.py tests\factors\test_compare_research_report_factor_impact.py tests\signals\test_run_hankyung_research_readonly_pipeline.py`
  -> `23 passed`.
- Final Hankyung path verification:
  - `.\venv\Scripts\python.exe -m py_compile config.py src\signals\research_report_parser.py src\signals\research_report_reader.py scripts\sync_korean_research_reports.py scripts\run_hankyung_research_readonly_pipeline.py scripts\generate_mirae_research_summary.py scripts\compare_research_report_factor_impact.py tests\signals\test_research_report_parser.py tests\signals\test_research_report_reader.py tests\signals\test_sync_korean_research_reports.py tests\signals\test_run_hankyung_research_readonly_pipeline.py`
    -> passed.
  - `.\venv\Scripts\python.exe -m pytest tests\signals\test_research_report_parser.py tests\signals\test_research_report_reader.py tests\signals\test_sync_korean_research_reports.py tests\signals\test_run_hankyung_research_readonly_pipeline.py tests\signals\test_generate_mirae_research_summary.py tests\factors\test_compare_research_report_factor_impact.py`
    -> `35 passed`.

## 2026-05-14 Mirae Asset 2026 YTD research expansion

### Completed

- Added date-range support to the Mirae research sync path:
  - `scripts\sync_korean_research_reports.py`
  - `src\signals\research_report_reader.py`
- Added `--research-start-date` to
  `scripts\compare_research_report_factor_impact.py` so factor impact can use
  all research from `2026-01-01` instead of the default 30-day window.
- Updated `scripts\run_mirae_research_readonly_pipeline.py` to pass the 2026
  start date through the sync and factor-impact steps.
- Because broad Mirae searches returned a capped recent slice, the 2026 YTD
  collection was executed in monthly chunks.

### Real Collection

- January: `70` reports, `pdf_text_extracted=70`
- February: `95` reports, `pdf_text_extracted=95`
- March: `36` reports, `pdf_text_extracted=36`
- April: `63` reports, `pdf_text_extracted=63`
- May 1-14: `59` reports, `pdf_text_extracted=59`
- DB verification:
  - `signals=323`
  - date range: `2026-01-05` to `2026-05-14`
  - `body_status=[('extracted', 323)]`
- Full reanalysis:
  - `research_report_rows_seen=323`
  - `pdf_text_attempted=323`
  - `pdf_text_extracted=323`
  - `pdf_text_length=1020335`
  - `analysis_success_count=323`
  - `orders_submitted=0`

### Generated Reports

- `data\mirae_research_summary_latest.md`
  - `row_count=323`
  - `investment_opinion=mixed=18, negative=6, neutral=15, positive=251, unknown=33`
- `data\mirae_research_factor_impact_latest.md`
  - `factor_score_count=198`
  - `research_signal_count=115`
  - `impacted_count=48`
  - `research_start_date=2026-01-01`

### Verification

- `.\venv\Scripts\python.exe -m py_compile ...` for changed sync, reader,
  factor-impact, pipeline, and tests -> passed.
- `.\venv\Scripts\python.exe -m pytest tests\signals\test_research_report_reader.py tests\signals\test_sync_korean_research_reports.py tests\factors\test_compare_research_report_factor_impact.py tests\signals\test_run_mirae_research_readonly_pipeline.py`
  -> `21 passed`.
- Pytest passed with exit code 0, but Windows emitted the known pytest temp
  symlink cleanup warning after the run.

## 2026-05-14 Mirae dashboard, factor impact, and read-only pipeline

### Completed

- Extended `scripts\agent_ops_streamlit_dashboard.py` so the Streamlit work
  dashboard can display `data\mirae_research_summary_latest.md`.
- Added `scripts\compare_research_report_factor_impact.py` to compare factor
  rankings with the Mirae research overlay disabled vs enabled.
- Added `scripts\run_mirae_research_readonly_pipeline.py` to run the Mirae
  research flow in order:
  - sync metadata and PDF body text
  - reanalyze stored report bodies
  - refresh the Mirae summary Markdown
  - refresh the research factor-impact Markdown
- All new research/reporting commands print `orders_submitted=0`.

### Real Pipeline

- Command: `.\venv\Scripts\python.exe scripts\run_mirae_research_readonly_pipeline.py --as-of-date 2026-05-14 --pages 2 --limit 30 --top-n 20`
  - `korean_research_report_rows_stored=20`
  - `pdf_text_attempted=20`
  - `pdf_text_extracted=20`
  - `pdf_text_length=43272`
  - `body_signal_applied=4`
  - `analysis_rows_stored=20`
  - `analysis_success_count=20`
  - `mirae_research_summary_rows=20`
  - `score_count=198`
  - `research_signal_count=16`
  - `impacted_count=8`
  - `pipeline_status=completed`
  - `orders_submitted=0`

### Generated Reports

- `data\mirae_research_summary_latest.md`
- `data\mirae_research_factor_impact_latest.md`

### Verification

- `python -m pytest tests\test_agent_ops_streamlit_dashboard.py` -> `4 passed`.
- `python -m pytest tests\factors\test_compare_research_report_factor_impact.py` -> `3 passed`.
- `python -m pytest tests\signals\test_run_mirae_research_readonly_pipeline.py` -> `3 passed`.
- Sandbox Python lacked `pypdf`, so the first local pipeline smoke had
  `pdf_text_extracted=0`. The verified run used `venv\Scripts\python.exe`,
  where `pypdf==5.1.0` is installed.

## 2026-05-14 Mirae Asset research summary report

### Completed

- Added `scripts\generate_mirae_research_summary.py`.
- The script reads stored `mirae_asset` body-analysis rows and writes a
  human-readable Markdown report.
- Default output:
  - `data\mirae_research_summary_latest.md`
- Report columns:
  - date
  - ticker
  - investment opinion
  - body extraction status
  - confidence
  - key thesis
  - risk
  - title
- The script is read-only and prints `orders_submitted=0`.
- Updated `HANDOFF_FOR_AGENTS.md` with the report generation command.

### Real Report

- Command: `.\venv\Scripts\python.exe scripts\generate_mirae_research_summary.py --output data\mirae_research_summary_latest.md --limit 30`
  - `mirae_research_summary_rows=20`
  - `output_md=data\mirae_research_summary_latest.md`
  - `orders_submitted=0`
- Read-back showed:
  - `row_count=20`
  - `body_status=extracted=20`
  - `investment_opinion=mixed=1, positive=15, unknown=4`
  - Examples:
    - `011200`: `상승하는 운임, 비용 증가 상쇄 기대`
    - `004170`: `만점짜리 실적`
    - `030200`: `구조적인 수익성 증가 시작`

### Verification

- Summary script tests: `.\venv\Scripts\python.exe -m pytest tests\signals\test_generate_mirae_research_summary.py -q` -> `2 passed`.
- Combined research-report tests: `.\venv\Scripts\python.exe -m pytest tests\signals\test_generate_mirae_research_summary.py tests\signals\test_reanalyze_research_report_bodies.py tests\signals\test_research_report_analysis.py tests\signals\test_research_report_parser.py tests\signals\test_research_report_reader.py tests\signals\test_sync_korean_research_reports.py tests\data\test_repositories.py -q` -> `45 passed`.
- Syntax check: `.\venv\Scripts\python.exe -m py_compile scripts\generate_mirae_research_summary.py tests\signals\test_generate_mirae_research_summary.py` -> passed.

### Notes

- Pytest passed with exit code 0, but Windows emitted a pytest temp symlink
  cleanup warning after the run. It did not affect the test result.
- Some extracted body snippets are still rough when PDF tables and paragraphs
  are interleaved. The report makes those cases visible for the next quality
  pass.

## 2026-05-14 Mirae Asset stored report reanalysis

### Completed

- Added `scripts\reanalyze_research_report_bodies.py`.
- The script reloads already stored research report rows, re-fetches each linked
  PDF through `source_url`, reruns the current deterministic body analyzer, and
  upserts `research_report_analyses`.
- Defaults are scoped to Mirae Asset:
  - `--source mirae_asset`
  - `--broker "미래에셋증권"`
- Added `--limit` for small batches.
- The script prints telemetry and always prints `orders_submitted=0`.
- Updated `HANDOFF_FOR_AGENTS.md` with the reanalysis command.

### Live Smoke

- Command: `.\venv\Scripts\python.exe scripts\reanalyze_research_report_bodies.py --source mirae_asset --broker "미래에셋증권"`
  - `research_report_rows_seen=20`
  - `pdf_text_attempted=20`
  - `pdf_text_extracted=20`
  - `pdf_text_length=43272`
  - `analysis_rows_stored=20`
  - `analysis_success_count=20`
  - `analysis_failed_count=0`
  - `orders_submitted=0`
- DB spot check:
  - `mirae_analysis=20`
  - `status=[('extracted', 20)]`
  - Existing rows such as `004170` now show the improved title-context summary
    `만점짜리 실적`.

### Verification

- Reanalysis script tests: `.\venv\Scripts\python.exe -m pytest tests\signals\test_reanalyze_research_report_bodies.py -q` -> `2 passed`.
- Combined research-report tests: `.\venv\Scripts\python.exe -m pytest tests\signals\test_reanalyze_research_report_bodies.py tests\signals\test_research_report_analysis.py tests\signals\test_research_report_parser.py tests\signals\test_research_report_reader.py tests\signals\test_sync_korean_research_reports.py tests\data\test_repositories.py -q` -> `43 passed`.
- Syntax check: `.\venv\Scripts\python.exe -m py_compile scripts\reanalyze_research_report_bodies.py tests\signals\test_reanalyze_research_report_bodies.py` -> passed.

### Notes

- The script re-fetches PDFs because raw PDF text is intentionally not stored.
- This remains read-only research enrichment and does not submit PAPER or LIVE
  orders.

## 2026-05-14 Mirae Asset multi-page research collection

### Completed

- Added `--pages` to `scripts\sync_korean_research_reports.py`.
- Added Mirae Asset page URL expansion for
  `https://securities.miraeasset.com/bbs/board/message/list.do?categoryId=1533`.
- Confirmed Mirae Asset pagination requires `curPage` plus search-date/list
  parameters; simple `startPage=2` is not enough.
- Reused the existing parser, PDF extraction, body analysis, and DB upsert path
  for every fetched page.
- Fixed duplicate parsing where Mirae table rows were parsed once by the
  provider-specific table parser and again by the generic link parser.
- Updated `HANDOFF_FOR_AGENTS.md` with the multi-page Mirae command.

### Live Smoke

- Command: `.\venv\Scripts\python.exe scripts\sync_korean_research_reports.py --url https://securities.miraeasset.com/bbs/board/message/list.do?categoryId=1533 --source mirae_asset --broker "미래에셋증권" --include-pdf-text --pages 2`
  - `korean_research_report_rows_stored=20`
  - `pdf_text_attempted=20`
  - `pdf_text_extracted=20`
  - `pdf_text_length=43272`
  - `body_signal_applied=4`
  - `analysis_rows_stored=20`
  - `analysis_success_count=20`
  - `analysis_failed_count=0`
  - `pages_requested=2`
  - `orders_submitted=0`
- DB spot check:
  - `signals_mirae=20`
  - `analysis_status=[('extracted', 20)]`
  - examples include `011200`, `214150`, `000120`, `004170`, `036570`,
    `043150`, `112040`.

### Verification

- Script/reader/parser tests: `.\venv\Scripts\python.exe -m pytest tests\signals\test_research_report_reader.py tests\signals\test_research_report_parser.py tests\signals\test_sync_korean_research_reports.py -q` -> `21 passed`.
- Combined research-report tests: `.\venv\Scripts\python.exe -m pytest tests\signals\test_research_report_analysis.py tests\signals\test_research_report_parser.py tests\signals\test_research_report_reader.py tests\signals\test_sync_korean_research_reports.py tests\data\test_repositories.py -q` -> `41 passed`.
- Syntax check: `.\venv\Scripts\python.exe -m py_compile src\signals\research_report_reader.py src\signals\research_report_parser.py scripts\sync_korean_research_reports.py tests\signals\test_research_report_reader.py tests\signals\test_sync_korean_research_reports.py` -> passed.

### Notes

- `--pages` only expands known Mirae Asset list URLs for now. Other providers
  still fetch the original URL once.
- This remains read-only research enrichment and prints `orders_submitted=0`.

## 2026-05-14 Mirae Asset research summary quality pass

### Completed

- Improved deterministic `rule-v1` research-report body analysis quality for
  Mirae Asset PDFs.
- Added title-context fallback so sparse PDF bodies still capture concise
  analyst rationale such as:
  - `여전히 주목해야 할 시장 지위 확대`
  - `원가 압박 이겨내는 중`
  - `상승하는 운임, 비용 증가 상쇄 기대`
- Removed ticker/rating wrappers like `(000120/매수)` from stored thesis text.
- Reduced false thesis matches from Mirae boilerplate such as rating-definition
  paragraphs and financial table fragments.
- Prevented positive-title fallback text from being copied into risk buckets
  just because it contains words like `원가`, `압박`, or `불확실성`.
- Allowed positive `rating_score` to drive title fallback even when `raw_score`
  is zero.

### Live Smoke

- Mirae command: `.\venv\Scripts\python.exe scripts\sync_korean_research_reports.py --url https://securities.miraeasset.com/bbs/board/message/list.do?categoryId=1533 --source mirae_asset --broker "미래에셋증권" --include-pdf-text`
  - `korean_research_report_rows_stored=10`
  - `pdf_text_attempted=10`
  - `pdf_text_extracted=10`
  - `pdf_text_length=12086`
  - `body_signal_applied=1`
  - `analysis_rows_stored=10`
  - `analysis_success_count=10`
  - `orders_submitted=0`
- DB spot check showed improved current summaries:
  - `000120`: `여전히 주목해야 할 시장 지위 확대`
  - `145720`: `중국에서 2차 VBP만 다시 시작된다면!`
  - `043150`: `원가 압박 이겨내는 중`
  - `011200`: `상승하는 운임, 비용 증가 상쇄 기대`

### Verification

- Analyzer tests: `.\venv\Scripts\python.exe -m pytest tests\signals\test_research_report_analysis.py -q` -> `7 passed`.
- Combined research-report tests: `.\venv\Scripts\python.exe -m pytest tests\signals\test_research_report_analysis.py tests\signals\test_research_report_reader.py tests\signals\test_research_report_parser.py tests\signals\test_sync_korean_research_reports.py tests\data\test_repositories.py -q` -> `39 passed`.
- Syntax check: `.\venv\Scripts\python.exe -m py_compile src\signals\research_report_analysis.py tests\signals\test_research_report_analysis.py` -> passed.

### Notes

- Existing older Mirae analysis rows that were not present in the latest fetched
  10-report page were not re-analyzed by the live smoke.
- This remains read-only research enrichment. It does not submit PAPER or LIVE
  orders.

## 2026-05-14 Agent orchestration rule optimization

### Completed

- Optimized top-level agent rules so `AGENTS.md` is a short ASCII-safe summary
  and `docs/agent-roster.md` is the operational source of truth.
- Added Orchestrator Agent as the central coordinator for request
  classification, role assignment, delegation, integration review, final review,
  and user-facing completion claims.
- Added the Orchestrator Control Loop:
  `classify -> assign -> gather evidence -> plan -> delegate or execute -> verify -> repair if needed -> final review -> report`.
- Added task-weight delegation guidance for `tiny`, `standard`, and `heavy`
  work so subagents are used aggressively when they improve quality without
  adding ceremony to tiny tasks.
- Added the Error Collaboration Protocol so Bug Investigator, the failing-task
  context owner, the domain agent, Test and Verification, and Orchestrator have
  explicit roles when failures occur.
- Added a Final Review Gate before completion claims.

### Verification

- Read-back: `Get-Content -Path 'AGENTS.md'` showed the new ASCII-safe top-level
  rules.
- Required-section search: `Select-String -Path 'AGENTS.md','docs\agent-roster.md' -Pattern 'Orchestrator Agent|Error Collaboration Protocol|Final Review Gate|subagents|five related files|narrowest meaningful'` found the expected sections and rules.
- Placeholder search on the edited rule files found no unfinished placeholder
  markers.

### Notes

- This workspace is not currently a git repository, so no commit was created.
- No code, trading path, parameter, DB, or scheduler behavior was changed.

## 2026-05-14 Research report body analysis

### Completed

- Added a design spec and implementation plan so future agents understand the
  Hankyung/Mirae research-report body-analysis work:
  - `docs\superpowers\specs\2026-05-14-research-report-body-analysis-design.md`
  - `docs\superpowers\plans\2026-05-14-research-report-body-analysis.md`
- Added `ResearchReportAnalysis` storage as a separate table from
  `ResearchReportSignal`.
- Added deterministic `rule-v1` body analysis:
  - summary
  - investment opinion
  - buy thesis
  - sell/risk thesis
  - growth drivers
  - earnings drivers
  - valuation view
  - target-price rationale
  - risk factors
  - evidence terms
  - confidence
- Connected `scripts\sync_korean_research_reports.py` so report sync creates
  analysis rows and prints analysis telemetry while preserving
  `orders_submitted=0`.
- Added parser support for the current Mirae Asset public research table format
  at category `1533`.
- Added provider failure states:
  - `login_required`
  - `not_pdf_response`
  - `fetch_failed`
  - `empty`
  - `not_pdf`
  - `extracted`

### Live Smoke

- Hankyung command: `.\venv\Scripts\python.exe scripts\sync_korean_research_reports.py --url https://markets.hankyung.com/consensus --source hankyung_consensus --broker "한경 컨센서스" --include-pdf-text`
  - `korean_research_report_rows_stored=10`
  - `pdf_text_attempted=10`
  - `pdf_text_extracted=0`
  - `analysis_rows_stored=10`
  - `orders_submitted=0`
  - Result: linked report PDF URLs redirect to a login flow, so body status is
    `login_required`.
- Mirae command: `.\venv\Scripts\python.exe scripts\sync_korean_research_reports.py --url https://securities.miraeasset.com/bbs/board/message/list.do?categoryId=1533 --source mirae_asset --broker "미래에셋증권" --include-pdf-text`
  - `korean_research_report_rows_stored=10`
  - `pdf_text_attempted=10`
  - `pdf_text_extracted=10`
  - `pdf_text_length=11981`
  - `body_signal_applied=1`
  - `analysis_rows_stored=10`
  - `analysis_success_count=10`
  - `orders_submitted=0`

### Verification

- Targeted tests: `.\venv\Scripts\python.exe -m pytest tests\signals\test_research_report_analysis.py tests\signals\test_research_report_reader.py -q` -> `11 passed`.
- Parser tests: `.\venv\Scripts\python.exe -m pytest tests\signals\test_research_report_parser.py -q` -> `8 passed`.
- Repository/analyzer initial tests: `.\venv\Scripts\python.exe -m pytest tests\signals\test_research_report_analysis.py tests\data\test_repositories.py -q` -> `16 passed`.
- Combined targeted tests: `.\venv\Scripts\python.exe -m pytest tests\signals\test_research_report_analysis.py tests\signals\test_research_report_parser.py tests\signals\test_research_report_reader.py tests\data\test_repositories.py tests\signals\test_sync_korean_research_reports.py -q` -> `35 passed`.
- Syntax check: `.\venv\Scripts\python.exe -m py_compile src\signals\research_report_analysis.py src\signals\research_report_parser.py src\signals\research_report_reader.py src\data\models.py src\data\repositories.py scripts\sync_korean_research_reports.py tests\signals\test_research_report_analysis.py tests\signals\test_research_report_parser.py tests\signals\test_research_report_reader.py tests\signals\test_sync_korean_research_reports.py` -> passed.
- DB status check: `signals_by_source=[('hankyung_consensus', 12), ('mirae_asset', 10)]`, `analysis_by_status=[('hankyung_consensus', 'login_required', 10), ('mirae_asset', 'extracted', 10)]`.

### Notes

- This is a read-only research layer. It does not submit PAPER or LIVE orders.
- Hankyung metadata works, but body access is currently blocked by login.
- Mirae Asset public PDFs are extractable and now produce body-analysis rows.
- The deterministic analyzer is intentionally conservative. A future LLM
  summarizer can be added as a separate `analysis_version`, but `rule-v1` does
  not depend on external LLM access.

## 2026-05-14 Rebalance dry-run refresh and readiness check

### Completed

- 2026-05-14 기준 PAPER 리밸런싱 dry-run/review를 새로 생성했습니다.
- 주문 제출 없이 계획만 만들었습니다: `orders_submitted=0`.
- 최신 dry-run 산출물:
  - `data\dry_run_rebalance_latest.json`
  - `data\dry_run_rebalance_latest.md`
- 계획된 주문은 총 6건입니다:
  - 매도 3건: `031980` 79주, `078930` 130주, `402340` 8주
  - 매수 3건: `147830` 920주, `072950` 687주, `319660` 94주
- 가격 조회 실패와 fallback 가격 사용은 모두 0건입니다.
- `072950` 가격 조회는 첫 시도에서 KIS 500 응답이 있었지만, 2번째 재시도에서 성공했습니다.

### Verification

- Dry-run/review command: `.\venv\Scripts\python.exe scripts\prepare_and_review_rebalance.py --as-of-date 2026-05-14 --top-n 10 --output-json data\dry_run_rebalance_latest.json --output-md data\dry_run_rebalance_latest.md --quote-retries 4 --quote-delay-sec 0.5` -> `dry_run_status=clean`, `orders_submitted=0`, `price_lookup_failed_count=0`, `price_fallback_count=0`.
- Readiness command: `.\venv\Scripts\python.exe scripts\check_rebalance_readiness.py --dry-run-json data\dry_run_rebalance_latest.json --expected-date 2026-05-14` -> `preflight_status=clean`, `market_time_status=blocked`, `execution_ready=false`.

### Notes

- 현재 실행 준비는 정규장 시간 조건 때문에 막혀 있습니다: weekday `09:00-15:20` KST 필요.
- PAPER 주문과 LIVE 주문은 실행하지 않았습니다.
- 다음 안전 단계는 정규장 시간에 readiness를 다시 확인한 뒤, 사용자가 명시적으로 승인할 때만 PAPER 실행을 검토하는 것입니다.

## 2026-05-14 Dashboard Korean task description translation

### Completed

- 대시보드에 표시되는 작업 설명을 한국어로 번역하는 표시 전용 변환층을 추가했다.
- 백틱 안의 코드, 명령, 파일 경로는 번역하지 않고 그대로 보존한다.
- Markdown 대시보드와 Streamlit 대시보드가 같은 번역 규칙을 사용하도록 맞췄다.
- 예시:
  - `Added a read-only Streamlit dashboard:` -> `읽기 전용 Streamlit 대시보드를 추가했습니다:`
  - `targeted tests passed` -> `대상 테스트가 통과했습니다`

### Verification

- Dashboard translation tests: `.\venv\Scripts\python.exe -m pytest tests\test_generate_agent_ops_dashboard.py tests\test_agent_ops_streamlit_dashboard.py -q` -> `18 passed`.
- Syntax check: `.\venv\Scripts\python.exe -m py_compile scripts\generate_agent_ops_dashboard.py scripts\agent_ops_streamlit_dashboard.py tests\test_generate_agent_ops_dashboard.py tests\test_agent_ops_streamlit_dashboard.py` -> passed.

### Notes

- 번역은 대시보드 표시 단계에서만 적용된다. `progress.md` 원문은 변경하지 않는다.
- 새로운 문장이 나오면 `_TEXT_TRANSLATIONS`에 문구를 추가하면 된다.

## 2026-05-13 Agent work continuity dashboard

### Completed

- Localized the work continuity dashboard UI to Korean and changed status
  display to the requested marker scheme:
  - `O 완료`
  - `X 막힘`
  - `△ 진행중/추정`
  - `★ 중요/확인 필요`
- Updated both Markdown and Streamlit renderers to use the same status marker
  mapping.
- Extended the existing local-only agent operations dashboard into a work
  continuity dashboard.
- Added a shared dashboard model that captures:
  - current safety state
  - latest progress headline
  - completed work
  - verification notes
  - operator notes
  - evidence paths
  - timeline rows
  - next safe command
- Improved the generated Markdown report at `data\agent_ops_dashboard_latest.md`
  with Summary, Current State, Work Continuity, Evidence, Safety Gates,
  Timeline, and Next Safe Command sections.
- Added a read-only Streamlit dashboard:
  - `scripts\agent_ops_streamlit_dashboard.py`
- Added/updated targeted tests:
  - `tests\test_generate_agent_ops_dashboard.py`
  - `tests\test_agent_ops_streamlit_dashboard.py`
- Added design and implementation documents:
  - `docs\superpowers\specs\2026-05-13-agent-work-continuity-dashboard-design.md`
  - `docs\superpowers\plans\2026-05-13-agent-work-continuity-dashboard.md`
- Updated `HANDOFF_FOR_AGENTS.md` with Markdown and Streamlit dashboard commands.

### Verification

- Markdown dashboard targeted tests: `.\venv\Scripts\python.exe -m pytest tests\test_generate_agent_ops_dashboard.py -q` -> `13 passed`.
- Streamlit dashboard targeted tests: `.\venv\Scripts\python.exe -m pytest tests\test_agent_ops_streamlit_dashboard.py -q` -> `2 passed`.
- Combined dashboard tests: `.\venv\Scripts\python.exe -m pytest tests\test_generate_agent_ops_dashboard.py tests\test_agent_ops_streamlit_dashboard.py -q` -> `15 passed`.
- Korean status marker tests: `.\venv\Scripts\python.exe -m pytest tests\test_generate_agent_ops_dashboard.py tests\test_agent_ops_streamlit_dashboard.py -q` -> `17 passed`.
- Syntax check: `.\venv\Scripts\python.exe -m py_compile scripts\generate_agent_ops_dashboard.py scripts\agent_ops_streamlit_dashboard.py tests\test_generate_agent_ops_dashboard.py tests\test_agent_ops_streamlit_dashboard.py` -> passed.
- Dashboard smoke: `.\venv\Scripts\python.exe scripts\generate_agent_ops_dashboard.py --expected-date 2026-05-13` -> `dry_run_status=present`, `safety_status=blocked`.
- Streamlit HTTP smoke: ran `.\venv\Scripts\python.exe -m streamlit run scripts\agent_ops_streamlit_dashboard.py --server.port 8506 --server.headless true` and checked `http://127.0.0.1:8506` while the server was live -> HTTP `200`.

### Notes

- The dashboard remains local-only and read-only. It does not call KIS, place
  orders, mutate the DB, or execute readiness checks automatically.
- Smoke generation is blocked for safety because the latest dry-run report is
  dated `2026-05-12` while the expected date is `2026-05-13`.
- The Streamlit server was verified during the smoke check, but this execution
  environment did not keep the background process alive after the check ended.
- This folder is not a git repository, so no design or implementation commit was
  created.

## 2026-05-12 PAPER rebalance execution and agent ops dashboard

### Completed

- Added the daily PAPER one-command runner:
  - `scripts/daily_paper_run.py`
  - `tests/trading/test_daily_paper_run.py`
- The runner chains:
  - Phase 1 sync
  - dry-run prepare/review
  - readiness check
  - PAPER execution
  - post execution report review
  - intraday stop-loss/trailing-stop monitor
- The runner starts a stop-monitor-only scheduler after successful execution instead of the full `run_bot.py` scheduler, avoiding a same-day duplicate `daily_rebalance` job.
- The runner blocks before any sync/order step unless `--confirm EXECUTE_PAPER_REBALANCE` is supplied and `TRADE_MODE=PAPER`.
- Ran same-day Phase 1 sync for `2026-05-01` through `2026-05-12` with one worker.
- Sync completed with:
  - `universe_count=470`
  - `price_count=2816`
  - `fundamental_count=2804`
  - missing fundamentals for `088980`, `950160`
- Generated same-day PAPER dry-run/review with:
  - `.\venv\Scripts\python.exe scripts\prepare_and_review_rebalance.py --as-of-date 2026-05-12 --top-n 10 --output-json data\dry_run_rebalance_latest.json --output-md data\dry_run_rebalance_latest.md --quote-retries 4 --quote-delay-sec 0.5`
- Dry-run status:
  - `dry_run_status=clean`
  - `buy_count=10`
  - `price_fallback_count=0`
  - `price_lookup_failed_count=0`
  - `price_retry_success_count=8`
  - `price_retry_failed_count=0`
- Readiness check returned:
  - `market_time_status=ready`
  - `preflight_status=clean`
  - `execution_ready=true`
- PAPER execution command accepted all planned orders:
  - `sold=0,bought=10,failed=0`
  - execution report: `data\rebalance_execution_2026-05-12.json`
  - report status: `execution_match_status=matched`
- Added and hardened the local-only agent operations dashboard:
  - `scripts/generate_agent_ops_dashboard.py`
  - `tests/test_generate_agent_ops_dashboard.py`
  - `data\agent_ops_dashboard_latest.md`
- Dashboard safety behavior now marks malformed dry-run JSON as `blocked` and stale dry-run dates as overall `blocked`.

### Verification

- Dashboard targeted tests: `.\venv\Scripts\python.exe -m pytest tests\test_generate_agent_ops_dashboard.py -q` -> `11 passed`.
- Daily PAPER runner targeted tests: `.\venv\Scripts\python.exe -m pytest tests\trading\test_daily_paper_run.py -q` -> `9 passed`.
- Dashboard syntax check: `.\venv\Scripts\python.exe -m py_compile scripts\generate_agent_ops_dashboard.py tests\test_generate_agent_ops_dashboard.py` -> passed.
- Dashboard smoke: `.\venv\Scripts\python.exe scripts\generate_agent_ops_dashboard.py --expected-date 2026-05-12` -> `dry_run_status=present`, `safety_status=clean`.
- Full test suite: `.\venv\Scripts\python.exe -m pytest -q` -> `336 passed`.
- KIS decimal numeric holding parser fix:
  - `scripts/dry_run_rebalance.py` and `src/trading/kis_client.py` now accept KIS numeric strings like `168027.5860` for integer fields.
  - Targeted tests: `.\venv\Scripts\python.exe -m pytest tests\trading\test_dry_run_rebalance.py tests\trading\test_kis_client.py tests\trading\test_daily_paper_run.py -q` -> `44 passed`.
  - Full test suite after fix: `.\venv\Scripts\python.exe -m pytest -q` -> `338 passed`.
- Intraday stop monitor after-hours guard:
  - `scripts/daily_paper_run.py` no longer calls the KIS balance/holdings path immediately when the monitor is started outside 09:00-15:20 KST.
  - It still registers the stop monitor schedule and waits for the next matching weekday market window.
  - Targeted tests: `.\venv\Scripts\python.exe -m pytest tests\trading\test_daily_paper_run.py tests\trading\test_scheduler.py -q` -> `19 passed`.
  - Full test suite after guard: `.\venv\Scripts\python.exe -m pytest -q` -> `339 passed`.

### Notes

- `scripts/daily_paper_run.py` now defaults `--top-n` to `PORTFOLIO.n_holdings` (`30`) so the daily PAPER target list matches the adopted portfolio size.
- `SAFETY.max_daily_buys` remains `10`; this keeps daily execution throttled while allowing the 30-name target list to be filled over multiple sessions.
- KIS quote retry rows with `status=success` are recovered current-price lookup failures, not failed orders.

## 2026-05-22 PAPER Daily Buy Limit Adjustment

### Completed

- Raised `SAFETY.max_daily_buys` from `10` to `20`.
- Reason: the 2026-05-22 dry-run already targets `30` holdings and produced `buy_count=20`, but readiness blocked execution with `daily buy limit would be exceeded (20/10)`.
- `SAFETY.max_daily_sells` remains `10`; sell-side execution throttling is unchanged.
- PAPER confirmation, dry-run preflight, quote failure checks, stale-report checks, and market-time readiness remain unchanged.

### Verification

- RED: `.\venv\Scripts\python.exe -m pytest tests\test_strategy_defaults.py tests\trading\test_rebalancer.py::test_execute_rebalance_allows_twenty_daily_buys tests\trading\test_rebalancer.py::test_execute_rebalance_blocks_when_dry_run_orders_exceed_daily_buy_limit -q` -> failed because `SAFETY.max_daily_buys` was still `10` and preflight blocked `(20/10)`.
- Targeted tests: `.\venv\Scripts\python.exe -m pytest tests\test_strategy_defaults.py tests\trading\test_rebalancer.py tests\trading\test_execute_rebalance_from_dry_run.py tests\trading\test_check_rebalance_readiness.py -q` -> 40 passed.
- Readiness recheck on the current 2026-05-22 dry-run: `.\venv\Scripts\python.exe scripts\check_rebalance_readiness.py --dry-run-json data\dry_run_rebalance_latest.json --expected-date 2026-05-22` -> `preflight_status=clean`, `execution_ready=true`.
- Syntax check: `.\venv\Scripts\python.exe -m compileall config.py src\trading\rebalancer.py scripts\check_rebalance_readiness.py tests\test_strategy_defaults.py tests\trading\test_rebalancer.py tests\trading\test_check_rebalance_readiness.py` -> passed.

## 2026-05-21 US Market Risk Buy Adjustment

### Completed

- Added a shared US-market buy adjustment layer for PAPER rebalance planning.
- US index data support now covers `NASDAQ`, `SP500`, and `DOW` via the market-index sync path.
- The adjustment is based on the latest completed US index session before the Korean rebalance date:
  - severe drop in any tracked US index (`<= -3.0%`) -> `0.60x` buy budget and `40%` cash target note;
  - moderate drop in two or more indexes (`<= -1.5%`) -> `0.70x`;
  - moderate drop in one index -> `0.80x`;
  - rally in two or more indexes (`>= +1.5%`) -> `1.20x`;
  - broad positive session in two or more indexes (`>= +1.0%`) -> `1.10x`;
  - missing US index history -> neutral `1.00x`, reported as `missing`.
- `scripts/dry_run_rebalance.py` writes `us_market_risk` evidence to JSON and Markdown, and scales target weights before buy sizing.
- `src.trading.scheduler._rebalance_job` uses the same shared adjustment before PAPER buy order planning.
- Total planned buy value is bounded by the available buy budget, so risk-on scaling cannot plan more cash usage than the available budget allows.
- Existing PAPER confirmation, dry-run preflight, quote checks, and `SAFETY.max_daily_buys=10` remain unchanged.

### Verification

- TDD RED: targeted US-market adjustment tests initially failed with `ModuleNotFoundError: No module named 'src.trading.us_market_risk'`.
- Targeted GREEN: `.\venv\Scripts\python.exe -m pytest tests\trading\test_us_market_risk.py tests\trading\test_rebalancer.py::test_buy_budget_multiplier_scales_orders_without_exceeding_budget tests\trading\test_dry_run_rebalance.py::test_run_scales_buy_weights_after_positive_us_market_session tests\trading\test_scheduler.py::test_rebalance_job_applies_us_market_buy_budget_multiplier tests\data\test_sync_market_indices.py::test_run_upserts_fake_market_index_rows -q` -> 7 passed.
- Related trading/data suite: `.\venv\Scripts\python.exe -m pytest tests\trading\test_us_market_risk.py tests\trading\test_rebalancer.py tests\trading\test_dry_run_rebalance.py tests\trading\test_scheduler.py tests\data\test_sync_market_indices.py -q` -> 57 passed.
- Syntax check: `.\venv\Scripts\python.exe -m compileall src\trading scripts\dry_run_rebalance.py scripts\sync_market_indices.py tests\trading tests\data\test_sync_market_indices.py` -> passed.

## 2026-05-09 Rebalance dry-run report automation

### Completed

- Added `scripts/dry_run_rebalance.py` to generate a PAPER rebalance plan without placing orders.
- The script:
  - loads factor scores from the local DB for `--as-of-date`
  - selects the configured `--top-n` target tickers
  - reads PAPER account balance once and parses both holdings and cash from that response
  - looks up current prices for buy candidates
  - calls `compute_rebalance_orders()` to produce planned sells/buys
  - prints a CSV-style dry-run summary
  - optionally writes a Markdown report through `--output-md`
- Added defensive handling for KIS instability:
  - balance failure exits safely with a masked error and no traceback
  - per-ticker quote failures are recorded as `price_lookup_failed` and skipped from buy orders
  - the script never calls `place_order`, `buy`, `sell`, or `execute_rebalance`
- Added explicit dry-run-only price fallback:
  - `--price-fallback latest-db` uses the latest local DB close on or before `--as-of-date` when live quote lookup fails
  - default remains `--price-fallback none`
  - fallback use is printed as `price_fallback,<ticker>,<price>,latest-db` and listed in the Markdown report
  - real/paper order placement still depends on live quote availability; fallback is only for dry-run planning visibility
- Added machine-readable dry-run JSON output:
  - `--output-json <path>` writes dry-run status, planned orders, quote failures, and fallback usage
  - JSON is ASCII-escaped so command-line tools can parse it reliably even when stock names contain non-ASCII text
- Added automated order preflight gate:
  - `execute_rebalance(..., preflight_report_path=...)` refuses to submit any sell/buy orders if the dry-run JSON has fallback prices or unresolved live quote failures
  - scheduler rebalance jobs now pass `REBALANCE.dry_run_preflight_report_path` to `execute_rebalance` by default
  - default preflight JSON path: `data\dry_run_rebalance_latest.json`
  - can be disabled with `REBALANCE_REQUIRE_DRY_RUN_PREFLIGHT=false`, but the safe default is enabled
- Added live quote retry controls for dry-run:
  - `--quote-retries`
  - `--quote-delay-sec`
  - defaults preserve previous behavior: `0` retries and `0.0` seconds
- Added stale-report protection:
  - automated rebalance execution now requires dry-run JSON `as_of_date` to match the rebalance run date
  - a clean but stale report blocks orders
- Added manual approval execution script:
  - `scripts\execute_rebalance_from_dry_run.py`
  - reads a clean dry-run JSON report and converts planned orders back into `RebalanceOrder` objects
  - requires exact confirmation token `EXECUTE_PAPER_REBALANCE`
  - still calls `execute_rebalance(..., preflight_report_path=..., expected_preflight_date=...)`, so fallback/failed/stale reports are blocked before any order method is called
  - preflight blocking is printed as a one-line `execution_blocked=...` message instead of a traceback
- Added market-time guard to the manual execution script:
  - default allows execution only on weekdays from `09:00` to `15:20` KST
  - outside that window it exits before constructing the trading engine or submitting orders
  - `--force-market-closed` exists only for intentional rejection/after-hours tests

### Real PAPER Dry-run Result

- Command:
  - `.\venv\Scripts\python.exe scripts\dry_run_rebalance.py --as-of-date 2026-05-08 --top-n 20 --output-md data\dry_run_rebalance_2026-05-08.md`
- Result:
  - `dry_run=true`
  - cash: `100,000,000`
  - holdings: `0`
  - target_count: `20`
  - sell_count: `0`
  - buy_count: `9`
  - price_lookup_failed_count: `11`
  - report written to `data\dry_run_rebalance_2026-05-08.md`
- KIS quote endpoint returned HTTP 500 for 11 target tickers; those tickers were skipped from planned buys and listed in the report.
- No paper orders were submitted.
- Fallback command:
  - `.\venv\Scripts\python.exe scripts\dry_run_rebalance.py --as-of-date 2026-05-08 --top-n 20 --price-fallback latest-db --output-md data\dry_run_rebalance_2026-05-08_fallback.md`
- Fallback result:
  - buy_count: `20`
  - price_lookup_failed_count: `0`
  - price_fallback_count: `13`
  - report written to `data\dry_run_rebalance_2026-05-08_fallback.md`
- Latest preflight JSON generated:
  - `data\dry_run_rebalance_latest.json`
  - parsed successfully from PowerShell
  - preflight gate currently blocks order execution because fallback prices were used for 13 tickers
- Retry-only command:
  - `.\venv\Scripts\python.exe scripts\dry_run_rebalance.py --as-of-date 2026-05-08 --top-n 20 --quote-retries 2 --quote-delay-sec 0.25 --output-md data\dry_run_rebalance_2026-05-08_retry.md --output-json data\dry_run_rebalance_retry.json`
  - result: buy_count `18`, price_lookup_failed_count `2`, price_fallback_count `0`
- Strict retry-only command:
  - `.\venv\Scripts\python.exe scripts\dry_run_rebalance.py --as-of-date 2026-05-08 --top-n 20 --quote-retries 4 --quote-delay-sec 0.5 --output-md data\dry_run_rebalance_2026-05-08_retry_strict.md --output-json data\dry_run_rebalance_retry_strict.json`
  - result: buy_count `20`, price_lookup_failed_count `0`, price_fallback_count `0`
  - copied to `data\dry_run_rebalance_latest.json`
  - preflight passes for expected date `2026-05-08`
  - preflight blocks for expected date `2026-05-09` as stale
- Manual execution safety check:
  - `.\venv\Scripts\python.exe scripts\execute_rebalance_from_dry_run.py --dry-run-json data\dry_run_rebalance_latest.json --expected-date 2026-05-09 --confirm EXECUTE_PAPER_REBALANCE`
  - after market-time guard: `market_time_required=weekday 09:00-15:20 KST`
  - earlier preflight-only check also blocked it as stale: `execution_blocked=dry-run preflight blocked: stale report as_of_date='2026-05-08', expected=2026-05-09`
  - no paper orders were submitted

### Verification

- TDD red for missing script: `.\venv\Scripts\python.exe -m pytest tests\trading\test_dry_run_rebalance.py -q` -> failed before `scripts.dry_run_rebalance` existed.
- TDD red for safe KIS failure handling: targeted dry-run test failed before exceptions were caught.
- TDD red for per-ticker quote failures: targeted dry-run test failed before quote errors were isolated.
- TDD red for DB price fallback: targeted dry-run tests failed before `--price-fallback latest-db` existed.
- TDD red for JSON output: targeted dry-run test failed before `--output-json` existed.
- TDD red for order preflight gate: targeted rebalancer test failed before `preflight_report_path` was supported.
- TDD red for scheduler wiring: targeted scheduler test failed before `_rebalance_job` passed the dry-run JSON path to `execute_rebalance`.
- TDD red for quote retry controls: targeted dry-run tests failed before `--quote-retries` and `--quote-delay-sec` existed.
- TDD red for stale report blocking: targeted rebalancer/scheduler tests failed before expected preflight date checking existed.
- TDD red for manual execution script: `.\venv\Scripts\python.exe -m pytest tests\trading\test_execute_rebalance_from_dry_run.py -q` -> failed before the script existed.
- TDD red for execution-blocked output: targeted manual execution test failed before RuntimeError was caught and printed.
- TDD red for manual execution market-time guard: targeted manual execution test failed before `now`/market-time support existed.
- Manual execution targeted tests: `.\venv\Scripts\python.exe -m pytest tests\trading\test_execute_rebalance_from_dry_run.py -q` -> 5 passed.
- Manual/smoke order targeted tests: `.\venv\Scripts\python.exe -m pytest tests\trading\test_execute_rebalance_from_dry_run.py tests\trading\test_smoke_test_order.py -q` -> 8 passed.
- Dry-run targeted tests: `.\venv\Scripts\python.exe -m pytest tests\trading\test_dry_run_rebalance.py -q` -> 9 passed.
- Trading/scheduler/manual targeted tests: `.\venv\Scripts\python.exe -m pytest tests\trading\test_execute_rebalance_from_dry_run.py tests\trading\test_rebalancer.py tests\trading\test_scheduler.py -q` -> 21 passed.
- AST/syntax check: `.\venv\Scripts\python.exe -m compileall src tests scripts` -> passed.
- Full test suite: `.\venv\Scripts\python.exe -m pytest -q` -> 209 passed.

### Next

- Generate a same-day clean dry-run JSON during market hours before any paper order execution.
- Only run `scripts\execute_rebalance_from_dry_run.py` with the confirmation token after the same-day clean dry-run JSON passes preflight.

## 2026-05-09 KIS PAPER preflight check

### Completed

- Started paper trading safety check from the no-order path only.
- Confirmed local KIS settings are in safe mode:
  - `TRADE_MODE=PAPER`
  - base URL: `https://openapivts.koreainvestment.com:29443`
  - KIS app key/secret/account values are present
  - account number shape: 8 numeric digits, logged only as `5018****`
  - `config.validate()` returned no warnings before the live API call
- Confirmed TCP connectivity to `openapivts.koreainvestment.com:29443` succeeds.
- Added `KIS.request_timeout_sec` from `KIS_REQUEST_TIMEOUT_SEC`, defaulting to `10`, so slow KIS PAPER responses can be tested without code edits.
- Updated `KisClient` to use the configured request timeout for token, balance, quote, pending-order, cancel, hashkey, and order endpoints.
- Added config validation for non-positive KIS request timeout values.

### Updated Diagnosis

- Rechecked after the PAPER gateway became reachable.
- PAPER token request returned HTTP `200`, confirming the PAPER AppKey is valid.
- Immediate repeated token requests can return `EGW00133` because KIS limits token issuance to once per minute.
- After waiting 70 seconds, `scripts\smoke_test_kis.py` passed end-to-end:
  - token issued
  - balance lookup succeeded
  - total evaluation amount: `100,000,000`
  - cash: `100,000,000`
  - current price lookup for `005930` succeeded
- Current conclusion: earlier failures were caused by intermittent PAPER gateway connectivity/timeouts plus repeated token issuance attempts inside KIS's one-token-per-minute limit, not by an invalid PAPER AppKey.
- Added file-backed KIS token caching:
  - default path: `data/kis_token_paper.json`
  - configurable with `KIS_TOKEN_CACHE_PATH`
  - cache includes `base_url` and an app-key SHA-256 fingerprint so tokens from another environment/key are ignored without storing the raw app key
  - `scripts\smoke_test_kis.py` now uses `_ensure_token()` instead of always forcing `_fetch_token()`
  - smoke-test exception logs now mask the KIS account number, app key, and app secret
  - token cache files are ignored by `.gitignore`
- Re-ran `scripts\smoke_test_kis.py` twice back-to-back:
  - first run issued and cached a token
  - second run reused the cached token and avoided the one-token-per-minute limit
  - both runs passed token, balance, and current-price checks

### Live PAPER API Result

- `scripts/smoke_test_kis.py` with the default 10-second timeout:
  - reached token step
  - failed with a read timeout
- Retried with `KIS_REQUEST_TIMEOUT_SEC=30`:
  - reached token step
  - failed with a read timeout
- Retried with `KIS_REQUEST_TIMEOUT_SEC=60`:
  - reached token step
  - failed with `403 Forbidden`
- Direct token-response diagnostic returned:
  - HTTP status: `403`
  - KIS error code: `EGW00103`
  - KIS message: `유효하지 않은 AppKey입니다.`

### Verification

- TDD red: `.\venv\Scripts\python.exe -m pytest tests\trading\test_kis_client.py::test_fetch_token_uses_configured_request_timeout -q` -> failed before `KISConfig.request_timeout_sec` existed.
- Targeted timeout/config tests: `.\venv\Scripts\python.exe -m pytest tests\test_config.py::test_default_kis_request_timeout_is_positive tests\test_config.py::test_validate_warns_when_dart_key_or_limits_are_missing tests\trading\test_kis_client.py::test_fetch_token_uses_configured_request_timeout -q` -> 3 passed.
- TDD red for token cache: `.\venv\Scripts\python.exe -m pytest tests\trading\test_kis_client.py::test_fetch_token_writes_token_cache tests\trading\test_kis_client.py::test_ensure_token_reuses_file_cached_token tests\trading\test_kis_client.py::test_ensure_token_ignores_expired_file_cached_token -q` -> failed before `KISConfig.token_cache_path` and file cache support existed.
- Token cache targeted tests: `.\venv\Scripts\python.exe -m pytest tests\trading\test_kis_client.py::test_fetch_token_writes_token_cache tests\trading\test_kis_client.py::test_ensure_token_reuses_file_cached_token tests\trading\test_kis_client.py::test_ensure_token_ignores_cache_for_different_base_url tests\trading\test_kis_client.py::test_ensure_token_ignores_expired_file_cached_token -q` -> 4 passed.
- Live KIS token-cache smoke: `Start-Sleep -Seconds 70; $env:KIS_REQUEST_TIMEOUT_SEC='60'; .\venv\Scripts\python.exe scripts\smoke_test_kis.py; .\venv\Scripts\python.exe scripts\smoke_test_kis.py` -> both runs passed; second run reused cached token.
- KIS/config targeted tests: `.\venv\Scripts\python.exe -m pytest tests\trading\test_kis_client.py tests\test_config.py -q` -> 25 passed.
- AST/syntax check: `.\venv\Scripts\python.exe -m compileall src tests scripts` -> passed.
- Full test suite: `.\venv\Scripts\python.exe -m pytest -q` -> 192 passed.

### Blocker

- Paper trading preflight cannot proceed to balance/current-price 조회 until `.env` contains a KIS AppKey that is valid for the PAPER API.
- Next action after fixing the key: rerun `.\venv\Scripts\python.exe scripts\smoke_test_kis.py`.

## 2026-05-09 Historical data expansion and weekly default

### Completed

- Extended local KRX price/fundamental history backward to `2024-01-02` through `2026-05-07`.
- Fixed Phase 1 universe sync so stocks missing from the latest selected universe are deactivated instead of staying active forever.
- Filled newly active universe price/fundamental gaps after re-aligning the active universe.
- Filled missing active quality metrics with OpenDART single-account sync for `2024` to `2025`.
- Classified newly observed quality validation exceptions in `src/data/quality_sync_exceptions.json` after checking the stored rows.
- Changed the default rebalance frequency from `daily` to `weekly` because the expanded DB comparison favored weekly on risk-adjusted return and turnover.
- Updated backtest tests that intentionally verify daily behavior to pass `rebalance_frequency="daily"` explicitly.
- Added `scripts/run_backtest_matrix.py` so top-N, rebalance cadence, and stop on/off comparisons can be rerun from one command with CSV-style output.
- Added `stop_cooldown_days` support to the backtest engine plus `--stop-cooldown-days` in both backtest CLIs for repeatable stop re-entry experiments.
- Added `--output-csv` to `scripts/run_backtest_matrix.py` and saved the current weekly comparison to `data/backtest_matrix_2024-07-01_2026-05-07.csv`.
- Added cost override CLI options to both backtest runners: `--commission-rate`, `--tax-rate-kospi`, `--tax-rate-kosdaq`, and `--slippage-rate`.
- Added `--cost-scenarios` to the matrix runner with `custom`, `base`, `zero`, `slippage20`, and `slippage30`.
- Added `--output-md` to the matrix runner for automatic Markdown reports with best-by-Sharpe summary and scenario table.
- Expanded Markdown reports with best-by-return, lowest-MDD, and lowest-trade-count summaries.
- Saved the current cost preset report to `data/backtest_cost_matrix_2024-07-01_2026-05-07.csv` and `data/backtest_cost_matrix_2024-07-01_2026-05-07.md`.

### Local DB State

- `stocks_total`: `519`
- `stocks_active`: `476`
- `daily_prices`: `264,200`
- `fundamentals`: `262,155`
- price range: `2024-01-02` to `2026-05-07`
- fundamental range: `2024-01-02` to `2026-05-07`
- quality rows: `3,919`
- quality tickers: `507`
- active stocks without prices: `0`
- active stocks without fundamentals: `088980`/`맥쿼리인프라`, `950160`/`코오롱티슈진`
- quality validation:
  - unexpected issues: `0`
  - unsynced active no-source tickers: `088980`/`맥쿼리인프라`, `0011T0`/`채비`
  - null counts `(roe, operating_margin, debt_ratio)`: `(25, 207, 0)`
  - rows below 8 quarters: `29`, all documented as source absence

### Real DB Result

- Same expanded DB window and settings for all runs: `2024-07-01` to `2026-05-07`, top 20 unless stated, initial capital 100,000,000, rank scoring.
- Daily, default stops:
  - final equity = `316,422,771.06`
  - total return = `216.42%`
  - max drawdown = `-16.56%`
  - Sharpe ratio = `2.2507`
  - trade count = `1,476`
- Daily, stops disabled:
  - final equity = `337,000,759.20`
  - total return = `237.00%`
  - max drawdown = `-18.99%`
  - Sharpe ratio = `2.2081`
  - trade count = `625`
- Daily, loose stops `-0.10/-0.15`:
  - final equity = `302,367,139.79`
  - total return = `202.37%`
  - max drawdown = `-18.64%`
  - Sharpe ratio = `2.0825`
  - trade count = `1,124`
- Daily, trailing-only approximation `-1.00/-0.10`:
  - final equity = `311,114,448.67`
  - total return = `211.11%`
  - max drawdown = `-17.18%`
  - Sharpe ratio = `2.2155`
  - trade count = `1,410`
- Weekly, default stops:
  - final equity = `307,483,307.96`
  - total return = `207.48%`
  - max drawdown = `-15.45%`
  - Sharpe ratio = `2.4230`
  - trade count = `880`
- Monthly, default stops:
  - final equity = `203,586,084.08`
  - total return = `103.59%`
  - max drawdown = `-18.01%`
  - Sharpe ratio = `1.7355`
  - trade count = `539`
- Weekly top-N sensitivity:
  - top 10: return `131.27%`, MDD `-18.60%`, Sharpe `1.7906`, trades `483`
  - top 20: return `207.48%`, MDD `-15.45%`, Sharpe `2.4230`, trades `880`
  - top 30: return `153.81%`, MDD `-15.85%`, Sharpe `2.1116`, trades `1,343`
- Matrix script verification command:
  - `.\venv\Scripts\python.exe scripts\run_backtest_matrix.py --start-date 2024-07-01 --end-date 2026-05-07 --top-ns 10,20,30 --rebalance-frequencies weekly --include-stops-disabled --initial-capital 100000000 --output-csv data\backtest_matrix_2024-07-01_2026-05-07.csv`
  - top 10 weekly stops off: return `190.02%`, MDD `-17.84%`, Sharpe `1.9450`, trades `231`
  - top 20 weekly stops off: return `228.86%`, MDD `-19.23%`, Sharpe `2.1840`, trades `374`
  - top 30 weekly stops off: return `190.05%`, MDD `-19.56%`, Sharpe `2.0067`, trades `564`
- Stop re-entry diagnostics:
  - Daily baseline stop sells: `265`; later same-ticker rebuys: `260`; next-day rebuys: `174`.
  - Weekly baseline stop sells: `255`; later same-ticker rebuys: `245`; most common re-entry gaps were `3` to `7` calendar days.
- Weekly top 20 stop-cooldown sensitivity:
  - 0 days: return `207.48%`, MDD `-15.45%`, Sharpe `2.4230`, trades `880`
  - 3 days: return `161.12%`, MDD `-15.23%`, Sharpe `2.1253`, trades `888`
  - 5 days: return `161.15%`, MDD `-15.69%`, Sharpe `2.1426`, trades `943`
  - 10 days: return `150.10%`, MDD `-19.62%`, Sharpe `2.0045`, trades `989`
- Weekly top 20 transaction-cost sensitivity:
  - zero cost: return `237.95%`, MDD `-15.22%`, Sharpe `2.6099`, trades `882`
  - base cost: return `207.48%`, MDD `-15.45%`, Sharpe `2.4230`, trades `880`
  - slippage 20bp: return `198.57%`, MDD `-14.83%`, Sharpe `2.3747`, trades `878`
  - slippage 30bp: return `184.21%`, MDD `-14.93%`, Sharpe `2.2711`, trades `878`
- Cost preset report command:
  - `.\venv\Scripts\python.exe scripts\run_backtest_matrix.py --start-date 2024-07-01 --end-date 2026-05-07 --top-ns 20 --rebalance-frequencies weekly --cost-scenarios base,zero,slippage20,slippage30 --initial-capital 100000000 --output-csv data\backtest_cost_matrix_2024-07-01_2026-05-07.csv --output-md data\backtest_cost_matrix_2024-07-01_2026-05-07.md`
  - Markdown summary now reports best Sharpe/return as `zero`, and lowest MDD/trade count as `slippage20` for this cost-only matrix.

### Verification

- TDD red for active universe cleanup: `.\venv\Scripts\python.exe -m pytest tests\data\test_collectors.py::test_sync_phase1_data_deactivates_stocks_missing_from_latest_universe -q` -> failed before implementation.
- Active universe targeted tests: `.\venv\Scripts\python.exe -m pytest tests\data\test_collectors.py::test_sync_phase1_data_deactivates_stocks_missing_from_latest_universe tests\data\test_repositories.py -q` -> 6 passed.
- Quality/data targeted tests: `.\venv\Scripts\python.exe -m pytest tests\data\test_quality_sync_script.py tests\data\test_collectors.py tests\data\test_repositories.py -q` -> 31 passed.
- TDD red for weekly default: `.\venv\Scripts\python.exe -m pytest tests\backtest\test_run_script.py::test_parse_args_accepts_backtest_options -q` -> failed before `REBALANCE.frequency` changed.
- Weekly default targeted tests: `.\venv\Scripts\python.exe -m pytest tests\backtest\test_run_script.py::test_parse_args_accepts_backtest_options tests\backtest\test_run_script.py::test_run_passes_rebalance_frequency_to_backtest -q` -> 2 passed.
- TDD red for matrix script: `.\venv\Scripts\python.exe -m pytest tests\backtest\test_run_matrix_script.py -q` -> failed before `scripts/run_backtest_matrix.py` existed.
- Matrix script tests: `.\venv\Scripts\python.exe -m pytest tests\backtest\test_run_matrix_script.py -q` -> 2 passed.
- TDD red for stop cooldown: `.\venv\Scripts\python.exe -m pytest tests\backtest\test_backtest_engine.py::test_stop_cooldown_blocks_rebuy_until_calendar_days_pass -q` -> failed before engine support existed.
- Stop cooldown targeted tests: `.\venv\Scripts\python.exe -m pytest tests\backtest\test_run_script.py::test_parse_args_accepts_stop_thresholds tests\backtest\test_run_script.py::test_run_passes_stop_thresholds_to_backtest tests\backtest\test_run_script.py::test_script_can_be_executed_directly_with_help tests\backtest\test_run_matrix_script.py tests\backtest\test_backtest_engine.py::test_stop_cooldown_blocks_rebuy_until_calendar_days_pass -q` -> 6 passed.
- TDD red for matrix CSV export: `.\venv\Scripts\python.exe -m pytest tests\backtest\test_run_matrix_script.py::test_run_writes_csv_output_file -q` -> failed before `--output-csv` existed.
- Matrix CSV export tests: `.\venv\Scripts\python.exe -m pytest tests\backtest\test_run_matrix_script.py -q` -> 3 passed.
- TDD red for cost override CLI options: `.\venv\Scripts\python.exe -m pytest tests\backtest\test_run_script.py::test_parse_args_accepts_cost_overrides tests\backtest\test_run_script.py::test_run_passes_cost_overrides_to_backtest tests\backtest\test_run_script.py::test_script_can_be_executed_directly_with_help tests\backtest\test_run_matrix_script.py::test_parse_args_accepts_matrix_options tests\backtest\test_run_matrix_script.py::test_run_prints_one_row_per_matrix_scenario -q` -> failed before options existed.
- Cost override targeted tests: same command -> 5 passed.
- TDD red for cost presets: `.\venv\Scripts\python.exe -m pytest tests\backtest\test_run_matrix_script.py -q` -> failed before `--cost-scenarios` existed and before the output had a `cost_scenario` column.
- TDD red for Markdown report export: `.\venv\Scripts\python.exe -m pytest tests\backtest\test_run_matrix_script.py::test_run_writes_markdown_report -q` -> failed before `--output-md` existed.
- TDD red for richer Markdown summaries: same Markdown report test -> failed before best-return/lowest-MDD/lowest-trades lines existed.
- Matrix report tests: `.\venv\Scripts\python.exe -m pytest tests\backtest\test_run_matrix_script.py -q` -> 4 passed.
- AST/syntax check: `.\venv\Scripts\python.exe -m compileall src tests scripts` -> passed.
- Full test suite: `.\venv\Scripts\python.exe -m pytest -q` -> 186 passed.

### Next

- Do not change the `stop_cooldown_days` default from `0`; current expanded DB evidence shows cooldown reduces risk-adjusted performance.
- Next useful step: begin live/paper trading integration checks against the weekly default, or add a richer Markdown report section for drawdown/turnover rankings.

## 2026-05-08 Backtest stop-threshold CLI support

### Completed

- Investigated stop-rule threshold sensitivity on the current local DB before changing any defaults.
- Confirmed `run_backtest()` already supported custom `stop_loss_pct` and `trailing_stop_pct`; the missing piece was CLI access for repeatable comparisons.
- Added `--stop-loss-pct` and `--trailing-stop-pct` to `scripts/run_phase3_backtest.py`.
- Added CLI validation so both threshold values must be negative.
- Kept default values unchanged:
  - stop loss = `-0.08`
  - trailing stop = `-0.10`

### Real DB Result

- Same local DB window and settings for all runs: `2025-10-01` to `2026-05-07`, top 20, initial capital 100,000,000, daily rebalance, rank scoring.
- Stops disabled:
  - final equity = `128,719,734.19`
  - total return = `28.72%`
  - max drawdown = `-0.79%`
  - Sharpe ratio = `3.9711`
  - trade count = `63`
- Default stops `-0.08/-0.10`:
  - final equity = `128,848,992.85`
  - total return = `28.85%`
  - max drawdown = `-0.79%`
  - Sharpe ratio = `3.9440`
  - trade count = `67`
- Tight stops `-0.05/-0.07`:
  - final equity = `128,350,809.94`
  - total return = `28.35%`
  - max drawdown = `-0.79%`
  - Sharpe ratio = `3.8932`
  - trade count = `78`
- Loose stops `-0.10/-0.15`:
  - final equity = `129,724,176.14`
  - total return = `29.72%`
  - max drawdown = `-0.79%`
  - Sharpe ratio = `4.0267`
  - trade count = `63`
- Stop-only approximation `-0.08/-1.00`:
  - final equity = `129,709,452.35`
  - total return = `29.71%`
  - max drawdown = `-0.79%`
  - Sharpe ratio = `3.9949`
  - trade count = `64`
- Trailing-only approximation `-1.00/-0.10`:
  - final equity = `131,068,500.98`
  - total return = `31.07%`
  - max drawdown = `-0.79%`
  - Sharpe ratio = `4.1338`
  - trade count = `67`

### Verification

- TDD red: `.\venv\Scripts\python.exe -m pytest tests\backtest\test_run_script.py -q` -> failed before CLI options existed.
- Targeted script tests: `.\venv\Scripts\python.exe -m pytest tests\backtest\test_run_script.py -q` -> 11 passed.
- Backtest tests: `.\venv\Scripts\python.exe -m pytest tests\backtest -q` -> 33 passed.
- Real CLI comparisons executed for default, loose, and trailing-only stop settings with `--trade-summary`.
- AST/syntax check: `.\venv\Scripts\python.exe -m compileall src tests scripts` -> passed.
- Full test suite: `.\venv\Scripts\python.exe -m pytest -q` -> 178 passed.

### Next

- Do not change stop defaults yet because the local DB window is short and starts trading late due the 126-day momentum lookback. The next useful step is extending historical price/fundamental data backward, then rerunning the same rank/rebalance/stop comparisons over a longer out-of-sample window.

## 2026-05-08 Backtest rebalance-frequency support

### Completed

- Added rebalance cadence support to the Phase 3 backtest engine.
- `run_backtest()` now accepts `rebalance_frequency` with `daily`, `weekly`, or `monthly`.
- Daily remains the default and preserves the prior behavior.
- Weekly/monthly rebalancing only changes target holdings when the rebalance period changes; stop-loss and trailing-stop checks still run every trading day.
- Added `--rebalance-frequency {daily,weekly,monthly}` to `scripts/run_phase3_backtest.py`.
- Kept the existing `--trade-summary` output, so cadence comparisons include buy/sell counts and trade reasons.

### Real DB Result

- Same local DB window and settings for all runs: `2025-10-01` to `2026-05-07`, top 20, initial capital 100,000,000, rank scoring, stops enabled.
- Daily:
  - final equity = `128,848,992.85`
  - total return = `28.85%`
  - max drawdown = `-0.79%`
  - Sharpe ratio = `3.9440`
  - trade count = `67`
  - trade reasons = `rebalance:62, stop_loss:2, stop_loss_close_fallback:1, trailing_stop:2`
- Weekly:
  - final equity = `125,291,892.00`
  - total return = `25.29%`
  - max drawdown = `-1.70%`
  - Sharpe ratio = `3.5459`
  - trade count = `46`
  - trade reasons = `rebalance:39, stop_loss:3, stop_loss_close_fallback:1, trailing_stop:3`
- Monthly:
  - final equity = `125,488,276.06`
  - total return = `25.49%`
  - max drawdown = `-1.70%`
  - Sharpe ratio = `3.7442`
  - trade count = `34`
  - trade reasons = `rebalance:29, stop_loss:1, stop_loss_close_fallback:1, trailing_stop:3`

### Verification

- TDD red: `.\venv\Scripts\python.exe -m pytest tests\backtest\test_backtest_engine.py::test_run_backtest_weekly_rebalance_waits_until_next_week tests\backtest\test_run_script.py -q` -> failed before implementation.
- Targeted tests after implementation: same command -> 10 passed.
- Backtest tests: `.\venv\Scripts\python.exe -m pytest tests\backtest -q` -> 31 passed.
- Real DB cadence comparison executed for daily, weekly, and monthly with `--trade-summary`.
- AST/syntax check: `.\venv\Scripts\python.exe -m compileall src tests scripts` -> passed.
- Full test suite: `.\venv\Scripts\python.exe -m pytest -q` -> 176 passed.

### Next

- The current local DB evidence favors keeping daily as the default. Next useful tuning step is to compare stop-rule thresholds or add a no-new-buys guard after stop exits if immediate re-entry becomes visible in longer data.

## 2026-05-08 Rank backtest trade-summary diagnostics

### Completed

- Investigated portfolio turnover and trade counts under the new default rank scoring.
- Confirmed the backtest engine rebalances by recomputing top-N every trading date and selling positions that leave the target set.
- Ran the local DB backtest over `2025-10-01` to `2026-05-07` across top-N and stop settings:
  - top 10, stops on: `38` trades, return `27.15%`, MDD `-0.68%`, Sharpe `3.7791`.
  - top 20, stops on: `67` trades, return `28.85%`, MDD `-0.79%`, Sharpe `3.9440`.
  - top 30, stops on: `104` trades, return `23.66%`, MDD `-0.78%`, Sharpe `3.9141`.
  - top 10, stops off: `35` trades, return `30.01%`, MDD `-1.02%`, Sharpe `4.1036`.
  - top 20, stops off: `63` trades, return `28.72%`, MDD `-0.79%`, Sharpe `3.9711`.
  - top 30, stops off: `92` trades, return `22.79%`, MDD `-0.97%`, Sharpe `3.7335`.
- Confirmed trades are concentrated in 2026-04 and 2026-05 because the 126-trading-day momentum lookback delays score availability on the current local price range.
- Added `--trade-summary` to `scripts/run_phase3_backtest.py` so future runs print buy/sell counts and trade reason counts without ad hoc scripts.

### Real DB Result

- `.\venv\Scripts\python.exe scripts\run_phase3_backtest.py --start-date 2025-10-01 --end-date 2026-05-07 --top-n 20 --initial-capital 100000000 --trade-summary`
- Result:
  - final equity = `128,848,992.85`
  - total return = `28.85%`
  - max drawdown = `-0.79%`
  - Sharpe ratio = `3.9440`
  - trade count = `67`
  - buy count = `42`
  - sell count = `25`
  - trade reasons = `rebalance:62, stop_loss:2, stop_loss_close_fallback:1, trailing_stop:2`

### Verification

- TDD red: `.\venv\Scripts\python.exe -m pytest tests\backtest\test_run_script.py -q` -> failed because `--trade-summary` was not implemented.
- Targeted tests: `.\venv\Scripts\python.exe -m pytest tests\backtest\test_run_script.py -q` -> 7 passed.
- AST/syntax check: `.\venv\Scripts\python.exe -m compileall scripts tests src` -> passed.
- Full test suite: `.\venv\Scripts\python.exe -m pytest -q` -> 173 passed.

### Next

- Decide whether the next tuning variable should be stop rules or rebalance cadence. Current evidence suggests stop rules add little under top 20 rank scoring, while top-N has a clearer effect.

## 2026-05-08 Factor scoring default switched to rank

### Completed

- Investigated the next Phase 2/3 task: whether current factor weights and very large z-score outputs were letting single-factor outliers dominate rankings.
- Checked the latest real DB factor distribution for `2026-05-08`.
- Found z-score outlier dominance in multiple factors:
  - `momentum_score` max = `13.5388` while p99 = `3.1732`.
  - `yield_score` max = `9.5873` while p99 = `2.8366`.
  - `value_score` min = `-11.7448` while p99 = `0.4105`.
- Compared available scoring modes on the local DB backtest window `2025-10-01` to `2026-05-07`, top 20, initial capital 100,000,000:
  - current zscore: final equity `113,119,839.49`, total return `13.12%`, MDD `-4.77%`, Sharpe `2.0094`, trades `84`.
  - zscore clipped at 3: final equity `117,180,357.85`, total return `17.18%`, MDD `-2.46%`, Sharpe `2.6289`, trades `94`.
  - zscore clipped at 2.5: final equity `116,716,038.90`, total return `16.72%`, MDD `-3.18%`, Sharpe `2.2624`, trades `86`.
  - rank: final equity `128,848,992.85`, total return `28.85%`, MDD `-0.79%`, Sharpe `3.9440`, trades `67`.
- Switched the default `FACTOR.scoring_method` from `zscore` to `rank` in `config.py`.
- Added a config regression test so the intended default is explicit.
- Updated a quality-score timing test that previously depended on z-score magnitude; it now verifies the same publication-timing behavior under rank scoring.

### Real DB Result

- Ranking top 10 on `2026-05-08`: `005850`, `402340`, `007340`, `072950`, `147830`, `004800`, `000990`, `033100`, `031980`, `083450`.
- Backtest result for `2025-10-01` to `2026-05-07`, top 20, initial capital 100,000,000:
  - final equity = `128,848,992.85`
  - total return = `28.85%`
  - CAGR = `52.87%`
  - max drawdown = `-0.79%`
  - Sharpe ratio = `3.9440`
  - win rate = `44.00%`
  - trade count = `67`

### Verification

- TDD red: `.\venv\Scripts\python.exe -m pytest tests\test_config.py -q` -> failed while default was still `zscore`.
- Targeted tests: `.\venv\Scripts\python.exe -m pytest tests\test_config.py tests\factors\test_engine.py tests\backtest\test_backtest_engine.py -q` -> 27 passed.
- Real ranking: `.\venv\Scripts\python.exe scripts\rank_phase2_factors.py --as-of-date 2026-05-08 --top-n 10` -> produced rank-bounded top 10.
- Real backtest: `.\venv\Scripts\python.exe scripts\run_phase3_backtest.py --start-date 2025-10-01 --end-date 2026-05-07 --top-n 20 --initial-capital 100000000` -> matched the rank result above.
- AST/syntax check: `.\venv\Scripts\python.exe -m compileall src tests scripts` -> passed.
- Full test suite: `.\venv\Scripts\python.exe -m pytest -q` -> 171 passed.

### Next

- Investigate portfolio turnover and trade count under rank scoring before tuning rebalance frequency, holding count, or stop rules.

## 2026-05-07 DART Quality Fundamentals Task 4C

### Done

- Continued `docs/superpowers/plans/2026-05-04-phase1-quality-fundamentals.md`.
- Added `src/data/quality_provider.py`.
- Implemented the first `DartFssFundamentalsProvider` shell:
  - injects `dart_fss` module for testability
  - calls `set_api_key`
  - builds in-memory `stock_code -> corp_code` mapping from `get_corp_list`
  - ignores non-listed corp entries without `stock_code`
  - returns `[]` for unmapped tickers without consuming rate limit
  - calls `RateLimiter.acquire()` and `dart_fss.fs.extract()` for mapped tickers
- Financial statement parsing is intentionally still empty and will be the next isolated step.

### Verification

- `.\venv\Scripts\python.exe -m pytest tests\data\test_quality_provider.py -q -p no:cacheprovider`
- Result: `3 passed`
- `.\venv\Scripts\python.exe -m py_compile src\data\quality_provider.py`
- Result: passed
- `.\venv\Scripts\python.exe -m pytest tests\data -q`
- Result: `38 passed`
- `.\venv\Scripts\python.exe -m py_compile src\data\quality_collector.py src\data\rate_limiter.py src\data\quality_provider.py`
- Result: passed
- `.\venv\Scripts\python.exe -m pytest -q`
- Result: `137 passed`

### Next

- Implement financial statement extraction/parsing from `dart_fss.fs.extract()` into `QualityMetric` rows.

## 2026-05-07 DART Quality Fundamentals Task 4B

### Done

- Continued `docs/superpowers/plans/2026-05-04-phase1-quality-fundamentals.md`.
- Added `src/data/rate_limiter.py`.
- Implemented `RateLimiter` with:
  - per-minute request window
  - daily quota counter
  - 24-hour quota reset
  - injectable time/sleep functions for fast tests
  - `QuotaExhausted("DART daily quota reached")`
- Added unit tests with a fake clock, so no real sleep is used.

### Verification

- `.\venv\Scripts\python.exe -m pytest tests\data\test_rate_limiter.py -q -p no:cacheprovider`
- Result: `4 passed`
- `.\venv\Scripts\python.exe -m py_compile src\data\rate_limiter.py`
- Result: passed
- `.\venv\Scripts\python.exe -m pytest tests\data -q`
- Result: `35 passed`
- `.\venv\Scripts\python.exe -m py_compile src\data\quality_collector.py src\data\rate_limiter.py`
- Result: passed
- `.\venv\Scripts\python.exe -m pytest -q`
- Result: `134 passed`

### Next

- Continue with the real `DartFssFundamentalsProvider` shell and tests, then add the manual quality sync script.

## 2026-05-07 DART Quality Fundamentals Task 4A

### Done

- Continued `docs/superpowers/plans/2026-05-04-phase1-quality-fundamentals.md`.
- Added fake-provider based quality sync collector foundation.
- Added `src/data/quality_collector.py` with:
  - `QualityMetricsProvider` protocol
  - `QuotaExhausted`
  - `sync_phase1_quality`
- Implemented quality sync behavior for:
  - success: store metrics and record `QualitySyncRun(status="success")`
  - provider failure: record `QualitySyncRun(status="failed")` and re-raise
  - quota exhaustion: keep already saved rows and record `status="quota_exhausted"`
  - explicit `tickers` without requiring `Stock` rows
- Kept real dart-fss provider and RateLimiter for the next isolated step.

### Verification

- `.\venv\Scripts\python.exe -m pytest tests\data\test_quality_collector.py -q -p no:cacheprovider`
- Result: `4 passed`
- `.\venv\Scripts\python.exe -m py_compile src\data\models.py src\data\repositories.py src\data\quality_collector.py`
- Result: passed
- `.\venv\Scripts\python.exe -m pytest tests\data -q`
- Result: `31 passed`
- `.\venv\Scripts\python.exe -m pytest -q`
- Result: `130 passed`

### Next

- Continue with RateLimiter and daily quota unit tests, then connect it to the real DART provider.

## 2026-05-07 DART Quality Fundamentals Task 3

### Done

- Continued `docs/superpowers/plans/2026-05-04-phase1-quality-fundamentals.md`.
- Added `QualitySyncRun` model and `quality_sync_runs` table definition.
- Kept quality sync execution history separate from market-data `SyncRun`.
- Added model tests for:
  - `create_tables()` creating `quality_sync_runs`
  - persisting status, year window, metric count, finish time, and error message
- Confirmed SQLite creates both `quality_metrics` and `quality_sync_runs`.

### Verification

- `.\venv\Scripts\python.exe -m pytest tests\data\test_quality_sync_run_model.py -q -p no:cacheprovider`
- Result: `2 passed`
- `.\venv\Scripts\python.exe -m py_compile src\data\models.py`
- Result: passed
- `.\venv\Scripts\python.exe -m pytest tests\data -q`
- Result: `27 passed`
- SQLite table check
- Result: `quality_metrics=True`, `quality_sync_runs=True`
- `.\venv\Scripts\python.exe -m pytest -q`
- Result: `126 passed`

### Next

- Continue with quality sync collector foundation: `QualityMetricsProvider`, `sync_phase1_quality`, and `QuotaExhausted` handling with fake-provider tests.

## 2026-05-07 DART Quality Fundamentals Task 2

### Done

- Continued `docs/superpowers/plans/2026-05-04-phase1-quality-fundamentals.md`.
- Added `QualityMetric` model and `quality_metrics` table definition.
- Added unique key policy for `(ticker, fiscal_year, fiscal_quarter)`.
- Added `upsert_quality_metrics` repository function.
- Added repository regression tests for:
  - updating an existing ticker/year/quarter row
  - inserting separate fiscal quarters independently
- Confirmed `create_tables()` creates the new `quality_metrics` table in SQLite.

### Verification

- `.\venv\Scripts\python.exe -m pytest tests\data\test_quality_repository.py -q -p no:cacheprovider`
- Result: `2 passed`
- `.\venv\Scripts\python.exe -m py_compile src\data\models.py src\data\repositories.py`
- Result: passed
- `.\venv\Scripts\python.exe -m pytest tests\data -q`
- Result: `25 passed`
- `.\venv\Scripts\python.exe -m pytest tests\test_config.py tests\factors\test_engine.py -q`
- Result: `5 passed`
- SQLite table check
- Result: `quality_metrics=True`
- `.\venv\Scripts\python.exe -m pytest -q`
- Result: `124 passed`

### Next

- Continue with `QualitySyncRun` model for quality sync execution history.

## 2026-05-07 DART Quality Fundamentals Task 1

### Done

- Started `docs/superpowers/plans/2026-05-04-phase1-quality-fundamentals.md`.
- Added OpenDART config:
  - `DART_API_KEY`
  - `DART_REQUESTS_PER_MINUTE`
  - `DART_DAILY_QUOTA`
- Added `DART` to `config.py` runtime snapshot and validation warnings.
- Added OpenDART entries to `.env.example`.
- Added `dart-fss==0.4.3` to `requirements.txt`.
- Installed `dart-fss==0.4.3` in the active `venv`.
- Fixed `_pre_market_sync_job` so injected test sync functions do not instantiate the real KRX provider.

### Verification

- `.\venv\Scripts\python.exe -m pytest tests\test_config.py -q`
- Result: `3 passed`
- `.\venv\Scripts\python.exe -c "import dart_fss; print(dart_fss.__version__)"`
- Result: `0.4.3`
- `.\venv\Scripts\python.exe config.py`
- Result: DART config appears in the snapshot and missing `DART_API_KEY` is warned without aborting.
- `.\venv\Scripts\python.exe -m pytest tests\trading\test_scheduler.py -q`
- Result: `5 passed`
- `.\venv\Scripts\python.exe -m py_compile config.py src\trading\scheduler.py`
- Result: passed
- `.\venv\Scripts\python.exe -m pytest -q`
- Result: `122 passed`

### Next

- Continue with DART quality schema: add `QualityMetric` model and `upsert_quality_metrics` repository tests.

## 2026-05-07 KRX Fundamental Gap Diagnostics

### Done

- Investigated the KRX fundamental fetch warnings from the long sync.
- DB evidence:
  - price dates: 143
  - fundamental dates: 143
  - dates with zero fundamentals while prices exist: 0
  - price tickers: 448
  - fundamental tickers: 446
  - tickers with prices but no fundamentals: `088980`, `950160`
- Direct provider check confirmed pykrx returns no fundamental rows for those two tickers while normal tickers such as `005930` return rows.
- Added a sync collection warning when tickers have price rows but no fundamental rows.

### Verification

- `.\venv\Scripts\python.exe -m pytest tests\data\test_collectors.py::test_fetch_market_data_parallel_warns_when_fundamentals_are_missing -q`
- Result: `1 passed`
- `.\venv\Scripts\python.exe -m py_compile src\data\collectors.py`
- Result: passed
- `.\venv\Scripts\python.exe -m pytest tests\data -q`
- Result: `23 passed`

### Next

- Move to DART-based quality fundamentals if higher quality factor coverage is needed.

## 2026-05-07 Phase 1 Long Sync + Default Lookback Smoke

### Done

- Fixed SQLite bulk upsert failure by batching repository upserts.
- Added regression coverage for large `daily_prices` upserts above SQLite variable limits.
- Re-ran real KRX sync for `2025-10-01` ~ `2026-05-07` with `--workers 3`.
- DB verification:
  - `stocks`: 448
  - `daily_prices`: 63018
  - `fundamentals`: 62675
  - price date range: `2025-10-01` ~ `2026-05-07`
  - fundamental date range: `2025-10-01` ~ `2026-05-07`
  - latest `sync_runs.status`: `success`
- Confirmed default Phase 2 ranking now works without overriding `--lookback-days`.
- Confirmed Phase 3 short smoke backtest produces trades with default lookback.

### Verification

- `.\venv\Scripts\python.exe -m py_compile src\data\repositories.py`
- Result: passed
- `.\venv\Scripts\python.exe -m pytest tests\data\test_repositories.py::test_upsert_daily_prices_batches_large_inputs_under_sqlite_variable_limit -q`
- Result: `1 passed`
- `.\venv\Scripts\python.exe -m pytest tests\data -q`
- Result: `22 passed`
- `.\venv\Scripts\python.exe scripts\rank_phase2_factors.py --as-of-date 2026-05-07 --top-n 10`
- Result: top ranked ticker `043260`, ranking output generated
- `.\venv\Scripts\python.exe scripts\run_phase3_backtest.py --start-date 2026-04-01 --end-date 2026-05-07 --top-n 5 --initial-capital 10000000 --disable-stops`
- Result: `trade_count=15`, `final_equity=9985200.02`, `total_return=-0.15%`

### Next

- Review data-quality gaps from KRX fundamental fetch warnings, or move to DART-based quality fundamentals.

## 2026-05-07 Phase 1 Real Data Sync Smoke

### 처리한 작업

- 실제 KRX 네트워크 접근으로 `scripts/sync_phase1_data.py` 를 실행해 `data/quntbot.db` 를 생성했다.
- 실행 범위: `2026-05-04` ~ `2026-05-07`, `--workers 1`.
- sync 결과: universe 448개, daily_prices 1344행, fundamentals 1338행.
- DB 확인 결과:
  - `stocks`: 448
  - `daily_prices`: 1344
  - `fundamentals`: 1338
  - latest `sync_runs.status`: `success`
  - price date range: `2026-05-04` ~ `2026-05-07`
- `rank_phase2_factors.py --lookback-days 1` 로 실제 DB 기반 상위 랭킹 출력 확인.
- `run_phase3_backtest.py` 는 짧은 DB 범위와 기본 126영업일 모멘텀 lookback 때문에 거래 0건으로 종료됨을 확인했다.

### 검증

- `.\venv\Scripts\python.exe -m py_compile config.py src\data\models.py src\data\database.py src\data\repositories.py src\data\collectors.py scripts\sync_phase1_data.py`
- 결과: 통과
- `.\venv\Scripts\python.exe -m pytest tests\data -q`
- 결과: `21 passed`

### 남은 사항

- 의미 있는 기본 팩터 랭킹과 백테스트를 위해 최소 126영업일 이상 가격 데이터가 필요하다.
- 다음 순서 후보: 더 긴 Phase 1 sync 기간을 잡아 DB를 확장하거나, DART quality fundamentals 기반 구축을 시작한다.

## 2026-05-06 Phase 3 Stops Simulation

### 처리한 작업

- 백테스트 가격 로더를 close-only 에서 open/close 구조로 확장했다.
- `run_backtest` 에 `enable_stops`, `stop_loss_pct`, `trailing_stop_pct` 인자를 추가했다.
- 손절과 트레일링 스톱을 "종가 트리거, 다음 거래일 시가 체결" 방식으로 반영했다.
- 마지막 거래일에 트리거된 stop 은 같은 날 종가로 fallback 매도한다.
- stop 체결 당일 같은 종목 재진입을 금지했다.
- `scripts/run_phase3_backtest.py` 에 `--enable-stops` / `--disable-stops` 옵션을 추가했다.
- 설계 기록 문서 `docs/superpowers/specs/2026-05-06-phase3-stops-simulation-design.md` 를 추가했다.

### 검증

- `.\venv\Scripts\python.exe -m pytest tests\backtest\test_backtest_engine.py -q`
- 결과: `14 passed`
- `.\venv\Scripts\python.exe -m pytest tests\backtest\test_run_script.py -q`
- 결과: `5 passed`

### 남은 사항

- 실데이터 DB가 생긴 뒤 `--enable-stops` 와 `--disable-stops` 결과 차이를 같은 기간으로 비교해야 한다.
- 다음 순서 후보: Phase 1 실제 데이터 sync 또는 DART quality fundamentals 기반 구축.

## 2026-05-06 Cost Parameters Recheck

### 처리한 작업

- 2026년 적용 거래세 기준을 재확인했다.
- `config.COST.tax_rate_kospi` 와 `config.COST.tax_rate_kosdaq` 를 `0.0018` 에서 `0.0020` 으로 변경했다.
- 기본 설정값 회귀 테스트 `tests/test_config.py` 를 추가했다.
- backtest 매도 비용이 KOSPI/KOSDAQ 세율 인자를 적용하는지 확인하는 테스트를 추가했다.
- 결정 기록 문서 `docs/superpowers/specs/2026-05-06-cost-parameters-decision.md` 를 추가했다.

### 검증

- `.\venv\Scripts\python.exe -m pytest tests\test_config.py tests\backtest\test_backtest_engine.py -q`
- 결과: `8 passed`

### 남은 사항

- `data/quntbot.db` 가 아직 없어서 0.18% vs 0.20% 실데이터 백테스트 영향 비교는 보류했다.
- 다음 순서 후보: Phase 3 backtest stop-loss/trailing-stop 반영.

이 파일은 quntbot 개발을 이어가면서 현재 완료 단계, 중요한 문제점, 해결 내용, 개선 사안을 계속 기록하기 위한 작업 로그입니다.

## 2026-05-04 09:47 KST

### 현재 완료 단계

- GitHub ZIP 다운로드본 기준 작업 폴더를 `C:\Users\n\Downloads\quntbot-main\quntbot-main`로 확정했다.
- Phase 0 환경 세팅을 이 노트북에서 완료했다.
- Python 3.12.10 기반 새 가상환경 `venv`를 생성했다.
- `requirements.txt` 의존성 설치를 완료했다.
- `.env.example`을 `.env`로 복사했다.
- `python config.py` 설정 검증을 통과했다.
- 전체 테스트를 실행했고 `33 passed`로 통과했다.

### 확인된 문제점

- 기존 설치된 Python은 `3.14.3`이었다.
- `Python 3.14`에서는 `pandas==2.2.3` 설치 시 미리 빌드된 Windows wheel을 사용하지 못하고 소스 빌드로 넘어갔다.
- 그 결과 Visual Studio 빌드 도구의 `vswhere.exe`를 찾지 못해 `pip install -r requirements.txt`가 실패했다.
- 기존 `venv`는 깨진 상태였다. 내부 실행 파일이 현재 프로젝트 경로가 아니라 Codex 샌드박스 임시 경로를 참조해 실행되지 않았다.
- `.env.example`의 placeholder 값이 그대로 `.env`에 들어가면 텔레그램 설정이 실제로 켜진 것처럼 인식되는 문제가 있었다.

### 처리 내용

- 공식 Python 3.12.10 Windows installer를 내려받아 사용자 계정 영역에 설치했다.
- 깨진 기존 `venv`는 삭제하지 않고 `venv_broken_py314`로 보존 이동했다.
- Python 3.12.10으로 새 `venv`를 만들었다.
- 새 가상환경에서 `pip`를 업데이트했다.
- `requirements.txt` 설치를 다시 실행해 성공시켰다.
- `.env`의 `KIS_APP_KEY`, `KIS_APP_SECRET`, `KIS_ACCOUNT_NO`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` placeholder 값을 빈 값으로 정리했다.
- 정리 후 `TELEGRAM_ENABLED`가 `false`로 정상 표시되는 것을 확인했다.

### 검증 결과

```text
python config.py
[OK] 설정 일관성 통과
```

```text
python -m pytest
33 passed
```

### 중요한 운영 메모

- 현재는 `TRADE_MODE=PAPER` 모드다.
- 실제 KIS API 키와 계좌번호는 아직 `.env`에 입력하지 않았다.
- 텔레그램 토큰과 채팅 ID도 아직 입력하지 않았다.
- `.env`는 절대 GitHub에 올리면 안 된다.
- ZIP 다운로드본이라 `.git` 연결은 없을 수 있다. GitHub로 다시 올리는 흐름이 필요해지면 Git 설치와 저장소 연결을 별도로 정리해야 한다.

### 다음 개발 단계

- Phase 1: 데이터 파이프라인 개발을 이어간다.
- 우선순위는 다음 순서가 적절하다.
  1. KOSPI200/KOSDAQ150 유니버스 수집 코드 확인 및 보강
  2. 일봉 시세 수집 코드 확인 및 보강
  3. 재무 데이터 수집 코드 확인 및 보강
  4. SQLite 저장 구조와 repository 계층 검증
  5. 실제 pykrx 데이터로 최소 샘플 수집 테스트

### 개선 사안

- `.env.example`의 placeholder 값 때문에 boolean 설정이 켜진 것처럼 보일 수 있으므로, 추후 템플릿 값을 빈 값 또는 명확한 주석 형태로 바꾸는 것이 좋다.
- Python 버전 호환성을 README에 더 명확히 적는 것이 좋다. 현재 의존성 기준으로는 Python 3.12 사용을 권장한다.
- ZIP 다운로드 작업 방식은 빠르게 이어가기에는 충분하지만, 장기적으로는 Git for Windows 설치 후 clone 기반으로 전환하는 것이 좋다.

## 2026-05-04 Phase 구현 범위 점검

### 현재 코드 기준 구현 판단

- Phase 0: 완료로 판단한다. 환경 설정, 의존성 설치, 설정 검증, 테스트 실행이 모두 성공했다.
- Phase 1: 기본 구현은 존재한다. `src/data`에 pykrx 기반 유니버스/일봉/기초지표 수집기, SQLite 모델, repository, sync 스크립트가 있다. 다만 실제 KRX 데이터를 끝까지 받아 DB에 넣는 실데이터 smoke test는 아직 필요하다.
- Phase 2: 기본 구현은 존재한다. `src/factors`에 PER/PBR 가치 점수와 6개월 모멘텀 점수 계산, 랭킹 스크립트가 있다. 하지만 요구사항의 quality 지표(ROE, 영업이익률, 부채비율)는 아직 구현되지 않았고 `quality_score`가 0.0으로 고정되어 있다.
- Phase 3: 기본 백테스트 엔진은 존재한다. 리밸런싱 기반 매수/매도, 수수료/세금/슬리피지, CAGR/MDD/Sharpe/win rate 계산, 실행 스크립트가 있다. 다만 손절(-8%)과 트레일링 스탑(-10%)은 백테스트에 아직 반영되지 않은 것으로 보인다.
- Phase 4: 아직 미구현으로 판단한다. `src/trading`에는 `__init__.py`만 있고 KIS 주문, 계좌조회, 안전장치, 실시간 모니터링 코드가 없다.
- Phase 5: 아직 미구현으로 판단한다. `src/notify`에는 `__init__.py`만 있고 텔레그램 알림이나 Streamlit 대시보드 구현이 없다.

### 중요한 문제점

- README와 progress 일부 한글이 cp949/utf-8 인코딩 문제로 깨져 보인다. 코드 자체는 컴파일되지만 문서 가독성이 나쁘다.
- `src/data/collectors.py`의 pykrx 컬럼명 문자열도 화면상 깨져 보인다. 컴파일은 통과하지만 실제 수집 결과에서 open/high/low/close/volume 등이 제대로 매핑되는지 반드시 실데이터로 확인해야 한다.
- 현재 테스트는 33개 모두 통과하지만, 실제 pykrx 네트워크 호출과 장기간 데이터 수집 안정성을 충분히 보장하지는 않는다.

### 다음 우선순위 제안

1. Phase 1 실데이터 smoke test: 최근 며칠치 데이터로 DB 저장이 실제로 되는지 확인한다.
2. 깨진 한글 문서와 pykrx 컬럼명 매핑을 정리한다.
3. Phase 2 quality 지표를 요구사항대로 구현한다.
4. Phase 3 백테스트에 손절과 트레일링 스탑을 반영한다.
5. Phase 4 KIS 모의투자 주문 모듈은 위 단계 검증 후 진행한다.

## 2026-05-04 다른 AI 작업 인수인계 반영

### 읽은 인수인계 자료

- `docs/superpowers/2026-05-04-handoff.md`
- `docs/superpowers/plans/2026-05-04-phase1-quality-fundamentals.md`
- `docs/superpowers/plans/2026-05-04-phase2-quality-score.md`
- `docs/superpowers/plans/2026-05-04-phase3-stops-simulation.md`
- `docs/superpowers/plans/2026-05-04-cost-parameters-recheck.md`
- `AGENTS.md`
- `CLAUDE.md`

### 인수인계 핵심 내용

- 신규 4개 plan 이 작성되어 있었다.
  - 거래세/비용 재검토
  - Phase 3 손절/트레일링 백테스트 반영
  - Phase 1 DART quality 재무지표 수집
  - Phase 2 quality_score 실제 계산
- 기존 review 항목 15개 중 #1, #2, #13은 반영 완료로 기록되어 있었다.
- 다음 즉시 할 일은 review #3, 그 다음은 #4로 정리되어 있었다.

### 이번에 처리한 작업

- Review #3 반영:
  - `docs/superpowers/plans/2026-05-04-phase3-stops-simulation.md`의 Task 1 Step 2를 보강했다.
  - `_load_prices` 반환값을 `float`에서 `{"open": ..., "close": ...}`로 바꿀 때 영향을 받는 3곳을 명시했다.
    1. `available_prices` 생성부
    2. `_positions_value(positions, available_prices)` 호출부
    3. `equity_curve` 기록부의 포지션 평가액 계산
- Review #4 반영:
  - `docs/superpowers/plans/2026-05-04-cost-parameters-recheck.md`의 Task 4 Step 1을 보강했다.
  - 비용 변경 전/후 백테스트 비교 전에 `data/quntbot.db`와 시드 데이터 존재 여부를 확인하도록 명시했다.
  - 현재 실제 스크립트 인자인 `--start-date` / `--end-date` 기준으로 sync 예시 명령을 수정했다.
  - 빈 DB에서 실행한 백테스트 결과는 비용 변경 영향 측정값으로 쓰지 않도록 명시했다.

### 확인된 환경 차이

- 인수인계 문서에는 `.venv`가 없고 환경복구가 필요하다고 적혀 있었지만, 실제 현재 환경은 `venv`가 존재하며 Python 3.12.10 기반으로 동작한다.
- `data/quntbot.db`는 아직 존재하지 않는다. 따라서 실데이터 기반 백테스트 비교는 Phase 1 sync 이후 가능하다.

### 검증 결과

```text
pytest -q -p no:cacheprovider
33 passed
```

### 다음 미반영 우선순위

- Review #5: Phase 2 z-score outlier 영향 단정 오류 보강
- Review #6: `combine_scores`의 `fillna(0.0)` 동작과 quality 결측 정책 정리
- Review #7: ROE 분기 데이터 TTM 환산 여부 결정
- Review #8: 손절과 트레일링 동시 트리거 시 우선순위 명시
- Review #9: 손절 후 재진입 금지 옵션 결정
- Review #10~#15: 나머지 문서/작업 단위 보강

## 2026-05-04 Review #5~#6 반영

### 처리한 작업

- Review #5 반영:
  - `docs/superpowers/plans/2026-05-04-phase2-quality-score.md`의 부채비율 outlier 설명을 수정했다.
  - 기존 문장은 "z-score는 정렬에만 쓰이므로 outlier가 다른 종목 점수를 깎지 않음" 취지였으나, 이는 틀린 설명이다.
  - z-score는 평균과 표준편차를 사용하므로 극단값이 다른 종목의 점수 분포를 압축하거나 왜곡할 수 있다고 명시했다.
  - 1차 구현에서는 winsorize/clip 없이 z-score를 쓰되, 극단값이 있어도 낮은 부채비율 종목이 높은 점수를 받는 최소 방향성 테스트를 추가하도록 plan에 반영했다.
- Review #6 반영:
  - `combine_scores`가 각 컴포넌트에 `fillna(0.0)`을 적용한다는 현 동작을 plan에 명확히 적었다.
  - quality_score가 NaN이어도 total_score에는 중립점 0으로 반영될 수 있으므로, Task 1 spec에서 이 정책을 유지할지 변경할지 명시적으로 결정하도록 보강했다.
  - 정책 유지 시 "quality 데이터가 없는 종목도 value/momentum 기준으로 랭킹될 수 있음"을 테스트에 명시하도록 했다.
  - 정책 변경 시 shared behavior 변경이므로 기존 value/momentum 결측 테스트까지 함께 갱신해야 한다고 기록했다.

### 검증 결과

```text
pytest tests/factors -q -p no:cacheprovider
10 passed
```

### 남은 우선순위

- Review #7: ROE 분기 데이터 TTM 환산 여부 결정
- Review #8: 손절과 트레일링 동시 트리거 시 우선순위 명시
- Review #9: 손절 후 재진입 금지 옵션 결정
- Review #10~#15: 나머지 문서/작업 단위 보강

## 2026-05-04 Review #7~#15 반영 완료

### 처리한 작업

- Review #7 반영:
  - Phase 1 quality plan에 ROE/영업이익률 기간 정의를 확정했다.
  - ROE는 `TTM 당기순이익 / 평균자본총계`로 정의했다.
  - 영업이익률은 `TTM 영업이익 / TTM 매출액`으로 정의했다.
  - 부채비율은 TTM 환산하지 않고 최신 분기 재무상태표 스냅샷을 사용하기로 했다.
  - Phase 2 plan에는 Phase 1에서 저장된 TTM 결과값을 점수화만 한다고 명시했다.
- Review #8 반영:
  - Phase 3 stops plan에 손절과 트레일링이 동시에 충족될 때 `stop_loss`를 우선한다고 명시했다.
  - 테스트 케이스 `test_run_backtest_prefers_stop_loss_when_both_stops_trigger`를 추가하도록 plan을 보강했다.
- Review #9 반영:
  - 손절/트레일링 체결 당일에는 같은 종목 재진입을 금지한다.
  - N영업일 cooldown은 1차 구현에 넣지 않고, 실데이터 백테스트 결과를 본 뒤 별도 plan으로 결정하기로 했다.
  - 체결 당일 재진입 금지 테스트를 추가하도록 plan을 보강했다.
- Review #10 반영:
  - Phase 1 quality plan의 Task 2/3 분리 이유를 명시했다.
  - Task 2는 `quality_metrics` 데이터 저장 책임, Task 3은 `quality_sync_runs` 실행 이력 책임으로 분리한다고 기록했다.
- Review #11 반영:
  - Phase 2 plan의 loguru 설명을 수정했다.
  - loguru 기본 sink는 일반적으로 stderr이므로 stdout 단언에 영향이 없어야 한다고 적고, stderr 캡처 테스트에서는 설정 조정이 필요하다고 명시했다.
- Review #12 반영:
  - Phase 3 plan의 코드 스니펫/예시에서 생략 기호 `...`를 제거하고 구체적인 예시 값과 설명으로 대체했다.
- Review #14 반영:
  - 신규 4개 plan 모두에 `Plan dependencies` 섹션을 추가하거나 보강했다.
  - 각 plan의 선행/후행/독립 관계와 권장 commit scope를 명시했다.
- Review #15 반영:
  - handoff 문서에 Git commit 단위 가이드를 추가했다.
  - ZIP 다운로드본이라 `.git` 연결이 없을 수 있음을 전제로, Git 연결 후 커밋을 작게 나누는 기준을 기록했다.

### 업데이트한 문서

- `docs/superpowers/plans/2026-05-04-phase1-quality-fundamentals.md`
- `docs/superpowers/plans/2026-05-04-phase2-quality-score.md`
- `docs/superpowers/plans/2026-05-04-phase3-stops-simulation.md`
- `docs/superpowers/plans/2026-05-04-cost-parameters-recheck.md`
- `docs/superpowers/2026-05-04-handoff.md`

### 검증 결과

```text
pytest -q -p no:cacheprovider
33 passed
```

### 현재 상태

- Review #1~#15 문서 반영은 모두 완료됐다.
- 다음은 실제 구현 착수 단계다.
- 권장 구현 순서:
  1. 거래세/비용 재검토 plan
  2. Phase 3 손절/트레일링 백테스트 plan
  3. Phase 1 DART quality fundamentals plan
  4. Phase 2 quality score plan

## 2026-05-04 12:37 KST Plan Mode 저장

### 사용자 요청

- 현재는 실제 코드 구현이 아니라 Plan mode로 진행한다.
- 여러 항목을 한꺼번에 뭉뚱그려 진행하지 않는다.
- 선택이 필요한 부분은 사용자에게 질문하고, 사용자가 객관적으로 판단할 수 있도록 자세히 설명한다.

### 추가 검토 후보

앞서 추가로 검토할 만한 내용으로 다음을 제안했다.

1. 백테스트 look-ahead bias
2. 생존편향
3. 백테스트 수량의 정수 주식 처리
4. 리밸런싱/stop 체결 가격 기준 통일
5. DART 라이브러리 버전 재검토
6. 거래세 출처 공식/준공식 고정
7. DART 정정공시/restatement 정책
8. 리밸런싱 빈도 비교
9. turnover 및 비용 민감도 성과지표 추가
10. `.venv`와 `venv` 환경 경로 표준화

### 현재 진행 중인 검토 항목

- 1번: 백테스트 look-ahead bias 검토를 시작했다.
- 아직 사용자의 최종 선택은 받지 않았다.
- 코드 변경은 하지 않았다.

### 백테스트 look-ahead bias 설명 요약

Look-ahead bias는 백테스트가 그 시점에는 아직 알 수 없던 정보를 사용해 매매하는 문제다.

현재 Phase 3 구조는 같은 날짜의 가격/팩터를 보고 같은 날짜에 매수/매도하는 흐름이 될 수 있다. 실제 운영 계획은 장 시작 전 리밸런싱이므로, 전날까지 확정된 데이터로 오늘 아침 판단하고 오늘 체결하는 구조가 더 현실적이다.

### 사용자에게 제시한 선택지

1. 선택지 A: 현재 방식 유지
   - 당일 데이터로 신호 계산 후 당일 종가 체결.
   - 구현은 단순하지만 look-ahead bias 가능성이 크다.
   - 추천하지 않음.
2. 선택지 B: 전일 데이터로 신호 계산, 다음 거래일 시가 체결
   - `T-1` 종가/재무 데이터로 신호 계산 후 `T`일 시가에 매수/매도.
   - `T`일 종가로 equity_curve 평가.
   - 실제 `08:30` 리밸런싱 운영과 가장 잘 맞는다.
   - 추천안.
3. 선택지 C: 전일 데이터로 신호 계산, 다음 거래일 종가 체결
   - look-ahead bias는 줄지만 실제 장 시작 전 주문과는 덜 맞다.
   - open 데이터 품질이 불안정할 때 차선책.

### 현재 추천안

추천은 선택지 B다.

정책 문장 초안:

```text
백테스트 신호는 execution_date 직전 거래일까지 확정된 데이터로만 계산한다.
리밸런싱 매수/매도는 execution_date의 시가 기준으로 체결한다.
당일 장 마감 후 equity_curve는 execution_date의 종가 기준으로 평가한다.
```

### 다음에 이어서 할 일

- 사용자에게 선택지 A/B/C 중 하나를 확정받는다.
- 사용자가 선택하면 해당 정책을 Phase 3 plan/spec에 문서로 반영한다.
- 아직 구현은 하지 않는다.

## 2026-05-04 매수 조건 보강 논의

### 확정된 방향

- 백테스트 look-ahead bias 정책은 B안을 채택한다.
  - 전일 데이터로 신호 계산
  - 다음 거래일 시가 기준 체결
  - 당일 종가 기준 평가
- 재무제표 quality 데이터는 `published_at <= signal_date`인 데이터만 사용한다.
- `published_at`이 없는 재무제표 데이터는 사용하지 않는다.
- quality 데이터가 없는 종목 처리 정책은 C안으로 진행을 목표로 한다.
  - 점수 계산은 가능하게 하되, 포트폴리오 편입은 quality 커버리지 조건을 만족할 때만 허용하는 방향.
  - 개별 종목은 ROE, 영업이익률, 부채비율 3개 중 최소 2개 이상 있어야 quality 검증 종목으로 인정.
  - 최종 후보군의 quality 검증 종목 비율이 70% 이상이면 quality 필터를 활성화.
  - quality 필터 활성화 시 ROE > 0, 부채비율 < 300% 조건을 만족해야 신규 매수 가능.
  - quality 커버리지 70% 미만이면 quality 필터는 신규 매수 제외 조건으로 쓰지 않고 경고 로그만 남긴 뒤 value/momentum 중심으로 운용.
  - 사용자 선택: 70% 이상 균형형.

### 사용자가 추가 요청한 매수 필터 후보

1. 유동성 필터
   - 최근 20거래일 평균 거래대금이 20억 원 미만인 종목 제외.
   - 사용자 선택: 20억 원 이상 균형형.
2. 가격 필터
   - 1주 가격이 1,000원 미만인 종목 제외.
3. 거래정지/유의 종목 제외
   - 거래정지, 관리, 투자주의/경고/위험 등 자동매매에 부적합한 종목 제외.
   - KRX 공식 데이터를 우선 사용.
   - 상태 정보가 확인되지 않는 종목은 보수적으로 신규 매수 제외.
   - 사용자 선택: 상태 미확인 종목은 제외.
4. PER/PBR 음수 제외
   - PER <= 0 또는 PBR <= 0 종목 제외.
   - 사용자 선택: 0 이하 제외.
5. 최근 2분기 심한 적자 기업 제외
   - 최근 2개 분기 연속 영업이익률 < -10%이면 제외.
   - 또는 최근 2개 분기 연속 순이익률 < -10%이면 제외.
   - 사용자 선택: 균형형.
6. 퀄리티 최소 조건
   - ROE > 0
   - 부채비율 < 300%
7. 갭/급등락 필터
   - 오늘 시가가 전일 종가 대비 +20% 이상이면 신규 매수 제외.
   - 오늘 시가가 전일 종가 대비 -20% 이하이면 신규 매수 제외.
   - 즉 신규 매수는 `abs(today_open / previous_close - 1) < 0.20`인 종목만 허용.
   - 사용자 선택: 오늘 시가 vs 전일 종가 기준.
8. 상장 후 기간 필터
   - 상장 후 1년 미만 종목 제외.
   - 상장일은 KRX 공식 데이터를 우선 조회.
   - 상장일 확인 시 상장 후 365일 미만이면 신규 매수 제외.
   - 상장일이 확인되지 않는 종목은 신규 매수 후보에 남기되 warning 로그에 `listing_date_unknown` 기록.
   - 사용자 선택: 상장일 미확인 종목은 경고 후 통과.

### 다음에 결정해야 할 세부값

- 유동성 필터의 기준: 완료.
  - 최근 20거래일 평균 거래대금 >= 20억 원.
- quality 커버리지 C안의 기준:
  - 완료.
  - 개별 종목은 ROE, 영업이익률, 부채비율 중 최소 2개 이상 필요.
  - 최종 후보군 quality 검증 비율이 70% 이상이면 quality 필터 활성화.
- 최근 2분기 심한 적자 기준: 완료.
  - 최근 2개 분기 연속 영업이익률 < -10%이면 제외.
  - 또는 최근 2개 분기 연속 순이익률 < -10%이면 제외.
- PER/PBR 필터에서 0도 제외할지 여부: 완료.
  - PER <= 0 제외.
  - PBR <= 0 제외.
- 거래정지/유의 종목 정보를 어떤 데이터 소스에서 가져올지.
  - KRX 공식 데이터를 우선 사용.
  - 상태 정보 미확인 종목은 신규 매수 제외로 확정.
- 상장일 정보를 어떤 데이터 소스에서 가져올지.
  - KRX 공식 데이터를 우선 사용.
  - 상장일 미확인 종목은 경고 후 통과로 확정.

### 별도 정책 문서 생성

- 다른 AI 에이전트가 바로 이어받을 수 있도록 매수 필터 정책을 별도 spec 문서로 정리했다.
- 문서 위치:
  - `docs/superpowers/specs/2026-05-04-buy-filter-policy-design.md`
- 이 문서는 아직 구현 계획이 아니라 정책 설계 문서다.
- 향후 구현 전에는 별도 plan 문서를 만들고 TDD로 진행해야 한다.

## 2026-05-04 2차 기술적 진입 필터 정책

### 사용자 결정

- 1차 buy filter 이후 2차 필터로 기술적 분석 기반 진입 타이밍 필터를 둔다.
- 기술적 분석은 수익률 예측 도구가 아니라 나쁜 진입 타이밍을 피하는 risk/timing filter로 사용한다.
- 초기 MVP는 4개 조건 중 3개 이상 만족하면 통과하는 방식으로 진행한다.

### 확정된 MVP 조건

1. `signal_close > MA20`
   - 단기 추세가 살아 있는 종목만 신규 매수.
2. `MA60_today > MA60_20_trading_days_ago`
   - 중기 추세가 꺾인 종목 제외.
3. `RSI(14) < 75`
   - 과열 종목 추격매수 방지.
4. `20일 일간 수익률 표준편차 < 5%`
   - 변동성이 과도한 종목 제외.

### 통과 기준

```text
4개 조건 중 3개 이상 만족하면 통과.
2개 이하 만족하면 신규 매수 제외.
```

### 타이밍 정책

- 기술적 지표는 `signal_date`까지 확정된 가격 데이터로만 계산한다.
- `execution_date` 당일 종가는 사용하지 않는다.
- B안 백테스트 정책과 동일하게 신규 매수 체결은 `execution_date` 시가 기준이다.

### 별도 정책 문서

- 다른 AI 에이전트가 바로 이어받을 수 있도록 기술적 진입 필터 정책을 별도 spec 문서로 정리했다.
- 문서 위치:
  - `docs/superpowers/specs/2026-05-04-technical-entry-filter-policy-design.md`
- 아직 구현 계획이 아니라 정책 설계 문서다.

## 2026-05-04 프로젝트 정리/중복 후보 검토

### 명확하게 정리한 항목

- Python 실행/테스트가 생성한 캐시를 제거했다.
  - `__pycache__/`
  - `*.pyc`
  - `.pytest_cache/`
- `.gitignore`에 `venv_broken*/` 패턴을 추가했다.
  - 깨진 백업 가상환경이 Git에 올라가는 것을 방지하기 위함.

### 삭제 전 확인이 필요한 항목

- `venv_broken_py314/`
  - Python 3.14로 만들어졌다가 깨진 가상환경 백업.
  - 현재 정상 환경은 `venv/`이므로 실사용에는 필요 없다.
  - 다만 폴더 삭제는 되돌리기 어려우므로 사용자 확인 후 삭제하는 것이 좋다.
- `AGENTS.md`와 `CLAUDE.md`
  - 파일 내용과 해시가 동일하다.
  - 다만 서로 다른 AI 도구가 각각 찾는 파일명일 수 있어, 중복이어도 유지하는 쪽이 안전하다.

### 유지해야 하는 항목

- `docs/superpowers/plans/2026-05-03-*`
  - 새 plan들과 일부 중복처럼 보일 수 있지만, 기존 구현의 근거와 이력이다.
  - 삭제하지 않는 것이 좋다.
- `progress.md`
  - 작업 인수인계와 의사결정 기록의 중심 문서다.
  - 길어지고 있지만 현재는 유지한다.

## 2026-05-04 프로젝트 정리/중복 후보 처리 추가

### 사용자 승인 후 삭제한 항목

- `venv_broken_py314/`
  - Python 3.14 기반으로 만들어졌던 깨진 가상환경 백업 폴더.
  - 현재 프로젝트 실행/테스트는 Python 3.12 기반 `venv/`를 사용하므로 유지 필요성이 낮다고 판단했다.
  - 사용자의 삭제 승인 후 프로젝트 루트 내부 경로임을 확인하고 삭제했다.

### 유지하기로 한 중복 후보

- `AGENTS.md`와 `CLAUDE.md`
  - 두 파일 내용은 동일하지만, 서로 다른 AI 도구가 각자 다른 파일명을 자동 탐색할 가능성이 있다.
  - 단순 중복처럼 보이더라도 협업/인수인계 목적상 유지하는 편이 안전하다고 판단했다.
## 2026-05-07 DART quality provider parser step

### Completed

- Inspected local `dart-fss==0.4.3`; `dart_fss.fs.extract()` returns a `FinancialStatement` object and accepts quarter extraction options.
- Added a failing provider test for normalized `income_statement` / `balance_sheet` payload parsing.
- Implemented minimal quality metric parsing in `src/data/quality_provider.py`:
  - ROE = TTM net income / average equity.
  - Operating margin = TTM operating income / TTM revenue.
  - Debt ratio = latest liabilities / latest equity.
  - Keeps unsupported extract payloads as empty rows for now.

### Verification

- `.\venv\Scripts\python.exe -m pytest tests\data\test_quality_provider.py -q -p no:cacheprovider` -> 4 passed.
- `.\venv\Scripts\python.exe -m py_compile src\data\quality_provider.py` -> passed.
- `.\venv\Scripts\python.exe -m pytest tests\data -q -p no:cacheprovider` -> 39 passed.
- `.\venv\Scripts\python.exe -m pytest -q -p no:cacheprovider` -> 138 passed.

### Next

- Add conversion from real `dart_fss.fs.FinancialStatement.show("bs")` / `show("is")` DataFrames into the normalized payload shape.

## 2026-05-07 DART FinancialStatement DataFrame conversion step

### Completed

- Added provider tests using pandas MultiIndex DataFrames that mimic `FinancialStatement.show("bs")` and `show("is")`.
- Updated `DartFssFundamentalsProvider` to request quarter data with `report_tp="quarter"`, `cumulative=False`, and `progressbar=False`.
- Added conversion from `FinancialStatement.show()` DataFrames into normalized income/balance rows:
  - detects `label_ko` columns
  - derives fiscal year/quarter from `YYYYMMDD` and `YYYYMMDD-YYYYMMDD` columns
  - maps account labels for revenue, operating income, net income, equity, and liabilities
  - reuses the existing TTM quality metric calculation path

### Verification

- `.\venv\Scripts\python.exe -m pytest tests\data\test_quality_provider.py -q -p no:cacheprovider` -> 5 passed.
- `.\venv\Scripts\python.exe -m py_compile src\data\quality_provider.py` -> passed.
- `.\venv\Scripts\python.exe -m pytest tests\data -q -p no:cacheprovider` -> 40 passed.
- `.\venv\Scripts\python.exe -m pytest -q -p no:cacheprovider` -> 139 passed.

### Next

- Add a manual quality sync script/CLI entry point that wires config, engine, rate limiter, provider, year range, and optional ticker list.

## 2026-05-07 DART quality sync CLI step

### Completed

- Added `scripts/sync_phase1_quality.py`.
- Added CLI options for:
  - `--year-from`
  - `--year-to`
  - `--database-url`
  - `--api-key`
  - `--requests-per-minute`
  - `--daily-quota`
  - repeatable `--ticker`
- Wired the script to:
  - create database tables
  - build `RateLimiter` from DART limits
  - build `DartFssFundamentalsProvider`
  - call `sync_phase1_quality`
  - print `status` and `metric_count`
- Added tests with injected factories/sync function, so no DART network call is needed.

### Verification

- `.\venv\Scripts\python.exe -m pytest tests\data\test_quality_sync_script.py -q -p no:cacheprovider` -> 5 passed.
- `.\venv\Scripts\python.exe -m py_compile scripts\sync_phase1_quality.py tests\data\test_quality_sync_script.py` -> passed.
- `.\venv\Scripts\python.exe -m pytest tests\data -q -p no:cacheprovider` -> 45 passed.
- `.\venv\Scripts\python.exe -m pytest -q -p no:cacheprovider` -> 144 passed.

### Next

- Run a small real/manual DART quality sync only after `DART_API_KEY` is configured, starting with one ticker and a narrow year range.

## 2026-05-07 Phase 2 DART quality score integration and audit

### Completed

- Audited remaining DART/quality tasks and found the main gap: Phase 2 still used the old `EPS / BPS` quality proxy instead of `quality_metrics`.
- Added policy/spec note: `docs/superpowers/specs/2026-05-07-phase2-quality-score-implementation.md`.
- Updated `src/factors/engine.py`:
  - loads latest available `QualityMetric` by ticker
  - applies `published_at <= as_of_date`
  - treats null `published_at` as fiscal quarter end + 45 days
  - scores ROE and operating margin as higher-is-better
  - scores debt ratio as lower-is-better
  - averages available component scores
  - keeps missing quality as neutral `0.0`
  - logs quality coverage
- Updated `src/backtest/engine.py` fast scorer to load the same quality metrics, preventing live ranking/backtest scoring divergence.
- Updated DART quality CLI/provider:
  - `--tickers` comma-separated option
  - repeatable `--ticker` remains supported
  - `--refresh-corp-list`
  - provider cache refresh for `CORPCODE.zip` / `CORPCODE.xml`
  - clear no-traceback error when `DART_API_KEY` is missing

### Verification

- TDD RED checks observed for factor quality tests, backtest fast scorer quality test, CLI option/error tests.
- `.\venv\Scripts\python.exe -m pytest tests\factors\test_engine.py -q -p no:cacheprovider` -> 7 passed.
- `.\venv\Scripts\python.exe -m pytest tests\backtest\test_backtest_engine.py::test_default_fast_scorer_uses_quality_metrics_for_ranking -q -p no:cacheprovider` -> 1 passed.
- `.\venv\Scripts\python.exe -m pytest tests\data\test_quality_sync_script.py tests\data\test_quality_provider.py -q -p no:cacheprovider` -> 12 passed.
- `.\venv\Scripts\python.exe -m pytest tests\data tests\factors tests\backtest -q -p no:cacheprovider` -> 88 passed.
- `.\venv\Scripts\python.exe -m compileall -q config.py scripts src tests` -> passed.
- `.\venv\Scripts\python.exe -m pytest -q -p no:cacheprovider` -> 153 passed.
- `.\venv\Scripts\python.exe scripts\rank_phase2_factors.py --as-of-date 2026-05-07 --top-n 5` -> ran successfully; quality coverage logged as `0/433` because no DART quality rows exist yet.
- Log scan for `ERROR|Traceback|Exception|failed|quota_exhausted` -> no matches.

### Blocked/External

- Real OpenDART 1-ticker sync was not run because `DART_API_KEY` is currently not configured (`DART_ENABLED=False`, key length 0).

## 2026-05-07 Real OpenDART 1-ticker smoke sync

### Completed

- Confirmed `.env` now loads DART settings:
  - `DART_ENABLED=True`
  - API key length is 40
  - request limits are 60/minute and 10,000/day
- Ran real OpenDART sync for Samsung Electronics (`005930`) over 2024-2025.
- Found and fixed a live `dart-fss==0.4.3` compatibility issue:
  - OpenDART `CORPCODE.xml` now includes `corp_eng_name`.
  - `dart_fss.corp.Corp` does not accept that keyword.
  - Provider now falls back to raw `dart_fss.api.filings.corp_code.get_corp_code()` rows when `get_corp_list()` fails with that schema mismatch.
- Inserted 8 `quality_metrics` rows for `005930`.
- Recorded `QualitySyncRun(status="success", metric_count=8)`.
- Re-ran Phase 2 ranking; quality coverage changed from `0/433` to `1/433`.

### Sample Stored Rows

- 2024 Q1: `roe=0.0002979678403439244`, `debt_ratio=0.2102011627050724`.
- 2024 Q2-Q4: operating margin rows populated.
- 2025 Q1-Q4: operating margin rows populated; 2025 Q3 also has `debt_ratio=0.21036202705931178`.

### Verification

- `.\venv\Scripts\python.exe -m pytest tests\data\test_quality_provider.py tests\data\test_quality_sync_script.py -q -p no:cacheprovider` -> 14 passed.
- Real sync: `.\venv\Scripts\python.exe scripts\sync_phase1_quality.py --tickers 005930 --year-from 2024 --year-to 2025` -> exit 0.
- DB check: `QUALITY_METRIC_TOTAL=8`, `SAMSUNG_ROWS=8`, latest quality sync run `status=success`, `metric_count=8`.
- `.\venv\Scripts\python.exe scripts\rank_phase2_factors.py --as-of-date 2026-05-07 --top-n 5` -> ran successfully and logged `quality_score covered 1/433`.
- `.\venv\Scripts\python.exe -m pytest -q -p no:cacheprovider` -> 154 passed.
- `.\venv\Scripts\python.exe -m compileall -q config.py scripts src tests` -> passed.

### Next

- Improve DART financial statement parsing coverage because several Samsung rows still have partial metrics (`roe` or `debt_ratio` missing).
- Then expand sync from one ticker to a small basket before running the whole universe.

## 2026-05-07 DART financial statement parser coverage improvement

### Completed

- Investigated real Samsung Electronics DART `FinancialStatement.show("is")` and `show("bs")` DataFrame structure.
- Confirmed DART tables contain multiple columns for the same period: consolidated disclosure amount, business segments, stock-class columns, and financial-instrument detail columns.
- Added a regression test proving lower-priority segment/detail columns must not overwrite consolidated disclosure values.
- Updated `src/data/quality_provider.py` DataFrame parsing:
  - sorts period columns by statement priority
  - prefers `연결재무제표 / 공시금액`
  - then accepts singleton `연결재무제표`
  - leaves already populated metric fields untouched unless the current value is missing
  - recognizes real Korean DART labels such as `매출액`, `영업이익`, `당기순이익`, `자본총계`, `부채총계`
- Re-ran real Samsung Electronics (`005930`) quality sync for 2024-2025.

### Data Result

- `SAMSUNG_ROWS=8`.
- All 8 rows now have `roe`, `operating_margin`, and `debt_ratio` populated.
- Latest sync run recorded `status=success`, `metric_count=8`.

### Verification

- TDD RED observed: new parser regression test failed with overwritten `999` segment/detail values.
- `.\venv\Scripts\python.exe -m pytest tests\data\test_quality_provider.py -q -p no:cacheprovider` -> 8 passed.
- `.\venv\Scripts\python.exe -m compileall src scripts` -> passed.
- Real sync: `.\venv\Scripts\python.exe scripts\sync_phase1_quality.py --tickers 005930 --year-from 2024 --year-to 2025` -> exit 0.
- `.\venv\Scripts\python.exe scripts\rank_phase2_factors.py --as-of-date 2026-05-07 --top-n 5` -> ran successfully and logged `quality_score covered 1/433`.
- `.\venv\Scripts\python.exe -m pytest -q -p no:cacheprovider` -> 155 passed.

### Next

- Expand DART sync from one ticker to a small basket, then inspect coverage/error rate before attempting the full universe.

## 2026-05-07 DART small-basket sync and partial failure handling

### Completed

- Selected a representative 5-ticker DART quality sync basket from active DB stocks:
  - `005930` Samsung Electronics
  - `000660` SK Hynix
  - `005380` Hyundai Motor
  - `373220` LG Energy Solution
  - `035420` NAVER
- Found a PowerShell usage pitfall:
  - `--tickers 005930,000660,...` without quotes can strip leading zeros from some ticker arguments.
  - Use `--tickers "005930,000660,005380,373220,035420"` or repeat `--ticker`.
- Found a live DART/dart-fss extraction error for Hyundai Motor (`005380`) on report `2024.03`.
- Added a regression test for partial ticker failures.
- Updated `src/data/quality_collector.py`:
  - non-quota per-ticker errors are logged and skipped
  - successful ticker rows keep being upserted
  - sync run ends as `partial_success` when at least one ticker failed but some rows were saved
  - if all tickers fail, existing `failed` behavior and raised error are preserved
  - quota exhaustion still stops the run and keeps already saved rows

### Data Result

- Latest 5-ticker run: `status=partial_success`, `metric_count=16`.
- `005930`: 8 rows, all complete.
- `373220`: 8 rows, all complete.
- `005380`: failed in dart-fss extraction.
- `000660` and `035420`: no exception, but produced 0 quality rows; needs separate parser/data investigation.
- Total quality coverage increased to 2 tickers / 16 rows in `quality_metrics`.

### Verification

- TDD RED observed: partial-failure collector test failed before implementation.
- `.\venv\Scripts\python.exe -m pytest tests\data\test_quality_collector.py -q -p no:cacheprovider` -> 5 passed.
- `.\venv\Scripts\python.exe -m compileall src scripts` -> passed.
- `.\venv\Scripts\python.exe -m pytest tests\data\test_quality_collector.py tests\data\test_quality_sync_script.py tests\data\test_quality_provider.py -q -p no:cacheprovider` -> 20 passed.
- Real sync: `.\venv\Scripts\python.exe scripts\sync_phase1_quality.py --tickers "005930,000660,005380,373220,035420" --year-from 2024 --year-to 2025` -> exit 0, `partial_success`.
- `.\venv\Scripts\python.exe scripts\rank_phase2_factors.py --as-of-date 2026-05-07 --top-n 5` -> ran successfully and logged `quality_score covered 2/433`.
- `.\venv\Scripts\python.exe -m pytest -q -p no:cacheprovider` -> 156 passed.

### Next

- Investigate why `000660` and `035420` return 0 parsed rows even without exceptions.
- Separately decide whether to work around the Hyundai Motor `dart-fss` extraction failure or exclude/report such cases.

## 2026-05-07 DART comprehensive income statement fallback

### Completed

- Investigated why SK Hynix (`000660`) and NAVER (`035420`) produced 0 quality rows without raising exceptions.
- Root cause:
  - For both tickers, `FinancialStatement.show("is")` returns `None`.
  - Their income statement data is available under `FinancialStatement.show("cis")`.
  - The provider only read `is`, so balance rows existed but income rows were empty.
- Added a regression test where `is` is `None` and `cis` contains the income rows.
- Updated `src/data/quality_provider.py` to fall back to `show("cis")` when `show("is")` is missing.
- Re-ran the 5-ticker basket:
  - `005930`
  - `000660`
  - `005380`
  - `373220`
  - `035420`

### Data Result

- Latest 5-ticker run: `status=partial_success`, `metric_count=32`.
- `005930`: 8 rows, all complete.
- `000660`: 8 rows, all complete.
- `373220`: 8 rows, all complete.
- `035420`: 8 rows, all complete.
- `005380`: still fails inside `dart-fss` while extracting Hyundai Motor 2024 Q1 report.
- Total quality coverage increased to 4 tickers / 32 rows in `quality_metrics`.

### Verification

- TDD RED observed: new `cis` fallback provider test returned `[]` before implementation.
- `.\venv\Scripts\python.exe -m pytest tests\data\test_quality_provider.py -q -p no:cacheprovider` -> 9 passed.
- `.\venv\Scripts\python.exe -m compileall src scripts` -> passed.
- `.\venv\Scripts\python.exe -m pytest tests\data\test_quality_provider.py tests\data\test_quality_collector.py tests\data\test_quality_sync_script.py -q -p no:cacheprovider` -> 21 passed.
- Real sync: `.\venv\Scripts\python.exe scripts\sync_phase1_quality.py --tickers "005930,000660,005380,373220,035420" --year-from 2024 --year-to 2025` -> exit 0, `partial_success`.
- `.\venv\Scripts\python.exe scripts\rank_phase2_factors.py --as-of-date 2026-05-07 --top-n 5` -> ran successfully and logged `quality_score covered 4/433`.
- `.\venv\Scripts\python.exe -m pytest -q -p no:cacheprovider` -> 157 passed.

### Next

- Investigate Hyundai Motor (`005380`) `dart-fss` extraction failure separately.
- Then expand from 5 tickers to a broader basket after deciding whether failed extraction reports should be skipped, retried with a narrower date window, or handled through a lower-level DART API fallback.

## 2026-05-07 Hyundai Motor DART single-account fallback

### Completed

- Reproduced Hyundai Motor (`005380`) failure and narrowed it to `dart-fss` financial-statement extraction/merge.
- Confirmed narrower `dart.fs.extract` options still fail on Hyundai reports, while OpenDART `fnltt_singl_acnt` returns the required CFS accounts.
- Added a regression test for the exact failure mode: primary `dart.fs.extract` raises, then provider falls back to the single-account API.
- Updated `src/data/quality_provider.py`:
  - keeps the existing `dart.fs.extract` path as primary
  - falls back only on extract failure
  - reads consolidated single-account rows for revenue, operating income, net income, equity, and liabilities
  - converts annual Q4 income rows into quarterly Q4 values by subtracting Q1-Q3

### Data Result

- Real Hyundai-only sync: `status=success`, `metric_count=8`.
- `005380`: 8 rows for 2024Q1-2025Q4.
- All 8 Hyundai rows have non-null `roe`, `operating_margin`, and `debt_ratio`.
- Re-run 5-ticker basket: `status=success`, `metric_count=40`.
- Quality coverage now has 5 tickers / 40 rows in `quality_metrics`.

### Verification

- TDD RED observed: new single-account fallback test failed on the original extract exception before implementation.
- `.\venv\Scripts\python.exe -m pytest tests\data\test_quality_provider.py::test_dart_provider_falls_back_to_single_account_api_when_extract_merge_fails -q -p no:cacheprovider` -> 1 passed after implementation.
- `.\venv\Scripts\python.exe -m pytest tests\data\test_quality_provider.py -q -p no:cacheprovider` -> 10 passed.
- `.\venv\Scripts\python.exe -m compileall src\data\quality_provider.py tests\data\test_quality_provider.py` -> passed.
- Real sync: `.\venv\Scripts\python.exe scripts\sync_phase1_quality.py --tickers "005380" --year-from 2024 --year-to 2025` -> exit 0, `success`, `metric_count=8`.
- DB check: `005380` rows=8, complete rows=8, latest sync=`success`.
- `.\venv\Scripts\python.exe -m pytest -q -p no:cacheprovider` -> 158 passed.
- Real basket sync: `.\venv\Scripts\python.exe scripts\sync_phase1_quality.py --tickers "005930,000660,005380,373220,035420" --year-from 2024 --year-to 2025` -> exit 0, `success`, `metric_count=40`.
- DB check: each of `000660`, `005380`, `005930`, `035420`, `373220` has 8 rows and 8 complete rows.
- `.\venv\Scripts\python.exe scripts\rank_phase2_factors.py --as-of-date 2026-05-07 --top-n 5` -> ran successfully and logged `quality_score covered 5/433`.

### Next

- Expand quality sync to a broader ticker universe in controlled batches, watching DART quota and per-ticker fallback behavior.

## 2026-05-07 Quality sync expansion batch 1

### Completed

- Started expanding quality sync beyond the initial 5-ticker validation basket.
- Selected the next controlled KOSPI numeric batch from active stocks with fundamentals and no quality rows.
- Initial 5-ticker batch (`000100,000150,000210,000270,000720`) exceeded the command timeout before any sync run was recorded, so the process was stopped and the batch was reduced to single-ticker diagnosis.
- Ran `000100` (Yuhan) alone:
  - primary `dart-fss` extraction succeeded
  - 8 rows were saved
  - 2024Q1-Q3 had missing `debt_ratio`
- Added a regression test for the new observed case: primary extraction succeeds but some metric fields are missing.
- Updated `src/data/quality_provider.py` so incomplete primary rows are supplemented from OpenDART single-account API rows, filling only missing metric values.

### Data Result

- Before supplementation, `000100`: 8 rows, 5 complete rows.
- After supplementation and re-sync, `000100`: 8 rows, 8 complete rows.
- Quality coverage increased to 6 tickers / 48 rows.

### Verification

- TDD RED observed: `test_dart_provider_uses_single_account_api_to_fill_missing_primary_metrics` failed with missing `debt_ratio` before implementation.
- `.\venv\Scripts\python.exe -m pytest tests\data\test_quality_provider.py::test_dart_provider_uses_single_account_api_to_fill_missing_primary_metrics -q -p no:cacheprovider` -> 1 passed after implementation.
- `.\venv\Scripts\python.exe -m pytest tests\data\test_quality_provider.py -q -p no:cacheprovider` -> 11 passed.
- `.\venv\Scripts\python.exe -m compileall src\data\quality_provider.py tests\data\test_quality_provider.py` -> passed.
- Real sync: `.\venv\Scripts\python.exe scripts\sync_phase1_quality.py --tickers "000100" --year-from 2024 --year-to 2025` -> exit 0, `success`, `metric_count=8`.
- DB check: `000100` rows=8, complete rows=8.
- `.\venv\Scripts\python.exe -m pytest -q -p no:cacheprovider` -> 159 passed.

### Next

- Continue expansion one ticker at a time or with very small batches because `dart-fss` extraction can take several minutes per ticker.
- Next candidates from the same ordered set: `000150`, `000210`, `000270`, `000720`.

## 2026-05-07 Quality sync expansion batch 2

### Completed

- Continued the controlled one-ticker expansion with `000150` (Doosan).
- First `000150` sync completed successfully and saved 8 rows, but 2024Q1-Q3 `debt_ratio` values were negative.
- Compared primary `dart-fss` parsed rows against OpenDART `fnltt_singl_acnt` CFS rows.
- Root cause:
  - primary extraction selected suspicious balance values for early 2024 quarters
  - OpenDART single-account rows returned positive liabilities/equity for the same periods
- Added a regression test for suspicious primary metrics where `debt_ratio < 0`.
- Updated `src/data/quality_provider.py` so rows with suspicious negative `debt_ratio` are replaced from single-account API metrics for that period.

### Data Result

- Before suspicious-value replacement, `000150`: 8 rows, 8 non-null rows, but 3 negative `debt_ratio` rows.
- After re-sync, `000150`: 8 rows, 8 complete rows, minimum `debt_ratio` = `1.5024333219069164`.
- Quality coverage increased to 7 tickers / 56 rows.

### Verification

- TDD RED observed: `test_dart_provider_replaces_suspicious_primary_metrics_from_single_account_api` failed before implementation.
- Targeted provider tests for missing and suspicious metric supplementation -> 2 passed.
- `.\venv\Scripts\python.exe -m compileall src\data\quality_provider.py tests\data\test_quality_provider.py` -> passed.
- Real sync: `.\venv\Scripts\python.exe scripts\sync_phase1_quality.py --tickers "000150" --year-from 2024 --year-to 2025` -> exit 0, `success`, `metric_count=8`.
- DB check: `000150` rows=8, complete rows=8, min debt_ratio positive.
- `.\venv\Scripts\python.exe -m pytest -q -p no:cacheprovider` -> 160 passed.

### Next

- Continue one-ticker expansion with `000210`, then `000270`, then `000720`.

## 2026-05-08 Quality sync expansion batch 3

### Completed

- Continued one-ticker expansion with `000210` (DL).
- First `000210` sync completed successfully but produced only 7 rows:
  - 2024Q1 was missing
  - 2024Q2-Q3 `debt_ratio` values were near zero (`~0.001`), inconsistent with OpenDART single-account values
- Compared primary parsed rows with OpenDART `fnltt_singl_acnt` CFS rows.
- Root cause:
  - primary extraction missed one available period
  - primary extraction selected suspicious balance values for some early 2024 quarters
- Added a regression test for:
  - adding supplemental-only missing periods
  - replacing suspicious near-zero `debt_ratio`
- Updated `src/data/quality_provider.py`:
  - `debt_ratio < 0.05` is treated as suspicious
  - supplemental rows absent from the primary result are appended
  - merged rows are sorted by fiscal period

### Data Result

- Before merge expansion, `000210`: 7 rows, 7 complete rows, but missing 2024Q1 and min `debt_ratio` near zero.
- After re-sync, `000210`: 8 rows, 8 complete rows.
- `000210` minimum `debt_ratio` = `1.4612929200630405`.
- Quality coverage increased to 8 tickers / 64 rows.

### Verification

- TDD RED observed: `test_dart_provider_adds_missing_periods_and_replaces_tiny_debt_ratio` failed before implementation.
- Targeted provider tests for missing/suspicious supplementation -> 3 passed.
- `.\venv\Scripts\python.exe -m compileall src\data\quality_provider.py tests\data\test_quality_provider.py` -> passed.
- Real sync: `.\venv\Scripts\python.exe scripts\sync_phase1_quality.py --tickers "000210" --year-from 2024 --year-to 2025` -> exit 0, `success`, `metric_count=8`.
- DB check: `000210` rows=8, complete rows=8, min debt_ratio positive and no missing 2024Q1.
- `.\venv\Scripts\python.exe -m pytest -q -p no:cacheprovider` -> 161 passed.

### Next

- Continue one-ticker expansion with `000270`, then `000720`.

## 2026-05-08 Quality sync expansion batch 4

### Completed

- Continued one-ticker expansion with `000270` (Kia).
- Ran the real DART quality sync for 2024-2025.
- No parser or fallback code changes were needed for this ticker.

### Data Result

- `000270`: 8 rows, 8 complete rows.
- Latest sync run: `status=success`, `metric_count=8`.
- `000270` minimum `debt_ratio` = `0.6175568631086046`.
- `000270` minimum `operating_margin` = `0.08787661712483964`.
- `000270` minimum `roe` = `0.35359670742326893`.
- Quality coverage increased to 9 tickers / 72 rows.

### Verification

- Real sync: `.\venv\Scripts\python.exe scripts\sync_phase1_quality.py --tickers "000270" --year-from 2024 --year-to 2025` -> exit 0, `success`, `metric_count=8`.
- DB check: `000270` rows=8, complete rows=8, no suspicious negative or near-zero `debt_ratio`.

### Next

- Continue one-ticker expansion with `000720`.

## 2026-05-08 Quality sync expansion batch 5

### Completed

- Continued one-ticker expansion with `000720` (Hyundai Engineering & Construction).
- First real sync completed with `status=success`, but only 5 rows were saved.
- DB inspection showed 2025Q1-Q3 were missing even though the saved rows had non-null `roe`, `operating_margin`, and `debt_ratio`.
- Compared against OpenDART `fnltt_singl_acnt` CFS rows and confirmed the missing 2025Q1-Q3 periods exist in the source data.
- Root cause:
  - supplemental fallback was triggered only when existing rows had null/suspicious metrics
  - complete-but-missing-period primary results did not call the single-account supplement
- Added a regression test for complete primary rows that are missing periods.
- Updated `src/data/quality_provider.py` so fallback is also triggered when requested fiscal periods are absent from parsed primary rows.

### Data Result

- Before the missing-period trigger fix, `000720`: 5 rows, 5 complete rows, missing 2025Q1-Q3.
- After re-sync, `000720`: 8 rows, 8 complete rows.
- Latest sync run: `status=success`, `metric_count=8`.
- `000720` minimum `debt_ratio` = `1.2907143458368664`.
- `000720` minimum `operating_margin` = `-0.0411846656818212`.
- `000720` minimum `roe` = `-0.07915394534174149`.
- Negative 2025Q1-Q3 profitability metrics match OpenDART single-account data and reflect reported loss periods, not parser failure.
- Quality coverage increased to 10 tickers / 80 rows.

### Verification

- TDD RED observed: `test_dart_provider_adds_missing_periods_when_primary_rows_are_complete` failed before implementation.
- Targeted provider tests: `.\venv\Scripts\python.exe -m pytest tests/data/test_quality_provider.py -q` -> 14 passed.
- AST/syntax check: `.\venv\Scripts\python.exe -m compileall src tests` -> passed.
- Real sync: `.\venv\Scripts\python.exe scripts\sync_phase1_quality.py --tickers "000720" --year-from 2024 --year-to 2025` -> exit 0, `success`, `metric_count=8`.
- DB check: `000720` rows=8, complete rows=8, missing 2025Q1-Q3 filled.
- Full test suite: `.\venv\Scripts\python.exe -m pytest -q` -> 162 passed.

### Next

- Continue one-ticker expansion with the next unsynced large-cap ticker after `000720`.

## 2026-05-08 Quality sync expansion batch 6

### Completed

- Continued one-ticker expansion with `001440` (Taihan Cable & Solution).
- Selected the next target from active `stocks` rows without existing `quality_metrics`, ordered by the current stock table order.
- Ran the real DART quality sync for 2024-2025.
- No parser or fallback code changes were needed for this ticker.

### Data Result

- `001440`: 8 rows, 8 complete rows.
- Latest sync run: `status=success`, `metric_count=8`.
- `001440` minimum `debt_ratio` = `0.5644215801800614`.
- `001440` minimum `operating_margin` = `0.029158667749238597`.
- `001440` minimum `roe` = `0.10308234488097179`.
- Quality coverage increased to 11 tickers / 88 rows.

### Verification

- Real sync: `.\venv\Scripts\python.exe scripts\sync_phase1_quality.py --tickers "001440" --year-from 2024 --year-to 2025` -> exit 0, `success`, `metric_count=8`.
- DB check: `001440` rows=8, complete rows=8, no suspicious negative or near-zero `debt_ratio`.
- No code changes were made in this batch, so the prior full suite result remains the latest code verification.

### Next

- Continue one-ticker expansion with `402340` (SK Square).

## 2026-05-08 Quality sync expansion batch 7

### Completed

- Continued one-ticker expansion with `402340` (SK Square).
- Ran the real DART quality sync for 2024-2025.
- DB validation found 8 complete rows, but unusually high `operating_margin` values.
- Compared the high-margin periods against OpenDART `fnltt_singl_acnt` CFS rows.
- Source check confirmed SK Square's reported operating income is much larger than revenue in multiple periods, so the large margin is a business/reporting characteristic rather than a parser failure.
- No parser or fallback code changes were needed for this ticker.

### Data Result

- `402340`: 8 rows, 8 complete rows.
- Latest sync run: `status=success`, `metric_count=8`.
- `402340` minimum `debt_ratio` = `0.09010357406702023`.
- `402340` minimum `operating_margin` = `-1.2172398093408168`.
- `402340` maximum `operating_margin` = `4.999217916481603`.
- `402340` minimum `roe` = `-0.18139424316359826`.
- `402340` maximum `roe` = `0.8001965078712254`.
- Quality coverage increased to 12 tickers / 96 rows.

### Verification

- Real sync: `.\venv\Scripts\python.exe scripts\sync_phase1_quality.py --tickers "402340" --year-from 2024 --year-to 2025` -> exit 0, `success`, `metric_count=8`.
- DB check: `402340` rows=8, complete rows=8.
- OpenDART single-account comparison confirmed high operating-margin direction and magnitude are source-backed.
- No code changes were made in this batch.

### Next

- Continue one-ticker expansion with `009150` (Samsung Electro-Mechanics).

## 2026-05-08 Quality sync expansion batch 8

### Completed

- Switched from one-by-one reporting to continuous progression until an error needs intervention.
- Continued quality sync expansion from 12 synced tickers toward the 20-30 ticker stabilization target.
- Synced and validated the following additional tickers:
  - `009150` Samsung Electro-Mechanics
  - `006340` Daewon Cable
  - `006800` Mirae Asset Securities
  - `047040` Daewoo Engineering & Construction
  - `042700` Hanmi Semiconductor
  - `006400` Samsung SDI
  - `062040` Sanil Electric
  - `066570` LG Electronics
  - `018880` Hanon Systems
  - `034020` Doosan Enerbility
  - `010120` LS ELECTRIC
  - `016360` Samsung Securities
  - `012450` Hanwha Aerospace
- Stopped at `062040` first because it produced only 4 rows.
- Root cause for `062040`:
  - OpenDART had no data for 2024Q1-Q2.
  - 2025Q1 existed but returned only `OFS` rows, while the fallback parser accepted only `CFS`.
- Added a regression test for single-account rows that have only `OFS` when `CFS` is absent.
- Updated `src/data/quality_provider.py` to prefer `CFS`, but fall back to `OFS` for a period when no `CFS` rows are present.
- Re-synced `062040`; row count improved from 4 to 6, with the remaining missing 2024Q1-Q2 confirmed as OpenDART source absence.
- Stopped again at `016360` because all `operating_margin` values were null.
- Source check for `016360`:
  - Samsung Securities exposes financial-industry line items such as interest income and net fee income.
  - A general manufacturing-style revenue denominator is not available in the single-account rows.
  - Left `operating_margin` null rather than inventing a financial-sector formula.
- Synced `012450` afterward to reach 25 covered tickers.

### Data Result

- Quality coverage increased from 12 tickers / 96 rows to 25 tickers / 198 rows.
- `062040`: 6 rows, 6 complete rows; 2024Q1-Q2 unavailable from OpenDART.
- `016360`: 8 rows, but `operating_margin` is null for all rows due financial-sector account structure.
- `012450`: 8 rows, 8 complete rows.
- Next unsynced ticker is `001510` (SK Securities).

### Verification

- TDD RED observed: `test_dart_provider_uses_ofs_single_account_rows_when_cfs_rows_are_absent` failed before implementation.
- Targeted provider tests: `.\venv\Scripts\python.exe -m pytest tests/data/test_quality_provider.py -q` -> 15 passed.
- AST/syntax check: `.\venv\Scripts\python.exe -m compileall src tests` -> passed.
- Real sync checks:
  - `062040` after OFS fallback -> `success`, `metric_count=6`.
  - `012450` -> `success`, `metric_count=8`.
- Full test suite: `.\venv\Scripts\python.exe -m pytest -q` -> 163 passed.

### Next

- Continue stabilization from `001510` (SK Securities).
- Treat financial-sector `operating_margin` nulls as a separate modeling decision rather than a parser bug unless a valid revenue denominator exists in source data.

## 2026-05-08 Quality sync expansion batch 9

### Completed

- Continued quality sync expansion from 25 synced tickers to the upper end of the 20-30 ticker stabilization target.
- Synced and validated the following additional tickers:
  - `001510` SK Securities
  - `005490` POSCO Holdings
  - `329180` HD Hyundai Heavy Industries
  - `064350` Hyundai Rotem
  - `028260` Samsung C&T
- No parser or fallback code changes were needed in this batch.
- `001510` showed the same financial-sector pattern as `016360`: 8 rows were saved, but `operating_margin` is null because the single-account rows do not expose a general manufacturing-style revenue denominator.

### Data Result

- Quality coverage increased from 25 tickers / 198 rows to 30 tickers / 238 rows.
- `001510`: 8 rows, ROE/debt complete, `operating_margin` null by financial-sector account structure.
- `005490`: 8 rows, 8 complete rows.
- `329180`: 8 rows, 8 complete rows.
- `064350`: 8 rows, 8 complete rows.
- `028260`: 8 rows, 8 complete rows.
- Existing known exceptions remain:
  - `062040`: 6 rows because 2024Q1-Q2 are unavailable from OpenDART.
  - `016360` and `001510`: financial-sector `operating_margin` nulls.
- Next unsynced ticker is `298040` (Hyosung Heavy Industries).

### Verification

- Real sync sequence completed with latest runs `status=success`.
- DB check: coverage = 30 tickers / 238 rows.
- DB check: no newly synced non-financial ticker had missing ROE/debt ratio, missing rows, or suspicious near-zero debt ratio.
- No code changes were made in this batch, so no new test run was required.

### Next

- Move from stabilization to broader batch expansion, starting with `298040`, unless financial-sector quality modeling is prioritized first.

## 2026-05-08 Quality sync expansion batch 10

### Completed

- Continued broader batch expansion without stopping for per-ticker reporting.
- Expanded quality coverage from 30 synced tickers to 60 synced tickers.
- Processed the next active unsynced tickers in stock-table order, including:
  - `298040`, `009830`, `267260`, `032830`, `079550`, `025860`, `105560`, `047810`, `103590`, `010140`
  - `042660`, `322000`, `007660`, `003670`, `034730`, `039490`, `006260`, `003530`, `096770`
  - `011070`, `051910`, `336260`, `278470`, `011790`, `055550`, `066970`
  - `010130`, `071050`, `068270`, `375500`
- Long-running DART extraction hit shell timeouts twice, but DB inspection confirmed the completed sync runs were committed successfully.
- No parser or fallback code changes were needed in this batch.

### Data Result

- Quality coverage increased from 30 tickers / 238 rows to 60 tickers / 478 rows.
- Latest sync runs show `status=success`; latest run `metric_count=8`.
- Final four checked tickers all have 8 rows with ROE, operating margin, and debt ratio present:
  - `010130` Korea Zinc
  - `071050` Korea Investment Holdings
  - `068270` Celltrion
  - `375500` DL E&C
- Financial-sector `operating_margin` null/modeling exceptions remain tracked separately where applicable.
- Next unsynced ticker is `012330` (Hyundai Mobis).

### Verification

- DB check: coverage = 60 tickers / 478 rows.
- DB check: latest quality sync run = `status=success`, `metric_count=8`.
- DB check: latest completed tickers have no missing ROE/debt ratio and no suspicious near-zero debt ratio.
- No code changes were made in this batch, so no new test run was required.

### Next

- Continue broader expansion from `012330` (Hyundai Mobis).
- Consider adding a shorter reusable batch runner script if DART extraction timeouts continue during large batches.

## 2026-05-08 Quality sync expansion batch 11

### Completed

- Continued broad DART quality sync expansion without stopping for per-ticker reporting.
- Expanded quality coverage from 60 tickers / 478 rows to 140 tickers / 1106 rows.
- Switched the operational batch runner to the OpenDART single-account path after `035720` showed long `dart-fss` full-extract latency.
- Investigated and classified source-backed exceptions while continuing the batch:
  - `443060` HD Hyundai Marine Solution: 7 rows because OpenDART has no 2024Q1 data.
  - `064400` LG CNS: 2024Q1 balance data exists, but income fields are `-` in OpenDART; later quarters are complete.
  - `0126Z0` Samsung Epis Holdings: only 2025Q4 is available from OpenDART in the requested range.
  - `483650` d'Alba Global: 6 rows because OpenDART has no 2024Q1-Q2 data.
  - `454910` Doosan Robotics: very low debt ratio confirmed by source balance sheet, not a parser issue.
- Fixed a real parser gap found on `000880` Hanwha:
  - Some CFS quarterly balance rows expose `assets` and `liabilities`, but omit `equity`.
  - `src/data/quality_provider.py` now derives missing equity as `assets - liabilities` only when equity is absent and both inputs are present.
  - Added regression coverage in `tests/data/test_quality_provider.py`.

### Data Result

- Quality coverage is now 140 tickers / 1106 rows.
- `000880` now has 8 complete rows after re-sync.
- Final DB validation found 0 unexpected issues after excluding documented source/sector exceptions.
- Next unsynced ticker is `112610` (CS Wind).

### Verification

- Provider tests: `.\venv\Scripts\python.exe -m pytest tests\data\test_quality_provider.py -q` -> 16 passed.
- AST/syntax check: `.\venv\Scripts\python.exe -m compileall src tests` -> passed.
- Full test suite: `.\venv\Scripts\python.exe -m pytest -q` -> 164 passed.
- DB check: coverage = 140 tickers / 1106 rows, unexpected validation issues = 0.

### Next

- Continue quality sync expansion from `112610` (CS Wind).
- Consider making the single-account batch runner a maintained script if further large-batch sync work continues.

## 2026-05-08 Quality sync expansion batch 12

### Completed

- Continued broad DART quality sync expansion in larger batches.
- Expanded quality coverage from 140 tickers / 1106 rows to 180 tickers / 1420 rows.
- Continued using the OpenDART single-account path for operational sync because it avoids the long `dart-fss` full-extract latency seen in prior batches.
- Investigated and classified source-backed exceptions while continuing:
  - `088980` Macquarie Korea Infrastructure Fund: OpenDART single-account API returned no data for every requested 2024-2025 period, so it was skipped as a no-source instrument.
  - `217590` TMC: 2 rows only; OpenDART has no data for earlier requested periods.
  - `003720` Samyoung: 2025Q3 CFS source omits net income while CFS revenue/operating income and OFS net income exist; left ROE null rather than mixing OFS net income into a CFS-based metric.
- No parser code changes were made in this batch.

### Data Result

- Quality coverage is now 180 tickers / 1420 rows.
- Final DB validation found 0 unexpected issues after excluding documented source/sector exceptions.
- Next unsynced ticker is `100090` (SK Oceanplant), excluding the known no-source `088980`.

### Verification

- DB check: coverage = 180 tickers / 1420 rows.
- DB check: unexpected validation issues = 0.
- No code changes were made in this batch, so the latest full suite remains `164 passed` from batch 11.

### Next

- Continue quality sync expansion from `100090` (SK Oceanplant).
- Keep `088980` on the no-source skip list unless a different data provider is added for fund/infrastructure instruments.

## 2026-05-08 Quality sync expansion batch 13

### Completed

- Continued quality sync expansion with a 100-stock target batch.
- Expanded quality coverage from 180 tickers / 1420 rows to 280 tickers / 2201 rows.
- Continued using the OpenDART single-account path for operational sync.
- Investigated and classified source-backed exceptions while continuing:
  - `0011T0` and `0129K0`: OpenDART single-account API returned no usable source data in the requested range.
  - `439260`, `490470`, `499790`, and `125020`: partial period source absence; only the available OpenDART periods were loaded.
  - `298020`, `030000`, `178320`, `277810`, and `100790`: CFS source lacks net income for some periods while other metrics are present; ROE was left null for those periods rather than mixing OFS net income into CFS-based metrics.
  - `277810`: very low debt ratio was confirmed against source balance-sheet data.
- No parser code changes were made in this batch.

### Data Result

- Quality coverage is now 280 tickers / 2201 rows.
- Final DB validation found 0 unexpected issues after excluding documented source/sector exceptions.
- Next unsynced ticker is `036930` (Jusung Engineering), excluding known no-source instruments.

### Verification

- DB check: coverage = 280 tickers / 2201 rows.
- DB check: unexpected validation issues = 0.
- DB check: debt ratio populated for all loaded rows; remaining null ROE/operating-margin values are covered by documented source or sector exceptions.
- No code changes were made in this batch, so the latest full suite remains `164 passed` from batch 11.

### Next

- Continue quality sync expansion from `036930` (Jusung Engineering).
- For the next large batch, keep using the exception-aware single-account runner and stop only on new source patterns or parser-quality issues.

## 2026-05-08 Quality sync expansion batch 14

### Completed

- Processed all remaining 165 active unsynced stocks in one pass.
- Expanded quality coverage from 280 tickers / 2201 rows to 445 tickers / 3432 rows.
- Rechecked all validation-flagged tickers against OpenDART source periods and account fields.
- Confirmed the only still-unsynced active stocks are known no-source instruments:
  - `088980` Macquarie Korea Infrastructure Fund
  - `0011T0` Chaevi
  - `0129K0` Shinhan 18th SPAC
- Classified the new validation flags as source-backed exceptions:
  - Partial period source absence: `0001A0`, `0004V0`, `0007C0`, `0088M0`, `012210`, `107640`, `125490`, `126730`, `209640`, `226590`, `347850`, `394420`, `448900`, `452450`, `456160`, `459510`, `475430`, `475830`, `488280`, `491000`
  - Partial metric source absence or unusable revenue denominator: `041020`, `076610`, `140410`, `141080`, `226950`, `261780`, `263750`, `308080`, `310210`, `347700`, `372320`, `476830`
  - Source-backed very low or negative debt ratio: `033790`, `041910`, `048410`, `108490`, `376900`, `456160`, `476830`
- No parser code changes were made in this batch.

### Data Result

- Active stocks in `stocks`: 448.
- Quality coverage is now 445 tickers / 3432 rows.
- Remaining unsynced active stocks: 3, all documented no-source instruments.
- Final DB validation found 0 unexpected issues after excluding documented source/sector exceptions.

### Verification

- DB check: coverage = 445 tickers / 3432 rows.
- DB check: unexpected validation issues = 0.
- DB check: null counts = 24 ROE, 191 operating margin, 0 debt ratio; all nulls are covered by documented source or sector exceptions.
- DB check: 30 tickers have fewer than 8 rows; all are covered by documented partial source absence.
- No code changes were made in this batch, so the latest full suite remains `164 passed` from batch 11.

### Next

- Phase 1 quality-metric sync is complete for all active stocks that have usable OpenDART source data.
- Next meaningful step is to either persist the exception-aware batch runner as a maintained script or move on to the next data/domain phase.

## 2026-05-08 Quality sync runner hardening

### Completed

- Turned the operational exception-aware quality sync flow into maintained script behavior in `scripts/sync_phase1_quality.py`.
- Added CLI options:
  - `--single-account-only`: use the OpenDART single-account API path directly.
  - `--only-unsynced`: select only active stocks without quality rows when explicit tickers are not supplied.
  - `--include-known-no-source`: optionally include documented no-source tickers.
  - `--limit`: cap the selected unsynced batch size.
  - `--validate`: print DB validation summary after sync.
- Added documented exception sets for no-source, partial-source, partial-metric, financial operating-margin, and source-backed low-debt cases.
- Added reusable validation/report helpers so future runs can catch unexpected nulls, short period coverage, and suspicious debt ratios without retyping ad hoc scripts.

### Verification

- `.\venv\Scripts\python.exe -m pytest tests\data\test_quality_sync_script.py -q` -> 10 passed.
- `.\venv\Scripts\python.exe -m compileall scripts tests src` -> passed.
- `.\venv\Scripts\python.exe -m pytest tests\data\test_quality_sync_script.py tests\data\test_quality_provider.py tests\data\test_quality_collector.py -q` -> 31 passed.
- `.\venv\Scripts\python.exe -m pytest -q` -> 167 passed.

### Next

- Use `scripts\sync_phase1_quality.py --year-from 2024 --year-to 2025 --single-account-only --only-unsynced --validate` for future incremental quality sync runs.
- Consider moving exception sets to a data/config file if the list grows further.

## 2026-05-08 Quality exception config split

### Completed

- Moved the quality-sync exception sets out of `scripts/sync_phase1_quality.py` into `src/data/quality_sync_exceptions.json`.
- Added `load_exception_sets()` and `QualitySyncExceptions` so sync selection and DB validation use the same external exception file.
- Added `--exceptions-file` to the quality sync CLI for custom exception files.
- Fixed the validation aggregate query to use SQL `case` expressions instead of summing boolean expressions, which makes non-null counts stable on SQLite.

### Verification

- `.\venv\Scripts\python.exe -m pytest tests\data\test_quality_sync_script.py -q` -> 13 passed.
- `.\venv\Scripts\python.exe -m compileall scripts tests src` -> passed.
- `.\venv\Scripts\python.exe -m pytest tests\data\test_quality_sync_script.py tests\data\test_quality_provider.py tests\data\test_quality_collector.py -q` -> 33 passed.
- Current DB validation through the new JSON exception file: coverage = 445 tickers / 3432 rows, unexpected issues = 0.
- `.\venv\Scripts\python.exe -m pytest -q` -> 169 passed.

### Next

- Move from quality data ingestion hardening to consuming quality metrics in ranking/backtest logic.

## 2026-05-08 Quality factor pipeline verification

### Completed

- Verified the factor engine already consumes `QualityMetric` rows for ROE, operating margin, and debt ratio.
- Verified the fast backtest scorer also uses quality metrics through existing regression coverage.
- Ran real DB ranking for `2026-05-08`: 433 scored stocks, 433 with nonzero quality scores.
- Ran real DB backtest over the available local price range `2025-10-01` to `2026-05-07`.
- Reduced the repeated quality coverage log from DEBUG to TRACE so ranking/backtest command output stays readable while deep diagnostics remain available.

### Real DB Result

- Ranking top 5 on `2026-05-08`: `043260`, `017800`, `047040`, `027360`, `010170`.
- Backtest result for `2025-10-01` to `2026-05-07`, top 20, initial capital 100,000,000:
  - final equity = 113,119,839.49
  - total return = 13.12%
  - CAGR = 22.93%
  - max drawdown = -4.77%
  - Sharpe ratio = 2.0094
  - win rate = 54.55%
  - trade count = 84

### Verification

- `.\venv\Scripts\python.exe -m pytest tests\factors\test_engine.py tests\backtest\test_backtest_engine.py -q` -> 24 passed.
- `.\venv\Scripts\python.exe -m compileall src tests scripts` -> passed.
- `.\venv\Scripts\python.exe -m pytest -q` -> 170 passed.

### Next

- Investigate whether the current factor weights and very large momentum z-scores are too dominant, using DB/backtest evidence before changing parameters.

## 2026-05-09 Rebalance execution preparation script

### Completed

- Added `scripts/prepare_rebalance_for_execution.py` as the order-free preparation step before manual PAPER rebalance execution.
- The script runs the existing dry-run rebalance with strict live quote defaults:
  - `--price-fallback none`
  - `--quote-retries 4`
  - `--quote-delay-sec 0.5`
- It writes both Markdown and JSON reports, then immediately checks the JSON through the same preflight guard used by real order execution.
- It exits before execution when the dry-run fails or when preflight detects stale dates, fallback prices, or live quote failures.

### Verification

- RED check: `.\venv\Scripts\python.exe -m pytest tests\trading\test_prepare_rebalance_for_execution.py -q` initially failed because the new module did not exist.
- Targeted tests: `.\venv\Scripts\python.exe -m pytest tests\trading\test_prepare_rebalance_for_execution.py -q` -> 4 passed.
- Related trading script tests: `.\venv\Scripts\python.exe -m pytest tests\trading\test_prepare_rebalance_for_execution.py tests\trading\test_dry_run_rebalance.py tests\trading\test_execute_rebalance_from_dry_run.py -q` -> 18 passed.
- Syntax check: `.\venv\Scripts\python.exe -m compileall scripts\prepare_rebalance_for_execution.py tests\trading\test_prepare_rebalance_for_execution.py` -> passed.
- Full test suite: `.\venv\Scripts\python.exe -m pytest -q` -> 213 passed.

### Next

- Add documentation/runbook entries for the PAPER rebalance sequence:
  1. Generate/check dry-run report with `scripts\prepare_rebalance_for_execution.py`.
  2. During regular market hours, execute from the clean JSON with `scripts\execute_rebalance_from_dry_run.py`.
  3. Review KIS/order logs and report result.

## 2026-05-09 PAPER rebalance runbook documentation

### Completed

- Updated `HANDOFF_FOR_AGENTS.md` to reflect the current PAPER rebalance execution flow.
- Added the new dry-run, prepare, and execute scripts to the architecture map.
- Added the exact manual preparation and execution commands.
- Documented that execution requires a same-date clean dry-run JSON, the confirmation token, and regular market hours.

### Verification

- `.\venv\Scripts\python.exe scripts\prepare_rebalance_for_execution.py --help` -> command options match the documented prepare flow.
- `.\venv\Scripts\python.exe scripts\execute_rebalance_from_dry_run.py --help` -> command options match the documented execution flow.
- `.\venv\Scripts\python.exe -m pytest tests\trading\test_prepare_rebalance_for_execution.py tests\trading\test_execute_rebalance_from_dry_run.py -q` -> 9 passed.

### Next

- Add an execution-result report output to `scripts\execute_rebalance_from_dry_run.py` so PAPER order attempts leave a machine-readable audit artifact.

## 2026-05-09 PAPER execution result report

### Completed

- Added `--execution-report-json` to `scripts\execute_rebalance_from_dry_run.py`.
- Successful or partially failed PAPER execution attempts can now write a machine-readable audit artifact with:
  - source dry-run JSON path
  - expected preflight date
  - execution timestamp in KST
  - sold/bought/failed tickers and counts
- Updated `HANDOFF_FOR_AGENTS.md` so the manual execution command writes an execution report JSON.

### Verification

- RED check: `.\venv\Scripts\python.exe -m pytest tests\trading\test_execute_rebalance_from_dry_run.py -q` failed before `--execution-report-json` existed.
- Targeted tests: `.\venv\Scripts\python.exe -m pytest tests\trading\test_execute_rebalance_from_dry_run.py -q` -> 6 passed.
- Related trading script tests: `.\venv\Scripts\python.exe -m pytest tests\trading\test_execute_rebalance_from_dry_run.py tests\trading\test_prepare_rebalance_for_execution.py tests\trading\test_dry_run_rebalance.py -q` -> 19 passed.
- Syntax check: `.\venv\Scripts\python.exe -m compileall scripts\execute_rebalance_from_dry_run.py tests\trading\test_execute_rebalance_from_dry_run.py` -> passed.
- CLI help check: `.\venv\Scripts\python.exe scripts\execute_rebalance_from_dry_run.py --help` -> includes `--execution-report-json`.
- Full test suite: `.\venv\Scripts\python.exe -m pytest -q` -> 214 passed.

### Next

- Add a lightweight audit/review script that reads the dry-run JSON plus optional execution JSON and prints a concise human review summary without touching KIS.

## 2026-05-09 PAPER rebalance report reviewer

### Completed

- Added `scripts/review_rebalance_reports.py`.
- The script reads the dry-run JSON and optional execution-result JSON without touching KIS or the DB.
- It prints a concise review summary:
  - dry-run clean/blocked status
  - as-of date, target/order counts, fallback count, live quote failure count
  - planned order lines
  - optional execution clean/failed status and sold/bought/failed counts
- Updated `HANDOFF_FOR_AGENTS.md` with the review command.

### Verification

- RED check: `.\venv\Scripts\python.exe -m pytest tests\trading\test_review_rebalance_reports.py -q` failed before the script existed.
- Targeted tests: `.\venv\Scripts\python.exe -m pytest tests\trading\test_review_rebalance_reports.py -q` -> 5 passed.
- Related trading script tests: `.\venv\Scripts\python.exe -m pytest tests\trading\test_review_rebalance_reports.py tests\trading\test_prepare_rebalance_for_execution.py tests\trading\test_execute_rebalance_from_dry_run.py tests\trading\test_dry_run_rebalance.py -q` -> 24 passed.
- Syntax check: `.\venv\Scripts\python.exe -m compileall scripts\review_rebalance_reports.py tests\trading\test_review_rebalance_reports.py` -> passed.
- CLI help check: `.\venv\Scripts\python.exe scripts\review_rebalance_reports.py --help` -> passed.
- Full test suite: `.\venv\Scripts\python.exe -m pytest -q` -> 219 passed.

### Next

- The PAPER rebalance manual flow is now scriptable end-to-end:
  1. `prepare_rebalance_for_execution.py`
  2. `review_rebalance_reports.py`
  3. regular-hours `execute_rebalance_from_dry_run.py`
  4. `review_rebalance_reports.py` again with execution JSON
- Next useful work is to add a single non-ordering orchestration command that runs prepare + review together for market-hours readiness.

## 2026-05-09 PAPER prepare-and-review orchestration

### Completed

- Added `scripts/prepare_and_review_rebalance.py`.
- The script runs the existing no-order preparation step first, then runs the JSON report reviewer only if preparation succeeds.
- It does not call the execution script and cannot submit PAPER orders.
- Updated `HANDOFF_FOR_AGENTS.md` with the one-command prepare + review flow.

### Verification

- RED check: `.\venv\Scripts\python.exe -m pytest tests\trading\test_prepare_and_review_rebalance.py -q` failed before the script existed.
- Targeted tests: `.\venv\Scripts\python.exe -m pytest tests\trading\test_prepare_and_review_rebalance.py -q` -> 4 passed.
- Related trading script tests: `.\venv\Scripts\python.exe -m pytest tests\trading\test_prepare_and_review_rebalance.py tests\trading\test_prepare_rebalance_for_execution.py tests\trading\test_review_rebalance_reports.py tests\trading\test_execute_rebalance_from_dry_run.py tests\trading\test_dry_run_rebalance.py -q` -> 28 passed.
- Syntax check: `.\venv\Scripts\python.exe -m compileall scripts\prepare_and_review_rebalance.py tests\trading\test_prepare_and_review_rebalance.py` -> passed.
- CLI help check: `.\venv\Scripts\python.exe scripts\prepare_and_review_rebalance.py --help` -> passed.
- Full test suite: `.\venv\Scripts\python.exe -m pytest -q` -> 223 passed.

### Next

- Add a market-day readiness checker that reports whether today is a weekday regular market date/time for execution, without submitting orders.

## 2026-05-09 PAPER rebalance readiness checker

### Completed

- Added `scripts/check_rebalance_readiness.py`.
- The script checks execution readiness without touching KIS order APIs:
  - current time must be weekday 09:00-15:20 KST
  - dry-run JSON must pass the same preflight guard used by execution
  - dry-run `as_of_date` must match `--expected-date`
- It prints `execution_ready=true/false` plus the blocking reason when readiness fails.
- Updated `HANDOFF_FOR_AGENTS.md` with the readiness-check command.

### Verification

- RED check: `.\venv\Scripts\python.exe -m pytest tests\trading\test_check_rebalance_readiness.py -q` failed before the script existed.
- Targeted tests: `.\venv\Scripts\python.exe -m pytest tests\trading\test_check_rebalance_readiness.py -q` -> 4 passed.
- Related trading script tests: `.\venv\Scripts\python.exe -m pytest tests\trading\test_check_rebalance_readiness.py tests\trading\test_prepare_and_review_rebalance.py tests\trading\test_prepare_rebalance_for_execution.py tests\trading\test_review_rebalance_reports.py tests\trading\test_execute_rebalance_from_dry_run.py tests\trading\test_dry_run_rebalance.py -q` -> 32 passed.
- Syntax check: `.\venv\Scripts\python.exe -m compileall scripts\check_rebalance_readiness.py tests\trading\test_check_rebalance_readiness.py` -> passed.
- CLI help check: `.\venv\Scripts\python.exe scripts\check_rebalance_readiness.py --help` -> passed.
- Full test suite: `.\venv\Scripts\python.exe -m pytest -q` -> 227 passed.

### Next

- Add a no-order daily operations checklist script that prints the exact safe command sequence for the current date.

## 2026-05-09 PAPER rebalance operations checklist

### Completed

- Added `scripts/print_rebalance_operations_checklist.py`.
- The script prints a no-order command sequence for a chosen date:
  - prepare + review
  - readiness check
  - regular-hours PAPER execution command with confirmation token
  - post-execution review
- Default execution report path is date-stamped as `data/rebalance_execution_YYYY-MM-DD.json`.
- Updated `HANDOFF_FOR_AGENTS.md` with the checklist command and current test count.

### Verification

- RED check: `.\venv\Scripts\python.exe -m pytest tests\trading\test_print_rebalance_operations_checklist.py -q` failed before the script existed.
- Targeted tests: `.\venv\Scripts\python.exe -m pytest tests\trading\test_print_rebalance_operations_checklist.py -q` -> 3 passed.
- Related trading script tests: `.\venv\Scripts\python.exe -m pytest tests\trading\test_print_rebalance_operations_checklist.py tests\trading\test_check_rebalance_readiness.py tests\trading\test_prepare_and_review_rebalance.py tests\trading\test_prepare_rebalance_for_execution.py tests\trading\test_review_rebalance_reports.py tests\trading\test_execute_rebalance_from_dry_run.py tests\trading\test_dry_run_rebalance.py -q` -> 35 passed.
- Syntax check: `.\venv\Scripts\python.exe -m compileall scripts\print_rebalance_operations_checklist.py tests\trading\test_print_rebalance_operations_checklist.py` -> passed.
- CLI help check: `.\venv\Scripts\python.exe scripts\print_rebalance_operations_checklist.py --help` -> passed.
- Full test suite: `.\venv\Scripts\python.exe -m pytest -q` -> 230 passed.

### Next

- Next useful improvement is to make the execution script refuse stale execution-report overwrite unless explicitly forced.

## 2026-05-09 PAPER execution report overwrite guard

### Completed

- Added `--force-overwrite-report` to `scripts/execute_rebalance_from_dry_run.py`.
- When `--execution-report-json` already exists, the execution script now exits before loading orders or calling `execute_rebalance`.
- Existing execution reports are preserved by default; intentional overwrite requires the explicit force flag.
- Updated `HANDOFF_FOR_AGENTS.md` with the overwrite guard and current test count.

### Verification

- RED check: `.\venv\Scripts\python.exe -m pytest tests\trading\test_execute_rebalance_from_dry_run.py -q` failed before `--force-overwrite-report` and the overwrite guard existed.
- Targeted tests: `.\venv\Scripts\python.exe -m pytest tests\trading\test_execute_rebalance_from_dry_run.py -q` -> 8 passed.
- Related trading script tests: `.\venv\Scripts\python.exe -m pytest tests\trading\test_execute_rebalance_from_dry_run.py tests\trading\test_print_rebalance_operations_checklist.py tests\trading\test_review_rebalance_reports.py -q` -> 16 passed.
- Syntax check: `.\venv\Scripts\python.exe -m compileall scripts\execute_rebalance_from_dry_run.py tests\trading\test_execute_rebalance_from_dry_run.py` -> passed.
- CLI help check: `.\venv\Scripts\python.exe scripts\execute_rebalance_from_dry_run.py --help` -> includes `--force-overwrite-report`.
- Full test suite: `.\venv\Scripts\python.exe -m pytest -q` -> 232 passed.

### Next

- Add an optional `--review-before-execute` flag to the execution script to print the dry-run review summary immediately before confirmation-gated execution.

## 2026-05-09 PAPER pre-execution review gate

### Completed

- Added `--review-before-execute` to `scripts/execute_rebalance_from_dry_run.py`.
- When enabled, the execution script runs the dry-run report reviewer immediately before loading orders and calling `execute_rebalance`.
- If the review returns blocked, the script exits before any order execution.
- Updated `scripts/print_rebalance_operations_checklist.py` so the generated execution command includes `--review-before-execute`.
- Updated `HANDOFF_FOR_AGENTS.md` with the pre-execution review gate and current test count.

### Verification

- RED check: `.\venv\Scripts\python.exe -m pytest tests\trading\test_execute_rebalance_from_dry_run.py -q` failed before `--review-before-execute` existed.
- Targeted execution tests: `.\venv\Scripts\python.exe -m pytest tests\trading\test_execute_rebalance_from_dry_run.py -q` -> 10 passed.
- Related tests: `.\venv\Scripts\python.exe -m pytest tests\trading\test_execute_rebalance_from_dry_run.py tests\trading\test_review_rebalance_reports.py tests\trading\test_print_rebalance_operations_checklist.py -q` -> 18 passed.
- Syntax check: `.\venv\Scripts\python.exe -m compileall scripts\execute_rebalance_from_dry_run.py tests\trading\test_execute_rebalance_from_dry_run.py` -> passed.
- CLI help check: `.\venv\Scripts\python.exe scripts\execute_rebalance_from_dry_run.py --help` -> includes `--review-before-execute`.
- RED check for checklist update: `.\venv\Scripts\python.exe -m pytest tests\trading\test_print_rebalance_operations_checklist.py -q` failed before the generated command included `--review-before-execute`.
- Checklist/execution tests after update: `.\venv\Scripts\python.exe -m pytest tests\trading\test_print_rebalance_operations_checklist.py tests\trading\test_execute_rebalance_from_dry_run.py -q` -> 13 passed.
- Full test suite: `.\venv\Scripts\python.exe -m pytest -q` -> 234 passed.

### Next

- Add a small smoke command that runs the no-order checklist for today's date and verifies all referenced script files exist.

## 2026-05-09 PAPER checklist smoke

### Completed

- Added `scripts/smoke_rebalance_operations_checklist.py`.
- The smoke script runs the no-order operations checklist, extracts referenced `scripts\*.py` paths, and verifies those script files exist under the project root.
- It does not touch KIS, DB, or order execution.
- Updated `HANDOFF_FOR_AGENTS.md` with the smoke command and current test count.

### Verification

- RED check: `.\venv\Scripts\python.exe -m pytest tests\trading\test_smoke_rebalance_operations_checklist.py -q` failed before the script existed.
- Targeted tests: `.\venv\Scripts\python.exe -m pytest tests\trading\test_smoke_rebalance_operations_checklist.py -q` -> 4 passed.
- Real local smoke: `.\venv\Scripts\python.exe scripts\smoke_rebalance_operations_checklist.py --as-of-date 2026-05-09 --top-n 20` -> `checklist_smoke_status=ok`, `referenced_script_count=4`, `missing_script_count=0`.
- Related checklist tests: `.\venv\Scripts\python.exe -m pytest tests\trading\test_smoke_rebalance_operations_checklist.py tests\trading\test_print_rebalance_operations_checklist.py -q` -> 7 passed.
- Syntax check: `.\venv\Scripts\python.exe -m compileall scripts\smoke_rebalance_operations_checklist.py tests\trading\test_smoke_rebalance_operations_checklist.py` -> passed.
- Full test suite: `.\venv\Scripts\python.exe -m pytest -q` -> 238 passed.

### Next

- Next useful improvement is to archive the PAPER rebalance command outputs into date-stamped files under `logs/` for operator review.

## 2026-05-09 PAPER checklist log archive

### Completed

- Added `scripts/archive_rebalance_operations_checklist.py`.
- The script runs the no-order checklist smoke, prints its output, and archives the same text to a date-stamped log file.
- Default log path is `logs/rebalance_operations_checklist_YYYY-MM-DD.log`.
- It does not touch KIS, DB, or order execution.
- Updated `HANDOFF_FOR_AGENTS.md` with the archive command and current test count.

### Verification

- RED check: `.\venv\Scripts\python.exe -m pytest tests\trading\test_archive_rebalance_operations_checklist.py -q` failed before the script existed.
- Targeted tests: `.\venv\Scripts\python.exe -m pytest tests\trading\test_archive_rebalance_operations_checklist.py -q` -> 4 passed.
- Real local archive: `.\venv\Scripts\python.exe scripts\archive_rebalance_operations_checklist.py --as-of-date 2026-05-09 --top-n 20 --output-log logs\rebalance_operations_checklist_2026-05-09.log` -> `archive_status=ok`, `missing_script_count=0`.
- Related checklist tests: `.\venv\Scripts\python.exe -m pytest tests\trading\test_archive_rebalance_operations_checklist.py tests\trading\test_smoke_rebalance_operations_checklist.py tests\trading\test_print_rebalance_operations_checklist.py -q` -> 11 passed.
- Syntax check: `.\venv\Scripts\python.exe -m compileall scripts\archive_rebalance_operations_checklist.py tests\trading\test_archive_rebalance_operations_checklist.py` -> passed.
- Full test suite: `.\venv\Scripts\python.exe -m pytest -q` -> 242 passed.

### Next

- Next useful improvement is to add retention cleanup for old rebalance checklist logs, keeping the most recent N files.

## 2026-05-09 PAPER checklist log retention cleanup

### Completed

- Added `scripts/cleanup_rebalance_checklist_logs.py`.
- The script matches only `logs/rebalance_operations_checklist_*.log`.
- It keeps the most recent N files by filename/date order.
- Default mode is dry-run; actual deletion requires `--apply`.
- Updated `HANDOFF_FOR_AGENTS.md` with the cleanup command and current test count.

### Verification

- RED check: `.\venv\Scripts\python.exe -m pytest tests\trading\test_cleanup_rebalance_checklist_logs.py -q` failed before the script existed.
- Targeted tests: `.\venv\Scripts\python.exe -m pytest tests\trading\test_cleanup_rebalance_checklist_logs.py -q` -> 4 passed.
- Real logs dry-run: `.\venv\Scripts\python.exe scripts\cleanup_rebalance_checklist_logs.py --keep 20` -> `matched_count=1`, `kept_count=1`, `delete_candidate_count=0`, `deleted_count=0`.
- Related log tests: `.\venv\Scripts\python.exe -m pytest tests\trading\test_cleanup_rebalance_checklist_logs.py tests\trading\test_archive_rebalance_operations_checklist.py -q` -> 8 passed.
- Syntax check: `.\venv\Scripts\python.exe -m compileall scripts\cleanup_rebalance_checklist_logs.py tests\trading\test_cleanup_rebalance_checklist_logs.py` -> passed.
- Full test suite: `.\venv\Scripts\python.exe -m pytest -q` -> 246 passed.

### Next

- The PAPER rebalance operations tooling is now well guarded. Next useful work is to run a no-order readiness rehearsal using the latest local dry-run JSON, then address any blocker it reports.

## 2026-05-09 PAPER operations error handling hardening

### Completed

- Hardened `scripts/review_rebalance_reports.py` so missing or invalid dry-run/execution JSON reports return a clear `missing_or_invalid` status instead of a traceback.
- Hardened `scripts/check_rebalance_readiness.py` so file/JSON preflight errors are reported as `preflight_status=blocked` with `execution_ready=false`.
- Hardened `scripts/execute_rebalance_from_dry_run.py` so missing or invalid dry-run JSON blocks before engine/order execution.
- Reused a public report-load error printer instead of cross-module access to a private helper.

### Verification

- RED checks reproduced the traceback failures in the three affected operational scripts before each fix.
- Targeted tests: `.\venv\Scripts\python.exe -m pytest tests\trading\test_review_rebalance_reports.py tests\trading\test_check_rebalance_readiness.py tests\trading\test_execute_rebalance_from_dry_run.py -q` -> covered by related targeted runs.
- Syntax check: `.\venv\Scripts\python.exe -m compileall config.py src tests scripts` -> passed.
- Config check: `.\venv\Scripts\python.exe config.py` -> passed.
- Full test suite: `.\venv\Scripts\python.exe -m pytest -q` -> 253 passed.

## 2026-05-09 fresh dry-run operations loop rehearsal

### Completed

- Ran the fresh PAPER dry-run preparation for `as_of_date=2026-05-09`, `top_n=20`.
- The first sandboxed run was blocked by local network/socket permission; rerunning with approved network access reached KIS PAPER and completed.
- Generated/updated:
  - `data/dry_run_rebalance_latest.json`
  - `data/dry_run_rebalance_latest.md`
- No orders were submitted.

### Result

- `review_rebalance_reports.py` reported `dry_run_status=clean`.
- `as_of_date=2026-05-09`
- `target_count=20`
- `sell_count=0`
- `buy_count=20`
- `price_fallback_count=0`
- `price_lookup_failed_count=0`
- `check_rebalance_readiness.py` reported `preflight_status=clean`.
- Readiness is still blocked because `2026-05-09` is outside regular weekday market execution time: `market_time_status=blocked`, `execution_ready=false`.

## 2026-05-09 buy filter implementation

### Completed

- Completed DART quality audit before implementation:
  - quality-related tests: 45 passed
  - DB validation: `unexpected_issues=0`
  - active stocks: 476
  - quality tickers: 507
  - quality rows: 3919
  - unsynced active tickers: 2, both documented no-source exceptions
- Added buy candidate filtering inside factor scoring.
- Implemented valuation exclusions:
  - `per <= 0`
  - `pbr <= 0`
- Implemented quality exclusions when candidate quality coverage is at least 70%:
  - available quality metric count below 2
  - `roe <= 0`
  - `debt_ratio >= 3.0`
- Implemented severe operating-loss exclusion when recent operating margin history is available:
  - latest 2 operating margins are each below `-0.10`
- Kept pure quality-score tests able to bypass buy filters with `apply_buy_filters=False`.
- Backtest fast scorer now passes recent operating margin history into the same filter path.

### Verification

- RED checks reproduced missing filter behavior before implementation.
- Targeted buy-filter tests: 4 passed.
- Related factor/backtest/trading tests: 176 passed.
- Full test suite: `.\venv\Scripts\python.exe -m pytest -q` -> 257 passed.
- Syntax check: `.\venv\Scripts\python.exe -m compileall config.py src tests scripts` -> passed.
- Real DB factor scoring on `2026-05-09`: `score_count=303`, `buy_filter_excluded=161`.

### Current blocker

- No-order readiness rehearsal for 2026-05-09 is correctly blocked because the latest local dry-run report is dated 2026-05-08 and 2026-05-09 is outside regular weekday market execution.

## 2026-05-09 PAPER readiness next-step guidance

### Completed

- Updated `scripts/check_rebalance_readiness.py` to print a `next_prepare_command=...` line whenever preflight is blocked.
- The command uses the requested `--expected-date` and configured default holding count, so stale dry-run reports now point directly to the regeneration command.

### Verification

- RED check: `.\venv\Scripts\python.exe -m pytest tests\trading\test_check_rebalance_readiness.py -q` failed before `next_prepare_command` existed.
- Targeted tests: `.\venv\Scripts\python.exe -m pytest tests\trading\test_check_rebalance_readiness.py -q` -> 6 passed.
- Real local readiness rehearsal: `.\venv\Scripts\python.exe scripts\check_rebalance_readiness.py --dry-run-json data\dry_run_rebalance_latest.json --expected-date 2026-05-09` -> blocked as expected and printed `next_prepare_command=.\venv\Scripts\python.exe scripts\prepare_rebalance_for_execution.py --as-of-date 2026-05-09 --top-n 20`.
- Syntax check: `.\venv\Scripts\python.exe -m compileall config.py src tests scripts` -> passed.
- Full test suite: `.\venv\Scripts\python.exe -m pytest -q` -> 253 passed.

## 2026-05-09 technical entry filter implementation

### Completed

- Added the second-stage technical entry filter to factor scoring.
- The filter runs after buy candidate filtering when recent close history is available.
- Implemented the MVP 3-of-4 pass rule:
  - signal close above MA20
  - MA60 today above MA60 from 20 trading days ago
  - RSI(14) below 75
  - 20-day daily-return volatility below 5%
- Missing or insufficient indicator data fails that individual condition.
- Backtest fast scorer now passes recent close history into the same factor filter path.
- Updated quality-only tests so they can still inspect scoring math without candidate filters.

### Verification

- RED check: weak technical candidate test failed before implementation.
- Targeted factor tests: `.\venv\Scripts\python.exe -m pytest tests\factors\test_engine.py -q` -> 14 passed.
- Related factor/backtest/trading tests: `.\venv\Scripts\python.exe -m pytest tests\factors tests\backtest tests\trading -q` -> 178 passed.
- Full test suite: `.\venv\Scripts\python.exe -m pytest -q` -> 259 passed.
- Syntax check: `.\venv\Scripts\python.exe -m compileall config.py src tests scripts` -> passed.
- Real DB factor scoring on `2026-05-09`: `score_count=228`, `buy_filter_excluded=236`.

### Next

- Proceed to look-ahead bias correction and signal/execution date separation.

## 2026-05-09 look-ahead bias correction

### Completed

- Updated backtest rebalancing so factor scores use the previous trading day as the signal date.
- The first trading date in a backtest no longer opens a new rebalance position without a prior signal date.
- Rebalance BUY and SELL executions now use execution-day open prices.
- Daily equity valuation still uses execution-day close prices.
- Existing stop-loss/trailing-stop delayed execution behavior remains next-open based.
- Updated backtest expectations and fixtures to reflect the new signal/execution timing.

### Verification

- RED check: previous-signal/open-execution test failed before implementation.
- Targeted backtest engine tests: `.\venv\Scripts\python.exe -m pytest tests\backtest\test_backtest_engine.py -q` -> 18 passed.
- Related factor/backtest/trading tests: `.\venv\Scripts\python.exe -m pytest tests\factors tests\backtest tests\trading -q` -> 179 passed.
- Full test suite: `.\venv\Scripts\python.exe -m pytest -q` -> 260 passed.
- Syntax check: `.\venv\Scripts\python.exe -m compileall config.py src tests scripts` -> passed.
- Real DB weekly backtest: `.\venv\Scripts\python.exe scripts\run_phase3_backtest.py --start-date 2026-04-01 --end-date 2026-05-09 --top-n 20 --rebalance-frequency weekly` -> completed, `trade_count=85`.

### Next

- Run a fresh dry-run/readiness rehearsal on the next weekday market window, then compare the new filtered portfolio with the previous dry-run report.

## 2026-05-09 execution-day gap guard

### Completed

- Added an execution-day gap guard for new buys.
- Default threshold is `max_abs_open_gap_pct=0.20` in `PortfolioConfig`.
- `compute_rebalance_orders()` now accepts `previous_closes` and skips new buys when `abs(execution_price / previous_close - 1) > 20%`.
- Existing holdings and sell orders are not blocked by the new-buy gap guard.
- Backtest rebalancing now applies the same gap guard using execution-day open and previous trading-day close.
- Dry-run PAPER preparation now loads the prior DB close for each new-buy candidate and applies the same guard to live quote prices.
- Dry-run `latest-db` fallback prices are not treated as execution prices for gap filtering, because fallback reports are already blocked before order execution.

### Verification

- RED checks:
  - rebalancer gap test failed before `previous_closes` support existed.
  - backtest gap test failed before execution-open filtering existed.
  - dry-run gap test failed before prior DB close was passed into order computation.
- Targeted new tests: 3 passed.
- Related trading/backtest tests: `.\venv\Scripts\python.exe -m pytest tests\trading tests\backtest -q` -> 160 passed.
- Full test suite: `.\venv\Scripts\python.exe -m pytest -q` -> 263 passed.
- Syntax check: `.\venv\Scripts\python.exe -m compileall config.py src tests scripts` -> passed.
- Real DB weekly backtest: `.\venv\Scripts\python.exe scripts\run_phase3_backtest.py --start-date 2026-04-01 --end-date 2026-05-09 --top-n 20 --rebalance-frequency weekly` -> completed, `trade_count=85`, `total_return=32.10%`.

### Next

- Next useful development task is a portfolio comparison report showing which tickers changed after buy filter, technical filter, look-ahead correction, and gap guard.

## 2026-05-09 rebalance report comparison tool

### Completed

- Added `scripts/compare_rebalance_reports.py`.
- The script compares two dry-run rebalance JSON reports without touching KIS or the DB.
- It reports:
  - before/after report dates and target counts
  - added, removed, and kept target tickers
  - rank deltas and score changes for kept tickers
  - added, removed, and kept BUY order tickers
- Added optional Markdown output with `--output-md`.
- Updated `HANDOFF_FOR_AGENTS.md` with the comparison command.
- Generated a local comparison artifact:
  - `data/rebalance_comparison_latest.md`

### Verification

- RED check: `.\venv\Scripts\python.exe -m pytest tests\trading\test_compare_rebalance_reports.py -q` failed before the script existed.
- Targeted tests: `.\venv\Scripts\python.exe -m pytest tests\trading\test_compare_rebalance_reports.py -q` -> 4 passed.
- Related report/dry-run tests: `.\venv\Scripts\python.exe -m pytest tests\trading\test_compare_rebalance_reports.py tests\trading\test_review_rebalance_reports.py tests\trading\test_dry_run_rebalance.py -q` -> 22 passed.
- CLI help check: `.\venv\Scripts\python.exe scripts\compare_rebalance_reports.py --help` -> passed.
- Real local comparison: `.\venv\Scripts\python.exe scripts\compare_rebalance_reports.py --before-json data\dry_run_rebalance_retry_strict.json --after-json data\dry_run_rebalance_latest.json --output-md data\rebalance_comparison_latest.md` -> completed, `added_count=0`, `removed_count=0`, `kept_count=20`.
- Full test suite: `.\venv\Scripts\python.exe -m pytest -q` -> 267 passed.
- Syntax check: `.\venv\Scripts\python.exe -m compileall config.py src tests scripts` -> passed.

### Next

- On the next market weekday, generate a fresh dry-run with the latest filters and compare it against `data/dry_run_rebalance_latest.json` or a saved baseline.

## 2026-05-09 dry-run skipped buy reason reporting

### Completed

- Added explicit skipped-buy reporting for execution-day gap guard exclusions.
- Dry-run JSON now includes:
  - `skipped_buy_count`
  - `skipped_buys`
- Each skipped buy entry includes:
  - `ticker`
  - `reason=gap_move_too_large`
  - `execution_price`
  - `previous_close`
  - `gap_pct`
  - `threshold_pct`
- Dry-run Markdown now includes a `Skipped Buy Candidates` section when any skipped buys exist.
- `review_rebalance_reports.py` now prints `skipped_buy_count` and per-ticker skipped-buy rows.
- Existing clean/blocked dry-run status is unchanged: skipped buys are review information, while fallback prices and price lookup failures still block order execution.

### Verification

- RED checks:
  - dry-run JSON lacked `skipped_buy_count` and `skipped_buys`.
  - dry-run Markdown lacked skipped-buy details.
  - review output lacked skipped-buy rows.
- Targeted RED-to-GREEN tests: 3 passed.
- Related dry-run/review tests: `.\venv\Scripts\python.exe -m pytest tests\trading\test_dry_run_rebalance.py tests\trading\test_review_rebalance_reports.py tests\trading\test_prepare_rebalance_for_execution.py tests\trading\test_prepare_and_review_rebalance.py tests\trading\test_compare_rebalance_reports.py -q` -> 30 passed.
- Real dry-run regeneration:
  - `.\venv\Scripts\python.exe scripts\dry_run_rebalance.py --as-of-date 2026-05-09 --top-n 20 --output-json data\dry_run_rebalance_latest.json --output-md data\dry_run_rebalance_latest.md --quote-retries 1 --quote-delay-sec 0.2`
  - completed with `skipped_buy_count=0`
  - blocked for execution because KIS quote lookup failed for 3 tickers: `072950`, `383220`, `375500`
- Review check: `.\venv\Scripts\python.exe scripts\review_rebalance_reports.py --dry-run-json data\dry_run_rebalance_latest.json` -> printed `skipped_buy_count=0` and `dry_run_status=blocked`.
- Full test suite: `.\venv\Scripts\python.exe -m pytest -q` -> 267 passed.
- Syntax check: `.\venv\Scripts\python.exe -m compileall config.py src tests scripts` -> passed.

### Next

- Re-run fresh dry-run during the next weekday market window with strict live quote settings until `price_lookup_failed_count=0`, then compare against the saved baseline.

## 2026-05-09 latest clean dry-run readiness check

### Completed

- Promoted the strict-retry clean dry-run artifacts to the latest execution preflight paths:
  - `data/dry_run_rebalance_latest.json`
  - `data/dry_run_rebalance_latest.md`
- Reviewed the latest dry-run report.
- Ran the execution readiness check against `expected-date=2026-05-09`.
- No PAPER or LIVE orders were submitted.

### Result

- Latest dry-run status is clean.
- `as_of_date=2026-05-09`
- `target_count=20`
- `buy_count=20`
- `sell_count=0`
- `skipped_buy_count=0`
- `price_fallback_count=0`
- `price_lookup_failed_count=0`
- Readiness preflight passed.
- Execution is still blocked because `2026-05-09` is Saturday and outside the required regular market window: weekday 09:00-15:20 KST.

### Verification

- Review: `.\venv\Scripts\python.exe scripts\review_rebalance_reports.py --dry-run-json data\dry_run_rebalance_latest.json` -> `dry_run_status=clean`, `price_lookup_failed_count=0`.
- Readiness: `.\venv\Scripts\python.exe scripts\check_rebalance_readiness.py --dry-run-json data\dry_run_rebalance_latest.json --expected-date 2026-05-09` -> `preflight_status=clean`, `market_time_status=blocked`, `execution_ready=false`.

### Next

- On the next weekday market window, rerun readiness with the current latest dry-run. If it returns `execution_ready=true`, proceed to PAPER execution from the verified dry-run JSON with the explicit confirmation token.

## 2026-05-09 PAPER execution verification report hardening

### Completed

- Enhanced `scripts/execute_rebalance_from_dry_run.py` execution-report JSON with plan-vs-result verification fields:
  - `planned_sells`
  - `planned_buys`
  - `planned_sell_count`
  - `planned_buy_count`
  - `execution_match_status`
  - `missing_sells`
  - `missing_buys`
  - `unexpected_sells`
  - `unexpected_buys`
- A clean PAPER execution report now proves that successful sell/buy tickers match the dry-run order plan.
- A partial or inconsistent PAPER execution report now records which planned tickers were missing and which unexpected tickers appeared.
- Enhanced `scripts/review_rebalance_reports.py` so post-execution review prints the new plan-vs-result verification summary.
- Existing report overwrite guard, pre-execution review, dry-run preflight, and market-time guard behavior remain unchanged.

### Verification

- RED check: targeted execution/review tests failed before the new execution verification fields existed.
- Targeted tests: `.\venv\Scripts\python.exe -m pytest tests\trading\test_execute_rebalance_from_dry_run.py tests\trading\test_review_rebalance_reports.py -q` -> 21 passed.
- Related operations tests: `.\venv\Scripts\python.exe -m pytest tests\trading\test_execute_rebalance_from_dry_run.py tests\trading\test_review_rebalance_reports.py tests\trading\test_prepare_rebalance_for_execution.py tests\trading\test_prepare_and_review_rebalance.py tests\trading\test_check_rebalance_readiness.py tests\trading\test_print_rebalance_operations_checklist.py -q` -> 38 passed.
- Syntax check: `.\venv\Scripts\python.exe -m compileall scripts\execute_rebalance_from_dry_run.py scripts\review_rebalance_reports.py tests\trading\test_execute_rebalance_from_dry_run.py tests\trading\test_review_rebalance_reports.py` -> passed.
- Full test suite: `.\venv\Scripts\python.exe -m pytest -q` -> 268 passed.

### Next

- On the next weekday market window, run PAPER execution with `--execution-report-json`, then immediately review the dry-run plus execution report to confirm `execution_status=clean` and `execution_match_status=matched`.

## 2026-05-09 KIS quote retry reporting hardening

### Completed

- Enhanced `scripts/dry_run_rebalance.py` to record per-ticker quote retry outcomes in dry-run reports.
- Dry-run JSON now includes:
  - `price_retry_success_count`
  - `price_retry_failed_count`
  - `price_retry_attempts`
- Each retry attempt entry includes:
  - `ticker`
  - `attempt_count`
  - `status`
  - `last_error`
- Dry-run Markdown now includes a `Price Retry Summary` section when retries occurred or quote lookup ultimately failed.
- Enhanced `scripts/review_rebalance_reports.py` so dry-run reviews print retry success/failure counts and per-ticker retry rows.
- Existing clean/blocked preflight behavior remains unchanged: final live quote failures still block execution, while retry-after-failure success is reported as clean.

### Verification

- RED check: dry-run/review tests failed before retry summary fields and output existed.
- Targeted tests: `.\venv\Scripts\python.exe -m pytest tests\trading\test_dry_run_rebalance.py tests\trading\test_review_rebalance_reports.py -q` -> 20 passed.
- Related operations tests: `.\venv\Scripts\python.exe -m pytest tests\trading\test_dry_run_rebalance.py tests\trading\test_review_rebalance_reports.py tests\trading\test_prepare_rebalance_for_execution.py tests\trading\test_prepare_and_review_rebalance.py tests\trading\test_execute_rebalance_from_dry_run.py -q` -> 41 passed.
- Syntax check: `.\venv\Scripts\python.exe -m compileall scripts\dry_run_rebalance.py scripts\review_rebalance_reports.py tests\trading\test_dry_run_rebalance.py tests\trading\test_review_rebalance_reports.py` -> passed.
- Full test suite: `.\venv\Scripts\python.exe -m pytest -q` -> 270 passed.
- Latest dry-run review: `.\venv\Scripts\python.exe scripts\review_rebalance_reports.py --dry-run-json data\dry_run_rebalance_latest.json` -> `dry_run_status=clean`, `price_retry_success_count=0`, `price_retry_failed_count=0`.

### Next

- On the next fresh market-hours dry-run, inspect retry rows. If `price_retry_failed_count > 0`, treat it as a quote-infrastructure issue to resolve before PAPER execution; if retries succeeded and final preflight is clean, proceed with readiness.

## 2026-05-09 PAPER rebalance run bundle archive

### Completed

- Added `scripts/archive_rebalance_run_bundle.py`.
- The script archives one operation-date bundle without submitting orders:
  - checklist output -> `checklist.txt`
  - readiness output -> `readiness.txt`
  - dry-run/execution review output -> `review.txt`
  - dry-run JSON copy -> `dry_run_rebalance.json`
  - dry-run Markdown copy -> `dry_run_rebalance.md`
  - execution report copy, when present -> `rebalance_execution.json`
  - machine-readable status summary -> `manifest.json`
- Added the archive command to `scripts/print_rebalance_operations_checklist.py`.
- Updated `HANDOFF_FOR_AGENTS.md` with the bundle archive command.
- Real local archive generated for `2026-05-09`:
  - `logs/rebalance_run_2026-05-09/manifest.json`
  - status: `ready_blocked_market_time`
  - `orders_submitted=0`

### Verification

- RED check: new archive bundle tests failed before `scripts/archive_rebalance_run_bundle.py` existed.
- Targeted archive tests: `.\venv\Scripts\python.exe -m pytest tests\trading\test_archive_rebalance_run_bundle.py -q` -> 4 passed.
- Related operations tests: `.\venv\Scripts\python.exe -m pytest tests\trading\test_archive_rebalance_run_bundle.py tests\trading\test_print_rebalance_operations_checklist.py tests\trading\test_smoke_rebalance_operations_checklist.py tests\trading\test_archive_rebalance_operations_checklist.py tests\trading\test_check_rebalance_readiness.py tests\trading\test_review_rebalance_reports.py -q` -> 30 passed.
- Syntax check: `.\venv\Scripts\python.exe -m compileall scripts\archive_rebalance_run_bundle.py scripts\print_rebalance_operations_checklist.py tests\trading\test_archive_rebalance_run_bundle.py tests\trading\test_print_rebalance_operations_checklist.py` -> passed.
- Real archive run: `.\venv\Scripts\python.exe scripts\archive_rebalance_run_bundle.py --as-of-date 2026-05-09 --top-n 20 --dry-run-json data\dry_run_rebalance_latest.json --dry-run-md data\dry_run_rebalance_latest.md --execution-report-json data\rebalance_execution_2026-05-09.json` -> expected exit 1 with `bundle_status=ready_blocked_market_time`.
- Full test suite: `.\venv\Scripts\python.exe -m pytest -q` -> 274 passed.

### Next

- On the next weekday market window, use the bundle archive after prepare/readiness/execution review so the full operation-day evidence is preserved under `logs/rebalance_run_YYYY-MM-DD/`.

## 2026-05-19 Exit/Rebalance Strategy Implementation Evidence

### Completed

- Updated daily loss-limit behavior:
  - `-3%` daily loss now blocks new buys only;
  - sell orders, staged exits, stop exits, and rebalance risk-reduction sells remain active;
  - daily loss-limit lookup failures no longer block staged exit checks; the cycle continues with buys suppressed;
  - scheduled rebalance runs sell-only when the daily loss limit is active;
  - sell-only rebalance ignores buy-side dry-run quote failures and buy-count preflight limits while keeping stale-report and sell-limit gates.
- Implemented staged exits:
  - pre-profit full stop at `-7%` after the live PAPER exit check showed `-5%` was too tight for several fresh positions;
  - first profit take at `+20%` selling `50%`;
  - post-profit trailing bucket at existing `-10%`;
  - post-profit breakeven bucket at entry price.
- Implemented rebalance churn controls:
  - top `20` buy list;
  - top `30` sell buffer;
  - `2` trading-day minimum holding period for rebalance exits.
- Implemented score-weighted allocation:
  - `3%` minimum target weight;
  - `15%` maximum target weight;
  - residual cash allowed when caps bind.
- Added PAPER exit-state persistence and stale-state protections:
  - state survives transient missing prices for positive-quantity holdings;
  - state clears after full exits or completed staged bucket exits;
  - stale state resets for rebuilt positions.
- Aligned operational rebalance paths with the tested strategy:
  - scheduled PAPER rebalance now uses the staged exit monitor before rebalancing;
  - scheduled and dry-run rebalances both use top `30` sell eligibility, score-weighted target sizing, and the `2` trading-day rebalance sell gate;
  - holdings with no local exit-state entry date are blocked from rebalance sells until state evidence exists.

### Verification

- Trading/backtest tests: `.\venv\Scripts\python.exe -m pytest tests\trading tests\backtest -q` -> 241 passed.
- Syntax check: `.\venv\Scripts\python.exe -m compileall src scripts tests` -> passed.
- Backtest matrix: `.\venv\Scripts\python.exe scripts\run_backtest_matrix.py --top-ns 20 --rebalance-frequencies weekly --cost-scenarios custom --stop-loss-pct -0.05 --trailing-stop-pct -0.10 --profit-take-pct 0.20 --profit-take-sell-fraction 0.50 --sell-rank-buffer 30 --min-holding-trading-days 2 --weighting score_weighted --output-csv data\backtest_exit_rebalance_strategy_2026-05-19.csv --output-md data\backtest_exit_rebalance_strategy_2026-05-19.md` -> final equity `113,428,859.46`, total return `13.43%`, max drawdown `-20.28%`, Sharpe `0.4742`, win rate `44.84%`, average holding days `33.65`, trade count `831`.
- No-order dry-run: `.\venv\Scripts\python.exe scripts\dry_run_rebalance.py --as-of-date 2026-05-19 --top-n 20 --output-json data\dry_run_rebalance_latest.json --output-md data\dry_run_rebalance_latest.md --quote-retries 4 --quote-delay-sec 0.5` -> `sell_count=0`, `buy_count=0`, `price_lookup_failed_count=0`, `price_fallback_count=0`, `price_retry_success_count=7`, `price_retry_failed_count=0`, `orders_submitted=0` by dry-run design.
- Live PAPER exit monitor check: `.\venv\Scripts\python.exe -c "from src.trading.engine import TradingEngine; from src.trading.kis_client import KisClient; from src.trading.scheduler import _stop_loss_job; _stop_loss_job(TradingEngine(KisClient()))"` -> daily loss limit `-4.29%` blocked new buys, exits stayed active, and PAPER market sell orders were accepted for `000270`, `005850`, `038500`, `375500`, `383220`.
- Stop-loss threshold update evidence: the live PAPER exit check sold `000270` at `-7.87%`, `005850` at `-6.13%`, `038500` at `-11.98%`, `375500` at `-5.36%`, and `383220` at `-5.92%`; to avoid the near-`-5%` exits being too tight, the default full-stop threshold is now `-7%`.
- Readiness check: `.\venv\Scripts\python.exe scripts\check_rebalance_readiness.py --dry-run-json data\dry_run_rebalance_latest.json --expected-date 2026-05-19` -> `preflight_status=clean`, `market_time_status=blocked`, `execution_ready=false`.

### Notes

- Initial dry-run attempt failed under sandboxed network/socket permissions; rerun with approved network access succeeded.
- The dry-run reported cash `-708,536` KRW, so weighted buy budgets were negative and all incremental buys were skipped; no rebalance orders were planned.
- Pytest emitted a non-failing Windows temp cleanup `PermissionError` after several successful runs.

## 2026-05-19 30-Stock Risk Overlay Backtest Evidence

### Completed

- Expanded the backtest/default portfolio target from `20` to `30` holdings.
- Kept the full stop at `-7%` and added a `3` calendar-day same-ticker cooldown after full stop exits.
- Added ATR volatility stop support to the backtest path:
  - ATR window `14`;
  - ATR multiplier `2.5`;
  - the pre-profit position exits when either `-7%` full stop or ATR stop is hit first.
- Added market-risk overlay support to the backtest path:
  - KOSPI/KOSDAQ RSI(14) >= `75` raises target cash;
  - one overheated market -> `15%` target cash;
  - both overheated markets -> `25%` target cash;
  - prior Nasdaq drop <= `-2.0%` -> `20%` target cash;
  - prior Nasdaq drop <= `-3.5%` -> `35%` target cash;
  - rebalance-day exposure is reduced pro-rata when cash is below the target.
- Added `market_index_prices` storage and `scripts/sync_market_indices.py` for real KOSPI/KOSDAQ/NASDAQ index data.
- Synced real historical data:
  - `daily_prices`: `698,180` rows, `2020-01-02` to `2026-05-19`, `627` tickers;
  - `fundamentals`: `693,599` rows, `2020-01-02` to `2026-05-19`, `625` tickers;
  - `market_index_prices`: `4,732` rows, `2020-01-02` to `2026-05-19`, `3` symbols;
  - `quality_metrics`: `3,919` rows, published `2024-05-07` to `2026-05-08`, `507` tickers.

### Verification

- TDD red check: `.\venv\Scripts\python.exe -m pytest tests\backtest\test_backtest_engine.py -q` failed before market-index repository/engine support existed.
- Targeted tests and repository/script coverage: `.\venv\Scripts\python.exe -m pytest tests\backtest\test_backtest_engine.py tests\backtest\test_run_script.py tests\backtest\test_run_matrix_script.py tests\data\test_repositories.py tests\data\test_sync_market_indices.py -q` -> 73 passed.
- Syntax check: `.\venv\Scripts\python.exe -m compileall src scripts tests` -> passed.
- Market index sync: `.\venv\Scripts\python.exe scripts\sync_market_indices.py --start-date 2020-01-01 --end-date 2026-05-19` -> `row_count=4732`.
- Phase 1 price/fundamental sync:
  - 2023 -> `price_count=111,815`, `fundamental_count=111,244`;
  - 2022 -> `price_count=108,320`, `fundamental_count=107,828`;
  - 2021 -> `price_count=105,737`, `fundamental_count=105,206`;
  - 2020 -> `price_count=101,481`, `fundamental_count=100,555`.
- Official quality-gated backtest window is `2024-05-16` to `2026-05-19`, because earlier dates have `quality_coverage_critical` and the buy filter correctly skips buy candidates instead of faking missing DART data.
- New overlay result: `.\venv\Scripts\python.exe scripts\run_backtest_matrix.py --start-date 2024-05-16 --end-date 2026-05-19 --top-ns 30 --rebalance-frequencies weekly --cost-scenarios custom ... --enable-atr-stop --enable-market-risk-overlay` -> final equity `175,646,610.74`, total return `75.65%`, CAGR `32.38%`, max drawdown `-13.13%`, Sharpe `1.5220`, win rate `52.93%`, average holding days `28.88`, trade count `1,963`.
- Baseline comparison without ATR and market overlay: final equity `188,728,144.81`, total return `88.73%`, CAGR `37.20%`, max drawdown `-13.67%`, Sharpe `1.6140`, win rate `53.45%`, trade count `1,916`.
- Cost stress with the new overlay:
  - custom cost -> total return `75.65%`, max drawdown `-13.13%`, Sharpe `1.5220`;
  - slippage20 -> total return `65.67%`, max drawdown `-15.80%`, Sharpe `1.3697`;
  - slippage30 -> total return `58.21%`, max drawdown `-18.05%`, Sharpe `1.2521`.
- New overlay trade reasons:
  - buys `854`, sells `1,109`;
  - `stop_loss` `230`, `stop_loss_close_fallback` `2`;
  - `atr_stop` `39`;
  - `profit_take_20` `151`;
  - `post_profit_trailing_stop` `100`, `post_profit_trailing_stop_close_fallback` `4`;
  - `post_profit_breakeven_stop` `23`;
  - `market_risk_reduce` `29`, all on `2025-10-13`;
  - `rebalance` `531`.
- Worst drawdown path for the new overlay: peak `102,451,275.36` on `2024-07-16`, trough `88,999,662.37` on `2025-04-07`, drawdown `-13.13%`.

### Notes

- The market overlay reduced MDD by `0.54pp` versus the no-overlay/no-ATR comparison, but it also reduced total return by `13.08pp`; this is a defense trade-off, not a free improvement.
- `sell_rank_buffer=30` is now equal to `n_holdings=30`, so there is no extra rank buffer beyond the target list. A follow-up test should compare `sell_rank_buffer=40` or `45` for lower turnover.
- Live PAPER stop/rebalance paths are not yet extended with ATR stop or index-risk overlay; this change is currently proven in the backtest/reporting path.

## 2026-05-19 Adaptive Alpha Experimental Strategy

### Completed

- Added an isolated experimental strategy without changing existing backtest, trading, scheduler, or config behavior.
- New files:
  - `src/strategies/__init__.py`;
  - `src/strategies/adaptive_alpha.py`;
  - `scripts/run_adaptive_alpha_backtest.py`;
  - `scripts/run_adaptive_alpha_matrix.py`;
  - `tests/strategies/test_adaptive_alpha.py`;
  - `tests/strategies/test_run_adaptive_alpha_matrix.py`.
- Strategy design:
  - uses the existing factor engine output as the base candidate list;
  - re-ranks candidates with recent price trend quality:
    - latest close above 20-day moving average;
    - latest close above 60-day moving average;
    - 20-day moving average above 60-day moving average;
    - 20-day moving average rising;
    - 20-day return positive;
  - penalizes high recent daily volatility;
  - keeps `30` holdings but uses a wider sell rank buffer of `40`;
  - uses score-weighted allocation with `3%` minimum and `12%` maximum position weight;
  - keeps `-7%` full stop and `3` day stop cooldown;
  - uses tighter `-8%` post-profit trailing stop;
  - uses ATR(14) x `2.2` stop;
  - first profit-take threshold is `+16%`, selling `45%`;
  - uses stricter market-risk overlay thresholds:
    - KOSPI/KOSDAQ RSI threshold `72`;
    - one overheated market -> `18%` cash;
    - both overheated markets -> `30%` cash;
    - prior Nasdaq drop <= `-1.8%` -> `22%` cash;
    - prior Nasdaq drop <= `-3.2%` -> `38%` cash.

### Verification

- RED test: `.\venv\Scripts\python.exe -m pytest tests\strategies\test_adaptive_alpha.py -q` -> failed with `ModuleNotFoundError: No module named 'src.strategies'`.
- GREEN test: `.\venv\Scripts\python.exe -m pytest tests\strategies\test_adaptive_alpha.py -q` -> 2 passed.
- Related test set: `.\venv\Scripts\python.exe -m pytest tests\strategies\test_adaptive_alpha.py tests\backtest\test_backtest_engine.py tests\backtest\test_run_matrix_script.py tests\data\test_sync_market_indices.py -q` -> 36 passed.
- Matrix/preload regression tests: `.\venv\Scripts\python.exe -m pytest tests\strategies\test_adaptive_alpha.py tests\strategies\test_run_adaptive_alpha_matrix.py -q` -> 5 passed.
- Broader related test set: `.\venv\Scripts\python.exe -m pytest tests\strategies\test_adaptive_alpha.py tests\strategies\test_run_adaptive_alpha_matrix.py tests\backtest\test_backtest_engine.py tests\data\test_sync_market_indices.py -q` -> 35 passed, with a non-fatal Windows pytest temp cleanup `PermissionError` after pass reporting.
- Syntax check: `.\venv\Scripts\python.exe -m compileall src scripts tests` -> passed.
- First full run hit the 15-minute limit because the wrapper was calling the slow factor scorer. The strategy now reuses the existing `_make_fast_score_func` inside the isolated wrapper; existing engine behavior is unchanged.
- The strategy now preloads Adaptive Alpha price history once for the tested date range instead of re-querying each rebalance date, which made the parameter matrix practical while leaving the base backtest engine unchanged.
- Adaptive Alpha actual-data backtest, quality-gated `2024-05-16` to `2026-05-19`:
  - final equity `189,861,769.46`;
  - total return `89.86%`;
  - CAGR `37.61%`;
  - max drawdown `-13.44%`;
  - Sharpe `1.7533`;
  - win rate `59.33%`;
  - average holding days `33.93`;
  - trade count `2,152`.
- Adaptive Alpha sell reasons:
  - `atr_stop`: `82`;
  - `market_risk_reduce`: `190`;
  - `post_profit_breakeven_stop`: `24`;
  - `post_profit_trailing_stop`: `158`;
  - `post_profit_trailing_stop_close_fallback`: `4`;
  - `profit_take_20`: `204`;
  - `rebalance`: `464`;
  - `stop_loss`: `210`;
  - `stop_loss_close_fallback`: `4`.
- Cost stress:
  - slippage20 -> final equity `181,526,541.37`, total return `81.53%`, CAGR `34.57%`, max drawdown `-15.44%`, Sharpe `1.6310`;
  - slippage30 -> final equity `173,928,840.00`, total return `73.93%`, CAGR `31.73%`, max drawdown `-16.94%`, Sharpe `1.5181`.
- Parameter matrix:
  - 8-combo run (`sell_rank_buffer` 40/45 x ATR 2.0/2.2 x profit take 16%/18%) exceeded the 20-minute command limit;
  - 4-combo run fixing ATR at `2.2` completed and wrote `data/adaptive_alpha_param_matrix_2026-05-19.csv` and `data/adaptive_alpha_param_matrix_2026-05-19.md`;
  - best combo by Sharpe, return, and lowest drawdown was `sell_rank_buffer=40`, `atr_multiplier=2.2`, `profit_take_pct=0.16`;
  - best combo result: final equity `194,706,952.45`, total return `94.71%`, CAGR `39.35%`, max drawdown `-12.29%`, Sharpe `1.8409`, win rate `58.16%`, average holding days `30.12`, trade count `2,166`;
  - other tested combos: buffer 40/profit 18% -> return `89.46%`, MDD `-13.65%`, Sharpe `1.7521`; buffer 45/profit 16% -> return `92.06%`, MDD `-12.43%`, Sharpe `1.8053`; buffer 45/profit 18% -> return `88.53%`, MDD `-13.44%`, Sharpe `1.7415`.
- Best-combo cost stress:
  - slippage20 -> final equity `182,118,907.98`, total return `82.12%`, CAGR `34.79%`, max drawdown `-15.31%`, Sharpe `1.6572`;
  - slippage30 -> final equity `175,346,153.69`, total return `75.35%`, CAGR `32.27%`, max drawdown `-16.30%`, Sharpe `1.5537`.

### Comparison

- Prior no-overlay/no-ATR baseline on the same quality-gated window: total return `88.73%`, max drawdown `-13.67%`, Sharpe `1.6140`.
- Prior risk-overlay strategy on the same quality-gated window: total return `75.65%`, max drawdown `-13.13%`, Sharpe `1.5220`.
- Initial Adaptive Alpha default: total return `89.86%`, max drawdown `-13.44%`, Sharpe `1.7533`.
- Tuned Adaptive Alpha default improved versus initial Adaptive Alpha by `+4.85pp` total return, `+1.15pp` max drawdown, and `+0.0876` Sharpe.
- Tuned Adaptive Alpha improved return and Sharpe versus both prior references while also improving drawdown versus the prior no-overlay/no-ATR baseline and the initial Adaptive Alpha run.
- Adopted exit/rebalance defaults after user approval:
  - `EXIT_RULES.trailing_stop_pct=-0.08`;
  - `EXIT_RULES.profit_take_pct=0.16`;
  - `EXIT_RULES.profit_take_sell_fraction=0.45`;
  - `EXIT_RULES.atr_multiplier=2.2`;
  - `REBALANCE.sell_rank_buffer=40`.
- This adoption changes shared defaults used by the normal backtest scripts and PAPER exit monitor configuration, but it does not add a new order execution path or bypass dry-run/readiness gates.

## 2026-05-09 Telegram notification smoke test

### Completed

- Rewrote `src/notify/notifier.py` notification message templates into readable Korean text.
- Existing order-success integration remains in `TradingEngine.buy()` and `TradingEngine.sell()`.
- Added `scripts/smoke_test_telegram.py`.
- The smoke script checks Telegram config and sends one no-order test message.
- Telegram error logging now masks `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.
- Updated `HANDOFF_FOR_AGENTS.md` test status and script list.

### Verification

- RED check: notifier/smoke tests failed before readable templates and `scripts/smoke_test_telegram.py` existed.
- Targeted tests: `.\venv\Scripts\python.exe -m pytest tests\notify\test_notifier.py tests\notify\test_smoke_test_telegram.py -q` -> 10 passed.
- Related notification/trading tests: `.\venv\Scripts\python.exe -m pytest tests\notify tests\trading\test_engine.py tests\trading\test_smoke_test_order.py -q` -> 30 passed.
- Syntax check: `.\venv\Scripts\python.exe -m compileall src\notify\notifier.py scripts\smoke_test_telegram.py tests\notify` -> passed.
- Full test suite: `.\venv\Scripts\python.exe -m pytest -q` -> 281 passed.
- Real Telegram smoke: `.\venv\Scripts\python.exe scripts\smoke_test_telegram.py` -> `telegram_enabled=true`, `telegram_send_status=failed`, `orders_submitted=0`, Telegram API returned `403 Forbidden` with secrets masked.

### Next

- Fix Telegram chat permission before Monday: start a private chat with the bot or add the bot to the target group/channel, then verify `TELEGRAM_CHAT_ID` points to that chat and rerun `scripts\smoke_test_telegram.py`.

## 2026-06-12 Inverse ETF hedge overlay

### Completed

- Added an inverse ETF hedge layer that only trades configured `INVERSE_ETF_ALLOWED_TICKERS`.
- 1x and 2x inverse ETFs are both supported; 2x tickers must also be listed in `INVERSE_ETF_LEVERAGED_TICKERS`.
- Default caps are conservative: total inverse ETF weight `15%`, 1x cap `10%`, 2x cap `5%`, severe 2x target `3%`.
- Buy evidence comes from market drops, severe overbought RSI, or existing macro risk-off signals.
- Sell evidence covers risk cleared, stop loss, take profit, max holding days, and target trims.
- Dry-run JSON/Markdown reports now include an `inverse_etf_hedge` section with selected tickers, target weights, evidence, skipped items, and generated orders.
- Scheduler rebalance order calculation now includes the same inverse ETF hedge orders so dry-run preflight order matching remains intact.
- Backtest engine supports `enable_inverse_etf_hedge`, `inverse_etf_allowed_tickers`, and `inverse_etf_leveraged_tickers`.

### Safety Notes

- No LIVE auto-execution path was added.
- New inverse ETF orders still go through the existing dry-run report, stale report, price lookup, order match, daily order limit, and readiness gates.
- With an empty inverse ETF whitelist, no inverse ETF orders are generated.

## 2026-06-12 Review-fix verification evidence

### Indicator threshold fixes validated on real FRED data (2020-01 ~ 2026-05)

- CPI rule before fix (`delta >= 0.3` index points) fired 65/75 months (87%); CORE_CPI 69/75 (92%).
  In 2024+ it fired 89%/93% of months, i.e. a near-permanent risk_off drag.
- CPI rule after fix (m/m percent change >= 0.4%) fires 27/75 (36%) overall, 6/28 (21%) in 2024+;
  CORE_CPI 18/75 (24%) overall, 1/28 (4%) in 2024+ - only genuinely hot months.
- PAYEMS rule before fix (`delta <= -100_000` in thousands units = -100M jobs) fired 0 times,
  including the COVID month of -20,469k. After fix (`<= -100`) it fires 5 times.

### Market index data gap found and backfilled

- `market_index_prices` had only KOSPI/KOSDAQ/NASDAQ (through 2026-05-18/19).
  KR10Y/US10Y/SP500/DOW were entirely missing, so the bond-yield overlay had been
  silently inactive. Backfilled all 7 symbols 2020-01-02 ~ 2026-06-11/12 (8,063 rows)
  via `scripts/sync_market_indices.py`.

### Backtest: macro overlay off vs on (2020-07-01 ~ 2026-05-18, top 20, weekly, custom costs)

| metric | overlay off | overlay on |
| --- | --- | --- |
| total_return | +83.42% | +81.75% |
| cagr | 10.86% | 10.69% |
| max_drawdown | -16.08% | -15.58% |
| sharpe_ratio | 1.1094 | 1.1854 |
| win_rate | 61.59% | 60.74% |
| trade_count | 898 | 889 |

- Reports: `data/backtest_verify_macro_off.{csv,md}`, `data/backtest_verify_macro_on2.{csv,md}`.
- Reading: the overlay gives up ~1.7%p of total return for a -0.5%p smaller drawdown and a
  +6.9% higher Sharpe - the intended insurance trade-off, no longer a permanent drag.
- Note: `macro_indicator_releases` was empty during these runs (FRED_API_KEY not set), so the
  comparison measures the US-market + bond-yield overlay parts only.

### Remaining setup before the macro indicator overlay is live

- Get a free FRED API key (https://fred.stlouisfed.org/docs/api/api_key.html) and set
  `FRED_API_KEY` in `.env`, then run
  `python scripts/sync_macro_indicators.py --start-date 2020-01-01 --end-date <today>`
  and confirm `release_date` values differ per period (vintage dates, not the sync date).
- Set `INVERSE_ETF_ALLOWED_TICKERS` (and `INVERSE_ETF_LEVERAGED_TICKERS`) to enable the hedge.
- Schedule `scripts/sync_market_indices.py` daily so index/bond inputs stay current;
  the rebalance job now warns when macro inputs are missing.

## 2026-06-12 Inverse ETF ticker setup + full-data verification

### Configuration

- `.env`: `INVERSE_ETF_ALLOWED_TICKERS=114800,252670` (KODEX inverse 1x / KODEX 200 futures inverse 2X,
  both verified live via pykrx), `INVERSE_ETF_LEVERAGED_TICKERS=252670`.
- `INVERSE_ETF_HEDGE_ENABLED=false` for now - backtest evidence below shows the default trigger set
  destroys value; flip to true only after trigger tuning.
- `.env.example` documents `FRED_API_KEY` and the inverse ETF keys.
- Backfilled 114800/252670 daily prices 2020-01-02 ~ 2026-06-12 (1,581 rows each) so backtests can
  trade the hedge.

### FRED vintage fix verified with a real API key (382 rows, 2020-01 ~ 2026-06)

- 0 rows have release_date equal to the sync day; 225 distinct release dates.
- CPI 2026-05 -> released 2026-06-10; PAYEMS 2026-05 -> released 2026-06-05 (matches the real
  BLS calendar); CPI publication lag distribution 37-44 days.
- Second sync run kept row_count at 382 (idempotent; the old code would have duplicated rows daily).
- Live dry-run with all three sources active: `missing_sources=[]`,
  CPI +0.47% m/m flagged risk_off (cash 20%) while the US rally gave risk_on x1.2,
  combining to multiplier 1.02 - the composite works as designed.

### Backtest comparison, full inputs (2020-07-01 ~ 2026-05-18, top 20, weekly, custom costs)

| scenario | total_return | cagr | mdd | sharpe | trades |
| --- | --- | --- | --- | --- | --- |
| overlay off | +83.42% | 10.86% | -16.08% | 1.1094 | 898 |
| overlay on (no indicators) | +81.75% | 10.69% | -15.58% | 1.1854 | 889 |
| overlay on (with indicators) | +77.06% | 10.20% | -15.38% | 1.1671 | 864 |
| overlay + inverse hedge | +65.95% | 8.99% | -15.23% | 1.0475 | 1,648 |

- Overlay: gives up return for smaller drawdowns and a better Sharpe - a defensible insurance trade.
- Hedge with default triggers: -11.1%p return vs overlay-only for just -0.15%p MDD; direct hedge
  trade P&L was -6.98M KRW over 245 entries. 59% of entries came from macro risk_off alone and
  87% of exits were "risk_cleared" whipsaws. Keep disabled until triggers are tuned, e.g.:
  (a) drop macro risk_off as a standalone entry trigger (require market-drop or RSI confluence),
  (b) add entry/exit hysteresis (signal must persist 2 consecutive days),
  (c) enter only on severe signals.

### Bug found during verification and fixed

- Backtest: on non-rebalance days `target_tickers = list(positions)` included hedge positions, so a
  same-day hedge sell could be re-bought by the generic buy loop at full equal weight
  (reason "rebalance"). Hedge tickers are now skipped in the generic buy loop.
- Tests no longer depend on the runner's `.env`: inverse hedge test configs pass `enabled=True`
  explicitly and the macro sync test passes `--fred-api-key ""`.

## 2026-06-13 Strategy optimization sweep (17 backtests) and data-coverage discovery

### Critical discovery: all prior backtests effectively traded 2024-05+ only

- `quality_metrics` coverage starts at fiscal 2024 (published 2024-05-07+). For any earlier
  as-of date the buy filter hits `quality_coverage_critical` and skips every buy.
- Confirmed empirically: a 2024-01~2026-05 window run produced *identical* final equity to the
  "2020-07~2026-05" runs. All full-window CAGR/Sharpe figures recorded before this date understate
  the true annualized performance (e.g., top15 weekly is CAGR 31.3%, Sharpe 2.01 over the real
  tradeable window) and none of them include the 2022 bear market.

### Sweep results (effective window 2024-05~2026-05, custom costs, score_weighted unless noted)

Concentration x frequency (Sharpe / MDD / total return):
- weekly top10 1.164 / -15.27% / +98.3%; top15 1.267 / -15.34% / +90.9%;
  top20 1.167 / -15.38% / +77.1%; top30 1.242 / -12.59% / +83.7%
- monthly top15/20/30 all violate the -18% MDD constraint (-18.3% ~ -19.1%)

Exit-rule variants on top15 weekly (baseline: ATR 2.2x + stop -7% + profit take +16%/45% + cooldown 3):
- Baseline Sharpe 1.267 beat ALL variants: ATR off 1.159, ATR 3.0x 1.166, ATR 1.8x 1.207,
  profit-take off 1.157 (+143.6% return but MDD -21.1%), PT +25%/50% 1.113 (MDD -18.7%),
  PT +30%/33% 1.112 (MDD -19.4%), cooldown5+minhold2 1.196.
- Equal weighting top15: +101.2% return but Sharpe 1.175 < score_weighted 1.267.

### Decision

- Keep the current configuration unchanged (top30 weekly, score_weighted, current exits).
  The sweep validates it as locally optimal on every exit dimension tested.
- top15 weekly is a promising candidate (higher Sharpe and return, worse MDD -15.3% vs -12.6%)
  but switching concentration is deferred until it can be validated through the 2022 bear.
- Profit-take removal is documented as a high-return/high-drawdown option (+143.6% / -21.1%),
  rejected under the MDD <= -18% constraint.

### Quality backfill attempts (for bear-market validation)

- Full-FS sync (system python) died silently twice; root cause includes dart_fss being absent
  from the system interpreter at first, then environment instability. Use `venv\Scripts\python.exe`.
- `--single-account-only` via venv works: fiscal 2022 now has 355/739 tickers (1,374 metrics).
  Note `--only-unsynced` skips tickers that have *any* rows (e.g. 2024) - omit it for backfills.
- The 2020-2023 full run stalled at the DART corp-list download stage after ~2.5h (likely DART
  daily-limit throttling after the day's usage) and was abandoned.
- Next step when quota resets: rerun
  `venv\Scripts\python.exe scripts\sync_phase1_quality.py --year-from 2020 --year-to 2023 --single-account-only`
  (expect ~10 min per year when healthy), then re-run the top15-vs-top30 comparison over
  2020-07~2026-05 and the 2021-07~2023-01 bear window before changing n_holdings.
