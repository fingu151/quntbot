from datetime import date, timedelta
from unittest.mock import MagicMock, patch

from src.data.database import create_tables, get_engine, session_scope
from src.data.repositories import upsert_daily_prices
from src.factors.models import FactorScore
from src.trading import scheduler


def test_pre_market_sync_job_records_success_for_today():
    state = scheduler.PreMarketSyncState()
    sync_func = MagicMock(return_value={
        "universe_count": 2,
        "price_count": 4,
        "fundamental_count": 4,
    })
    today = date(2026, 5, 6)

    scheduler._pre_market_sync_job(
        db_engine="db-engine",
        state=state,
        today=today,
        sync_func=sync_func,
    )

    assert state.last_success_date == today
    assert state.last_error is None
    sync_func.assert_called_once()
    call_kwargs = sync_func.call_args.kwargs
    assert call_kwargs["engine"] == "db-engine"
    assert call_kwargs["start_date"] == today - timedelta(days=30)
    assert call_kwargs["end_date"] == today


def test_pre_market_sync_job_records_failure_for_today():
    state = scheduler.PreMarketSyncState()
    sync_func = MagicMock(side_effect=RuntimeError("network down"))
    today = date(2026, 5, 6)

    scheduler._pre_market_sync_job(
        db_engine="db-engine",
        state=state,
        today=today,
        sync_func=sync_func,
    )

    assert state.last_success_date is None
    assert state.last_failure_date == today
    assert state.last_error == "network down"


def test_rebalance_job_skips_when_required_pre_market_sync_missing():
    engine = MagicMock()
    state = scheduler.PreMarketSyncState()

    scheduler._rebalance_job(
        engine=engine,
        db_engine="db-engine",
        sync_state=state,
        today=date(2026, 5, 6),
    )

    engine.check_daily_loss_limit.assert_not_called()


def test_rebalance_job_continues_after_today_pre_market_sync_success():
    engine = MagicMock()
    engine.check_daily_loss_limit.return_value = False
    engine.check_stop_loss.return_value = []
    engine._client.get_holdings.return_value = []
    engine._client.get_balance.return_value = {"output2": [{"dnca_tot_amt": "0"}]}
    state = scheduler.PreMarketSyncState(last_success_date=date(2026, 5, 6))

    scheduler._rebalance_job(
        engine=engine,
        db_engine="db-engine",
        sync_state=state,
        today=date(2026, 5, 6),
        score_func=MagicMock(return_value=[]),
    )

    engine.check_daily_loss_limit.assert_called_once()


def test_rebalance_job_passes_dry_run_preflight_report_to_executor():
    engine = MagicMock()
    engine.check_daily_loss_limit.return_value = False
    engine.check_stop_loss.return_value = []
    engine.get_holdings.return_value = []
    engine.get_balance.return_value = {"output2": [{"dnca_tot_amt": "100000"}]}
    engine.get_current_price.return_value = {"rt_cd": "0", "output": {"stck_prpr": "10000"}}
    state = scheduler.PreMarketSyncState(last_success_date=date(2026, 5, 6))
    score = FactorScore(
        ticker="005930",
        name="Samsung",
        market="KOSPI",
        as_of_date=date(2026, 5, 6),
        value_score=1.0,
        quality_score=1.0,
        momentum_score=1.0,
        yield_score=1.0,
        telegram_score=0.0,
        total_score=1.0,
        rank=1,
    )
    execute = MagicMock(return_value={"sold": [], "bought": [], "failed": []})

    with (
        patch.object(scheduler, "_get_previous_closes", MagicMock(return_value={})),
        patch.object(scheduler, "execute_rebalance", execute),
    ):
        scheduler._rebalance_job(
            engine=engine,
            db_engine="db-engine",
            sync_state=state,
            today=date(2026, 5, 6),
            score_func=MagicMock(return_value=[score]),
        )

    assert execute.call_args.kwargs["preflight_report_path"] == (
        scheduler.REBALANCE.dry_run_preflight_report_path
    )
    assert execute.call_args.kwargs["expected_preflight_date"] == date(2026, 5, 6)


def test_rebalance_job_passes_previous_closes_to_rebalancer():
    db_engine = get_engine("sqlite:///:memory:")
    create_tables(db_engine)
    with session_scope(db_engine) as session:
        upsert_daily_prices(
            session,
            [
                {
                    "ticker": "005930",
                    "date": date(2026, 5, 5),
                    "open": 90000,
                    "high": 101000,
                    "low": 89000,
                    "close": 100000,
                    "volume": 1000,
                }
            ],
        )

    engine = MagicMock()
    engine.check_daily_loss_limit.return_value = False
    engine.check_stop_loss.return_value = []
    engine.get_holdings.return_value = []
    engine.get_balance.return_value = {"output2": [{"dnca_tot_amt": "100000"}]}
    engine.get_current_price.return_value = {"rt_cd": "0", "output": {"stck_prpr": "121000"}}
    state = scheduler.PreMarketSyncState(last_success_date=date(2026, 5, 6))
    score = FactorScore(
        ticker="005930",
        name="Samsung",
        market="KOSPI",
        as_of_date=date(2026, 5, 6),
        value_score=1.0,
        quality_score=1.0,
        momentum_score=1.0,
        yield_score=1.0,
        telegram_score=0.0,
        total_score=1.0,
        rank=1,
    )
    compute = MagicMock(return_value=([], []))

    with (
        patch.object(scheduler, "compute_rebalance_orders", compute),
        patch.object(
            scheduler,
            "execute_rebalance",
            MagicMock(return_value={"sold": [], "bought": [], "failed": []}),
        ),
    ):
        scheduler._rebalance_job(
            engine=engine,
            db_engine=db_engine,
            sync_state=state,
            today=date(2026, 5, 6),
            score_func=MagicMock(return_value=[score]),
        )

    assert compute.call_args.kwargs["previous_closes"] == {"005930": 100000}


def test_run_scheduler_registers_pre_market_sync_before_rebalance():
    fake_scheduler = MagicMock()
    fake_scheduler.start.side_effect = KeyboardInterrupt

    with (
        patch.object(scheduler, "BlockingScheduler", return_value=fake_scheduler),
        patch.object(scheduler, "get_engine", return_value="db-engine"),
        patch.object(scheduler, "create_tables"),
        patch.object(scheduler, "KisClient"),
    ):
        scheduler.run_scheduler()

    job_ids = [call.kwargs["id"] for call in fake_scheduler.add_job.call_args_list]
    assert job_ids[:2] == ["pre_market_sync", "daily_rebalance"]
    assert "busanstock_signal_poll" in job_ids
    assert "research_report_poll" in job_ids
    rebalance_kwargs = fake_scheduler.add_job.call_args_list[1].kwargs["kwargs"]
    assert isinstance(rebalance_kwargs["sync_state"], scheduler.PreMarketSyncState)


def test_run_scheduler_uses_busanstock_signal_poll_window():
    fake_scheduler = MagicMock()
    fake_scheduler.start.side_effect = KeyboardInterrupt

    with (
        patch.object(scheduler, "BlockingScheduler", return_value=fake_scheduler),
        patch.object(scheduler, "get_engine", return_value="db-engine"),
        patch.object(scheduler, "create_tables"),
        patch.object(scheduler, "KisClient"),
        patch.object(
            scheduler,
            "BUSANSTOCK_SIGNAL",
            scheduler.BUSANSTOCK_SIGNAL.__class__(poll_start_hour=10, poll_end_hour=11),
        ),
    ):
        scheduler.run_scheduler()

    busanstock_job = next(
        call for call in fake_scheduler.add_job.call_args_list
        if call.kwargs["id"] == "busanstock_signal_poll"
    )
    assert busanstock_job.kwargs["hour"] == "10-11"


def test_busanstock_signal_job_fetches_and_logs_count():
    fetcher = MagicMock(return_value=7)

    scheduler._busanstock_signal_job("db-engine", fetch_func=fetcher)

    fetcher.assert_called_once_with("db-engine")


def test_research_report_job_fetches_configured_hankyung_source():
    fetcher = MagicMock(return_value=10)

    scheduler._research_report_job("db-engine", fetch_func=fetcher)

    fetcher.assert_called_once_with(
        "db-engine",
        url=scheduler.RESEARCH_REPORT.url,
        source=scheduler.RESEARCH_REPORT.source,
        broker=scheduler.RESEARCH_REPORT.broker,
    )


def test_run_scheduler_uses_research_report_poll_window():
    fake_scheduler = MagicMock()
    fake_scheduler.start.side_effect = KeyboardInterrupt

    with (
        patch.object(scheduler, "BlockingScheduler", return_value=fake_scheduler),
        patch.object(scheduler, "get_engine", return_value="db-engine"),
        patch.object(scheduler, "create_tables"),
        patch.object(scheduler, "KisClient"),
        patch.object(
            scheduler,
            "RESEARCH_REPORT",
            scheduler.RESEARCH_REPORT.__class__(
                enabled=True,
                source="hankyung_consensus",
                broker="한경 컨센서스",
                url="https://markets.hankyung.com/consensus",
                poll_start_hour=7,
                poll_end_hour=8,
            ),
        ),
    ):
        scheduler.run_scheduler()

    research_job = next(
        call for call in fake_scheduler.add_job.call_args_list
        if call.kwargs["id"] == "research_report_poll"
    )
    assert research_job.kwargs["hour"] == "7-8"
