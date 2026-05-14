from datetime import date
from pathlib import Path
from unittest.mock import MagicMock


def test_parse_args_accepts_smoke_options(tmp_path):
    import scripts.smoke_rebalance_operations_checklist as smoke

    args = smoke.parse_args([
        "--as-of-date",
        "2026-05-08",
        "--top-n",
        "20",
        "--root-dir",
        str(tmp_path),
    ])

    assert args.as_of_date == date(2026, 5, 8)
    assert args.top_n == 20
    assert args.root_dir == tmp_path


def test_run_passes_when_all_referenced_scripts_exist(tmp_path, capsys):
    import scripts.smoke_rebalance_operations_checklist as smoke

    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    for name in [
        "prepare_and_review_rebalance.py",
        "check_rebalance_readiness.py",
        "execute_rebalance_from_dry_run.py",
        "review_rebalance_reports.py",
    ]:
        (scripts_dir / name).write_text("", encoding="utf-8")

    checklist_output = "\n".join([
        "step,command",
        r"prepare,.\venv\Scripts\python.exe scripts\prepare_and_review_rebalance.py",
        r"ready,.\venv\Scripts\python.exe scripts\check_rebalance_readiness.py",
        r"execute,.\venv\Scripts\python.exe scripts\execute_rebalance_from_dry_run.py",
        r"review,.\venv\Scripts\python.exe scripts\review_rebalance_reports.py",
    ])
    checklist_run = MagicMock(side_effect=lambda _args: print(checklist_output) or 0)
    args = smoke.parse_args(["--as-of-date", "2026-05-08", "--root-dir", str(tmp_path)])

    result = smoke.run(args, checklist_run=checklist_run)

    output = capsys.readouterr().out
    assert result == 0
    assert "checklist_smoke_status=ok" in output
    assert "missing_script_count=0" in output


def test_run_returns_error_when_referenced_script_is_missing(tmp_path, capsys):
    import scripts.smoke_rebalance_operations_checklist as smoke

    checklist_output = r"execute,.\venv\Scripts\python.exe scripts\missing.py"
    checklist_run = MagicMock(side_effect=lambda _args: print(checklist_output) or 0)
    args = smoke.parse_args(["--as-of-date", "2026-05-08", "--root-dir", str(tmp_path)])

    result = smoke.run(args, checklist_run=checklist_run)

    output = capsys.readouterr().out
    assert result == 1
    assert "checklist_smoke_status=blocked" in output
    assert "missing_script_count=1" in output
    assert "missing_script=scripts\\missing.py" in output


def test_run_returns_error_when_checklist_generation_fails(tmp_path, capsys):
    import scripts.smoke_rebalance_operations_checklist as smoke

    checklist_run = MagicMock(return_value=1)
    args = smoke.parse_args(["--as-of-date", "2026-05-08", "--root-dir", str(tmp_path)])

    result = smoke.run(args, checklist_run=checklist_run)

    assert result == 1
    assert "checklist_generation_failed=1" in capsys.readouterr().out
