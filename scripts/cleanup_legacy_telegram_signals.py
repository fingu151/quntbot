from __future__ import annotations

import argparse
import csv
from collections.abc import Sequence
from pathlib import Path
import sys
from typing import Any

from sqlalchemy import Engine, text

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import DATABASE_URL, DATA_DIR
from src.data.database import get_engine


LEGACY_TABLE = "telegram_signals"
LEGACY_COLUMNS = [
    "id",
    "message_date",
    "ticker",
    "signal_type",
    "star_rating",
    "raw_score",
    "target_price",
    "message_id",
    "fetched_at",
]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Archive and drop the removed MTProto Telegram stock-signal table."
    )
    parser.add_argument("--database-url", default=DATABASE_URL)
    parser.add_argument(
        "--archive-csv",
        type=Path,
        default=DATA_DIR / "legacy_telegram_signals_archive.csv",
    )
    parser.add_argument(
        "--archive-md",
        type=Path,
        default=DATA_DIR / "legacy_telegram_signals_archive.md",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write archives and drop the legacy table. Without this flag, only reports.",
    )
    return parser.parse_args(argv)


def table_exists(engine: Engine, table_name: str = LEGACY_TABLE) -> bool:
    with engine.connect() as connection:
        if engine.dialect.name == "sqlite":
            result = connection.execute(
                text(
                    "select count(*) from sqlite_master "
                    "where type = 'table' and name = :table_name"
                ),
                {"table_name": table_name},
            )
            return bool(result.scalar_one())
        return table_name in engine.dialect.get_table_names(connection)


def load_legacy_rows(engine: Engine) -> list[dict[str, Any]]:
    with engine.connect() as connection:
        result = connection.execute(
            text(
                f"select {', '.join(LEGACY_COLUMNS)} from {LEGACY_TABLE} "
                "order by message_date, ticker, id"
            )
        )
        return [dict(row._mapping) for row in result]


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=LEGACY_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Legacy Telegram Signals Archive",
        "",
        "The MTProto Telegram stock-signal scorer was removed. These rows were preserved before dropping the legacy SQLite table.",
        "",
        f"- row_count: `{len(rows)}`",
        "",
    ]
    if rows:
        lines.append("| " + " | ".join(LEGACY_COLUMNS) + " |")
        lines.append("| " + " | ".join("---" for _ in LEGACY_COLUMNS) + " |")
        for row in rows:
            values = [str(row.get(column, "") or "") for column in LEGACY_COLUMNS]
            lines.append("| " + " | ".join(value.replace("|", "\\|") for value in values) + " |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def drop_legacy_table(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(text(f"drop table if exists {LEGACY_TABLE}"))


def run(args: argparse.Namespace) -> int:
    engine = get_engine(args.database_url)
    exists = table_exists(engine)
    print(f"cleanup_mode={'apply' if args.apply else 'dry-run'}")
    print(f"database_url={args.database_url}")
    print(f"legacy_table={LEGACY_TABLE}")
    print(f"legacy_table_exists={str(exists).lower()}")
    if not exists:
        print("row_count=0")
        print("dropped=false")
        return 0

    rows = load_legacy_rows(engine)
    print(f"row_count={len(rows)}")
    print(f"archive_csv={args.archive_csv}")
    print(f"archive_md={args.archive_md}")
    if not args.apply:
        print("dropped=false")
        return 0

    write_csv(rows, args.archive_csv)
    write_markdown(rows, args.archive_md)
    drop_legacy_table(engine)
    print("archive_status=written")
    print("dropped=true")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    return run(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
