from __future__ import annotations

import json
from pathlib import Path


def _source(**overrides):
    row = {
        "report_date": "2026-05-16",
        "ticker": "005930",
        "source": "yuanta_pdf_naver",
        "region": "domestic",
        "broker": "yuanta_pdf_naver",
        "title": "Samsung candidate",
        "source_url": "https://example.test/samsung.pdf",
        "source_type": "pdf",
        "raw_score": 0.0,
    }
    row.update(overrides)
    return row


def test_verify_supplemental_sources_keeps_rows_when_ticker_is_in_body(tmp_path: Path):
    from scripts.verify_supplemental_research_sources import verify_supplemental_research_sources

    input_path = tmp_path / "draft.json"
    verified_path = tmp_path / "verified.json"
    rejected_path = tmp_path / "rejected.json"
    input_path.write_text(json.dumps([_source()]), encoding="utf-8")

    result = verify_supplemental_research_sources(
        input_path=input_path,
        verified_output_path=verified_path,
        rejected_output_path=rejected_path,
        text_fetcher=lambda source: "삼성전자(005930) 실적 개선과 서버 수요 회복을 점검한다.",
    )

    verified = json.loads(verified_path.read_text(encoding="utf-8"))
    rejected = json.loads(rejected_path.read_text(encoding="utf-8"))
    assert result["verified_count"] == 1
    assert result["rejected_count"] == 0
    assert verified[0]["verification_status"] == "ticker_found_in_body"
    assert "005930" in verified[0]["body_text"]
    assert rejected == []


def test_verify_supplemental_sources_rejects_rows_without_ticker_in_body(tmp_path: Path):
    from scripts.verify_supplemental_research_sources import verify_supplemental_research_sources

    input_path = tmp_path / "draft.json"
    verified_path = tmp_path / "verified.json"
    rejected_path = tmp_path / "rejected.json"
    input_path.write_text(json.dumps([_source()]), encoding="utf-8")

    result = verify_supplemental_research_sources(
        input_path=input_path,
        verified_output_path=verified_path,
        rejected_output_path=rejected_path,
        text_fetcher=lambda source: "다른 종목 리포트 본문입니다.",
    )

    verified = json.loads(verified_path.read_text(encoding="utf-8"))
    rejected = json.loads(rejected_path.read_text(encoding="utf-8"))
    assert result["verified_count"] == 0
    assert result["rejected_count"] == 1
    assert verified == []
    assert rejected[0]["reason"] == "ticker_not_found_in_body"
