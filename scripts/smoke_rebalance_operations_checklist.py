from __future__ import annotations

import argparse
import io
import re
from collections.abc import Callable, Sequence
from contextlib import redirect_stdout
from datetime import date
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import scripts.print_rebalance_operations_checklist as checklist


ChecklistRun = Callable[[argparse.Namespace], int]
SCRIPT_PATTERN = re.compile(r"scripts\\[^ \r\n,]+\.py|scripts/[^ \r\n,]+\.py")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Smoke-check the PAPER rebalance operations checklist without placing orders."
    )
    parser.add_argument("--as-of-date", type=_parse_date, default=date.today())
    parser.add_argument("--top-n", type=int, default=20)
    parser.add_argument("--root-dir", type=Path, default=ROOT_DIR)
    args = parser.parse_args(argv)
    if args.top_n <= 0:
        parser.error("--top-n must be greater than 0")
    return args


def run(
    args: argparse.Namespace,
    *,
    checklist_run: ChecklistRun = checklist.run,
) -> int:
    checklist_args = checklist.parse_args([
        "--as-of-date",
        str(args.as_of_date),
        "--top-n",
        str(args.top_n),
    ])
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        checklist_result = checklist_run(checklist_args)
    output = buffer.getvalue()
    print(output, end="")

    if checklist_result != 0:
        print(f"checklist_generation_failed={checklist_result}")
        return checklist_result

    referenced_scripts = _extract_script_paths(output)
    missing = [
        script_path
        for script_path in referenced_scripts
        if not (args.root_dir / script_path).exists()
    ]
    status = "ok" if not missing else "blocked"
    print(f"checklist_smoke_status={status}")
    print(f"referenced_script_count={len(referenced_scripts)}")
    print(f"missing_script_count={len(missing)}")
    for script_path in missing:
        print(f"missing_script={script_path}")
    return 0 if not missing else 1


def _extract_script_paths(output: str) -> list[Path]:
    seen: set[str] = set()
    paths: list[Path] = []
    for match in SCRIPT_PATTERN.findall(output):
        normalized = match.replace("/", "\\")
        if normalized in seen:
            continue
        seen.add(normalized)
        paths.append(Path(normalized))
    return paths


def main(argv: Sequence[str] | None = None) -> int:
    return run(parse_args(argv))


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


if __name__ == "__main__":
    raise SystemExit(main())
