from pathlib import Path


def _write_log(path: Path) -> None:
    path.write_text("log\n", encoding="utf-8")


def test_parse_args_accepts_cleanup_options(tmp_path):
    import scripts.cleanup_rebalance_checklist_logs as cleanup

    args = cleanup.parse_args([
        "--logs-dir",
        str(tmp_path),
        "--keep",
        "3",
        "--apply",
    ])

    assert args.logs_dir == tmp_path
    assert args.keep == 3
    assert args.apply is True


def test_run_dry_run_keeps_files_and_reports_delete_candidates(tmp_path, capsys):
    import scripts.cleanup_rebalance_checklist_logs as cleanup

    for day in ["2026-05-01", "2026-05-02", "2026-05-03"]:
        _write_log(tmp_path / f"rebalance_operations_checklist_{day}.log")
    args = cleanup.parse_args(["--logs-dir", str(tmp_path), "--keep", "1"])

    result = cleanup.run(args)

    output = capsys.readouterr().out
    assert result == 0
    assert "cleanup_mode=dry-run" in output
    assert "kept_count=1" in output
    assert "delete_candidate_count=2" in output
    assert (tmp_path / "rebalance_operations_checklist_2026-05-01.log").exists()
    assert (tmp_path / "rebalance_operations_checklist_2026-05-02.log").exists()
    assert (tmp_path / "rebalance_operations_checklist_2026-05-03.log").exists()


def test_run_apply_deletes_old_logs_and_keeps_most_recent(tmp_path, capsys):
    import scripts.cleanup_rebalance_checklist_logs as cleanup

    old = tmp_path / "rebalance_operations_checklist_2026-05-01.log"
    mid = tmp_path / "rebalance_operations_checklist_2026-05-02.log"
    new = tmp_path / "rebalance_operations_checklist_2026-05-03.log"
    for path in [old, mid, new]:
        _write_log(path)
    args = cleanup.parse_args(["--logs-dir", str(tmp_path), "--keep", "2", "--apply"])

    result = cleanup.run(args)

    output = capsys.readouterr().out
    assert result == 0
    assert "cleanup_mode=apply" in output
    assert "deleted_count=1" in output
    assert not old.exists()
    assert mid.exists()
    assert new.exists()


def test_run_ignores_unrelated_log_files(tmp_path, capsys):
    import scripts.cleanup_rebalance_checklist_logs as cleanup

    unrelated = tmp_path / "quntbot.log"
    _write_log(unrelated)
    _write_log(tmp_path / "rebalance_operations_checklist_2026-05-01.log")
    args = cleanup.parse_args(["--logs-dir", str(tmp_path), "--keep", "0", "--apply"])

    result = cleanup.run(args)

    assert result == 0
    assert unrelated.exists()
    assert "matched_count=1" in capsys.readouterr().out
