from __future__ import annotations

import json
from pathlib import Path

from scripts.export_research_quality_queue import (
    classify_quality_issue,
    export_quality_queue,
)


def test_classify_quality_issue_prioritizes_actionable_source_work():
    assert (
        classify_quality_issue(
            {
                "ticker": "200470",
                "reasons": [
                    "missing_sections",
                    "stale_report",
                    "low_confidence",
                    "weak_source_quality",
                ],
                "source_quality": "title_or_sparse",
                "missing_sections": ["stock_view", "growth", "earnings", "risk"],
                "report_age_days": 107,
            }
        )
        == "supplemental_source_needed"
    )
    assert (
        classify_quality_issue(
            {
                "ticker": "092730",
                "reasons": ["missing_sections", "stale_report"],
                "source_quality": "full_text",
                "missing_sections": ["risk"],
                "report_age_days": 107,
            }
        )
        == "latest_report_needed"
    )
    assert (
        classify_quality_issue(
            {
                "ticker": "092730",
                "reasons": ["stale_report"],
                "source_quality": "full_text",
                "missing_sections": [],
                "report_age_days": 107,
            },
            refreshed_through="2026-05-15",
        )
        == "latest_report_not_found"
    )
    assert (
        classify_quality_issue(
            {
                "ticker": "478340",
                "reasons": ["stale_report", "weak_source_quality"],
                "source_quality": "title_or_sparse",
                "missing_sections": [],
                "report_age_days": 95,
            },
            refreshed_through="2026-05-15",
        )
        == "weak_or_stale_source_only"
    )
    assert (
        classify_quality_issue(
            {
                "ticker": "064850",
                "reasons": ["missing_sections"],
                "source_quality": "full_text",
                "missing_sections": ["valuation", "risk"],
                "report_age_days": 10,
            }
        )
        == "parser_section_backfill_candidate"
    )


def test_export_quality_queue_writes_json_and_markdown(tmp_path: Path):
    artifact = {
        "generated_at": "2026-05-15T09:00:00+09:00",
        "tickers": [
            {
                "ticker": "005930",
                "latest_report_date": "2026-05-14",
                "sections": {
                    "stock_view": "AI server demand supports HBM shipments.",
                    "growth": "HBM demand improves.",
                    "earnings": "DRAM margin recovery continues.",
                    "risk": "FX volatility can pressure margins.",
                },
                "quality": {"source_quality": "full_text", "confidence": 0.82, "report_count": 3},
            },
            {
                "ticker": "200470",
                "latest_report_date": "2026-01-28",
                "sections": {},
                "quality": {
                    "source_quality": "title_or_sparse",
                    "confidence": 0.49,
                    "report_count": 1,
                },
            },
            {
                "ticker": "092730",
                "latest_report_date": "2026-01-28",
                "sections": {"stock_view": "Sales recover."},
                "quality": {"source_quality": "full_text", "confidence": 0.8, "report_count": 1},
            },
            {
                "ticker": "478340",
                "latest_report_date": "2026-02-09",
                "sections": {
                    "stock_view": "Platform data demand improves.",
                    "growth": "Government orders add growth.",
                    "earnings": "Sales pipeline expands.",
                    "risk": "Execution delay can weigh.",
                },
                "quality": {
                    "source_quality": "title_or_sparse",
                    "confidence": 0.8,
                    "report_count": 1,
                },
            },
        ],
    }
    artifact_path = tmp_path / "briefs.json"
    json_output = tmp_path / "queue.json"
    md_output = tmp_path / "queue.md"
    artifact_path.write_text(json.dumps(artifact), encoding="utf-8")

    result = export_quality_queue(
        artifact_path=artifact_path,
        output_path=json_output,
        markdown_output_path=md_output,
        now_iso="2026-05-15T00:00:00+00:00",
        refreshed_through="2026-05-15",
    )

    payload = json.loads(json_output.read_text(encoding="utf-8"))
    markdown = md_output.read_text(encoding="utf-8")
    assert result["summary"]["issue_count"] == 3
    assert payload["summary"]["complete_count"] == 1
    assert payload["summary"]["action_counts"] == {
        "latest_report_not_found": 1,
        "supplemental_source_needed": 1,
        "weak_or_stale_source_only": 1,
    }
    assert payload["items"][0]["primary_action"] == "supplemental_source_needed"
    assert payload["items"][1]["primary_action"] == "latest_report_not_found"
    assert payload["items"][2]["primary_action"] == "weak_or_stale_source_only"
    assert "supplemental_source_needed" in markdown
    assert "orders_submitted=0" not in markdown
