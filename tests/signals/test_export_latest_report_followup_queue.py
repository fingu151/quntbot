from __future__ import annotations

import json
from pathlib import Path


def test_export_latest_report_followup_queue_prioritizes_portfolio_and_low_confidence(tmp_path: Path):
    from scripts.export_latest_report_followup_queue import export_latest_report_followup_queue

    queue_path = tmp_path / "queue.json"
    briefs_path = tmp_path / "briefs.json"
    snapshot_path = tmp_path / "snapshot.json"
    output_path = tmp_path / "latest.json"
    csv_path = tmp_path / "latest.csv"
    markdown_path = tmp_path / "latest.md"
    queue_path.write_text(
        json.dumps(
            {
                "items": [
                    {
                        "ticker": "005930",
                        "primary_action": "latest_report_not_found",
                        "latest_report_date": "2026-01-01",
                        "confidence": 0.4,
                        "report_count": 1,
                        "report_age_days": 100,
                    },
                    {
                        "ticker": "000660",
                        "primary_action": "latest_report_not_found",
                        "latest_report_date": "2026-04-01",
                        "confidence": 0.9,
                        "report_count": 5,
                        "report_age_days": 44,
                    },
                    {"ticker": "035720", "primary_action": "supplemental_source_needed"},
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
                        "ticker": "005930",
                        "headline": "Samsung brief",
                        "source_reports": [{"broker": "Broker A", "title": "Samsung title"}],
                    },
                    {
                        "ticker": "000660",
                        "headline": "Hynix brief",
                        "source_reports": [{"broker": "Broker B", "title": "Hynix title"}],
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    snapshot_path.write_text(
        json.dumps({"positions": [{"ticker": "000660", "name": "SK Hynix"}]}, ensure_ascii=False),
        encoding="utf-8",
    )

    payload = export_latest_report_followup_queue(
        queue_path=queue_path,
        ticker_brief_path=briefs_path,
        snapshot_path=snapshot_path,
        json_output_path=output_path,
        csv_output_path=csv_path,
        markdown_output_path=markdown_path,
    )

    assert payload["summary"]["item_count"] == 2
    assert payload["summary"]["portfolio_item_count"] == 1
    assert payload["items"][0]["ticker"] == "000660"
    assert payload["items"][0]["priority_bucket"] == "portfolio"
    assert payload["items"][1]["priority_bucket"] == "stale_low_confidence"
    assert output_path.exists()
    assert csv_path.read_text(encoding="utf-8-sig").startswith("priority_rank,ticker")
    assert "000660" in markdown_path.read_text(encoding="utf-8")
