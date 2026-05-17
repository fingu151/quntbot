from __future__ import annotations

from argparse import Namespace
from datetime import date

from sqlalchemy import select

from scripts.ingest_supplemental_research_reports import (
    SupplementalReportIngestResult,
    ingest_supplemental_reports,
    parse_args,
    run,
)
from src.data.database import create_tables, get_engine, session_scope
from src.data.models import ResearchReportAnalysis, ResearchReportBrief, ResearchReportSignal


def _report(**overrides):
    row = {
        "report_date": "2026-05-14",
        "ticker": "007340",
        "source": "kiwoom_research",
        "region": "domestic",
        "broker": "Kiwoom Securities",
        "title": "DN Automotive margin recovery",
        "source_url": "https://example.test/dn-auto",
        "rating": "Buy",
        "rating_score": 0.6,
        "target_price": 120000,
        "raw_score": 0.4,
        "report_type": "stock_report",
        "headline": "DN Automotive margin recovery report added.",
        "opinion": "positive",
        "stock_view": "Report view is positive.",
        "earnings": "Margin recovery is the main earnings point.",
        "industry": "Auto parts demand remains relevant.",
        "new_business": "",
        "valuation": "Target price implies upside.",
        "risks": "Auto demand and FX are key risks.",
        "summary": "DN Automotive supplemental report summary.",
        "investment_opinion": "positive",
        "buy_thesis": "Margin recovery and target price upside.",
        "sell_or_risk_thesis": "Auto demand and FX risk.",
        "growth_drivers": "Auto parts demand.",
        "earnings_drivers": "Margin recovery.",
        "valuation_view": "Target price upside.",
        "target_price_rationale": "Broker target price.",
        "risk_factors": "Auto demand and FX.",
        "evidence_terms": "margin recovery, target price",
        "confidence": 0.55,
    }
    row.update(overrides)
    return row


def test_parse_args_accepts_supplemental_input_and_database_url():
    args = parse_args(["--input", "reports.json", "--database-url", "sqlite:///:memory:"])

    assert args.input == "reports.json"
    assert args.database_url == "sqlite:///:memory:"


def test_ingest_supplemental_reports_upserts_signal_analysis_and_brief():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)

    result = ingest_supplemental_reports(
        engine,
        [
            _report(),
            _report(
                headline="Updated DN Automotive report.",
                summary="Updated supplemental summary.",
                confidence=0.7,
            ),
        ],
    )

    with session_scope(engine) as session:
        signals = session.scalars(select(ResearchReportSignal)).all()
        analyses = session.scalars(select(ResearchReportAnalysis)).all()
        briefs = session.scalars(select(ResearchReportBrief)).all()

    assert result == SupplementalReportIngestResult(
        input_count=2,
        valid_count=2,
        skipped_count=0,
        signal_rows_stored=2,
        analysis_rows_stored=2,
        brief_rows_stored=2,
    )
    assert len(signals) == 1
    assert signals[0].report_date == date(2026, 5, 14)
    assert signals[0].ticker == "007340"
    assert len(analyses) == 1
    assert analyses[0].summary == "Updated supplemental summary."
    assert analyses[0].body_text_status == "supplemental_summary"
    assert len(briefs) == 1
    assert briefs[0].headline == "Updated DN Automotive report."
    assert briefs[0].source_quality == "supplemental_summary"
    assert briefs[0].confidence == 0.7


def test_run_prints_counts_without_orders(capsys):
    engine = get_engine("sqlite:///:memory:")

    def engine_factory(database_url):
        assert database_url == "sqlite:///:memory:"
        return engine

    def report_loader(path):
        assert path == "reports.json"
        return [_report(), {"ticker": "005930"}]

    exit_code = run(
        Namespace(input="reports.json", database_url="sqlite:///:memory:"),
        engine_factory=engine_factory,
        report_loader=report_loader,
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "supplemental_research_report_input_count=2" in captured.out
    assert "supplemental_research_report_valid_count=1" in captured.out
    assert "supplemental_research_report_skipped_count=1" in captured.out
    assert "supplemental_research_report_signal_rows_stored=1" in captured.out
    assert "supplemental_research_report_analysis_rows_stored=1" in captured.out
    assert "supplemental_research_report_brief_rows_stored=1" in captured.out
    assert "orders_submitted=0" in captured.out


def test_run_treats_empty_supplemental_file_as_successful_noop(capsys):
    engine = get_engine("sqlite:///:memory:")

    exit_code = run(
        Namespace(input="empty.json", database_url=None),
        engine_factory=lambda database_url: engine,
        report_loader=lambda path: [],
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "supplemental_research_report_input_count=0" in captured.out
    assert "supplemental_research_report_valid_count=0" in captured.out
    assert "orders_submitted=0" in captured.out
