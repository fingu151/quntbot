from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace


def test_build_refresh_commands_runs_snapshot_then_ticker_briefs():
    from scripts.refresh_public_dashboard_artifacts import build_refresh_commands

    commands = build_refresh_commands(
        python_path=Path(".venv/Scripts/python.exe"),
        snapshot_output=Path("data/public.json"),
        ticker_brief_output=Path("data/ticker.json"),
        quality_queue_output=Path("data/queue.json"),
        quality_queue_markdown_output=Path("data/queue.md"),
        database_url="sqlite:///example.db",
        llm_status="ready",
        supplemental_input=Path("data/supplemental.json"),
        supplemental_source_input=Path("data/sources.json"),
        include_supplemental=True,
        fallback_existing_snapshot=True,
    )

    assert commands == [
        [
            ".venv\\Scripts\\python.exe",
            "-m",
            "scripts.ingest_supplemental_research_sources",
            "--input",
            "data\\sources.json",
            "--database-url",
            "sqlite:///example.db",
        ],
        [
            ".venv\\Scripts\\python.exe",
            "-m",
            "scripts.ingest_supplemental_research_reports",
            "--input",
            "data\\supplemental.json",
            "--database-url",
            "sqlite:///example.db",
        ],
        [
            ".venv\\Scripts\\python.exe",
            "scripts/generate_public_portfolio_snapshot.py",
            "--output",
            "data\\public.json",
            "--database-url",
            "sqlite:///example.db",
            "--fallback-existing-snapshot",
        ],
        [
            ".venv\\Scripts\\python.exe",
            "-m",
            "scripts.backfill_research_report_briefs",
            "--database-url",
            "sqlite:///example.db",
        ],
        [
            ".venv\\Scripts\\python.exe",
            "-m",
            "scripts.generate_research_report_ticker_briefs",
            "--output",
            "data\\ticker.json",
            "--database-url",
            "sqlite:///example.db",
            "--llm-status",
            "ready",
        ],
        [
            ".venv\\Scripts\\python.exe",
            "-m",
            "scripts.export_research_quality_queue",
            "--input",
            "data\\ticker.json",
            "--output",
            "data\\queue.json",
            "--markdown-output",
            "data\\queue.md",
        ],
        [
            ".venv\\Scripts\\python.exe",
            "-m",
            "scripts.export_latest_report_followup_queue",
            "--queue",
            "data\\queue.json",
            "--ticker-briefs",
            "data\\ticker.json",
            "--snapshot",
            "data\\public.json",
            "--json-output",
            "data\\latest_report_followup_queue.json",
            "--csv-output",
            "data\\latest_report_followup_queue.csv",
            "--markdown-output",
            "data\\latest_report_followup_queue.md",
        ],
        [
            ".venv\\Scripts\\python.exe",
            "-m",
            "scripts.export_supplemental_source_candidates",
            "--queue",
            "data\\queue.json",
            "--ticker-briefs",
            "data\\ticker.json",
            "--json-output",
            "data\\supplemental_source_candidates.json",
            "--csv-output",
            "data\\supplemental_source_candidates.csv",
            "--markdown-output",
            "data\\supplemental_source_candidates.md",
            "--latest-report-followup-queue",
            "data\\latest_report_followup_queue.json",
        ],
        [
            ".venv\\Scripts\\python.exe",
            "-m",
            "scripts.export_research_brief_qa_sample",
            "--ticker-briefs",
            "data\\ticker.json",
            "--queue",
            "data\\queue.json",
            "--json-output",
            "data\\research_brief_qa_sample.json",
            "--markdown-output",
            "data\\research_brief_qa_sample.md",
        ],
        [
            ".venv\\Scripts\\python.exe",
            "-m",
            "scripts.export_research_qa_action_queue",
            "--qa-sample",
            "data\\research_brief_qa_sample.json",
            "--source-discovery",
            "data\\supplemental_source_discovery_results.json",
            "--json-output",
            "data\\research_qa_action_queue.json",
            "--markdown-output",
            "data\\research_qa_action_queue.md",
        ],
    ]


def test_build_refresh_commands_skips_supplemental_when_disabled():
    from scripts.refresh_public_dashboard_artifacts import build_refresh_commands

    commands = build_refresh_commands(
        python_path=Path("python.exe"),
        snapshot_output=Path("data/public.json"),
        ticker_brief_output=Path("data/ticker.json"),
        supplemental_input=Path("data/supplemental.json"),
        include_supplemental=False,
    )

    assert len(commands) == 8
    assert "scripts.ingest_supplemental_research_reports" not in commands[0]


def test_build_refresh_commands_passes_refreshed_through_to_quality_queue():
    from scripts.refresh_public_dashboard_artifacts import build_refresh_commands

    commands = build_refresh_commands(
        python_path=Path("python.exe"),
        snapshot_output=Path("data/public.json"),
        ticker_brief_output=Path("data/ticker.json"),
        quality_queue_output=Path("data/queue.json"),
        quality_queue_markdown_output=Path("data/queue.md"),
        refreshed_through="2026-05-15",
    )

    assert commands[-5][-2:] == ["--refreshed-through", "2026-05-15"]


def test_build_refresh_commands_can_run_supplemental_discovery_then_rebuild_artifacts():
    from scripts.refresh_public_dashboard_artifacts import build_refresh_commands

    commands = build_refresh_commands(
        python_path=Path("python.exe"),
        snapshot_output=Path("data/public.json"),
        ticker_brief_output=Path("data/ticker.json"),
        quality_queue_output=Path("data/queue.json"),
        quality_queue_markdown_output=Path("data/queue.md"),
        supplemental_source_candidate_output=Path("data/candidates.json"),
        supplemental_source_discovery_output=Path("data/discovery.json"),
        supplemental_research_source_draft_output=Path("data/draft.json"),
        supplemental_research_source_verified_output=Path("data/verified.json"),
        supplemental_research_source_rejected_output=Path("data/rejected.json"),
        latest_report_followup_output=Path("data/latest.json"),
        latest_report_followup_csv_output=Path("data/latest.csv"),
        latest_report_followup_markdown_output=Path("data/latest.md"),
        include_supplemental_discovery=True,
        supplemental_discovery_max_candidates=10,
        supplemental_discovery_max_urls_per_candidate=8,
        database_url="sqlite:///example.db",
    )

    command_modules = [
        command[2] for command in commands if len(command) > 2 and command[1] == "-m"
    ]
    assert command_modules == [
        "scripts.backfill_research_report_briefs",
        "scripts.generate_research_report_ticker_briefs",
        "scripts.export_research_quality_queue",
        "scripts.export_latest_report_followup_queue",
        "scripts.export_supplemental_source_candidates",
        "scripts.discover_supplemental_research_sources",
        "scripts.verify_supplemental_research_sources",
        "scripts.ingest_supplemental_research_sources",
        "scripts.backfill_research_report_briefs",
        "scripts.generate_research_report_ticker_briefs",
        "scripts.export_research_quality_queue",
        "scripts.export_latest_report_followup_queue",
        "scripts.export_supplemental_source_candidates",
        "scripts.export_research_brief_qa_sample",
        "scripts.export_research_qa_action_queue",
    ]
    action_queue_command = commands[-1]
    assert action_queue_command[
        action_queue_command.index("--source-discovery") + 1
    ] == "data\\discovery.json"
    assert commands[6] == [
        "python.exe",
        "-m",
        "scripts.discover_supplemental_research_sources",
        "--candidates",
        "data\\candidates.json",
        "--discovery-output",
        "data\\discovery.json",
        "--source-draft-output",
        "data\\draft.json",
        "--max-candidates",
        "10",
        "--max-urls-per-candidate",
        "8",
    ]
    assert commands[8][-2:] == ["--database-url", "sqlite:///example.db"]


def test_build_refresh_commands_converts_supplemental_table_before_ingest():
    from scripts.refresh_public_dashboard_artifacts import build_refresh_commands

    commands = build_refresh_commands(
        python_path=Path("python.exe"),
        snapshot_output=Path("data/public.json"),
        ticker_brief_output=Path("data/ticker.json"),
        supplemental_input=Path("data/supplemental.json"),
        supplemental_source_input=None,
        supplemental_table_input=Path("data/supplemental.csv"),
        supplemental_table_format="csv",
        include_supplemental=True,
    )

    assert commands[:2] == [
        [
            "python.exe",
            "-m",
            "scripts.convert_supplemental_research_reports",
            "--input",
            "data\\supplemental.csv",
            "--output",
            "data\\supplemental.json",
            "--format",
            "csv",
        ],
        [
            "python.exe",
            "-m",
            "scripts.ingest_supplemental_research_reports",
            "--input",
            "data\\supplemental.json",
        ],
    ]


def test_refresh_dashboard_artifacts_stops_on_failed_step(monkeypatch):
    from scripts.refresh_public_dashboard_artifacts import main

    calls: list[list[str]] = []

    def fake_run(command, cwd=None, check=False):
        calls.append(list(command))
        return SimpleNamespace(returncode=7)

    monkeypatch.setattr("scripts.refresh_public_dashboard_artifacts.subprocess.run", fake_run)

    exit_code = main(["--python-path", "python.exe"])

    assert exit_code == 7
    assert len(calls) == 1
