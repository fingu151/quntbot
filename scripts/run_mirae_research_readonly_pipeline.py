from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import DATA_DIR
from scripts import compare_research_report_factor_impact
from scripts import generate_mirae_research_summary
from scripts import reanalyze_research_report_bodies
from scripts import sync_korean_research_reports


MIRAE_RESEARCH_URL = (
    "https://securities.miraeasset.com/bbs/board/message/list.do?categoryId=1533"
)
DEFAULT_SUMMARY_OUTPUT = DATA_DIR / "mirae_research_summary_latest.md"
DEFAULT_FACTOR_OUTPUT = DATA_DIR / "mirae_research_factor_impact_latest.md"
StepRunner = Callable[[Sequence[str]], int]


@dataclass(frozen=True)
class PipelineStep:
    name: str
    argv: list[str]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the Mirae research collection and reporting pipeline without orders."
    )
    parser.add_argument("--url", default=MIRAE_RESEARCH_URL)
    parser.add_argument("--source", default="mirae_asset")
    parser.add_argument("--broker", default="미래에셋증권")
    parser.add_argument("--pages", type=int, default=80)
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--start-date", type=_parse_date, default=date(2026, 1, 1))
    parser.add_argument("--end-date", type=_parse_date, default=None)
    parser.add_argument("--as-of-date", type=_parse_date, default=date.today())
    parser.add_argument("--top-n", type=int, default=20)
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--summary-output", type=Path, default=DEFAULT_SUMMARY_OUTPUT)
    parser.add_argument("--factor-output", type=Path, default=DEFAULT_FACTOR_OUTPUT)
    args = parser.parse_args(argv)
    if args.pages <= 0:
        parser.error("--pages must be greater than 0")
    if args.limit <= 0:
        parser.error("--limit must be greater than 0")
    if args.top_n <= 0:
        parser.error("--top-n must be greater than 0")
    return args


def run(
    args: argparse.Namespace,
    *,
    runners: Mapping[str, StepRunner] | None = None,
) -> int:
    step_runners = runners or {
        "sync": sync_korean_research_reports.main,
        "reanalyze": reanalyze_research_report_bodies.main,
        "summary": generate_mirae_research_summary.main,
        "factor_impact": compare_research_report_factor_impact.main,
    }
    for step in build_pipeline_steps(args):
        print(f"step_start={step.name}")
        exit_code = step_runners[step.name](step.argv)
        print(f"step_done={step.name} exit_code={exit_code}")
        if exit_code != 0:
            print(f"pipeline_status=failed failed_step={step.name}")
            print("orders_submitted=0")
            return exit_code
    print("pipeline_status=completed")
    print("orders_submitted=0")
    return 0


def build_pipeline_steps(args: argparse.Namespace) -> list[PipelineStep]:
    database_arg = _database_args(args.database_url)
    return [
        PipelineStep(
            "sync",
            [
                "--url",
                args.url,
                "--source",
                args.source,
                "--broker",
                args.broker,
                "--include-pdf-text",
                "--pages",
                str(args.pages),
                "--start-date",
                args.start_date.isoformat(),
                *(
                    ["--end-date", args.end_date.isoformat()]
                    if args.end_date is not None
                    else []
                ),
                *database_arg,
            ],
        ),
        PipelineStep(
            "reanalyze",
            [
                "--source",
                args.source,
                "--broker",
                args.broker,
                "--limit",
                str(args.limit),
                *database_arg,
            ],
        ),
        PipelineStep(
            "summary",
            [
                "--source",
                args.source,
                "--broker",
                args.broker,
                "--output",
                str(args.summary_output),
                "--limit",
                str(args.limit),
                *database_arg,
            ],
        ),
        PipelineStep(
            "factor_impact",
            [
                "--as-of-date",
                args.as_of_date.isoformat(),
                "--source",
                args.source,
                "--broker",
                args.broker,
                "--research-start-date",
                args.start_date.isoformat(),
                "--top-n",
                str(args.top_n),
                "--output-md",
                str(args.factor_output),
                *database_arg,
            ],
        ),
    ]


def _database_args(database_url: str | None) -> list[str]:
    if not database_url:
        return []
    return ["--database-url", database_url]


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def main(argv: Sequence[str] | None = None) -> int:
    return run(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
