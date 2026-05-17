from __future__ import annotations


def test_build_portfolio_research_coverage_splits_missing_stale_and_clean():
    from scripts.report_portfolio_research_coverage import build_portfolio_research_coverage

    snapshot = {
        "positions": [
            {"ticker": "007340", "name": "DN Automotive"},
            {"ticker": "000990", "name": "DB HiTek"},
            {"ticker": "005930", "name": "Samsung Electronics"},
        ]
    }
    ticker_brief_artifact = {
        "tickers": [
            {
                "ticker": "000990",
                "latest_report_date": "2026-01-21",
                "sections": {
                    "stock_view": "Foundry utilization remains high.",
                    "growth": "ASP rebound starts later.",
                    "earnings": "Margins recover.",
                    "risk": "Merger overhang remains.",
                },
                "quality": {"source_quality": "full_text", "confidence": 1.0, "report_count": 1},
            },
            {
                "ticker": "005930",
                "latest_report_date": "2026-05-14",
                "sections": {
                    "stock_view": "HBM competitiveness recovers.",
                    "growth": "HBM demand improves.",
                    "earnings": "Margins recover.",
                    "risk": "Supply growth concern remains.",
                },
                "quality": {"source_quality": "full_text", "confidence": 1.0, "report_count": 5},
            },
        ]
    }
    db_counts = {
        "007340": {"signals": 0, "analyses": 0, "briefs": 0},
        "000990": {"signals": 1, "analyses": 1, "briefs": 1},
        "005930": {"signals": 5, "analyses": 5, "briefs": 5},
    }

    report = build_portfolio_research_coverage(
        snapshot,
        ticker_brief_artifact,
        db_counts=db_counts,
        as_of_date="2026-05-15",
        stale_days=45,
    )

    assert report["summary"] == {
        "holding_count": 3,
        "matched_brief_count": 2,
        "missing_brief_count": 1,
        "stale_brief_count": 1,
        "needs_review_count": 0,
        "clean_count": 1,
    }
    assert report["items"][0]["ticker"] == "007340"
    assert report["items"][0]["status"] == "missing_brief"
    assert report["items"][1]["ticker"] == "000990"
    assert report["items"][1]["status"] == "stale_brief"
    assert report["items"][1]["missing_sections"] == []
    assert report["items"][1]["source_quality"] == "full_text"
    assert report["items"][2]["ticker"] == "005930"
    assert report["items"][2]["status"] == "ok"


def test_build_portfolio_research_coverage_marks_sparse_and_section_gaps():
    from scripts.report_portfolio_research_coverage import build_portfolio_research_coverage

    snapshot = {"positions": [{"ticker": "078930", "name": "GS"}]}
    ticker_brief_artifact = {
        "tickers": [
            {
                "ticker": "078930",
                "latest_report_date": "2026-05-14",
                "sections": {"stock_view": "Holding company view."},
                "quality": {"source_quality": "supplemental_summary", "confidence": 0.45, "report_count": 1},
            },
        ]
    }

    report = build_portfolio_research_coverage(
        snapshot,
        ticker_brief_artifact,
        as_of_date="2026-05-15",
    )

    item = report["items"][0]
    assert item["status"] == "needs_review"
    assert item["missing_sections"] == ["growth", "earnings", "risk"]
    assert "weak_source_quality" in item["reasons"]
    assert "low_confidence" in item["reasons"]
