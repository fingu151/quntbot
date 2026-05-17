from __future__ import annotations

from argparse import Namespace
from datetime import date

from sqlalchemy import select

from scripts.ingest_supplemental_research_sources import (
    SupplementalSourceIngestResult,
    _extract_pdf_links,
    fetch_source_text,
    ingest_supplemental_research_sources,
    parse_args,
    run,
)
from src.data.database import create_tables, get_engine, session_scope
from src.data.models import ResearchReportAnalysis, ResearchReportBrief, ResearchReportSignal


def _source(**overrides):
    row = {
        "report_date": "2026-05-12",
        "ticker": "000990",
        "source": "supplemental_public_source",
        "region": "domestic",
        "broker": "DS Investment",
        "title": "DB HiTek NDR review",
        "source_url": "https://example.test/db-hitek",
        "rating": "Buy",
        "rating_score": 0.6,
        "target_price": 210000,
        "raw_score": 0.6,
    }
    row.update(overrides)
    return row


def test_parse_args_accepts_source_input_and_database_url():
    args = parse_args(["--input", "sources.json", "--database-url", "sqlite:///:memory:"])

    assert args.input == "sources.json"
    assert args.database_url == "sqlite:///:memory:"


def test_ingest_supplemental_research_sources_fetches_analyzes_and_briefs():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)

    result = ingest_supplemental_research_sources(
        engine,
        [_source()],
        text_fetcher=lambda source: (
            "DB HiTek foundry ASP increase improves earnings. "
            "Target price upside remains meaningful. "
            "Display subsidiary weakness is a risk."
        ),
    )

    with session_scope(engine) as session:
        signal = session.scalars(select(ResearchReportSignal)).one()
        analysis = session.scalars(select(ResearchReportAnalysis)).one()
        brief = session.scalars(select(ResearchReportBrief)).one()

    assert result == SupplementalSourceIngestResult(
        input_count=1,
        valid_count=1,
        skipped_count=0,
        signal_rows_stored=1,
        analysis_rows_stored=1,
        brief_rows_stored=1,
    )
    assert signal.ticker == "000990"
    assert signal.report_date == date(2026, 5, 12)
    assert analysis.body_text_status == "extracted"
    assert analysis.body_text_chars > 0
    assert brief.ticker == "000990"
    assert brief.brief_version == "brief-rule-v3"
    assert brief.source_quality in {"title_or_sparse", "partial_text", "full_text"}


def test_run_prints_counts_without_orders(capsys):
    engine = get_engine("sqlite:///:memory:")

    exit_code = run(
        Namespace(input="sources.json", database_url=None),
        engine_factory=lambda database_url: engine,
        source_loader=lambda path: [_source(), {"ticker": "005850"}],
        text_fetcher=lambda source: "SL earnings improve, but FX is a risk.",
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "supplemental_source_input_count=2" in captured.out
    assert "supplemental_source_valid_count=1" in captured.out
    assert "supplemental_source_skipped_count=1" in captured.out
    assert "supplemental_source_brief_rows_stored=1" in captured.out
    assert "orders_submitted=0" in captured.out


def test_ingest_supplemental_sources_extracts_risk_from_uncertainty_text():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)

    ingest_supplemental_research_sources(
        engine,
        [
            _source(
                ticker="095610",
                title="TES equipment upcycle",
                report_date="2026-05-13",
                source_url="https://example.test/tes",
            )
        ],
        text_fetcher=lambda source: (
            "TES should benefit from Samsung and SK Hynix capex expansion. "
            "BSD equipment visibility improves earnings. "
            "The key risk is uncertainty around capex execution speed and NAND recovery timing."
        ),
    )

    with session_scope(engine) as session:
        brief = session.scalars(select(ResearchReportBrief)).one()

    assert "uncertainty" in brief.risks


def test_ingest_supplemental_sources_uses_inline_body_text_before_fetching():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)

    ingest_supplemental_research_sources(
        engine,
        [
            _source(
                ticker="095610",
                title="TES risk supplement",
                report_date="2026-05-13",
                source_url="https://example.test/tes",
                body_text=(
                    "TES benefits from capex expansion. "
                    "The key risk is uncertainty around customer investment execution speed."
                ),
            )
        ],
        text_fetcher=lambda source: "",
    )

    with session_scope(engine) as session:
        brief = session.scalars(select(ResearchReportBrief)).one()

    assert "uncertainty" in brief.risks


def test_extract_pdf_links_resolves_relative_supported_pdf_urls():
    html = """
<html><body>
  <a href="/analysis/downpdf?report_idx=123">PDF</a>
  <a href="https://example.test/report.pdf">PDF 2</a>
  <a href="/notice.html">HTML</a>
</body></html>
"""

    assert _extract_pdf_links(html, "https://consensus.hankyung.com/analysis/list") == [
        "https://consensus.hankyung.com/analysis/downpdf?report_idx=123",
        "https://example.test/report.pdf",
    ]


def test_fetch_source_text_appends_linked_pdf_text(monkeypatch):
    monkeypatch.setattr(
        "scripts.ingest_supplemental_research_sources.fetch_html",
        lambda url: "<html><body>HTML summary<a href='/report.pdf'>PDF</a></body></html>",
    )
    monkeypatch.setattr(
        "scripts.ingest_supplemental_research_sources.fetch_pdf_text",
        lambda url: "PDF body earnings risk text",
    )

    text = fetch_source_text({"source_url": "https://example.test/page.html", "source_type": "html"})

    assert "HTML summary" in text
    assert "PDF body earnings risk text" in text
