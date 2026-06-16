from datetime import date
from pathlib import Path


def test_parse_args_accepts_checklist_options(tmp_path):
    import scripts.print_rebalance_operations_checklist as checklist

    json_path = tmp_path / "dry_run.json"
    md_path = tmp_path / "dry_run.md"
    execution_path = tmp_path / "execution.json"
    args = checklist.parse_args([
        "--as-of-date",
        "2026-05-08",
        "--top-n",
        "20",
        "--dry-run-json",
        str(json_path),
        "--dry-run-md",
        str(md_path),
        "--execution-report-json",
        str(execution_path),
    ])

    assert args.as_of_date == date(2026, 5, 8)
    assert args.top_n == 20
    assert args.dry_run_json == json_path
    assert args.dry_run_md == md_path
    assert args.execution_report_json == execution_path


def test_run_prints_safe_command_sequence(tmp_path, capsys):
    import scripts.print_rebalance_operations_checklist as checklist

    json_path = tmp_path / "dry_run.json"
    md_path = tmp_path / "dry_run.md"
    execution_path = tmp_path / "execution.json"
    args = checklist.parse_args([
        "--as-of-date",
        "2026-05-08",
        "--top-n",
        "20",
        "--dry-run-json",
        str(json_path),
        "--dry-run-md",
        str(md_path),
        "--execution-report-json",
        str(execution_path),
    ])

    result = checklist.run(args)

    output = capsys.readouterr().out
    assert result == 0
    assert "daily_operations_date=2026-05-08" in output
    assert "rebalance_operations_date=2026-05-08" in output
    assert "orders_submitted=0" in output
    assert "scripts\\daily_paper_run.py --as-of-date 2026-05-08 --top-n 20" in output
    assert "daily_paper_run_includes=research,sync,prepare_review,readiness,execute,post_review,archive,monitor" in output
    assert "--confirm EXECUTE_PAPER_REBALANCE" in output
    assert "scripts\\prepare_and_review_rebalance.py --as-of-date 2026-05-08 --top-n 20" in output
    assert f"--output-json {json_path}" in output
    assert f"--output-md {md_path}" in output
    assert "scripts\\check_rebalance_readiness.py" in output
    assert "scripts\\execute_rebalance_from_dry_run.py" in output
    assert "--confirm EXECUTE_PAPER_REBALANCE" in output
    assert "--review-before-execute" in output
    assert f"--execution-report-json {execution_path}" in output
    assert "scripts\\review_rebalance_reports.py" in output
    assert "scripts\\archive_rebalance_run_bundle.py" in output
    assert "scripts\\cleanup_rebalance_checklist_logs.py --keep 20" in output
    assert "scripts\\run_bot.py" in output
    assert "safety_note=do_not_run_daily_paper_run_and_run_bot_together" in output
    assert "archive_note=use the execution_report_json path printed by daily_paper_run if it chose a retry file" in output


def test_default_execution_report_path_uses_as_of_date():
    import scripts.print_rebalance_operations_checklist as checklist

    args = checklist.parse_args(["--as-of-date", "2026-05-08"])

    assert args.execution_report_json == Path("data") / "rebalance_execution_2026-05-08.json"
