from __future__ import annotations

import argparse
import io
from collections.abc import Callable, Sequence
from contextlib import redirect_stdout
from datetime import date
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import scripts.smoke_rebalance_operations_checklist as smoke


SmokeRun = Callable[[argparse.Namespace], int]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Archive the no-order PAPER rebalance checklist smoke output."
    )
    parser.add_argument("--as-of-date", type=_parse_date, default=date.today())
    parser.add_argument("--top-n", type=int, default=20)
    parser.add_argument("--output-log", type=Path, default=None)
    args = parser.parse_args(argv)
    if args.top_n <= 0:
        parser.error("--top-n must be greater than 0")
    if args.output_log is None:
        args.output_log = Path("logs") / f"rebalance_operations_checklist_{args.as_of_date}.log"
    return args


def run(
    args: argparse.Namespace,
    *,
    smoke_run: SmokeRun = smoke.run,
) -> int:
    smoke_args = smoke.parse_args([
        "--as-of-date",
        str(args.as_of_date),
        "--top-n",
        str(args.top_n),
    ])
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        smoke_result = smoke_run(smoke_args)
    smoke_output = buffer.getvalue()
    status = "ok" if smoke_result == 0 else "blocked"
    archive_output = (
        smoke_output
        + f"archive_status={status}\n"
        + f"archive_log={args.output_log}\n"
    )

    print(archive_output, end="")
    args.output_log.parent.mkdir(parents=True, exist_ok=True)
    args.output_log.write_text(archive_output, encoding="utf-8")
    return smoke_result


def main(argv: Sequence[str] | None = None) -> int:
    return run(parse_args(argv))


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


if __name__ == "__main__":
    raise SystemExit(main())
