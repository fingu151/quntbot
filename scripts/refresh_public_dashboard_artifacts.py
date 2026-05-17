from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys
from typing import Sequence


ROOT_DIR = Path(__file__).resolve().parents[1]


def build_refresh_commands(
    *,
    python_path: Path,
    snapshot_output: Path,
    ticker_brief_output: Path,
    quality_queue_output: Path = Path("data/research_quality_review_queue.json"),
    quality_queue_markdown_output: Path = Path("data/research_quality_review_queue.md"),
    supplemental_source_candidate_output: Path = Path("data/supplemental_source_candidates.json"),
    supplemental_source_candidate_csv_output: Path = Path("data/supplemental_source_candidates.csv"),
    supplemental_source_candidate_markdown_output: Path = Path("data/supplemental_source_candidates.md"),
    supplemental_source_discovery_output: Path = Path("data/supplemental_source_discovery_results.json"),
    supplemental_research_source_draft_output: Path = Path("data/supplemental_research_sources_draft.json"),
    supplemental_research_source_verified_output: Path = Path("data/supplemental_research_sources_verified.json"),
    supplemental_research_source_rejected_output: Path = Path("data/supplemental_research_sources_rejected.json"),
    latest_report_followup_output: Path = Path("data/latest_report_followup_queue.json"),
    latest_report_followup_csv_output: Path = Path("data/latest_report_followup_queue.csv"),
    latest_report_followup_markdown_output: Path = Path("data/latest_report_followup_queue.md"),
    research_brief_qa_sample_output: Path = Path("data/research_brief_qa_sample.json"),
    research_brief_qa_sample_markdown_output: Path = Path("data/research_brief_qa_sample.md"),
    research_qa_action_queue_output: Path = Path("data/research_qa_action_queue.json"),
    research_qa_action_queue_markdown_output: Path = Path("data/research_qa_action_queue.md"),
    database_url: str | None = None,
    llm_status: str = "disabled",
    supplemental_input: Path = Path("data/supplemental_research_reports.json"),
    supplemental_source_input: Path | None = Path("data/supplemental_research_sources.json"),
    supplemental_table_input: Path | None = None,
    supplemental_table_format: str = "auto",
    include_supplemental: bool = False,
    include_supplemental_discovery: bool = False,
    supplemental_discovery_max_candidates: int = 112,
    supplemental_discovery_max_urls_per_candidate: int = 8,
    refreshed_through: str | None = None,
    fallback_existing_snapshot: bool = False,
) -> list[list[str]]:
    commands: list[list[str]] = []
    if include_supplemental:
        if supplemental_source_input is not None:
            supplemental_source_command = [
                str(python_path),
                "-m",
                "scripts.ingest_supplemental_research_sources",
                "--input",
                str(supplemental_source_input),
            ]
            if database_url:
                supplemental_source_command.extend(["--database-url", database_url])
            commands.append(supplemental_source_command)
        if supplemental_table_input is not None:
            commands.append(
                [
                    str(python_path),
                    "-m",
                    "scripts.convert_supplemental_research_reports",
                    "--input",
                    str(supplemental_table_input),
                    "--output",
                    str(supplemental_input),
                    "--format",
                    supplemental_table_format,
                ]
            )
        supplemental_command = [
            str(python_path),
            "-m",
            "scripts.ingest_supplemental_research_reports",
            "--input",
            str(supplemental_input),
        ]
        if database_url:
            supplemental_command.extend(["--database-url", database_url])
        commands.append(supplemental_command)

    snapshot_command = [
        str(python_path),
        "scripts/generate_public_portfolio_snapshot.py",
        "--output",
        str(snapshot_output),
    ]
    ticker_command = [
        str(python_path),
        "-m",
        "scripts.generate_research_report_ticker_briefs",
        "--output",
        str(ticker_brief_output),
    ]
    if database_url:
        snapshot_command.extend(["--database-url", database_url])
        ticker_command.extend(["--database-url", database_url])
    if fallback_existing_snapshot:
        snapshot_command.append("--fallback-existing-snapshot")
    ticker_command.extend(["--llm-status", llm_status])
    quality_queue_command = [
        str(python_path),
        "-m",
        "scripts.export_research_quality_queue",
        "--input",
        str(ticker_brief_output),
        "--output",
        str(quality_queue_output),
        "--markdown-output",
        str(quality_queue_markdown_output),
    ]
    if refreshed_through:
        quality_queue_command.extend(["--refreshed-through", refreshed_through])
    supplemental_source_candidate_command = [
        str(python_path),
        "-m",
        "scripts.export_supplemental_source_candidates",
        "--queue",
        str(quality_queue_output),
        "--ticker-briefs",
        str(ticker_brief_output),
        "--json-output",
        str(supplemental_source_candidate_output),
        "--csv-output",
        str(supplemental_source_candidate_csv_output),
        "--markdown-output",
        str(supplemental_source_candidate_markdown_output),
    ]
    latest_report_followup_command = [
        str(python_path),
        "-m",
        "scripts.export_latest_report_followup_queue",
        "--queue",
        str(quality_queue_output),
        "--ticker-briefs",
        str(ticker_brief_output),
        "--snapshot",
        str(snapshot_output),
        "--json-output",
        str(latest_report_followup_output),
        "--csv-output",
        str(latest_report_followup_csv_output),
        "--markdown-output",
        str(latest_report_followup_markdown_output),
    ]
    supplemental_source_candidate_command.extend(
        [
            "--latest-report-followup-queue",
            str(latest_report_followup_output),
        ]
    )
    research_brief_qa_sample_command = [
        str(python_path),
        "-m",
        "scripts.export_research_brief_qa_sample",
        "--ticker-briefs",
        str(ticker_brief_output),
        "--queue",
        str(quality_queue_output),
        "--json-output",
        str(research_brief_qa_sample_output),
        "--markdown-output",
        str(research_brief_qa_sample_markdown_output),
    ]
    research_qa_action_queue_command = [
        str(python_path),
        "-m",
        "scripts.export_research_qa_action_queue",
        "--qa-sample",
        str(research_brief_qa_sample_output),
        "--source-discovery",
        str(supplemental_source_discovery_output),
        "--json-output",
        str(research_qa_action_queue_output),
        "--markdown-output",
        str(research_qa_action_queue_markdown_output),
    ]
    supplemental_discovery_commands: list[list[str]] = []
    if include_supplemental_discovery:
        supplemental_discovery_commands.extend(
            [
                [
                    str(python_path),
                    "-m",
                    "scripts.discover_supplemental_research_sources",
                    "--candidates",
                    str(supplemental_source_candidate_output),
                    "--discovery-output",
                    str(supplemental_source_discovery_output),
                    "--source-draft-output",
                    str(supplemental_research_source_draft_output),
                    "--max-candidates",
                    str(supplemental_discovery_max_candidates),
                    "--max-urls-per-candidate",
                    str(supplemental_discovery_max_urls_per_candidate),
                ],
                [
                    str(python_path),
                    "-m",
                    "scripts.verify_supplemental_research_sources",
                    "--input",
                    str(supplemental_research_source_draft_output),
                    "--verified-output",
                    str(supplemental_research_source_verified_output),
                    "--rejected-output",
                    str(supplemental_research_source_rejected_output),
                ],
                [
                    str(python_path),
                    "-m",
                    "scripts.ingest_supplemental_research_sources",
                    "--input",
                    str(supplemental_research_source_verified_output),
                ],
            ]
        )
        if database_url:
            supplemental_discovery_commands[-1].extend(["--database-url", database_url])
        supplemental_discovery_commands.extend(
            [
                ticker_command.copy(),
                quality_queue_command.copy(),
                latest_report_followup_command.copy(),
                supplemental_source_candidate_command.copy(),
            ]
        )
    commands.extend(
        [
            snapshot_command,
            ticker_command,
            quality_queue_command,
            latest_report_followup_command,
            supplemental_source_candidate_command,
            *supplemental_discovery_commands,
            research_brief_qa_sample_command,
            research_qa_action_queue_command,
        ]
    )
    return commands


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Refresh all read-only public dashboard artifacts.",
    )
    parser.add_argument("--python-path", type=Path, default=Path(sys.executable))
    parser.add_argument(
        "--snapshot-output",
        type=Path,
        default=Path("data/public_portfolio_snapshot.json"),
    )
    parser.add_argument(
        "--ticker-brief-output",
        type=Path,
        default=Path("data/research_report_ticker_briefs.json"),
    )
    parser.add_argument(
        "--quality-queue-output",
        type=Path,
        default=Path("data/research_quality_review_queue.json"),
    )
    parser.add_argument(
        "--quality-queue-markdown-output",
        type=Path,
        default=Path("data/research_quality_review_queue.md"),
    )
    parser.add_argument(
        "--supplemental-source-candidate-output",
        type=Path,
        default=Path("data/supplemental_source_candidates.json"),
    )
    parser.add_argument(
        "--supplemental-source-candidate-csv-output",
        type=Path,
        default=Path("data/supplemental_source_candidates.csv"),
    )
    parser.add_argument(
        "--supplemental-source-candidate-markdown-output",
        type=Path,
        default=Path("data/supplemental_source_candidates.md"),
    )
    parser.add_argument(
        "--supplemental-source-discovery-output",
        type=Path,
        default=Path("data/supplemental_source_discovery_results.json"),
    )
    parser.add_argument(
        "--supplemental-research-source-draft-output",
        type=Path,
        default=Path("data/supplemental_research_sources_draft.json"),
    )
    parser.add_argument(
        "--supplemental-research-source-verified-output",
        type=Path,
        default=Path("data/supplemental_research_sources_verified.json"),
    )
    parser.add_argument(
        "--supplemental-research-source-rejected-output",
        type=Path,
        default=Path("data/supplemental_research_sources_rejected.json"),
    )
    parser.add_argument(
        "--latest-report-followup-output",
        type=Path,
        default=Path("data/latest_report_followup_queue.json"),
    )
    parser.add_argument(
        "--latest-report-followup-csv-output",
        type=Path,
        default=Path("data/latest_report_followup_queue.csv"),
    )
    parser.add_argument(
        "--latest-report-followup-markdown-output",
        type=Path,
        default=Path("data/latest_report_followup_queue.md"),
    )
    parser.add_argument(
        "--research-brief-qa-sample-output",
        type=Path,
        default=Path("data/research_brief_qa_sample.json"),
    )
    parser.add_argument(
        "--research-brief-qa-sample-markdown-output",
        type=Path,
        default=Path("data/research_brief_qa_sample.md"),
    )
    parser.add_argument(
        "--research-qa-action-queue-output",
        type=Path,
        default=Path("data/research_qa_action_queue.json"),
    )
    parser.add_argument(
        "--research-qa-action-queue-markdown-output",
        type=Path,
        default=Path("data/research_qa_action_queue.md"),
    )
    parser.add_argument("--database-url", default=None)
    parser.add_argument(
        "--supplemental-input",
        type=Path,
        default=Path("data/supplemental_research_reports.json"),
        help="Optional curated supplemental report JSON. Ingested first when the file exists.",
    )
    parser.add_argument(
        "--supplemental-source-input",
        type=Path,
        default=Path("data/supplemental_research_sources.json"),
        help="Optional public report URL source list. Fetched and ingested before manual supplemental JSON.",
    )
    parser.add_argument(
        "--skip-supplemental-sources",
        action="store_true",
        help="Skip public supplemental URL source ingestion.",
    )
    parser.add_argument(
        "--supplemental-table-input",
        type=Path,
        default=None,
        help="Optional CSV, TSV, or XLSX table. Converted to supplemental JSON before ingest.",
    )
    parser.add_argument(
        "--supplemental-table-format",
        choices=["auto", "csv", "tsv", "xlsx"],
        default="auto",
    )
    parser.add_argument(
        "--skip-supplemental",
        action="store_true",
        help="Skip supplemental report ingestion even if the input file exists.",
    )
    parser.add_argument(
        "--include-supplemental-discovery",
        action="store_true",
        help=(
            "After quality queues are built, discover public supplemental URLs, "
            "verify PDF text contains the ticker, ingest verified rows, and rebuild research artifacts."
        ),
    )
    parser.add_argument("--supplemental-discovery-max-candidates", type=int, default=112)
    parser.add_argument("--supplemental-discovery-max-urls-per-candidate", type=int, default=8)
    parser.add_argument(
        "--llm-status",
        choices=["disabled", "ready", "generated"],
        default="disabled",
    )
    parser.add_argument(
        "--refreshed-through",
        default=None,
        help=(
            "Date through which supported report sources were broadly refreshed. "
            "Forwarded to the quality queue so stale items are marked as not found."
        ),
    )
    parser.add_argument(
        "--fallback-existing-snapshot",
        action="store_true",
        help="Reuse the existing public snapshot if KIS holdings are temporarily unavailable.",
    )
    args = parser.parse_args(argv)

    commands = build_refresh_commands(
        python_path=args.python_path,
        snapshot_output=args.snapshot_output,
        ticker_brief_output=args.ticker_brief_output,
        quality_queue_output=args.quality_queue_output,
        quality_queue_markdown_output=args.quality_queue_markdown_output,
        supplemental_source_candidate_output=args.supplemental_source_candidate_output,
        supplemental_source_candidate_csv_output=args.supplemental_source_candidate_csv_output,
        supplemental_source_candidate_markdown_output=args.supplemental_source_candidate_markdown_output,
        supplemental_source_discovery_output=args.supplemental_source_discovery_output,
        supplemental_research_source_draft_output=args.supplemental_research_source_draft_output,
        supplemental_research_source_verified_output=args.supplemental_research_source_verified_output,
        supplemental_research_source_rejected_output=args.supplemental_research_source_rejected_output,
        latest_report_followup_output=args.latest_report_followup_output,
        latest_report_followup_csv_output=args.latest_report_followup_csv_output,
        latest_report_followup_markdown_output=args.latest_report_followup_markdown_output,
        research_brief_qa_sample_output=args.research_brief_qa_sample_output,
        research_brief_qa_sample_markdown_output=args.research_brief_qa_sample_markdown_output,
        research_qa_action_queue_output=args.research_qa_action_queue_output,
        research_qa_action_queue_markdown_output=args.research_qa_action_queue_markdown_output,
        database_url=args.database_url,
        llm_status=args.llm_status,
        supplemental_input=args.supplemental_input,
        supplemental_source_input=(
            None
            if args.skip_supplemental_sources or not args.supplemental_source_input.exists()
            else args.supplemental_source_input
        ),
        supplemental_table_input=args.supplemental_table_input,
        supplemental_table_format=args.supplemental_table_format,
        include_supplemental=(
            not args.skip_supplemental
            and (
                args.supplemental_input.exists()
                or args.supplemental_source_input.exists()
                or (args.supplemental_table_input is not None and args.supplemental_table_input.exists())
            )
        ),
        include_supplemental_discovery=args.include_supplemental_discovery,
        supplemental_discovery_max_candidates=args.supplemental_discovery_max_candidates,
        supplemental_discovery_max_urls_per_candidate=args.supplemental_discovery_max_urls_per_candidate,
        refreshed_through=args.refreshed_through,
        fallback_existing_snapshot=args.fallback_existing_snapshot,
    )
    for command in commands:
        print("running=" + " ".join(command))
        completed = subprocess.run(command, cwd=ROOT_DIR, check=False)
        if completed.returncode != 0:
            print(f"failed_exit_code={completed.returncode}")
            return int(completed.returncode)
    print("public_dashboard_artifacts_refreshed=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
