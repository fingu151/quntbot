from datetime import date, timedelta

from src.data.database import create_tables, get_engine, session_scope
from src.data.repositories import (
    upsert_daily_prices,
    upsert_market_index_prices,
    upsert_stocks,
)
from src.strategies.kwr import (
    KwrCandidate,
    calculate_kwr_candidates,
    calculate_kwr_score_from_rows,
    risk_guard_signal,
)


def _price_rows(
    ticker: str,
    *,
    start: date,
    closes: list[float],
    market: str = "KOSPI",
) -> list[dict]:
    rows = []
    previous = closes[0]
    for index, close in enumerate(closes):
        current_date = start + timedelta(days=index)
        open_price = previous * 0.96 if index == len(closes) - 1 else close
        high = max(open_price, close) * 1.01
        low = min(open_price, close) * 0.99
        rows.append(
            {
                "ticker": ticker,
                "date": current_date,
                "open": open_price,
                "high": high,
                "low": low,
                "close": close,
                "volume": 1000 + index,
            }
        )
        previous = close
    return rows


def _index_rows(symbol: str, *, start: date, closes: list[float]) -> list[dict]:
    return [
        {
            "symbol": symbol,
            "date": start + timedelta(days=index),
            "open": close,
            "high": close,
            "low": close,
            "close": close,
            "volume": 1000,
        }
        for index, close in enumerate(closes)
    ]


def _kosdaq_washout_rows() -> list[dict]:
    rows = _price_rows(
        "KDQ",
        start=date(2025, 7, 1),
        closes=[100.0 + index * 0.1 for index in range(220)] + [95.0, 92.0, 76.0],
        market="KOSDAQ",
    )
    rows[-1]["volume"] = 50000
    return rows


def test_kospi_kwr_score_counts_gap_money_flow_and_liquidity_components():
    closes = [100.0] * 70 + [98.0, 96.0, 94.0, 90.0]
    rows = _price_rows("KPI", start=date(2026, 1, 1), closes=closes)

    score = calculate_kwr_score_from_rows(rows, market="KOSPI")

    assert score >= 40.0


def test_kosdaq_kwr_score_counts_connors_extreme_and_trend_components():
    rows = _kosdaq_washout_rows()

    score = calculate_kwr_score_from_rows(rows, market="KOSDAQ")

    assert score >= 40.0


def test_risk_guard_signal_disables_kospi_without_visible_washout():
    signal = risk_guard_signal(
        market="KOSPI",
        kwr_score=70.0,
        index_ret20=0.02,
        index_dd60=-0.05,
        index_below_ma200=False,
    )

    assert signal is None


def test_risk_guard_signal_sets_kosdaq_hold_by_market_regime():
    long_hold = risk_guard_signal(
        market="KOSDAQ",
        kwr_score=40.0,
        index_ret20=-0.11,
        index_dd60=-0.15,
        index_below_ma200=True,
    )
    fast_hold = risk_guard_signal(
        market="KOSDAQ",
        kwr_score=45.0,
        index_ret20=-0.02,
        index_dd60=-0.08,
        index_below_ma200=True,
    )

    assert long_hold == 20
    assert fast_hold == 10


def test_calculate_kwr_candidates_returns_ranked_no_order_candidates_from_db():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    start = date(2025, 7, 1)
    as_of_date = start + timedelta(days=222)
    with session_scope(engine) as session:
        upsert_stocks(
            session,
            [
                {"ticker": "KDQ", "name": "Kosdaq Washout", "market": "KOSDAQ"},
                {"ticker": "QUIET", "name": "Quiet Stock", "market": "KOSDAQ"},
            ],
        )
        upsert_daily_prices(
            session,
            _kosdaq_washout_rows()
            + _price_rows(
                "QUIET",
                start=start,
                closes=[100.0 + index * 0.01 for index in range(223)],
                market="KOSDAQ",
            ),
        )
        upsert_market_index_prices(
            session,
            _index_rows(
                "KOSDAQ",
                start=start,
                closes=[100.0 + index * 0.1 for index in range(223)],
            ),
        )

    candidates = calculate_kwr_candidates(engine, as_of_date=as_of_date)

    assert candidates
    assert isinstance(candidates[0], KwrCandidate)
    assert candidates[0].ticker == "KDQ"
    assert candidates[0].hold_days in {10, 20}
    assert all(candidate.ticker != "QUIET" for candidate in candidates)


def test_calculate_kwr_candidates_skips_stale_stock_price_history():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    start = date(2025, 7, 1)
    as_of_date = start + timedelta(days=222)
    stale_rows = _kosdaq_washout_rows()
    for row in stale_rows:
        row["date"] = row["date"] - timedelta(days=5)
    with session_scope(engine) as session:
        upsert_stocks(
            session,
            [{"ticker": "KDQ", "name": "Stale Washout", "market": "KOSDAQ"}],
        )
        upsert_daily_prices(session, stale_rows)
        upsert_market_index_prices(
            session,
            _index_rows(
                "KOSDAQ",
                start=start,
                closes=[100.0 + index * 0.1 for index in range(223)],
            ),
        )

    candidates = calculate_kwr_candidates(engine, as_of_date=as_of_date)

    assert candidates == []
