# Research Report Body Analysis Design

## Purpose

quntbot already collects Korean research report metadata and converts titles,
ratings, target prices, and simple sentiment words into a small auxiliary factor.
The next step is to collect actual report body text, extract the analyst's
investment logic, and store a compact Korean summary that future agents can read
without re-opening every PDF.

This feature is a read-only market-intelligence layer. It must not submit orders,
change holdings, or bypass existing PAPER dry-run and readiness gates.

## Agent Orchestration

Lead agent:
- Research Brief Agent

Supporting agents:
- Signal Agent: provider parsing, PDF/text extraction, parser fixtures.
- Data and DB Agent: schema, row counts, source coverage, upserts.
- Strategy and Factor Agent: how the structured analysis affects ranking.
- Trading Safety Agent: confirms this remains non-order market intelligence.
- Test and Verification Agent: targeted parser, reader, repository, and script tests.
- Docs and Handoff Agent: records source contracts and operational commands.

Agent rules:
- Treat every provider response and PDF as untrusted input.
- Keep source evidence attached to every stored analysis.
- Do not store raw PDF body text by default.
- Do not convert analyst summaries directly into order execution.
- Mark weak or missing body extraction as a data-quality state, not as a neutral
  investment signal.

## Current State

Existing implementation:
- `config.py` defines `RESEARCH_REPORT` with default source
  `hankyung_consensus`, broker `한경 컨센서스`, and URL
  `https://markets.hankyung.com/consensus`.
- `src/signals/research_report_parser.py` parses Korean report list rows,
  including Hankyung Nuxt data and Mirae Asset public `document.write` rows.
- `src/signals/research_report_reader.py` can fetch HTML and optionally fetch
  linked PDF text through `pypdf`.
- `scripts/sync_korean_research_reports.py` stores metadata and prints
  `orders_submitted=0`.
- `research_report_signals` rows are already folded into
  `research_report_score` as a small auxiliary factor.

Observed local DB state before this design:
- `research_report_signals` total rows: `10`.
- Latest report date: `2026-05-13`.
- Existing rows are from source `hankyung_consensus`, broker `한경 컨센서스`.

Public source checks on 2026-05-14:
- Hankyung consensus entry page:
  `https://markets.hankyung.com/consensus`.
- Mirae Asset public investment-info entry page:
  `https://securities.miraeasset.com/bbsmain.jsp`.

## Required Behavior

The system should:
- Collect report metadata from Hankyung and Mirae Asset public sources.
- Fetch linked PDF body text when available.
- Extract a structured Korean analysis from body text, not only the title.
- Store why the analyst is positive, neutral, or negative.
- Preserve the original metadata score for compatibility.
- Add body analysis as explainability first; score changes remain conservative.
- Expose telemetry so agents can tell whether a report was fully analyzed,
  partially analyzed, or only title-scored.

## Data Contract

Add a separate table instead of widening `research_report_signals`.

Table: `research_report_analyses`

Unique key:
- `report_signal_id`

Fields:
- `report_signal_id`: FK to `research_report_signals.id`.
- `ticker`
- `report_date`
- `source`
- `broker`
- `title`
- `source_url`
- `body_text_status`: one of `not_requested`, `not_pdf`, `fetch_failed`,
  `empty`, `extracted`, `login_required`, `not_pdf_response`,
  `analysis_failed`.
- `body_text_chars`: extracted body-text length, or `0`.
- `summary`: concise Korean summary.
- `investment_opinion`: one of `positive`, `neutral`, `negative`, `mixed`,
  `unknown`.
- `buy_thesis`: why the report supports buying or positive review.
- `sell_or_risk_thesis`: why the report warns against buying, suggests selling,
  or highlights risk.
- `growth_drivers`: demand, orders, capacity, market expansion, product cycle.
- `earnings_drivers`: revenue, margin, cost, operating profit, EPS.
- `valuation_view`: target price, valuation multiple, upside or overvaluation.
- `target_price_rationale`: reason for target price change or maintenance.
- `risk_factors`: operational, macro, demand, cost, valuation, execution risks.
- `evidence_terms`: compact comma-separated source terms used by the analyzer.
- `analysis_version`: starts at `rule-v1`.
- `confidence`: `0.0` to `1.0`.
- `created_at`, `updated_at`.

Raw body text is not stored by default. This reduces DB bloat and avoids turning
licensed PDF contents into a local corpus. Agents can re-fetch a source URL when
necessary and permitted.

## Analysis Approach

Version `rule-v1` should be deterministic and testable:
- Normalize whitespace and split Korean/English body text into sentences.
- Classify sentences into buckets with domain keyword sets:
  - buy or positive thesis
  - sell, neutral, or risk thesis
  - growth drivers
  - earnings drivers
  - valuation view
  - target price rationale
  - risk factors
- Summarize each bucket with the best one or two short sentences.
- Infer `investment_opinion` from rating, raw score, and extracted risk/positive
  balance.
- Compute confidence from body availability, bucket coverage, rating presence,
  and target-price evidence.

LLM-based summarization can be added later as a separate `analysis_version`
behind an explicit provider interface. The first implementation should not
require network LLM access to pass tests or run a local smoke.

## Source Collection

The existing single-source script remains valid for Hankyung. To add Mirae Asset
cleanly, use explicit CLI options first:

```powershell
.\venv\Scripts\python.exe scripts\sync_korean_research_reports.py --url https://markets.hankyung.com/consensus --source hankyung_consensus --broker "한경 컨센서스" --include-pdf-text
.\venv\Scripts\python.exe scripts\sync_korean_research_reports.py --url https://securities.miraeasset.com/bbsmain.jsp --source mirae_asset --broker "미래에셋증권" --include-pdf-text
```

Scheduler multi-source polling can follow after the single-source script stores
both providers correctly in local smoke checks.

## Failure Handling

Provider and PDF failures should not crash the scheduler:
- HTML fetch failure stores no rows and returns `0`.
- PDF fetch failure keeps the metadata row and writes analysis status
  `fetch_failed`.
- Login-gated provider PDFs keep the metadata row and write analysis status
  `login_required`.
- URLs that look like PDFs but return HTML or another non-PDF response write
  status `not_pdf_response`.
- Empty PDF extraction writes status `empty`.
- Non-PDF URLs write status `not_pdf`.
- Parser success with body extraction writes status `extracted`.
- Analysis exceptions write status `analysis_failed` and leave metadata intact.

Every script must continue to print `orders_submitted=0`.

## Testing

Targeted tests:
- Parser tests for Hankyung and Mirae Asset list formats.
- Analyzer tests for buy thesis, risk thesis, valuation, target-price rationale,
  and confidence.
- Repository tests for analysis upsert and lookup.
- Reader tests proving PDF body text creates analysis rows and PDF failures keep
  metadata rows.
- Script tests proving telemetry is printed and no orders are submitted.

Verification commands:

```powershell
.\venv\Scripts\python.exe -m pytest tests\signals\test_research_report_analysis.py tests\signals\test_research_report_reader.py tests\data\test_repositories.py tests\signals\test_sync_korean_research_reports.py -q
.\venv\Scripts\python.exe -m py_compile src\signals\research_report_analysis.py src\signals\research_report_reader.py src\data\models.py src\data\repositories.py scripts\sync_korean_research_reports.py
```

## Out Of Scope

- Automatic order execution from analyst opinion.
- LIVE trading changes.
- Storing full raw PDF text by default.
- Paid or authenticated provider scraping.
- Claims that analyst reports are correct or sufficient investment advice.
