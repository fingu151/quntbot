"""APScheduler-based trading loop for pre-market sync, rebalance, and stops."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from apscheduler.schedulers.blocking import BlockingScheduler
from loguru import logger
from sqlalchemy import select

from config import BUSANSTOCK_SIGNAL, INVERSE_ETF, PORTFOLIO, REBALANCE, RESEARCH_REPORT
from src.data.collectors import PykrxMarketDataProvider, sync_phase1_data
from src.data.database import create_tables, get_engine, session_scope
from src.data.models import DailyPrice, MarketIndexPrice
from src.signals.busanstock_reader import fetch_and_store_busanstock_signals
from src.signals.research_report_reader import fetch_and_store_korean_research_reports
from src.factors.engine import calculate_factor_scores
from src.trading.allocation import compute_score_weights
from src.trading.engine import TradingEngine
from src.trading.inverse_etf_hedge import (
    calculate_inverse_etf_signal,
    compute_inverse_etf_orders,
)
from src.trading.kis_client import KisClient
from src.trading.macro_risk import load_macro_exposure_adjustment
from src.trading.rebalance_policy import compute_rebalance_sell_eligible_tickers
from src.trading.rebalancer import (
    compute_macro_reduction_orders,
    compute_rebalance_orders,
    execute_rebalance,
)
from src.trading.us_market_risk import scale_target_weights
from scripts import run_intraday_macro_risk_dry_run


@dataclass
class PreMarketSyncState:
    last_success_date: date | None = None
    last_failure_date: date | None = None
    last_error: str | None = None


def _pre_market_sync_job(
    *,
    db_engine: object,
    state: PreMarketSyncState,
    today: date | None = None,
    sync_func: Callable[..., dict[str, int]] = sync_phase1_data,
    provider: Any | None = None,
) -> None:
    """Sync recent market data before new rebalance orders are considered."""
    run_date = today or date.today()
    start_date = run_date - timedelta(days=REBALANCE.pre_market_sync_lookback_days)

    logger.info("=" * 50)
    logger.info("Pre-market data sync started")
    logger.info("=" * 50)
    logger.info(f"Sync window: {start_date} -> {run_date}")

    try:
        sync_kwargs: dict[str, Any] = {
            "engine": db_engine,
            "start_date": start_date,
            "end_date": run_date,
        }
        if provider is not None:
            sync_kwargs["provider"] = provider
        elif sync_func is sync_phase1_data:
            sync_kwargs["provider"] = PykrxMarketDataProvider()
        result = sync_func(**sync_kwargs)
    except Exception as exc:
        state.last_failure_date = run_date
        state.last_error = str(exc)
        logger.exception(f"Pre-market data sync failed: {exc}")
        return

    state.last_success_date = run_date
    state.last_error = None
    logger.success(
        "Pre-market data sync complete: "
        f"universe_count={result['universe_count']} "
        f"price_count={result['price_count']} "
        f"fundamental_count={result['fundamental_count']}"
    )


def _get_previous_closes(
    db_engine: object,
    tickers: list[str],
    *,
    as_of_date: date,
) -> dict[str, int | float]:
    if not tickers:
        return {}

    previous_closes: dict[str, int | float] = {}
    with session_scope(db_engine) as session:
        for ticker in tickers:
            row = session.scalars(
                select(DailyPrice)
                .where(
                    DailyPrice.ticker == ticker,
                    DailyPrice.date < as_of_date,
                    DailyPrice.close.is_not(None),
                )
                .order_by(DailyPrice.date.desc())
                .limit(1)
            ).first()
            if row is not None and row.close is not None:
                previous_closes[ticker] = row.close
    return previous_closes


def _load_daily_price_atr(
    db_engine: object,
    ticker: str,
    *,
    as_of_date: date,
    window: int,
) -> float | None:
    if window <= 0:
        return None
    with session_scope(db_engine) as session:
        rows = list(
            session.scalars(
                select(DailyPrice)
                .where(
                    DailyPrice.ticker == ticker,
                    DailyPrice.date <= as_of_date,
                    DailyPrice.high.is_not(None),
                    DailyPrice.low.is_not(None),
                    DailyPrice.close.is_not(None),
                )
                .order_by(DailyPrice.date.desc())
                .limit(window + 1)
            ).all()
        )
    rows.reverse()
    if len(rows) <= window:
        return None

    true_ranges: list[float] = []
    for previous, current in zip(rows[-window - 1 :], rows[-window:]):
        if previous.close is None or current.high is None or current.low is None:
            return None
        true_ranges.append(
            max(
                float(current.high) - float(current.low),
                abs(float(current.high) - float(previous.close)),
                abs(float(current.low) - float(previous.close)),
            )
        )
    if len(true_ranges) < window:
        return None
    return sum(true_ranges) / window


def _load_domestic_index_closes(db_engine: object, *, as_of_date: date) -> dict[str, list[float]]:
    if not hasattr(db_engine, "connect"):
        return {}
    with session_scope(db_engine) as session:
        rows = session.scalars(
            select(MarketIndexPrice)
            .where(
                MarketIndexPrice.symbol.in_(("KOSPI", "KOSDAQ")),
                MarketIndexPrice.date < as_of_date,
            )
            .order_by(MarketIndexPrice.symbol, MarketIndexPrice.date)
        ).all()
    closes: dict[str, list[float]] = {"KOSPI": [], "KOSDAQ": []}
    for row in rows:
        if row.close is not None and row.close > 0:
            closes.setdefault(row.symbol, []).append(float(row.close))
    return closes


def _rebalance_job(
    engine: TradingEngine,
    db_engine: object,
    sync_state: PreMarketSyncState | None = None,
    today: date | None = None,
    score_func: Callable[..., Any] = calculate_factor_scores,
    macro_adjustment_loader: Callable[..., Any] = load_macro_exposure_adjustment,
) -> None:
    """Run daily rebalance after the required pre-market sync succeeds."""
    run_date = today or date.today()
    logger.info("=" * 50)
    logger.info("Rebalance job started")
    logger.info("=" * 50)

    if (
        REBALANCE.require_pre_market_sync
        and sync_state is not None
        and sync_state.last_success_date != run_date
    ):
        logger.error(
            "Skipping rebalance because today's pre-market sync has not succeeded. "
            f"last_success_date={sync_state.last_success_date}, "
            f"last_failure_date={sync_state.last_failure_date}, "
            f"last_error={sync_state.last_error}"
        )
        return

    try:
        risk_off_sell_only = _check_daily_loss_limit_or_continue(engine)
        triggered = engine.check_exit_rules()
        if triggered:
            logger.warning(f"Exit sells executed before rebalance: {triggered}")

        logger.info("Calculating factor scores...")
        scores = score_func(db_engine, as_of_date=run_date)
        if not scores:
            logger.warning("No factor scores found. Rebalance skipped.")
            return
        logger.info(f"Factor scoring complete: {len(scores)} tickers")

        top_n = PORTFOLIO.n_holdings
        target_scores = scores[:top_n]
        buffer_scores = scores[:max(top_n, REBALANCE.sell_rank_buffer)]
        target_tickers = [s.ticker for s in target_scores]
        buffer_tickers = {s.ticker for s in buffer_scores}
        logger.info(f"Target portfolio {top_n} tickers: {target_tickers[:5]}...")

        holdings = engine.get_holdings()
        balance = engine.get_balance()
        output2 = (balance.get("output2") or [{}])[0]
        cash = int(output2.get("dnca_tot_amt", 0) or 0)
        logger.info(f"Holdings={len(holdings)}, cash={cash:,} KRW")

        prices: dict[str, int] = {}
        held_tickers = {h["ticker"] for h in holdings}
        inverse_allowed = set(INVERSE_ETF.allowed_tickers)
        buy_targets = [] if risk_off_sell_only else [
            ticker for ticker in target_tickers if ticker not in held_tickers
        ]
        for ticker in buy_targets:
            try:
                resp = engine.get_current_price(ticker)
                if resp.get("rt_cd") == "0":
                    price = int(resp.get("output", {}).get("stck_prpr", 0) or 0)
                    prices[ticker] = price
            except Exception as exc:
                logger.warning(f"Current price lookup failed: ticker={ticker}, error={exc}")
        previous_closes = _get_previous_closes(
            db_engine,
            buy_targets,
            as_of_date=run_date,
        )
        entry_dates = engine.get_exit_state_entry_dates()
        sell_eligible_tickers = compute_rebalance_sell_eligible_tickers(
            holdings=holdings,
            buffer_tickers=buffer_tickers,
            entry_dates=entry_dates,
            db_engine=db_engine,
            as_of_date=run_date,
            min_holding_trading_days=REBALANCE.min_holding_trading_days,
            protected_tickers=engine.get_rebalance_protected_tickers(),
        )
        if inverse_allowed:
            sell_eligible_tickers = [
                ticker for ticker in sell_eligible_tickers if ticker not in inverse_allowed
            ]
        target_weights = {}
        if PORTFOLIO.weighting == "score_weighted":
            target_weights = compute_score_weights(
                [(score.ticker, score.total_score) for score in target_scores],
                min_weight=PORTFOLIO.min_position_weight,
                max_weight=PORTFOLIO.max_position_weight,
            )
        macro_adjustment = macro_adjustment_loader(db_engine, as_of_date=run_date)
        if macro_adjustment.missing_sources:
            logger.warning(
                f"Macro overlay inputs missing: {macro_adjustment.missing_sources}. "
                "Run scripts/sync_market_indices.py and scripts/sync_macro_indicators.py "
                "or the overlay silently stays neutral."
            )
        inverse_signal = calculate_inverse_etf_signal(
            as_of_date=run_date,
            macro_adjustment=macro_adjustment,
            domestic_index_closes=_load_domestic_index_closes(db_engine, as_of_date=run_date),
            config=INVERSE_ETF,
        )
        if not risk_off_sell_only:
            for ticker in inverse_signal.selected_tickers:
                if ticker in held_tickers or ticker in prices:
                    continue
                try:
                    resp = engine.get_current_price(ticker)
                    if resp.get("rt_cd") == "0":
                        prices[ticker] = int(resp.get("output", {}).get("stck_prpr", 0) or 0)
                except Exception as exc:
                    logger.warning(f"Inverse ETF price lookup failed: ticker={ticker}, error={exc}")
        combined_buy_budget_multiplier = macro_adjustment.buy_budget_multiplier
        target_weights = scale_target_weights(
            target_weights,
            combined_buy_budget_multiplier,
        )
        if macro_adjustment.us_market.status in {"risk_off", "risk_on"}:
            logger.info(
                "US market buy adjustment: "
                f"status={macro_adjustment.us_market.status}, "
                f"multiplier={macro_adjustment.us_market.buy_budget_multiplier:.2f}, "
                f"reasons={macro_adjustment.us_market.reasons}"
            )
        if macro_adjustment.bond_yield.status in {"risk_off", "risk_on"}:
            logger.info(
                "Bond yield buy adjustment: "
                f"status={macro_adjustment.bond_yield.status}, "
                f"multiplier={macro_adjustment.bond_yield.buy_budget_multiplier:.2f}, "
                f"reasons={macro_adjustment.bond_yield.reasons}"
            )

        sells, buys = compute_rebalance_orders(
            holdings=holdings,
            target_tickers=[] if risk_off_sell_only else target_tickers,
            prices=prices,
            previous_closes=previous_closes,
            cash=cash,
            sell_eligible_tickers=sell_eligible_tickers,
            target_weights={} if risk_off_sell_only else target_weights,
            buy_budget_multiplier=(
                1.0 if risk_off_sell_only else combined_buy_budget_multiplier
            ),
        )
        if risk_off_sell_only:
            logger.warning("Risk-off mode active: rebalance buys suppressed.")
            buys = []
        macro_sells, macro_skips = compute_macro_reduction_orders(
            holdings=[
                holding for holding in holdings if str(holding.get("ticker", "")) not in inverse_allowed
            ],
            prices=prices,
            cash=cash,
            target_cash_ratio=macro_adjustment.cash_target,
            existing_sells=sells,
        )
        if macro_sells:
            logger.warning(
                f"Macro risk reduction sells generated: "
                f"{[(order.ticker, order.qty) for order in macro_sells]}"
            )
            sells.extend(macro_sells)
        if macro_skips:
            logger.warning(f"Macro risk reduction skipped: {macro_skips}")
        portfolio_value = cash + sum(
            int(holding.get("qty", 0) or 0)
            * int(
                prices.get(str(holding.get("ticker", "")))
                or holding.get("current_price")
                or 0
            )
            for holding in holdings
        )
        inverse_orders, inverse_skips = compute_inverse_etf_orders(
            holdings=holdings,
            prices=prices,
            cash=cash,
            portfolio_value=portfolio_value,
            signal=inverse_signal,
            entry_dates=entry_dates,
            as_of_date=run_date,
            config=INVERSE_ETF,
        )
        inverse_sells = [order for order in inverse_orders if order.side == "SELL"]
        inverse_buys = [] if risk_off_sell_only else [
            order for order in inverse_orders if order.side == "BUY"
        ]
        if inverse_sells or inverse_buys:
            logger.warning(
                "Inverse ETF hedge orders generated: "
                f"sells={[(order.ticker, order.qty) for order in inverse_sells]}, "
                f"buys={[(order.ticker, order.qty) for order in inverse_buys]}"
            )
            sells.extend(inverse_sells)
            buys.extend(inverse_buys)
        if inverse_skips:
            logger.warning(f"Inverse ETF hedge skipped: {inverse_skips}")
        preflight_report_path = (
            REBALANCE.dry_run_preflight_report_path
            if REBALANCE.require_dry_run_preflight
            else None
        )
        result = execute_rebalance(
            engine,
            sells,
            buys,
            preflight_report_path=preflight_report_path,
            expected_preflight_date=run_date,
            allow_buys=not risk_off_sell_only,
            enforce_preflight_order_match=True,
        )

        logger.info(f"Engine status: {engine.status}")
        logger.info(
            f"Rebalance complete: sold={len(result['sold'])}, "
            f"bought={len(result['bought'])}, failed={len(result['failed'])}"
        )

    except Exception as exc:
        logger.exception(f"Rebalance job failed: {exc}")


def _busanstock_signal_job(
    db_engine: object,
    *,
    fetch_func: Callable[..., int] = fetch_and_store_busanstock_signals,
) -> None:
    """Fetch and store today's Busanstock news/consensus overlay signals."""
    try:
        count = fetch_func(db_engine)
        if count:
            logger.info(f"Busanstock signal job: {count} signals stored")
    except Exception as exc:
        logger.warning(f"Busanstock signal job failed: {exc}")


def _research_report_job(
    db_engine: object,
    *,
    fetch_func: Callable[..., int] = fetch_and_store_korean_research_reports,
) -> None:
    """Fetch and store Korean broker research report metadata without placing orders."""
    try:
        count = fetch_func(
            db_engine,
            url=RESEARCH_REPORT.url,
            source=RESEARCH_REPORT.source,
            broker=RESEARCH_REPORT.broker,
        )
        if count:
            logger.info(f"Research report job: {count} reports stored")
    except Exception as exc:
        logger.warning(f"Research report job failed: {exc}")


def _intraday_macro_risk_dry_run_job(
    *,
    today: date | None = None,
    run_func: Callable[..., int] = run_intraday_macro_risk_dry_run.run,
) -> None:
    run_date = today or date.today()
    try:
        args = run_intraday_macro_risk_dry_run.parse_args([
            "--as-of-date",
            str(run_date),
        ])
        run_func(args)
        logger.info("Intraday macro risk dry-run report generated")
    except Exception as exc:
        logger.warning(f"Intraday macro risk dry-run failed: {exc}")


def _stop_loss_job(engine: TradingEngine) -> None:
    """Intraday staged exit monitor."""
    _check_daily_loss_limit_or_continue(engine)
    try:
        triggered = engine.check_exit_rules()
        if triggered:
            logger.warning(f"[Intraday exits] sells executed: {triggered}")
    except Exception as exc:
        logger.exception(f"Exit monitor failed: {exc}")


def _check_daily_loss_limit_or_continue(engine: TradingEngine) -> bool:
    try:
        risk_off_sell_only = engine.check_daily_loss_limit()
    except Exception as exc:
        logger.warning(
            "Daily loss limit check failed; continuing exit monitor. "
            f"New buys stay suppressed for this cycle. error={exc}"
        )
        return True

    if risk_off_sell_only:
        logger.error(
            "Daily loss limit exceeded. New buys are halted; exits remain active."
        )
    return risk_off_sell_only


def _split_hhmm(value: str) -> tuple[int, int]:
    hour, minute = value.split(":")
    return int(hour), int(minute)


def run_scheduler() -> None:
    """Start the blocking scheduler. Stop with Ctrl+C."""
    db_engine = get_engine()
    create_tables(db_engine)

    client = KisClient()
    engine = TradingEngine(
        client,
        atr_lookup=lambda ticker, as_of_date, window: _load_daily_price_atr(
            db_engine,
            ticker,
            as_of_date=as_of_date,
            window=window,
        ),
    )
    sync_state = PreMarketSyncState()

    scheduler = BlockingScheduler(timezone="Asia/Seoul")

    sync_hour, sync_minute = _split_hhmm(REBALANCE.pre_market_sync_time)
    scheduler.add_job(
        _pre_market_sync_job,
        trigger="cron",
        day_of_week="mon-fri",
        hour=sync_hour,
        minute=sync_minute,
        kwargs={"db_engine": db_engine, "state": sync_state},
        id="pre_market_sync",
    )

    rebalance_hour, rebalance_minute = _split_hhmm(REBALANCE.rebalance_time)
    scheduler.add_job(
        _rebalance_job,
        trigger="cron",
        day_of_week="mon-fri",
        hour=rebalance_hour,
        minute=rebalance_minute,
        kwargs={"engine": engine, "db_engine": db_engine, "sync_state": sync_state},
        id="daily_rebalance",
    )

    scheduler.add_job(
        _stop_loss_job,
        trigger="cron",
        day_of_week="mon-fri",
        hour="9-15",
        minute="*/10",
        kwargs={"engine": engine},
        id="intraday_stop_loss",
    )

    scheduler.add_job(
        _intraday_macro_risk_dry_run_job,
        trigger="cron",
        day_of_week="mon-fri",
        hour="9-15",
        # 매크로 입력(미국 지수·금리·지표)은 일중에 변하지 않으므로 30분이면 충분하다.
        minute="*/30",
        id="intraday_macro_risk_dry_run",
    )

    scheduler.add_job(
        _busanstock_signal_job,
        trigger="cron",
        day_of_week="mon-fri",
        hour=f"{BUSANSTOCK_SIGNAL.poll_start_hour}-{BUSANSTOCK_SIGNAL.poll_end_hour}",
        minute="*/15",
        kwargs={"db_engine": db_engine},
        id="busanstock_signal_poll",
    )
    logger.info(
        f"Busanstock signal polling enabled: "
        f"{BUSANSTOCK_SIGNAL.poll_start_hour}:00-{BUSANSTOCK_SIGNAL.poll_end_hour}:00 KST every 15 min"
    )

    if RESEARCH_REPORT.enabled:
        scheduler.add_job(
            _research_report_job,
            trigger="cron",
            day_of_week="mon-fri",
            hour=f"{RESEARCH_REPORT.poll_start_hour}-{RESEARCH_REPORT.poll_end_hour}",
            minute="*/30",
            kwargs={"db_engine": db_engine},
            id="research_report_poll",
        )
        logger.info(
            f"Research report polling enabled: source={RESEARCH_REPORT.source} "
            f"{RESEARCH_REPORT.poll_start_hour}:00-{RESEARCH_REPORT.poll_end_hour}:00 KST every 30 min"
        )

    logger.info(
        "Scheduler started: "
        f"pre_market_sync={REBALANCE.pre_market_sync_time} KST, "
        f"rebalance={REBALANCE.rebalance_time} KST"
    )
    logger.info("Press Ctrl+C to stop.")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped")
