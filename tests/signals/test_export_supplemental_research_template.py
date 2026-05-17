from __future__ import annotations

import csv

from scripts.export_supplemental_research_template import (
    build_template_rows,
    parse_args,
    run,
)


def test_build_template_rows_prefills_only_research_needs():
    coverage_report = {
        "items": [
            {
                "ticker": "007340",
                "name": "DN Automotive",
                "status": "missing_brief",
                "latest_report_date": "",
                "reasons": ["missing_brief"],
                "missing_sections": ["stock_view", "growth", "earnings", "risk"],
            },
            {
                "ticker": "000990",
                "name": "DB HiTek",
                "status": "needs_review",
                "latest_report_date": "2026-01-21",
                "reasons": ["stale_report"],
                "missing_sections": [],
            },
            {
                "ticker": "005930",
                "name": "Samsung Electronics",
                "status": "ok",
                "latest_report_date": "2026-05-14",
                "reasons": [],
                "missing_sections": [],
            },
        ]
    }

    rows = build_template_rows(coverage_report, as_of_date="2026-05-15")

    assert [row["종목코드"] for row in rows] == ["007340", "000990"]
    assert rows[0]["종목명"] == "DN Automotive"
    assert rows[0]["보충상태"] == "missing_brief"
    assert rows[0]["발간일"] == "2026-05-15"
    assert rows[0]["보충필요사유"] == "missing_brief"
    assert rows[0]["부족섹션"] == "stock_view, growth, earnings, risk"
    assert rows[0]["제목"] == ""


def test_parse_args_accepts_snapshot_ticker_briefs_and_output():
    args = parse_args(
        [
            "--snapshot",
            "data/public.json",
            "--ticker-briefs",
            "data/briefs.json",
            "--output",
            "data/template.csv",
            "--as-of-date",
            "2026-05-15",
        ]
    )

    assert str(args.snapshot) == "data\\public.json"
    assert str(args.ticker_briefs) == "data\\briefs.json"
    assert str(args.output) == "data\\template.csv"
    assert args.as_of_date == "2026-05-15"


def test_run_writes_prefilled_template_csv(tmp_path, capsys):
    output = tmp_path / "template.csv"
    coverage_report = {
        "items": [
            {
                "ticker": "005850",
                "name": "SL",
                "status": "stale_brief",
                "latest_report_date": "2026-02-23",
                "reasons": ["stale_report"],
                "missing_sections": [],
            }
        ]
    }

    exit_code = run(
        parse_args(["--output", str(output), "--as-of-date", "2026-05-15"]),
        coverage_loader=lambda args: coverage_report,
    )

    captured = capsys.readouterr()
    with output.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert exit_code == 0
    assert rows[0]["종목코드"] == "005850"
    assert rows[0]["발간일"] == "2026-05-15"
    assert rows[0]["보충상태"] == "stale_brief"
    assert f"wrote_template={output}" in captured.out
    assert "supplemental_template_rows=1" in captured.out
    assert "orders_submitted=0" in captured.out
