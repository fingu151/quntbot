from __future__ import annotations

import json
from pathlib import Path


def test_generate_research_report_ticker_briefs_writes_rows_to_json(tmp_path: Path):
    from scripts.generate_research_report_ticker_briefs import main

    output_path = tmp_path / "ticker_briefs.json"

    exit_code = main(
        [
            "--output",
            str(output_path),
            "--sample-row",
            json.dumps(
                {
                    "ticker": "005930",
                    "report_date": "2026-05-14",
                    "source": "hankyung_consensus",
                    "broker": "Broker A",
                    "title": "Samsung memory upcycle",
                    "summary": "Memory demand improves.",
                    "investment_opinion": "positive",
                    "buy_thesis": "AI server demand supports HBM shipments.",
                    "growth_drivers": "HBM demand and foundry utilization improve.",
                    "earnings_drivers": "DRAM margin recovery continues.",
                    "valuation_view": "Upside remains versus peer multiples.",
                    "risk_factors": "FX volatility can pressure margins.",
                    "new_business": "Advanced packaging expansion adds momentum.",
                    "confidence": 0.82,
                    "body_text_status": "full_text",
                    "evidence_terms": "industry_outlook, full_text, brief-rule-v3",
                    "source_url": "https://example.test/new.pdf",
                }
            ),
        ]
    )

    assert exit_code == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["summary"]["ticker_count"] == 1
    assert payload["tickers"][0]["ticker"] == "005930"
    assert payload["llm"]["status"] == "disabled"


def test_generate_research_report_ticker_briefs_accepts_llm_status_metadata(tmp_path: Path):
    from scripts.generate_research_report_ticker_briefs import main

    output_path = tmp_path / "ticker_briefs.json"

    exit_code = main(
        [
            "--output",
            str(output_path),
            "--llm-status",
            "ready",
            "--sample-row",
            json.dumps(
                {
                    "ticker": "005930",
                    "report_date": "2026-05-14",
                    "title": "Samsung memory upcycle",
                    "summary": "Memory demand improves.",
                    "investment_opinion": "positive",
                    "buy_thesis": "AI server demand supports HBM shipments.",
                    "growth_drivers": "HBM demand and foundry utilization improve.",
                    "confidence": 0.82,
                    "body_text_status": "full_text",
                }
            ),
        ]
    )

    assert exit_code == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["llm"]["status"] == "ready"
    assert payload["tickers"][0]["quality"]["llm_status"] == "ready"
