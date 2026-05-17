from __future__ import annotations

import csv
import json

from scripts.convert_supplemental_research_reports import (
    SupplementalTableConvertResult,
    convert_table_rows,
    parse_args,
    run,
)


def test_parse_args_accepts_input_output_and_format():
    args = parse_args(
        [
            "--input",
            "reports.csv",
            "--output",
            "data/supplemental_research_reports.json",
            "--format",
            "csv",
        ]
    )

    assert args.input == "reports.csv"
    assert args.output == "data/supplemental_research_reports.json"
    assert args.format == "csv"


def test_convert_table_rows_maps_korean_headers_and_skips_incomplete_rows():
    rows = [
        {
            "발간일": "2026-05-14",
            "종목코드": "7340",
            "증권사": "Kiwoom Securities",
            "제목": "DN Automotive margin recovery",
            "핵심요약": "Margin recovery is the key point.",
            "의견": "positive",
            "목표주가": "120,000",
            "리스크": "Auto demand and FX.",
            "신뢰도": "0.55",
        },
        {"발간일": "2026-05-15", "종목코드": "005930"},
    ]

    result = convert_table_rows(rows)

    assert result == SupplementalTableConvertResult(input_count=2, valid_count=1, skipped_count=1)
    assert len(result.reports) == 1
    report = result.reports[0]
    assert report["report_date"] == "2026-05-14"
    assert report["ticker"] == "007340"
    assert report["source"] == "supplemental_research"
    assert report["title"] == "DN Automotive margin recovery"
    assert report["headline"] == "Margin recovery is the key point."
    assert report["summary"] == "Margin recovery is the key point."
    assert report["opinion"] == "positive"
    assert report["investment_opinion"] == "positive"
    assert report["target_price"] == 120000.0
    assert report["risks"] == "Auto demand and FX."
    assert report["risk_factors"] == "Auto demand and FX."
    assert report["confidence"] == 0.55


def test_run_reads_csv_and_writes_supplemental_json(tmp_path, capsys):
    input_path = tmp_path / "reports.csv"
    output_path = tmp_path / "supplemental.json"
    with input_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["report_date", "ticker", "title", "summary"])
        writer.writeheader()
        writer.writerow(
            {
                "report_date": "2026-05-14",
                "ticker": "005850",
                "title": "SL earnings visibility",
                "summary": "Earnings visibility improved.",
            }
        )

    exit_code = run(
        parse_args(["--input", str(input_path), "--output", str(output_path)])
    )

    captured = capsys.readouterr()
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert payload[0]["ticker"] == "005850"
    assert payload[0]["summary"] == "Earnings visibility improved."
    assert "supplemental_table_input_count=1" in captured.out
    assert "supplemental_table_valid_count=1" in captured.out
    assert f"wrote_json={output_path}" in captured.out
    assert "orders_submitted=0" in captured.out


def test_run_treats_unfilled_template_as_successful_noop(tmp_path, capsys):
    input_path = tmp_path / "template.csv"
    output_path = tmp_path / "supplemental.json"
    with input_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["발간일", "종목코드", "제목"])
        writer.writeheader()
        writer.writerow({"발간일": "2026-05-15", "종목코드": "007340", "제목": ""})

    exit_code = run(
        parse_args(["--input", str(input_path), "--output", str(output_path)])
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert json.loads(output_path.read_text(encoding="utf-8")) == []
    assert "supplemental_table_input_count=1" in captured.out
    assert "supplemental_table_valid_count=0" in captured.out
    assert "supplemental_table_skipped_count=1" in captured.out
