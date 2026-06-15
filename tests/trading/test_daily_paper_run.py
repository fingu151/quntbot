from datetime import date, datetime
from pathlib import Path
from unittest.mock import MagicMock


def test_parse_args_requires_confirm_token():
    import scripts.daily_paper_run as script

    args = script.parse_args(["--confirm", "EXECUTE_PAPER_REBALANCE"])

    assert args.confirm == "EXECUTE_PAPER_REBALANCE"
    assert args.as_of_date == date.today()
    assert args.top_n == 30
    assert args.workers == 1


def test_parse_args_uses_retry_execution_report_when_default_exists(tmp_path, monkeypatch):
    import scripts.daily_paper_run as script

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "rebalance_execution_2026-05-12.json").write_text("{}", encoding="utf-8")
    (data_dir / "rebalance_execution_2026-05-12_retry_1.json").write_text("{}", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    args = script.parse_args([
        "--as-of-date",
        "2026-05-12",
        "--confirm",
        "EXECUTE_PAPER_REBALANCE",
    ])

    assert args.execution_report_json == Path("data") / "rebalance_execution_2026-05-12_retry_2.json"


def test_parse_args_preserves_explicit_execution_report_when_it_exists(tmp_path):
    import scripts.daily_paper_run as script

    execution_json = tmp_path / "execution.json"
    execution_json.write_text("{}", encoding="utf-8")

    args = script.parse_args([
        "--as-of-date",
        "2026-05-12",
        "--execution-report-json",
        str(execution_json),
        "--confirm",
        "EXECUTE_PAPER_REBALANCE",
    ])

    assert args.execution_report_json == execution_json


def test_run_blocks_without_confirm(tmp_path):
    import scripts.daily_paper_run as script

    sync_run = MagicMock()
    args = script.parse_args([
        "--as-of-date",
        "2026-05-12",
        "--dry-run-json",
        str(tmp_path / "dry.json"),
    ])

    result = script.run(args, sync_run=sync_run)

    assert result == 1
    sync_run.assert_not_called()


def test_run_chains_all_steps_and_starts_stop_monitor_after_success(tmp_path):
    import scripts.daily_paper_run as script

    dry_run_json = tmp_path / "dry_run.json"
    dry_run_md = tmp_path / "dry_run.md"
    execution_json = tmp_path / "execution.json"
    sync_run = MagicMock(return_value=0)
    prepare_review_run = MagicMock(return_value=0)
    readiness_run = MagicMock(return_value=0)
    execute_run = MagicMock(return_value=0)
    post_review_run = MagicMock(return_value=0)
    monitor_run = MagicMock()
    args = script.parse_args([
        "--as-of-date",
        "2026-05-12",
        "--start-date",
        "2026-05-01",
        "--top-n",
        "10",
        "--dry-run-json",
        str(dry_run_json),
        "--dry-run-md",
        str(dry_run_md),
        "--execution-report-json",
        str(execution_json),
        "--confirm",
        "EXECUTE_PAPER_REBALANCE",
    ])

    result = script.run(
        args,
        sync_run=sync_run,
        prepare_review_run=prepare_review_run,
        readiness_run=readiness_run,
        execute_run=execute_run,
        post_review_run=post_review_run,
        monitor_run=monitor_run,
    )

    assert result == 0
    assert sync_run.call_args.args[0].start_date == date(2026, 5, 1)
    assert sync_run.call_args.args[0].end_date == date(2026, 5, 12)
    assert sync_run.call_args.args[0].workers == 1
    prepare_args = prepare_review_run.call_args.args[0]
    assert prepare_args.as_of_date == date(2026, 5, 12)
    assert prepare_args.top_n == 10
    assert prepare_args.output_json == dry_run_json
    assert prepare_args.output_md == dry_run_md
    assert readiness_run.call_args.args[0].dry_run_json == dry_run_json
    assert readiness_run.call_args.args[0].expected_date == date(2026, 5, 12)
    execute_args = execute_run.call_args.args[0]
    assert execute_args.dry_run_json == dry_run_json
    assert execute_args.expected_date == date(2026, 5, 12)
    assert execute_args.confirm == "EXECUTE_PAPER_REBALANCE"
    assert execute_args.review_before_execute is True
    assert execute_args.execution_report_json == execution_json
    assert post_review_run.call_args.args[0].execution_report_json == execution_json
    monitor_run.assert_called_once_with()


def test_run_stops_before_order_when_readiness_fails(tmp_path):
    import scripts.daily_paper_run as script

    execute_run = MagicMock()
    monitor_run = MagicMock()
    args = script.parse_args([
        "--as-of-date",
        "2026-05-12",
        "--dry-run-json",
        str(tmp_path / "dry.json"),
        "--confirm",
        "EXECUTE_PAPER_REBALANCE",
    ])

    result = script.run(
        args,
        sync_run=MagicMock(return_value=0),
        prepare_review_run=MagicMock(return_value=0),
        readiness_run=MagicMock(return_value=1),
        execute_run=execute_run,
        monitor_run=monitor_run,
    )

    assert result == 1
    execute_run.assert_not_called()
    monitor_run.assert_not_called()


def test_run_stops_when_prepare_review_fails(tmp_path):
    import scripts.daily_paper_run as script

    readiness_run = MagicMock()
    execute_run = MagicMock()
    monitor_run = MagicMock()
    args = script.parse_args([
        "--as-of-date",
        "2026-05-12",
        "--dry-run-json",
        str(tmp_path / "dry.json"),
        "--confirm",
        "EXECUTE_PAPER_REBALANCE",
    ])

    result = script.run(
        args,
        sync_run=MagicMock(return_value=0),
        prepare_review_run=MagicMock(return_value=1),
        readiness_run=readiness_run,
        execute_run=execute_run,
        monitor_run=monitor_run,
    )

    assert result == 1
    readiness_run.assert_not_called()
    execute_run.assert_not_called()
    monitor_run.assert_not_called()


def test_run_does_not_start_bot_when_execution_fails(tmp_path):
    import scripts.daily_paper_run as script

    monitor_run = MagicMock()
    args = script.parse_args([
        "--as-of-date",
        "2026-05-12",
        "--dry-run-json",
        str(tmp_path / "dry.json"),
        "--confirm",
        "EXECUTE_PAPER_REBALANCE",
    ])

    result = script.run(
        args,
        sync_run=MagicMock(return_value=0),
        prepare_review_run=MagicMock(return_value=0),
        readiness_run=MagicMock(return_value=0),
        execute_run=MagicMock(return_value=1),
        monitor_run=monitor_run,
    )

    assert result == 1
    monitor_run.assert_not_called()


def test_run_does_not_start_bot_when_post_review_fails(tmp_path):
    import scripts.daily_paper_run as script

    monitor_run = MagicMock()
    args = script.parse_args([
        "--as-of-date",
        "2026-05-12",
        "--dry-run-json",
        str(tmp_path / "dry.json"),
        "--confirm",
        "EXECUTE_PAPER_REBALANCE",
    ])

    result = script.run(
        args,
        sync_run=MagicMock(return_value=0),
        prepare_review_run=MagicMock(return_value=0),
        readiness_run=MagicMock(return_value=0),
        execute_run=MagicMock(return_value=0),
        post_review_run=MagicMock(return_value=1),
        monitor_run=monitor_run,
    )

    assert result == 1
    monitor_run.assert_not_called()


def test_run_blocks_when_trade_mode_is_not_paper(tmp_path, monkeypatch):
    import scripts.daily_paper_run as script

    sync_run = MagicMock()
    monkeypatch.setattr(script, "TRADE_MODE", "LIVE")
    args = script.parse_args([
        "--as-of-date",
        "2026-05-12",
        "--dry-run-json",
        str(tmp_path / "dry.json"),
        "--confirm",
        "EXECUTE_PAPER_REBALANCE",
    ])

    result = script.run(args, sync_run=sync_run)

    assert result == 1
    sync_run.assert_not_called()


def test_intraday_monitor_registers_only_stop_monitor(monkeypatch):
    import scripts.daily_paper_run as script

    jobs = []
    stop_job = MagicMock()

    class FakeScheduler:
        def __init__(self, *, timezone):
            self.timezone = timezone

        def add_job(self, func, **kwargs):
            jobs.append((func, kwargs))

        def start(self):
            raise KeyboardInterrupt

    monkeypatch.setattr(script, "BlockingScheduler", FakeScheduler)
    monkeypatch.setattr(script, "KisClient", MagicMock(return_value="client"))
    engine_ctor = MagicMock(return_value="engine")
    monkeypatch.setattr(script, "TradingEngine", engine_ctor)
    monkeypatch.setattr(script, "get_engine", MagicMock(return_value="db-engine"))
    monkeypatch.setattr(script, "create_tables", MagicMock())
    monkeypatch.setattr(script, "_stop_loss_job", stop_job)

    script.run_intraday_stop_monitor(now=datetime(2026, 5, 12, 10, 0, tzinfo=script.KST))

    assert len(jobs) == 1
    assert jobs[0][1]["id"] == "intraday_stop_loss"
    assert jobs[0][1]["kwargs"] == {"engine": "engine"}
    assert engine_ctor.call_args.kwargs["atr_lookup"] is not None
    stop_job.assert_called_once_with("engine")


def test_intraday_monitor_skips_immediate_check_outside_market_hours(monkeypatch):
    import scripts.daily_paper_run as script

    stop_job = MagicMock()

    class FakeScheduler:
        def __init__(self, *, timezone):
            self.timezone = timezone

        def add_job(self, func, **kwargs):
            pass

        def start(self):
            raise KeyboardInterrupt

    monkeypatch.setattr(script, "BlockingScheduler", FakeScheduler)
    monkeypatch.setattr(script, "KisClient", MagicMock(return_value="client"))
    monkeypatch.setattr(script, "TradingEngine", MagicMock(return_value="engine"))
    monkeypatch.setattr(script, "get_engine", MagicMock(return_value="db-engine"))
    monkeypatch.setattr(script, "create_tables", MagicMock())
    monkeypatch.setattr(script, "_stop_loss_job", stop_job)

    script.run_intraday_stop_monitor(now=datetime(2026, 5, 12, 17, 36, tzinfo=script.KST))

    stop_job.assert_not_called()
