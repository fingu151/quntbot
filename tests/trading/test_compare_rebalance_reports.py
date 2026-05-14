import json
from pathlib import Path


def _write_report(path: Path, *, targets: list[dict], orders: list[dict] | None = None) -> None:
    path.write_text(
        json.dumps(
            {
                "dry_run": True,
                "as_of_date": "2026-05-08",
                "target_count": len(targets),
                "buy_count": len([order for order in (orders or []) if order["side"] == "BUY"]),
                "sell_count": len([order for order in (orders or []) if order["side"] == "SELL"]),
                "targets": targets,
                "orders": orders or [],
            }
        ),
        encoding="utf-8",
    )


def test_parse_args_accepts_compare_options(tmp_path):
    import scripts.compare_rebalance_reports as compare

    before = tmp_path / "before.json"
    after = tmp_path / "after.json"
    output = tmp_path / "compare.md"

    args = compare.parse_args([
        "--before-json",
        str(before),
        "--after-json",
        str(after),
        "--output-md",
        str(output),
    ])

    assert args.before_json == before
    assert args.after_json == after
    assert args.output_md == output


def test_run_prints_added_removed_kept_and_rank_changes(tmp_path, capsys):
    import scripts.compare_rebalance_reports as compare

    before = tmp_path / "before.json"
    after = tmp_path / "after.json"
    _write_report(
        before,
        targets=[
            {"rank": 1, "ticker": "AAA", "name": "Alpha", "total_score": 3.0},
            {"rank": 2, "ticker": "BBB", "name": "Beta", "total_score": 2.0},
        ],
        orders=[{"side": "BUY", "ticker": "BBB", "qty": 5, "reason": "include"}],
    )
    _write_report(
        after,
        targets=[
            {"rank": 1, "ticker": "CCC", "name": "Gamma", "total_score": 4.0},
            {"rank": 2, "ticker": "AAA", "name": "Alpha", "total_score": 3.1},
        ],
        orders=[{"side": "BUY", "ticker": "CCC", "qty": 3, "reason": "include"}],
    )
    args = compare.parse_args(["--before-json", str(before), "--after-json", str(after)])

    result = compare.run(args)

    output = capsys.readouterr().out
    assert result == 0
    assert "comparison_status=clean" in output
    assert "added_count=1" in output
    assert "removed_count=1" in output
    assert "kept_count=1" in output
    assert "ADDED,CCC,Gamma,1,4.0000" in output
    assert "REMOVED,BBB,Beta,2,2.0000" in output
    assert "KEPT,AAA,Alpha,1,2,1,3.0000,3.1000" in output
    assert "buy_added_count=1" in output
    assert "buy_removed_count=1" in output


def test_run_writes_markdown_report(tmp_path):
    import scripts.compare_rebalance_reports as compare

    before = tmp_path / "before.json"
    after = tmp_path / "after.json"
    output = tmp_path / "compare.md"
    _write_report(before, targets=[{"rank": 1, "ticker": "AAA", "name": "Alpha", "total_score": 3.0}])
    _write_report(after, targets=[{"rank": 1, "ticker": "BBB", "name": "Beta", "total_score": 4.0}])
    args = compare.parse_args([
        "--before-json",
        str(before),
        "--after-json",
        str(after),
        "--output-md",
        str(output),
    ])

    result = compare.run(args)

    report = output.read_text(encoding="utf-8")
    assert result == 0
    assert "# Rebalance Report Comparison" in report
    assert "| ADDED | BBB | Beta | 1 | 4.0000 |" in report
    assert "| REMOVED | AAA | Alpha | 1 | 3.0000 |" in report


def test_run_returns_error_when_report_is_missing(tmp_path, capsys):
    import scripts.compare_rebalance_reports as compare

    before = tmp_path / "missing.json"
    after = tmp_path / "after.json"
    _write_report(after, targets=[])
    args = compare.parse_args(["--before-json", str(before), "--after-json", str(after)])

    result = compare.run(args)

    output = capsys.readouterr().out
    assert result == 1
    assert "comparison_status=missing_or_invalid" in output
    assert "report_error=" in output
