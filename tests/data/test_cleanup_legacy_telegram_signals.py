from __future__ import annotations

import sqlite3


def _create_legacy_db(path):
    connection = sqlite3.connect(path)
    connection.execute(
        """
        create table telegram_signals (
            id integer primary key,
            message_date date not null,
            ticker varchar(12) not null,
            signal_type varchar(10) not null,
            star_rating integer not null,
            raw_score float not null,
            target_price float,
            message_id integer,
            fetched_at datetime not null
        )
        """
    )
    connection.execute(
        """
        insert into telegram_signals (
            id, message_date, ticker, signal_type, star_rating, raw_score,
            target_price, message_id, fetched_at
        ) values (1, '2026-05-09', '005930', 'warning', 0, -1.0, null, 58, '2026-05-09 14:09:59')
        """
    )
    connection.commit()
    connection.close()


def _table_names(path):
    connection = sqlite3.connect(path)
    rows = connection.execute(
        "select name from sqlite_master where type = 'table' order by name"
    ).fetchall()
    connection.close()
    return {row[0] for row in rows}


def test_dry_run_reports_legacy_table_without_dropping(tmp_path, capsys):
    from scripts import cleanup_legacy_telegram_signals as cleanup

    db_path = tmp_path / "legacy.db"
    _create_legacy_db(db_path)
    args = cleanup.parse_args([
        "--database-url",
        f"sqlite:///{db_path}",
        "--archive-csv",
        str(tmp_path / "archive.csv"),
        "--archive-md",
        str(tmp_path / "archive.md"),
    ])

    result = cleanup.run(args)

    output = capsys.readouterr().out
    assert result == 0
    assert "cleanup_mode=dry-run" in output
    assert "legacy_table_exists=true" in output
    assert "row_count=1" in output
    assert "dropped=false" in output
    assert "telegram_signals" in _table_names(db_path)
    assert not (tmp_path / "archive.csv").exists()


def test_apply_archives_rows_and_drops_legacy_table(tmp_path, capsys):
    from scripts import cleanup_legacy_telegram_signals as cleanup

    db_path = tmp_path / "legacy.db"
    csv_path = tmp_path / "archive.csv"
    md_path = tmp_path / "archive.md"
    _create_legacy_db(db_path)
    args = cleanup.parse_args([
        "--database-url",
        f"sqlite:///{db_path}",
        "--archive-csv",
        str(csv_path),
        "--archive-md",
        str(md_path),
        "--apply",
    ])

    result = cleanup.run(args)

    output = capsys.readouterr().out
    assert result == 0
    assert "archive_status=written" in output
    assert "dropped=true" in output
    assert "telegram_signals" not in _table_names(db_path)
    assert "005930" in csv_path.read_text(encoding="utf-8")
    assert "row_count: `1`" in md_path.read_text(encoding="utf-8")


def test_apply_is_noop_when_legacy_table_is_absent(tmp_path, capsys):
    from scripts import cleanup_legacy_telegram_signals as cleanup

    db_path = tmp_path / "clean.db"
    sqlite3.connect(db_path).close()
    args = cleanup.parse_args([
        "--database-url",
        f"sqlite:///{db_path}",
        "--archive-csv",
        str(tmp_path / "archive.csv"),
        "--archive-md",
        str(tmp_path / "archive.md"),
        "--apply",
    ])

    result = cleanup.run(args)

    output = capsys.readouterr().out
    assert result == 0
    assert "legacy_table_exists=false" in output
    assert "dropped=false" in output
    assert not (tmp_path / "archive.csv").exists()
