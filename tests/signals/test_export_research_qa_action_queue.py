from __future__ import annotations

import json
from pathlib import Path


def test_export_research_qa_action_queue_groups_auto_flags(tmp_path: Path):
    from scripts.export_research_qa_action_queue import export_research_qa_action_queue

    qa_sample_path = tmp_path / "qa_sample.json"
    json_output_path = tmp_path / "qa_action_queue.json"
    markdown_output_path = tmp_path / "qa_action_queue.md"
    qa_sample_path.write_text(
        json.dumps(
            {
                "items": [
                    {
                        "ticker": "005930",
                        "qa_bucket": "complete",
                        "latest_report_date": "2026-05-14",
                        "headline": "YoY) fragment needs rewrite",
                        "needs_section_rewrite": "true",
                        "needs_source_refresh": "",
                        "issue_category": "section_rewrite_candidate",
                        "auto_issue_reasons": ["headline:starts_mid_sentence"],
                        "sections": {"stock_view": "YoY) fragment remains", "risk": "Risk is stated."},
                        "source_reports": [{"broker": "Broker A", "title": "Samsung report"}],
                    },
                    {
                        "ticker": "000660",
                        "qa_bucket": "latest_report_not_found",
                        "latest_report_date": "2026-01-01",
                        "headline": "Needs a newer public source",
                        "needs_section_rewrite": "",
                        "needs_source_refresh": "true",
                        "issue_category": "source_refresh_candidate",
                        "auto_issue_reasons": ["stale_or_missing_latest_report"],
                        "sections": {"stock_view": "View exists.", "risk": "Risk exists."},
                    },
                    {
                        "ticker": "035420",
                        "qa_bucket": "complete",
                        "latest_report_date": "2026-05-10",
                        "headline": "Complete item",
                        "needs_section_rewrite": "",
                        "needs_source_refresh": "",
                        "issue_category": "",
                        "auto_issue_reasons": [],
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    payload = export_research_qa_action_queue(
        qa_sample_path=qa_sample_path,
        json_output_path=json_output_path,
        markdown_output_path=markdown_output_path,
    )

    assert payload["summary"] == {
        "sample_count": 3,
        "action_item_count": 2,
        "section_rewrite_count": 1,
        "source_refresh_count": 1,
        "source_refresh_attempted_no_new_source_count": 0,
    }
    assert [item["ticker"] for item in payload["items"]] == ["005930", "000660"]
    rewrite_item = payload["items"][0]
    assert rewrite_item["actions"] == ["section_rewrite"]
    assert rewrite_item["primary_action"] == "section_rewrite"
    assert "scripts.reanalyze_research_report_bodies --ticker 005930" in rewrite_item["suggested_commands"][0]
    refresh_item = payload["items"][1]
    assert refresh_item["actions"] == ["source_refresh"]
    assert refresh_item["primary_action"] == "source_refresh"
    assert "IncludeSupplementalDiscovery" in refresh_item["suggested_commands"][0]
    assert json_output_path.exists()
    markdown = markdown_output_path.read_text(encoding="utf-8")
    assert "005930" in markdown
    assert "000660" in markdown
    assert "section_rewrite" in markdown


def test_export_research_qa_action_queue_suppresses_completed_source_refresh_attempts(tmp_path: Path):
    from scripts.export_research_qa_action_queue import export_research_qa_action_queue

    qa_sample_path = tmp_path / "qa_sample.json"
    discovery_path = tmp_path / "discovery.json"
    json_output_path = tmp_path / "qa_action_queue.json"
    qa_sample_path.write_text(
        json.dumps(
            {
                "items": [
                    {
                        "ticker": "000520",
                        "qa_bucket": "latest_report_not_found",
                        "latest_report_date": "2026-02-20",
                        "headline": "Needs source refresh",
                        "needs_section_rewrite": "",
                        "needs_source_refresh": "true",
                        "issue_category": "source_refresh_candidate",
                        "auto_issue_reasons": ["stale_or_missing_latest_report"],
                    },
                    {
                        "ticker": "000640",
                        "qa_bucket": "complete",
                        "latest_report_date": "2026-03-27",
                        "headline": "Still needs rewrite",
                        "needs_section_rewrite": "true",
                        "needs_source_refresh": "true",
                        "issue_category": "section_rewrite_candidate",
                        "auto_issue_reasons": ["headline:starts_mid_sentence"],
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    discovery_path.write_text(
        json.dumps(
            {
                "summary": {"candidate_count": 1, "checked_url_count": 8, "usable_source_count": 0},
                "results": [
                    {
                        "ticker": "000520",
                        "checks": [{"status": "provider_list_reachable"}],
                        "discovered_sources": [],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    payload = export_research_qa_action_queue(
        qa_sample_path=qa_sample_path,
        source_discovery_path=discovery_path,
        json_output_path=json_output_path,
        markdown_output_path=None,
    )

    assert payload["summary"]["action_item_count"] == 1
    assert payload["summary"]["source_refresh_attempted_no_new_source_count"] == 1
    assert [item["ticker"] for item in payload["items"]] == ["000640"]
    assert payload["items"][0]["actions"] == ["section_rewrite", "source_refresh"]
