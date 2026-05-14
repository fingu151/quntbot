from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import LOG_DIR


LOG_PATTERN = "rebalance_operations_checklist_*.log"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Clean up old PAPER rebalance checklist logs."
    )
    parser.add_argument("--logs-dir", type=Path, default=LOG_DIR)
    parser.add_argument("--keep", type=int, default=20)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Delete old logs. Without this flag, only prints delete candidates.",
    )
    args = parser.parse_args(argv)
    if args.keep < 0:
        parser.error("--keep must be zero or greater")
    return args


def run(args: argparse.Namespace) -> int:
    logs = sorted(args.logs_dir.glob(LOG_PATTERN), key=lambda path: path.name, reverse=True)
    keep = logs[:args.keep]
    delete_candidates = logs[args.keep:]

    print(f"cleanup_mode={'apply' if args.apply else 'dry-run'}")
    print(f"logs_dir={args.logs_dir}")
    print(f"matched_count={len(logs)}")
    print(f"kept_count={len(keep)}")
    print(f"delete_candidate_count={len(delete_candidates)}")

    deleted_count = 0
    for path in delete_candidates:
        print(f"delete_candidate={path}")
        if args.apply:
            path.unlink()
            deleted_count += 1
            print(f"deleted={path}")
    print(f"deleted_count={deleted_count}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    return run(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
