from __future__ import annotations

import json
from pathlib import Path


def test_discover_candidates_records_reachable_pdf_and_html_pdf_links(tmp_path: Path):
    from scripts.discover_supplemental_research_sources import discover_supplemental_research_sources

    candidate_path = tmp_path / "candidates.json"
    output_path = tmp_path / "discovery.json"
    candidate_path.write_text(
        json.dumps(
            {
                "candidates": [
                    {
                        "ticker": "005930",
                        "name": "Samsung Electronics",
                        "latest_report_date": "2026-02-01",
                        "latest_title": "Old Samsung report",
                        "provider_searches": [
                            {
                                "provider": "direct_pdf",
                                "label": "Direct PDF",
                                "kind": "candidate_url",
                                "url": "https://example.test/report.pdf",
                            },
                            {
                                "provider": "html_with_pdf",
                                "label": "HTML",
                                "kind": "candidate_url",
                                "url": "https://example.test/page",
                            },
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    def fetcher(url: str):
        if url.endswith("report.pdf"):
            return {
                "status_code": 200,
                "content_type": "application/pdf",
                "text": "%PDF body",
                "final_url": url,
            }
        return {
            "status_code": 200,
            "content_type": "text/html",
            "text": "<html><a href='/linked.pdf'>PDF</a></html>",
            "final_url": url,
        }

    payload = discover_supplemental_research_sources(
        candidate_path=candidate_path,
        output_path=output_path,
        fetcher=fetcher,
    )

    assert payload["summary"]["candidate_count"] == 1
    assert payload["summary"]["checked_url_count"] == 2
    assert payload["summary"]["usable_source_count"] == 2
    result = payload["results"][0]
    assert result["ticker"] == "005930"
    assert result["discovered_sources"][0]["source_url"] == "https://example.test/report.pdf"
    assert result["discovered_sources"][0]["source_type"] == "pdf"
    assert result["discovered_sources"][1]["source_url"] == "https://example.test/linked.pdf"
    assert result["discovered_sources"][1]["source_type"] == "pdf"
    assert output_path.exists()


def test_discover_promotes_reference_pdf_url_to_source(tmp_path: Path):
    from scripts.discover_supplemental_research_sources import discover_supplemental_research_sources

    candidate_path = tmp_path / "candidates.json"
    output_path = tmp_path / "discovery.json"
    candidate_path.write_text(
        json.dumps(
            {
                "candidates": [
                    {
                        "ticker": "005930",
                        "name": "Samsung Electronics",
                        "latest_report_date": "2026-02-01",
                        "provider_searches": [
                            {
                                "provider": "latest_report_url",
                                "label": "Latest known report URL",
                                "kind": "reference_url",
                                "url": "https://example.test/report.pdf",
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    payload = discover_supplemental_research_sources(
        candidate_path=candidate_path,
        output_path=output_path,
        fetcher=lambda url: {
            "status_code": 200,
            "content_type": "application/pdf",
            "text": "%PDF body",
            "final_url": url,
        },
    )

    assert payload["summary"]["usable_source_count"] == 1
    check = payload["results"][0]["checks"][0]
    assert check["status"] == "reference_pdf"
    source = check["discovered_sources"][0]
    assert source["source_url"] == "https://example.test/report.pdf"
    assert source["source_type"] == "pdf"
    assert source["status"] == "reference_pdf"


def test_latest_report_not_found_candidate_does_not_reuse_old_latest_url(tmp_path: Path):
    from scripts.discover_supplemental_research_sources import discover_supplemental_research_sources

    candidate_path = tmp_path / "candidates.json"
    output_path = tmp_path / "discovery.json"
    candidate_path.write_text(
        json.dumps(
            {
                "candidates": [
                    {
                        "ticker": "005930",
                        "name": "Samsung Electronics",
                        "primary_action": "latest_report_not_found",
                        "latest_report_date": "2026-02-01",
                        "latest_url": "https://example.test/old-report.pdf",
                        "provider_searches": [],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    payload = discover_supplemental_research_sources(
        candidate_path=candidate_path,
        output_path=output_path,
        fetcher=lambda url: {
            "status_code": 200,
            "content_type": "application/pdf",
            "text": "%PDF body",
            "final_url": url,
        },
    )

    assert payload["summary"]["checked_url_count"] == 0
    assert payload["summary"]["usable_source_count"] == 0
    assert payload["results"][0]["discovered_sources"] == []


def test_supplemental_source_needed_candidate_does_not_reuse_old_latest_url(tmp_path: Path):
    from scripts.discover_supplemental_research_sources import discover_supplemental_research_sources

    candidate_path = tmp_path / "candidates.json"
    output_path = tmp_path / "discovery.json"
    candidate_path.write_text(
        json.dumps(
            {
                "candidates": [
                    {
                        "ticker": "000520",
                        "name": "Samil",
                        "primary_action": "supplemental_source_needed",
                        "latest_url": "https://example.com/old-report.pdf",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    payload = discover_supplemental_research_sources(
        candidate_path=candidate_path,
        output_path=output_path,
        fetcher=lambda url: {"status_code": 200, "content_type": "application/pdf", "text": "", "final_url": url},
    )

    assert payload["summary"]["checked_url_count"] == 0
    assert payload["summary"]["usable_source_count"] == 0
    assert payload["results"][0]["discovered_sources"] == []


def test_convert_discovery_results_to_supplemental_source_draft(tmp_path: Path):
    from scripts.discover_supplemental_research_sources import convert_discovery_results_to_sources

    discovery_path = tmp_path / "discovery.json"
    output_path = tmp_path / "sources_draft.json"
    discovery_path.write_text(
        json.dumps(
            {
                "results": [
                    {
                        "ticker": "005930",
                        "name": "Samsung Electronics",
                        "latest_report_date": "2026-02-01",
                        "latest_title": "Old Samsung report",
                        "discovered_sources": [
                            {
                                "provider": "direct_pdf",
                                "source_url": "https://example.test/report.pdf",
                                "source_type": "pdf",
                                "status": "usable_pdf",
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    rows = convert_discovery_results_to_sources(
        discovery_path=discovery_path,
        output_path=output_path,
        report_date="2026-05-16",
    )

    assert rows == [
        {
            "report_date": "2026-05-16",
            "ticker": "005930",
            "source": "direct_pdf",
            "region": "domestic",
            "broker": "direct_pdf",
            "title": "Samsung Electronics latest public research candidate",
            "source_url": "https://example.test/report.pdf",
            "source_type": "pdf",
            "discovery_status": "usable_pdf",
            "raw_score": 0.0,
        }
    ]
    assert json.loads(output_path.read_text(encoding="utf-8")) == rows


def test_reference_pdf_discovery_converts_to_verifiable_source_and_keeps_status(tmp_path: Path):
    from scripts.discover_supplemental_research_sources import (
        convert_discovery_results_to_sources,
        discover_supplemental_research_sources,
    )
    from scripts.verify_supplemental_research_sources import verify_supplemental_research_sources

    candidate_path = tmp_path / "candidates.json"
    discovery_path = tmp_path / "discovery.json"
    draft_path = tmp_path / "draft.json"
    verified_path = tmp_path / "verified.json"
    rejected_path = tmp_path / "rejected.json"
    candidate_path.write_text(
        json.dumps(
            {
                "candidates": [
                    {
                        "ticker": "005930",
                        "name": "Samsung Electronics",
                        "latest_report_date": "2026-02-01",
                        "provider_searches": [
                            {
                                "provider": "latest_report_url",
                                "label": "Latest known report URL",
                                "kind": "reference_url",
                                "url": "https://example.test/samsung.pdf",
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    discover_supplemental_research_sources(
        candidate_path=candidate_path,
        output_path=discovery_path,
        fetcher=lambda url: {
            "status_code": 200,
            "content_type": "application/pdf",
            "text": "%PDF body",
            "final_url": url,
        },
    )
    rows = convert_discovery_results_to_sources(
        discovery_path=discovery_path,
        output_path=draft_path,
        report_date="2026-05-16",
    )
    result = verify_supplemental_research_sources(
        input_path=draft_path,
        verified_output_path=verified_path,
        rejected_output_path=rejected_path,
        text_fetcher=lambda source: "Samsung Electronics 005930 earnings and risk body text.",
    )

    assert rows[0]["source_url"] == "https://example.test/samsung.pdf"
    assert rows[0]["source_type"] == "pdf"
    assert rows[0]["discovery_status"] == "reference_pdf"
    assert result["verified_count"] == 1
    verified = json.loads(verified_path.read_text(encoding="utf-8"))
    assert verified[0]["discovery_status"] == "reference_pdf"
    assert verified[0]["verification_status"] == "ticker_found_in_body"


def test_discover_does_not_turn_generic_provider_lists_into_sources(tmp_path: Path):
    from scripts.discover_supplemental_research_sources import discover_supplemental_research_sources

    candidate_path = tmp_path / "candidates.json"
    output_path = tmp_path / "discovery.json"
    candidate_path.write_text(
        json.dumps(
            {
                "candidates": [
                    {
                        "ticker": "005930",
                        "name": "Samsung Electronics",
                        "latest_report_date": "2026-02-01",
                        "provider_searches": [
                            {
                                "provider": "hankyung_consensus",
                                "label": "Hankyung list",
                                "kind": "provider_list",
                                "url": "https://consensus.hankyung.com/analysis/list",
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    payload = discover_supplemental_research_sources(
        candidate_path=candidate_path,
        output_path=output_path,
        fetcher=lambda url: {
            "status_code": 200,
            "content_type": "text/html",
            "text": "<html><a href='/analysis/downpdf?report_idx=999'>Unrelated PDF</a></html>",
            "final_url": url,
        },
    )

    assert payload["summary"]["usable_source_count"] == 0
    assert payload["results"][0]["checks"][0]["status"] == "provider_list_reachable"
    assert payload["results"][0]["discovered_sources"] == []


def test_discover_promotes_matching_provider_list_report(tmp_path: Path):
    from scripts.discover_supplemental_research_sources import discover_supplemental_research_sources

    candidate_path = tmp_path / "candidates.json"
    output_path = tmp_path / "discovery.json"
    candidate_path.write_text(
        json.dumps(
            {
                "candidates": [
                    {
                        "ticker": "005930",
                        "name": "Samsung Electronics",
                        "latest_report_date": "2026-02-01",
                        "provider_searches": [
                            {
                                "provider": "hankyung_consensus",
                                "label": "Hankyung list",
                                "kind": "provider_list",
                                "url": "https://consensus.hankyung.com/analysis/list",
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    payload = discover_supplemental_research_sources(
        candidate_path=candidate_path,
        output_path=output_path,
        fetcher=lambda url: {
            "status_code": 200,
            "content_type": "text/html",
            "text": """
                <table>
                  <tr>
                    <td>2026-05-15</td>
                    <td><a href="/analysis/downpdf?report_idx=100">삼성전자(005930) AI 서버 수요 점검</a></td>
                    <td>전기전자</td><td>홍길동</td><td>테스트증권</td>
                  </tr>
                  <tr>
                    <td>2026-05-15</td>
                    <td><a href="/analysis/downpdf?report_idx=101">SK하이닉스(000660) 업황 점검</a></td>
                    <td>반도체</td><td>홍길동</td><td>테스트증권</td>
                  </tr>
                </table>
            """,
            "final_url": url,
        },
    )

    assert payload["summary"]["usable_source_count"] == 1
    check = payload["results"][0]["checks"][0]
    assert check["status"] == "provider_list_match_found"
    source = check["discovered_sources"][0]
    assert source["source_url"] == "https://consensus.hankyung.com/analysis/downpdf?report_idx=100"
    assert source["report_date"] == "2026-05-15"
    assert source["title"] == "삼성전자(005930) AI 서버 수요 점검"


def test_discover_ignores_stale_provider_list_report(tmp_path: Path):
    from scripts.discover_supplemental_research_sources import discover_supplemental_research_sources

    candidate_path = tmp_path / "candidates.json"
    output_path = tmp_path / "discovery.json"
    candidate_path.write_text(
        json.dumps(
            {
                "candidates": [
                    {
                        "ticker": "005930",
                        "name": "Samsung Electronics",
                        "latest_report_date": "2026-05-15",
                        "provider_searches": [
                            {
                                "provider": "hankyung_consensus",
                                "label": "Hankyung list",
                                "kind": "provider_list",
                                "url": "https://consensus.hankyung.com/analysis/list",
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    payload = discover_supplemental_research_sources(
        candidate_path=candidate_path,
        output_path=output_path,
        fetcher=lambda url: {
            "status_code": 200,
            "content_type": "text/html",
            "text": """
                <table>
                  <tr>
                    <td>2026-05-14</td>
                    <td><a href="/analysis/downpdf?report_idx=100">삼성전자(005930) 이전 리포트</a></td>
                    <td>전기전자</td><td>홍길동</td><td>테스트증권</td>
                  </tr>
                </table>
            """,
            "final_url": url,
        },
    )

    assert payload["summary"]["usable_source_count"] == 0
    assert payload["results"][0]["checks"][0]["status"] == "provider_list_reachable"


def test_discover_promotes_search_result_pdf_links(tmp_path: Path):
    from scripts.discover_supplemental_research_sources import discover_supplemental_research_sources

    candidate_path = tmp_path / "candidates.json"
    output_path = tmp_path / "discovery.json"
    candidate_path.write_text(
        json.dumps(
            {
                "candidates": [
                    {
                        "ticker": "005930",
                        "name": "Samsung Electronics",
                        "latest_report_date": "2026-02-01",
                        "provider_searches": [
                            {
                                "provider": "yuanta_pdf",
                                "label": "Yuanta search",
                                "kind": "web_search",
                                "url": "https://www.google.com/search?q=samsung+pdf",
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    payload = discover_supplemental_research_sources(
        candidate_path=candidate_path,
        output_path=output_path,
        fetcher=lambda url: {
            "status_code": 200,
            "content_type": "text/html",
            "text": (
                "<html><body>"
                "<a href='/url?q=https%3A%2F%2Ffile.myasset.com%2Fsitemanager%2Fupload%2F2026%2F0515%2F090000%2Fsamsung.pdf&sa=U'>result</a>"
                "<a href='https://accounts.google.com/login'>login</a>"
                "</body></html>"
            ),
            "final_url": url,
        },
    )

    assert payload["summary"]["usable_source_count"] == 1
    check = payload["results"][0]["checks"][0]
    assert check["status"] == "search_result_pdf_found"
    assert check["discovered_sources"][0]["source_url"] == "https://file.myasset.com/sitemanager/upload/2026/0515/090000/samsung.pdf"
    assert check["discovered_sources"][0]["report_date"] == "2026-05-15"


def test_discover_ignores_stale_search_result_pdf_links(tmp_path: Path):
    from scripts.discover_supplemental_research_sources import discover_supplemental_research_sources

    candidate_path = tmp_path / "candidates.json"
    output_path = tmp_path / "discovery.json"
    candidate_path.write_text(
        json.dumps(
            {
                "candidates": [
                    {
                        "ticker": "005930",
                        "name": "Samsung Electronics",
                        "latest_report_date": "2026-05-15",
                        "provider_searches": [
                            {
                                "provider": "yuanta_pdf",
                                "label": "Yuanta search",
                                "kind": "web_search",
                                "url": "https://search.naver.com/search.naver?query=samsung+pdf",
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    payload = discover_supplemental_research_sources(
        candidate_path=candidate_path,
        output_path=output_path,
        fetcher=lambda url: {
            "status_code": 200,
            "content_type": "text/html",
            "text": (
                "<html><body>"
                "<a href='https://file.myasset.com/sitemanager/upload/2024/0311/153748/stale.pdf'>old</a>"
                "</body></html>"
            ),
            "final_url": url,
        },
    )

    assert payload["summary"]["usable_source_count"] == 0
    assert payload["results"][0]["checks"][0]["status"] == "reachable_html"


def test_discover_marks_rate_limited_web_searches_for_manual_followup(tmp_path: Path):
    from scripts.discover_supplemental_research_sources import discover_supplemental_research_sources

    candidate_path = tmp_path / "candidates.json"
    output_path = tmp_path / "discovery.json"
    search_url = "https://www.google.com/search?q=samsung+pdf"
    candidate_path.write_text(
        json.dumps(
            {
                "candidates": [
                    {
                        "ticker": "005930",
                        "name": "Samsung Electronics",
                        "provider_searches": [
                            {
                                "provider": "yuanta_pdf",
                                "label": "Yuanta search",
                                "kind": "web_search",
                                "search_engine": "bing",
                                "query": "Samsung Electronics 005930 site:file.myasset.com pdf",
                                "url": search_url,
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    payload = discover_supplemental_research_sources(
        candidate_path=candidate_path,
        output_path=output_path,
        fetcher=lambda url: {
            "status_code": 429,
            "content_type": "text/html",
            "text": "<html>rate limited</html>",
            "final_url": url,
        },
    )

    check = payload["results"][0]["checks"][0]
    assert payload["summary"]["usable_source_count"] == 0
    assert check["status"] == "search_rate_limited"
    assert check["query"] == "Samsung Electronics 005930 site:file.myasset.com pdf"
    assert check["search_engine"] == "bing"
    assert check["manual_next_step"] == f"Open or retry this search manually: {search_url}"
    assert check["discovered_sources"] == []
