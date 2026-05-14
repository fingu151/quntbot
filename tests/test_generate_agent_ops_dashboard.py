import json
from pathlib import Path


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_load_dry_run_summary_reports_clean_fields(tmp_path):
    import scripts.generate_agent_ops_dashboard as dashboard

    path = tmp_path / "dry_run.json"
    _write_json(
        path,
        {
            "dry_run": True,
            "as_of_date": "2026-05-12",
            "target_count": 10,
            "sell_count": 0,
            "buy_count": 10,
            "skipped_buy_count": 0,
            "price_lookup_failed_count": 0,
            "price_fallback_count": 0,
            "price_retry_success_count": 8,
            "price_retry_failed_count": 0,
        },
    )

    summary = dashboard.load_dry_run_summary(path)

    assert summary.path == path
    assert summary.status == "present"
    assert summary.as_of_date == "2026-05-12"
    assert summary.target_count == 10
    assert summary.buy_count == 10
    assert summary.price_lookup_failed_count == 0
    assert summary.price_fallback_count == 0
    assert summary.safety_status == "clean"


def test_load_dry_run_summary_marks_missing_fields_unknown(tmp_path):
    import scripts.generate_agent_ops_dashboard as dashboard

    path = tmp_path / "dry_run.json"
    _write_json(path, {"dry_run": True, "as_of_date": "2026-05-12"})

    summary = dashboard.load_dry_run_summary(path)

    assert summary.status == "present"
    assert summary.price_lookup_failed_count is None
    assert summary.price_fallback_count is None
    assert summary.safety_status == "unknown"


def test_load_dry_run_summary_reports_missing_file(tmp_path):
    import scripts.generate_agent_ops_dashboard as dashboard

    path = tmp_path / "missing.json"

    summary = dashboard.load_dry_run_summary(path)

    assert summary.path == path
    assert summary.status == "missing"
    assert summary.safety_status == "unknown"


def test_load_dry_run_summary_blocks_malformed_json(tmp_path):
    import scripts.generate_agent_ops_dashboard as dashboard

    path = tmp_path / "dry_run.json"
    path.write_text("{", encoding="utf-8")

    summary = dashboard.load_dry_run_summary(path)

    assert summary.status == "read-error"
    assert summary.safety_status == "blocked"
    assert summary.error


def test_load_dry_run_summary_blocks_invalid_count_type(tmp_path):
    import scripts.generate_agent_ops_dashboard as dashboard

    path = tmp_path / "dry_run.json"
    _write_json(
        path,
        {
            "dry_run": True,
            "as_of_date": "2026-05-12",
            "price_lookup_failed_count": "N/A",
            "price_fallback_count": 0,
        },
    )

    summary = dashboard.load_dry_run_summary(path)

    assert summary.status == "read-error"
    assert summary.safety_status == "blocked"
    assert "price_lookup_failed_count" in str(summary.error)


def test_render_dashboard_includes_unknown_safety_fields(tmp_path):
    import scripts.generate_agent_ops_dashboard as dashboard

    path = tmp_path / "dry_run.json"
    _write_json(path, {"dry_run": True, "as_of_date": "2026-05-12"})
    summary = dashboard.load_dry_run_summary(path)

    markdown = dashboard.render_dashboard(summary, expected_date="2026-05-12")

    assert "## 안전 게이트" in markdown
    assert "| 가격 조회 실패 | △ 추정 | `unknown` |" in markdown
    assert "| 대체 가격 사용 | △ 추정 | `unknown` |" in markdown
    assert "| 전체 로컬 안전 | △ 추정 | 브로커 호출 없음 |" in markdown


def test_render_dashboard_marks_stale_date_as_blocked_overall(tmp_path):
    import scripts.generate_agent_ops_dashboard as dashboard

    path = tmp_path / "dry_run.json"
    _write_json(
        path,
        {
            "dry_run": True,
            "as_of_date": "2026-05-11",
            "target_count": 10,
            "price_lookup_failed_count": 0,
            "price_fallback_count": 0,
        },
    )
    summary = dashboard.load_dry_run_summary(path)

    markdown = dashboard.render_dashboard(summary, expected_date="2026-05-12")

    assert "| dry-run 기준일 | X 오래됨 | `2026-05-11` |" in markdown
    assert "| 전체 로컬 안전 | X 막힘 | 브로커 호출 없음 |" in markdown


def test_run_prints_overall_safety_for_stale_date(tmp_path, capsys):
    import scripts.generate_agent_ops_dashboard as dashboard

    dry_run = tmp_path / "dry_run.json"
    output = tmp_path / "dashboard.md"
    _write_json(
        dry_run,
        {
            "dry_run": True,
            "as_of_date": "2026-05-11",
            "price_lookup_failed_count": 0,
            "price_fallback_count": 0,
        },
    )
    args = dashboard.parse_args(
        [
            "--dry-run-json",
            str(dry_run),
            "--output",
            str(output),
            "--expected-date",
            "2026-05-12",
        ]
    )

    result = dashboard.run(args)

    assert result == 0
    output_text = capsys.readouterr().out
    assert "safety_status=blocked" in output_text


def test_run_writes_markdown_dashboard(tmp_path, capsys):
    import scripts.generate_agent_ops_dashboard as dashboard

    dry_run = tmp_path / "dry_run.json"
    output = tmp_path / "dashboard.md"
    _write_json(
        dry_run,
        {
            "dry_run": True,
            "as_of_date": "2026-05-12",
            "target_count": 2,
            "sell_count": 0,
            "buy_count": 2,
            "price_lookup_failed_count": 0,
            "price_fallback_count": 0,
        },
    )
    args = dashboard.parse_args(
        [
            "--dry-run-json",
            str(dry_run),
            "--output",
            str(output),
            "--expected-date",
            "2026-05-12",
        ]
    )

    result = dashboard.run(args)

    assert result == 0
    text = output.read_text(encoding="utf-8")
    assert "# 에이전트 작업 연속성 대시보드" in text
    assert "## 에이전트 역할" in text
    assert "## 하기로 한 일" in text
    assert "## 근거" in text
    assert "## 안전 게이트" in text
    assert "## 타임라인" in text
    assert "scripts\\check_rebalance_readiness.py" in text
    output_text = capsys.readouterr().out
    assert "dashboard_written=" in output_text
    assert "safety_status=clean" in output_text


def test_run_opens_dashboard_when_requested(tmp_path, capsys):
    import scripts.generate_agent_ops_dashboard as dashboard

    dry_run = tmp_path / "dry_run.json"
    output = tmp_path / "dashboard.md"
    _write_json(
        dry_run,
        {
            "dry_run": True,
            "as_of_date": "2026-05-12",
            "target_count": 2,
            "sell_count": 0,
            "buy_count": 2,
            "price_lookup_failed_count": 0,
            "price_fallback_count": 0,
        },
    )
    opened_paths = []
    args = dashboard.parse_args(
        [
            "--dry-run-json",
            str(dry_run),
            "--output",
            str(output),
            "--expected-date",
            "2026-05-12",
            "--open",
        ]
    )

    result = dashboard.run(args, opener=opened_paths.append)

    assert result == 0
    assert opened_paths == [output]
    output_text = capsys.readouterr().out
    assert "dashboard_written=" in output_text
    assert "dashboard_opened=" in output_text


def test_run_reports_open_failure_without_failing_write(tmp_path, capsys):
    import scripts.generate_agent_ops_dashboard as dashboard

    dry_run = tmp_path / "dry_run.json"
    output = tmp_path / "dashboard.md"
    _write_json(
        dry_run,
        {
            "dry_run": True,
            "as_of_date": "2026-05-12",
            "price_lookup_failed_count": 0,
            "price_fallback_count": 0,
        },
    )
    args = dashboard.parse_args(
        [
            "--dry-run-json",
            str(dry_run),
            "--output",
            str(output),
            "--expected-date",
            "2026-05-12",
            "--open",
        ]
    )

    result = dashboard.run(
        args,
        opener=lambda _path: (_ for _ in ()).throw(OSError("notepad unavailable")),
    )

    assert result == 0
    assert output.exists()
    output_text = capsys.readouterr().out
    assert "dashboard_written=" in output_text
    assert "dashboard_open_failed=notepad unavailable" in output_text


def test_build_dashboard_model_extracts_latest_progress_sections(tmp_path):
    import scripts.generate_agent_ops_dashboard as dashboard

    progress = tmp_path / "progress.md"
    handoff = tmp_path / "HANDOFF_FOR_AGENTS.md"
    comparison = tmp_path / "rebalance_comparison_latest.md"
    dry_run = tmp_path / "dry_run.json"
    progress.write_text(
        "# quntbot Progress Log\n\n"
        "## 2026-05-13 Dashboard work\n\n"
        "### Completed\n\n"
        "- improved Markdown dashboard\n"
        "- added Streamlit dashboard\n\n"
        "### Verification\n\n"
        "- targeted tests passed\n\n"
        "### Notes\n\n"
        "- continue with browser verification later\n\n"
        "## 2026-05-12 Older work\n\n"
        "### Completed\n\n"
        "- old item\n",
        encoding="utf-8",
    )
    handoff.write_text("# Handoff\n\nNext safe command: run dashboard\n", encoding="utf-8")
    comparison.write_text("# Comparison\n\n- added_count: `0`\n", encoding="utf-8")
    _write_json(
        dry_run,
        {
            "dry_run": True,
            "as_of_date": "2026-05-13",
            "target_count": 3,
            "buy_count": 2,
            "sell_count": 1,
            "price_lookup_failed_count": 0,
            "price_fallback_count": 0,
        },
    )

    model = dashboard.build_dashboard_model(
        dry_run_json=dry_run,
        expected_date="2026-05-13",
        progress_path=progress,
        handoff_path=handoff,
        comparison_path=comparison,
    )

    assert model.latest_progress_title == "2026-05-13 Dashboard work"
    assert "improved Markdown dashboard" in model.completed_items
    assert "added Streamlit dashboard" in model.completed_items
    assert "targeted tests passed" in model.verification_items
    assert "continue with browser verification later" in model.note_items
    assert model.current_state["overall_local_safety"] == "clean"
    assert model.current_state["dry_run_as_of_date"] == "2026-05-13"
    assert model.task_lanes["done"]["status"] == "inferred"
    assert model.task_lanes["needs_input"]["status"] == "clean"


def test_render_dashboard_model_includes_work_continuity_sections(tmp_path):
    import scripts.generate_agent_ops_dashboard as dashboard

    dry_run = tmp_path / "dry_run.json"
    progress = tmp_path / "progress.md"
    _write_json(
        dry_run,
        {
            "dry_run": True,
            "as_of_date": "2026-05-13",
            "price_lookup_failed_count": 0,
            "price_fallback_count": 0,
        },
    )
    progress.write_text(
        "# quntbot Progress Log\n\n"
        "## 2026-05-13 Dashboard work\n\n"
        "### Completed\n\n"
        "- model added\n\n"
        "### Verification\n\n"
        "- tests passed\n",
        encoding="utf-8",
    )

    model = dashboard.build_dashboard_model(
        dry_run_json=dry_run,
        expected_date="2026-05-13",
        progress_path=progress,
        handoff_path=tmp_path / "HANDOFF_FOR_AGENTS.md",
        comparison_path=tmp_path / "rebalance_comparison_latest.md",
    )
    markdown = dashboard.render_dashboard_model(model)

    assert "## ★ 지금 확인할 것" in markdown
    assert "## 현재 상태" in markdown
    assert "## 작업 이어가기" in markdown
    assert "## 다음 안전 명령" in markdown
    assert "2026-05-13 Dashboard work" in markdown
    assert "모델을 추가했습니다" in markdown


def test_render_dashboard_model_uses_korean_status_markers(tmp_path):
    import scripts.generate_agent_ops_dashboard as dashboard

    dry_run = tmp_path / "dry_run.json"
    progress = tmp_path / "progress.md"
    _write_json(
        dry_run,
        {
            "dry_run": True,
            "as_of_date": "2026-05-12",
            "price_lookup_failed_count": 0,
            "price_fallback_count": 0,
        },
    )
    progress.write_text(
        "# quntbot Progress Log\n\n"
        "## 2026-05-13 Dashboard work\n\n"
        "### Completed\n\n"
        "- Korean marker work\n\n"
        "### Verification\n\n"
        "- tests pending\n",
        encoding="utf-8",
    )

    model = dashboard.build_dashboard_model(
        dry_run_json=dry_run,
        expected_date="2026-05-13",
        progress_path=progress,
        handoff_path=tmp_path / "HANDOFF_FOR_AGENTS.md",
        comparison_path=tmp_path / "rebalance_comparison_latest.md",
    )
    markdown = dashboard.render_dashboard_model(model)

    assert "# 에이전트 작업 연속성 대시보드" in markdown
    assert "★ 지금 확인할 것" in markdown
    assert "O 완료" in markdown
    assert "X 오래됨" in markdown
    assert "△ 추정" in markdown
    assert "하기로 한 일" in markdown


def test_render_dashboard_model_translates_task_descriptions_but_keeps_code(tmp_path):
    import scripts.generate_agent_ops_dashboard as dashboard

    dry_run = tmp_path / "dry_run.json"
    progress = tmp_path / "progress.md"
    _write_json(
        dry_run,
        {
            "dry_run": True,
            "as_of_date": "2026-05-14",
            "price_lookup_failed_count": 0,
            "price_fallback_count": 0,
        },
    )
    progress.write_text(
        "# quntbot Progress Log\n\n"
        "## 2026-05-14 Translation work\n\n"
        "### Completed\n\n"
        "- Added a read-only Streamlit dashboard:\n"
        "  - `scripts\\agent_ops_streamlit_dashboard.py`\n\n"
        "### Verification\n\n"
        "- targeted tests passed\n",
        encoding="utf-8",
    )

    model = dashboard.build_dashboard_model(
        dry_run_json=dry_run,
        expected_date="2026-05-14",
        progress_path=progress,
        handoff_path=tmp_path / "HANDOFF_FOR_AGENTS.md",
        comparison_path=tmp_path / "rebalance_comparison_latest.md",
    )
    markdown = dashboard.render_dashboard_model(model)

    assert "읽기 전용 Streamlit 대시보드를 추가했습니다" in markdown
    assert "`scripts\\agent_ops_streamlit_dashboard.py`" in markdown
    assert "대상 테스트가 통과했습니다" in markdown
