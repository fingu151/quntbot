from __future__ import annotations

import json
from pathlib import Path


def test_export_supplemental_source_candidates_prefills_from_briefs(tmp_path: Path):
    from scripts.export_supplemental_source_candidates import export_supplemental_source_candidates

    queue_path = tmp_path / "queue.json"
    briefs_path = tmp_path / "briefs.json"
    output_path = tmp_path / "candidates.json"
    csv_path = tmp_path / "candidates.csv"
    markdown_path = tmp_path / "candidates.md"
    queue_path.write_text(
        json.dumps(
            {
                "items": [
                    {
                        "ticker": "123456",
                        "primary_action": "supplemental_source_needed",
                        "latest_report_date": "2026-01-02",
                        "reasons": ["missing_sections", "weak_source_quality"],
                        "missing_sections": ["risk"],
                        "source_quality": "title_or_sparse",
                        "confidence": 0.47,
                        "report_count": 1,
                        "report_age_days": 10,
                    },
                    {
                        "ticker": "999999",
                        "primary_action": "latest_report_not_found",
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    briefs_path.write_text(
        json.dumps(
            {
                "tickers": [
                    {
                        "ticker": "123456",
                        "headline": "테스트 리포트",
                        "source_reports": [
                            {
                                "report_date": "2026-01-02",
                                "broker": "예시증권",
                                "title": "테스트기업 (123456/Not Rated) 성장 점검",
                                "url": "https://example.com/report.pdf",
                            }
                        ],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    payload = export_supplemental_source_candidates(
        queue_path=queue_path,
        ticker_brief_path=briefs_path,
        json_output_path=output_path,
        csv_output_path=csv_path,
        markdown_output_path=markdown_path,
    )

    assert payload["summary"]["candidate_count"] == 1
    assert payload["summary"]["missing_section_counts"] == {"risk": 1}
    candidate = payload["candidates"][0]
    assert candidate["name"] == "테스트기업"
    assert candidate["latest_broker"] == "예시증권"
    assert candidate["latest_url"] == "https://example.com/report.pdf"
    assert "테스트기업" in candidate["search_query"]
    assert output_path.exists()
    assert csv_path.read_text(encoding="utf-8-sig").startswith("ticker,name")
    assert "123456" in markdown_path.read_text(encoding="utf-8")


def test_export_supplemental_source_candidates_can_include_latest_not_found_followups(tmp_path: Path):
    from scripts.export_supplemental_source_candidates import export_supplemental_source_candidates

    queue_path = tmp_path / "queue.json"
    briefs_path = tmp_path / "briefs.json"
    followup_path = tmp_path / "latest.json"
    output_path = tmp_path / "candidates.json"
    queue_path.write_text(json.dumps({"items": []}), encoding="utf-8")
    briefs_path.write_text(json.dumps({"tickers": []}), encoding="utf-8")
    followup_path.write_text(
        json.dumps(
            {
                "items": [
                    {
                        "ticker": "005930",
                        "name": "Samsung Electronics",
                        "primary_action": "latest_report_not_found",
                        "latest_report_date": "2026-02-01",
                        "confidence": 1.0,
                        "report_count": 2,
                        "report_age_days": 100,
                        "latest_broker": "Broker A",
                        "latest_title": "Old Samsung report",
                        "latest_url": "https://example.test/old.pdf",
                        "search_query": "Samsung Electronics 005930 latest securities report",
                        "next_step": "Check another public source.",
                    },
                    {"ticker": "000660", "primary_action": "latest_report_needed"},
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    payload = export_supplemental_source_candidates(
        queue_path=queue_path,
        ticker_brief_path=briefs_path,
        latest_report_followup_queue_path=followup_path,
        json_output_path=output_path,
        csv_output_path=None,
        markdown_output_path=None,
    )

    assert payload["summary"]["candidate_count"] == 1
    assert payload["summary"]["candidate_source_counts"] == {"latest_report_followup_queue": 1}
    candidate = payload["candidates"][0]
    assert candidate["ticker"] == "005930"
    assert candidate["candidate_source"] == "latest_report_followup_queue"
    assert candidate["missing_sections"] == ["latest_report"]
    assert candidate["latest_url"] == "https://example.test/old.pdf"
    assert candidate["search_query"] == "Samsung Electronics 005930 latest securities report"
    assert {item["provider"] for item in candidate["provider_searches"]} >= {
        "hankyung_consensus",
        "mirae_asset",
        "kiwoom_public_research",
        "kiwoom_public_research_naver",
        "yuanta_pdf_naver",
    }
    search_urls = {item["provider"]: item["url"] for item in candidate["provider_searches"]}
    assert search_urls["kiwoom_public_research"].startswith("https://www.bing.com/search?q=")
    assert search_urls["kiwoom_public_research_naver"].startswith("https://search.naver.com/search.naver?query=")
