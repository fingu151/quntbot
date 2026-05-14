from datetime import date
from pathlib import Path
from unittest.mock import MagicMock


def test_parse_args_accepts_archive_options(tmp_path):
    import scripts.archive_rebalance_operations_checklist as archive

    output_path = tmp_path / "checklist.log"
    args = archive.parse_args([
        "--as-of-date",
        "2026-05-08",
        "--top-n",
        "20",
        "--output-log",
        str(output_path),
    ])

    assert args.as_of_date == date(2026, 5, 8)
    assert args.top_n == 20
    assert args.output_log == output_path


def test_default_output_log_uses_as_of_date():
    import scripts.archive_rebalance_operations_checklist as archive

    args = archive.parse_args(["--as-of-date", "2026-05-08"])

    assert args.output_log == Path("logs") / "rebalance_operations_checklist_2026-05-08.log"


def test_run_writes_smoke_output_to_log(tmp_path, capsys):
    import scripts.archive_rebalance_operations_checklist as archive

    output_path = tmp_path / "checklist.log"
    smoke_run = MagicMock(side_effect=lambda _args: print("checklist_smoke_status=ok") or 0)
    args = archive.parse_args([
        "--as-of-date",
        "2026-05-08",
        "--output-log",
        str(output_path),
    ])

    result = archive.run(args, smoke_run=smoke_run)

    output = capsys.readouterr().out
    archived = output_path.read_text(encoding="utf-8")
    assert result == 0
    assert "checklist_smoke_status=ok" in output
    assert "archive_log=" in output
    assert "checklist_smoke_status=ok" in archived
    assert "archive_status=ok" in archived


def test_run_preserves_smoke_failure_exit_code(tmp_path, capsys):
    import scripts.archive_rebalance_operations_checklist as archive

    output_path = tmp_path / "checklist.log"
    smoke_run = MagicMock(side_effect=lambda _args: print("checklist_smoke_status=blocked") or 1)
    args = archive.parse_args([
        "--as-of-date",
        "2026-05-08",
        "--output-log",
        str(output_path),
    ])

    result = archive.run(args, smoke_run=smoke_run)

    assert result == 1
    assert "archive_status=blocked" in output_path.read_text(encoding="utf-8")
    assert "archive_status=blocked" in capsys.readouterr().out
