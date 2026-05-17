from __future__ import annotations

import json
from pathlib import Path


def test_export_research_brief_qa_sample_mixes_complete_and_queue_items(tmp_path: Path):
    from scripts.export_research_brief_qa_sample import export_research_brief_qa_sample

    briefs_path = tmp_path / "briefs.json"
    queue_path = tmp_path / "queue.json"
    output_path = tmp_path / "qa.json"
    markdown_path = tmp_path / "qa.md"
    briefs_path.write_text(
        json.dumps(
            {
                "tickers": [
                    {
                        "ticker": "005930",
                        "latest_report_date": "2026-05-14",
                        "headline": "Complete brief shows stable earnings growth.",
                        "sections": {
                            "stock_view": "Business outlook remains constructive.",
                            "growth": "Demand growth remains visible.",
                            "earnings": "Earnings recovery continues.",
                            "risk": "FX volatility remains the key risk.",
                        },
                        "quality": {"source_quality": "full_text", "confidence": 0.9, "report_count": 3},
                        "source_reports": [{"broker": "Broker A", "title": "Complete title"}],
                    },
                    {
                        "ticker": "000660",
                        "latest_report_date": "2026-01-01",
                        "headline": "Needs review brief shows stable earnings growth.",
                        "sections": {
                            "stock_view": "Business outlook remains constructive.",
                            "growth": "Demand growth remains visible.",
                            "earnings": "Earnings recovery continues.",
                            "risk": "FX volatility remains the key risk.",
                        },
                        "quality": {"source_quality": "partial_text", "confidence": 0.55, "report_count": 1},
                        "source_reports": [{"broker": "Broker B", "title": "Review title"}],
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    queue_path.write_text(
        json.dumps(
            {
                "items": [
                    {
                        "ticker": "000660",
                        "primary_action": "latest_report_not_found",
                        "reasons": ["stale_report"],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    payload = export_research_brief_qa_sample(
        ticker_brief_path=briefs_path,
        queue_path=queue_path,
        json_output_path=output_path,
        markdown_output_path=markdown_path,
        sample_size=2,
    )

    assert payload["summary"]["sample_count"] == 2
    assert {item["qa_bucket"] for item in payload["items"]} == {"complete", "latest_report_not_found"}
    review_item = next(item for item in payload["items"] if item["ticker"] == "000660")
    assert review_item["issue_category"] == "source_refresh_candidate"
    assert review_item["needs_source_refresh"] == "true"
    assert review_item["needs_section_rewrite"] == ""
    assert "stale_or_missing_latest_report" in review_item["auto_issue_reasons"]
    assert payload["summary"]["auto_flag_count"] == 1
    assert payload["summary"]["needs_source_refresh_count"] == 1
    assert output_path.exists()
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "Complete brief" in markdown
    assert "Needs review brief" in markdown
    assert "QA issue category" in markdown


def test_export_research_brief_qa_sample_flags_broken_section_text(tmp_path: Path):
    from scripts.export_research_brief_qa_sample import export_research_brief_qa_sample

    briefs_path = tmp_path / "briefs.json"
    queue_path = tmp_path / "queue.json"
    output_path = tmp_path / "qa.json"
    briefs_path.write_text(
        json.dumps(
            {
                "tickers": [
                    {
                        "ticker": "005930",
                        "latest_report_date": "2026-05-14",
                        "headline": "005930: YoY) grows but fragment remains",
                        "sections": {
                            "stock_view": "YoY) grows but fragment remains",
                            "growth": "Growth sentence is valid.",
                            "earnings": "Earnings sentence is valid.",
                            "risk": "Risk sentence is valid.",
                        },
                        "quality": {"source_quality": "full_text", "confidence": 0.9, "report_count": 3},
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    queue_path.write_text(json.dumps({"items": []}), encoding="utf-8")

    payload = export_research_brief_qa_sample(
        ticker_brief_path=briefs_path,
        queue_path=queue_path,
        json_output_path=output_path,
        markdown_output_path=None,
        sample_size=1,
    )

    item = payload["items"][0]
    assert item["issue_category"] == "section_rewrite_candidate"
    assert item["needs_section_rewrite"] == "true"
    assert "headline:starts_mid_sentence" in item["auto_issue_reasons"]
    assert payload["summary"]["needs_section_rewrite_count"] == 1


def test_section_quality_reason_does_not_flag_valid_go_prefix_sentence():
    from scripts.export_research_brief_qa_sample import _section_quality_reason

    text = "고정비 절감 효과를 가져갈 수 있을 것이고, 다품종 소량 생산체제에 따른 높은 대당 이익 또한 기대된다."

    assert _section_quality_reason(text) == ""
