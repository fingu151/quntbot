from datetime import date
import json
from pathlib import Path
from unittest.mock import MagicMock


def test_parse_args_accepts_bundle_options(tmp_path):
    import scripts.archive_rebalance_run_bundle as bundle

    dry_run_json = tmp_path / "dry_run.json"
    dry_run_md = tmp_path / "dry_run.md"
    execution_json = tmp_path / "execution.json"
    output_dir = tmp_path / "bundle"
    args = bundle.parse_args([
        "--as-of-date",
        "2026-05-08",
        "--top-n",
        "20",
        "--dry-run-json",
        str(dry_run_json),
        "--dry-run-md",
        str(dry_run_md),
        "--execution-report-json",
        str(execution_json),
        "--output-dir",
        str(output_dir),
    ])

    assert args.as_of_date == date(2026, 5, 8)
    assert args.top_n == 20
    assert args.dry_run_json == dry_run_json
    assert args.dry_run_md == dry_run_md
    assert args.execution_report_json == execution_json
    assert args.output_dir == output_dir


def test_default_output_dir_uses_as_of_date():
    import scripts.archive_rebalance_run_bundle as bundle

    args = bundle.parse_args(["--as-of-date", "2026-05-08"])

    assert args.output_dir == Path("logs") / "rebalance_run_2026-05-08"


def test_run_archives_existing_artifacts_and_captured_outputs(tmp_path, capsys):
    import scripts.archive_rebalance_run_bundle as bundle

    dry_run_json = tmp_path / "dry_run.json"
    dry_run_md = tmp_path / "dry_run.md"
    execution_json = tmp_path / "execution.json"
    output_dir = tmp_path / "bundle"
    dry_run_json.write_text('{"dry_run": true}', encoding="utf-8")
    dry_run_md.write_text("# dry-run", encoding="utf-8")
    execution_json.write_text('{"paper_execution": true}', encoding="utf-8")

    checklist_run = MagicMock(side_effect=lambda _args: print("checklist_ok") or 0)
    readiness_run = MagicMock(side_effect=lambda _args: print("execution_ready=true") or 0)
    review_run = MagicMock(side_effect=lambda _args: print("execution_status=clean") or 0)
    args = bundle.parse_args([
        "--as-of-date",
        "2026-05-08",
        "--dry-run-json",
        str(dry_run_json),
        "--dry-run-md",
        str(dry_run_md),
        "--execution-report-json",
        str(execution_json),
        "--output-dir",
        str(output_dir),
    ])

    result = bundle.run(
        args,
        checklist_run=checklist_run,
        readiness_run=readiness_run,
        review_run=review_run,
    )

    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    output = capsys.readouterr().out

    assert result == 0
    assert "bundle_status=executed_clean" in output
    assert (output_dir / "dry_run_rebalance.json").read_text(encoding="utf-8") == '{"dry_run": true}'
    assert (output_dir / "dry_run_rebalance.md").read_text(encoding="utf-8") == "# dry-run"
    assert (output_dir / "rebalance_execution.json").read_text(encoding="utf-8") == '{"paper_execution": true}'
    assert "checklist_ok" in (output_dir / "checklist.txt").read_text(encoding="utf-8")
    assert "execution_ready=true" in (output_dir / "readiness.txt").read_text(encoding="utf-8")
    assert "execution_status=clean" in (output_dir / "review.txt").read_text(encoding="utf-8")
    assert manifest["bundle_status"] == "executed_clean"
    assert manifest["artifacts"]["dry_run_json"]["copied"] is True
    assert manifest["artifacts"]["execution_report_json"]["copied"] is True
    checklist_run.assert_called_once()
    readiness_run.assert_called_once()
    review_run.assert_called_once()


def test_run_reports_market_blocked_when_readiness_fails_without_execution_report(tmp_path, capsys):
    import scripts.archive_rebalance_run_bundle as bundle

    dry_run_json = tmp_path / "dry_run.json"
    dry_run_json.write_text('{"dry_run": true}', encoding="utf-8")
    output_dir = tmp_path / "bundle"
    args = bundle.parse_args([
        "--as-of-date",
        "2026-05-08",
        "--dry-run-json",
        str(dry_run_json),
        "--dry-run-md",
        str(tmp_path / "missing.md"),
        "--execution-report-json",
        str(tmp_path / "missing_execution.json"),
        "--output-dir",
        str(output_dir),
    ])

    result = bundle.run(
        args,
        checklist_run=MagicMock(side_effect=lambda _args: print("checklist_ok") or 0),
        readiness_run=MagicMock(side_effect=lambda _args: print("market_time_status=blocked") or 1),
        review_run=MagicMock(side_effect=lambda _args: print("dry_run_status=clean") or 0),
    )

    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))

    assert result == 1
    assert "bundle_status=ready_blocked_market_time" in capsys.readouterr().out
    assert manifest["bundle_status"] == "ready_blocked_market_time"
    assert manifest["artifacts"]["dry_run_md"]["copied"] is False
    assert manifest["artifacts"]["execution_report_json"]["copied"] is False
