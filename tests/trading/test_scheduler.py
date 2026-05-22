from datetime import date, timedelta
from unittest.mock import MagicMock, patch

from src.data.database import create_tables, get_engine, session_scope
from src.data.repositories import upsert_daily_prices, upsert_market_index_prices
from src.factors.models import FactorScore
from src.trading import scheduler
from src.trading.rebalancer import RebalanceOrder


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
    engine.check_exit_rules.return_value = []
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
    engine.check_exit_rules.return_value = []
    engine.get_holdings.return_value = []
    engine.get_balance.return_value = {"output2": [{"dnca_tot_amt": "100000"}]}
    engine.get_current_price.return_value = {"rt_cd": "0", "output": {"stck_prpr": "10000"}}
    engine.get_exit_state_entry_dates.return_value = {}
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
    engine.check_exit_rules.return_value = []
    engine.get_holdings.return_value = []
    engine.get_balance.return_value = {"output2": [{"dnca_tot_amt": "100000"}]}
    engine.get_current_price.return_value = {"rt_cd": "0", "output": {"stck_prpr": "121000"}}
    engine.get_exit_state_entry_dates.return_value = {}
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


def test_rebalance_job_applies_buffer_min_holding_and_target_weights():
    db_engine = get_engine("sqlite:///:memory:")
    create_tables(db_engine)
    with session_scope(db_engine) as session:
        upsert_daily_prices(
            session,
            [
                {"ticker": "HELD3", "date": date(2026, 5, 4), "close": 1000},
                {"ticker": "HELD3", "date": date(2026, 5, 5), "close": 1000},
                {"ticker": "HELD3", "date": date(2026, 5, 6), "close": 1000},
            ],
        )

    engine = MagicMock()
    engine.check_daily_loss_limit.return_value = False
    engine.check_exit_rules.return_value = []
    engine.get_holdings.return_value = [
        {"ticker": "HELD2", "qty": 1, "avg_price": 1000, "current_price": 1000},
        {"ticker": "HELD3", "qty": 1, "avg_price": 1000, "current_price": 1000},
        {"ticker": "NEWISH", "qty": 1, "avg_price": 1000, "current_price": 1000},
    ]
    engine.get_balance.return_value = {"output2": [{"dnca_tot_amt": "100000"}]}
    engine.get_current_price.return_value = {"rt_cd": "0", "output": {"stck_prpr": "10000"}}
    engine.get_exit_state_entry_dates.return_value = {
        "HELD3": date(2026, 5, 4),
        "NEWISH": date(2026, 5, 5),
    }
    state = scheduler.PreMarketSyncState(last_success_date=date(2026, 5, 6))
    scores = [
        FactorScore(
            ticker=ticker,
            name=ticker,
            market="KOSPI",
            as_of_date=date(2026, 5, 6),
            value_score=1.0,
            quality_score=1.0,
            momentum_score=1.0,
            yield_score=1.0,
            telegram_score=0.0,
            total_score=score,
            rank=rank,
        )
        for rank, (ticker, score) in enumerate(
            [("TARGET", 10.0), ("HELD2", 5.0), ("HELD3", 1.0), ("NEWISH", 0.5)],
            start=1,
        )
    ]
    compute = MagicMock(return_value=([], []))

    with (
        patch.object(
            scheduler,
            "PORTFOLIO",
            scheduler.PORTFOLIO.__class__(
                n_holdings=1,
                weighting="score_weighted",
                min_position_weight=0.03,
                max_position_weight=0.15,
            ),
        ),
        patch.object(
            scheduler,
            "REBALANCE",
            scheduler.REBALANCE.__class__(sell_rank_buffer=2, min_holding_trading_days=2),
        ),
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
            score_func=MagicMock(return_value=scores),
        )

    engine.check_exit_rules.assert_called_once()
    engine.check_stop_loss.assert_not_called()
    assert compute.call_args.kwargs["sell_eligible_tickers"] == ["HELD3"]
    assert compute.call_args.kwargs["target_weights"] == {"TARGET": 0.15}


def test_rebalance_job_applies_us_market_buy_budget_multiplier():
    db_engine = get_engine("sqlite:///:memory:")
    create_tables(db_engine)
    with session_scope(db_engine) as session:
        upsert_market_index_prices(
            session,
            [
                {"symbol": "NASDAQ", "date": date(2026, 5, 5), "close": 100.0},
                {"symbol": "NASDAQ", "date": date(2026, 5, 6), "close": 102.0},
                {"symbol": "SP500", "date": date(2026, 5, 5), "close": 100.0},
                {"symbol": "SP500", "date": date(2026, 5, 6), "close": 101.6},
                {"symbol": "DOW", "date": date(2026, 5, 5), "close": 100.0},
                {"symbol": "DOW", "date": date(2026, 5, 6), "close": 101.4},
            ],
        )
    engine = MagicMock()
    engine.check_daily_loss_limit.return_value = False
    engine.check_exit_rules.return_value = []
    engine.get_holdings.return_value = []
    engine.get_balance.return_value = {"output2": [{"dnca_tot_amt": "100000"}]}
    engine.get_current_price.return_value = {"rt_cd": "0", "output": {"stck_prpr": "10000"}}
    engine.get_exit_state_entry_dates.return_value = {}
    state = scheduler.PreMarketSyncState(last_success_date=date(2026, 5, 7))
    score = FactorScore(
        ticker="TARGET",
        name="TARGET",
        market="KOSPI",
        as_of_date=date(2026, 5, 7),
        value_score=1.0,
        quality_score=1.0,
        momentum_score=1.0,
        yield_score=1.0,
        telegram_score=0.0,
        total_score=10.0,
        rank=1,
    )
    compute = MagicMock(return_value=([], []))

    with (
        patch.object(
            scheduler,
            "PORTFOLIO",
            scheduler.PORTFOLIO.__class__(
                n_holdings=1,
                weighting="score_weighted",
                min_position_weight=0.03,
                max_position_weight=0.15,
            ),
        ),
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
            today=date(2026, 5, 7),
            score_func=MagicMock(return_value=[score]),
        )

    assert compute.call_args.kwargs["buy_budget_multiplier"] == 1.2
    assert compute.call_args.kwargs["target_weights"] == {"TARGET": 0.18}


def test_rebalance_job_combines_us_market_and_bond_yield_multipliers():
    db_engine = get_engine("sqlite:///:memory:")
    create_tables(db_engine)
    with session_scope(db_engine) as session:
        upsert_market_index_prices(
            session,
            [
                {"symbol": "NASDAQ", "date": date(2026, 5, 5), "close": 100.0},
                {"symbol": "NASDAQ", "date": date(2026, 5, 6), "close": 102.0},
                {"symbol": "SP500", "date": date(2026, 5, 5), "close": 100.0},
                {"symbol": "SP500", "date": date(2026, 5, 6), "close": 101.6},
                {"symbol": "DOW", "date": date(2026, 5, 5), "close": 100.0},
                {"symbol": "DOW", "date": date(2026, 5, 6), "close": 101.4},
                {"symbol": "KR10Y", "date": date(2026, 5, 5), "close": 3.40},
                {"symbol": "KR10Y", "date": date(2026, 5, 6), "close": 3.57},
                {"symbol": "US10Y", "date": date(2026, 5, 5), "close": 4.30},
                {"symbol": "US10Y", "date": date(2026, 5, 6), "close": 4.47},
            ],
        )
    engine = MagicMock()
    engine.check_daily_loss_limit.return_value = False
    engine.check_exit_rules.return_value = []
    engine.get_holdings.return_value = []
    engine.get_balance.return_value = {"output2": [{"dnca_tot_amt": "100000"}]}
    engine.get_current_price.return_value = {"rt_cd": "0", "output": {"stck_prpr": "10000"}}
    engine.get_exit_state_entry_dates.return_value = {}
    state = scheduler.PreMarketSyncState(last_success_date=date(2026, 5, 7))
    score = FactorScore(
        ticker="TARGET",
        name="TARGET",
        market="KOSPI",
        as_of_date=date(2026, 5, 7),
        value_score=1.0,
        quality_score=1.0,
        momentum_score=1.0,
        yield_score=1.0,
        telegram_score=0.0,
        total_score=10.0,
        rank=1,
    )
    compute = MagicMock(return_value=([], []))

    with (
        patch.object(
            scheduler,
            "PORTFOLIO",
            scheduler.PORTFOLIO.__class__(
                n_holdings=1,
                weighting="score_weighted",
                min_position_weight=0.03,
                max_position_weight=0.15,
            ),
        ),
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
            today=date(2026, 5, 7),
            score_func=MagicMock(return_value=[score]),
        )

    assert compute.call_args.kwargs["buy_budget_multiplier"] == 0.84
    assert compute.call_args.kwargs["target_weights"] == {"TARGET": 0.126}


def test_rebalance_job_runs_sell_only_when_daily_loss_limit_triggered():
    engine = MagicMock()
    engine.check_daily_loss_limit.return_value = True
    engine.check_exit_rules.return_value = []
    engine.get_holdings.return_value = []
    engine.get_balance.return_value = {"output2": [{"dnca_tot_amt": "100000"}]}
    engine.get_current_price.return_value = {"rt_cd": "0", "output": {"stck_prpr": "10000"}}
    engine.get_exit_state_entry_dates.return_value = {}
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
    sells = [RebalanceOrder("OLD", "SELL", 1, "risk reduction")]
    buys = [RebalanceOrder("005930", "BUY", 1, "target entry")]
    compute = MagicMock(return_value=(sells, buys))
    execute = MagicMock(return_value={"sold": ["OLD"], "bought": [], "failed": []})

    with (
        patch.object(scheduler, "_get_previous_closes", MagicMock(return_value={})),
        patch.object(scheduler, "compute_rebalance_orders", compute),
        patch.object(scheduler, "execute_rebalance", execute),
    ):
        scheduler._rebalance_job(
            engine=engine,
            db_engine="db-engine",
            sync_state=state,
            today=date(2026, 5, 6),
            score_func=MagicMock(return_value=[score]),
        )

    engine.check_exit_rules.assert_called_once()
    execute.assert_called_once()
    assert execute.call_args.args[1] == sells
    assert execute.call_args.args[2] == []
    assert execute.call_args.kwargs["allow_buys"] is False


def test_rebalance_job_still_checks_exits_when_daily_loss_check_fails():
    engine = MagicMock()
    engine.check_daily_loss_limit.side_effect = TimeoutError("balance timeout")
    engine.check_exit_rules.return_value = ["005930"]
    engine.get_holdings.return_value = []
    engine.get_balance.return_value = {"output2": [{"dnca_tot_amt": "100000"}]}
    engine.get_exit_state_entry_dates.return_value = {}
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
    sells = [RebalanceOrder("OLD", "SELL", 1, "risk reduction")]
    buys = [RebalanceOrder("005930", "BUY", 1, "target entry")]
    compute = MagicMock(return_value=(sells, buys))
    execute = MagicMock(return_value={"sold": ["OLD"], "bought": [], "failed": []})

    with (
        patch.object(scheduler, "_get_previous_closes", MagicMock(return_value={})),
        patch.object(scheduler, "compute_rebalance_orders", compute),
        patch.object(scheduler, "execute_rebalance", execute),
    ):
        scheduler._rebalance_job(
            engine=engine,
            db_engine="db-engine",
            sync_state=state,
            today=date(2026, 5, 6),
            score_func=MagicMock(return_value=[score]),
        )

    engine.check_daily_loss_limit.assert_called_once()
    engine.check_exit_rules.assert_called_once()
    engine.get_current_price.assert_not_called()
    assert compute.call_args.kwargs["target_tickers"] == []
    assert compute.call_args.kwargs["prices"] == {}
    assert compute.call_args.kwargs["target_weights"] == {}
    execute.assert_called_once()
    assert execute.call_args.args[1] == sells
    assert execute.call_args.args[2] == []
    assert execute.call_args.kwargs["allow_buys"] is False


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


def test_stop_loss_job_uses_generalized_exit_monitor():
    engine = MagicMock()
    engine.check_daily_loss_limit.return_value = False
    engine.check_exit_rules.return_value = ["005930"]

    scheduler._stop_loss_job(engine)

    engine.check_daily_loss_limit.assert_called_once()
    engine.check_exit_rules.assert_called_once()
    engine.check_stop_loss.assert_not_called()
    engine.check_trailing_stop.assert_not_called()


def test_stop_loss_job_runs_exit_monitor_when_daily_loss_limit_triggered():
    engine = MagicMock()
    engine.check_daily_loss_limit.return_value = True
    engine.check_exit_rules.return_value = ["005930"]

    scheduler._stop_loss_job(engine)

    engine.check_daily_loss_limit.assert_called_once()
    engine.check_exit_rules.assert_called_once()


def test_stop_loss_job_runs_exit_monitor_when_daily_loss_check_fails():
    engine = MagicMock()
    engine.check_daily_loss_limit.side_effect = TimeoutError("balance timeout")
    engine.check_exit_rules.return_value = ["005930"]

    scheduler._stop_loss_job(engine)

    engine.check_daily_loss_limit.assert_called_once()
    engine.check_exit_rules.assert_called_once()


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
