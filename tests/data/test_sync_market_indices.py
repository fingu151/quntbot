from datetime import date

from sqlalchemy import select

from scripts import sync_market_indices
from src.data.database import session_scope
from src.data.models import MarketIndexPrice


def test_parse_args_rejects_reversed_dates():
    try:
        sync_market_indices.parse_args(["--start-date", "2026-01-02", "--end-date", "2026-01-01"])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("parse_args should reject reversed dates")


def test_run_upserts_fake_market_index_rows(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'indices.db'}"
    args = sync_market_indices.parse_args(
        [
            "--start-date",
            "2026-01-01",
            "--end-date",
            "2026-01-02",
            "--database-url",
            database_url,
        ]
    )

    def fake_krx(start_date, end_date):
        assert start_date == date(2026, 1, 1)
        assert end_date == date(2026, 1, 2)
        return [
            {
                "symbol": "KOSPI",
                "date": date(2026, 1, 1),
                "open": 100,
                "high": 101,
                "low": 99,
                "close": 100,
                "volume": 10,
            }
        ]

    def fake_us(start_date, end_date):
        assert start_date == date(2026, 1, 1)
        assert end_date == date(2026, 1, 2)
        return [
            {
                "symbol": "NASDAQ",
                "date": date(2026, 1, 1),
                "open": 200,
                "high": 202,
                "low": 198,
                "close": 201,
                "volume": 20,
            },
            {
                "symbol": "SP500",
                "date": date(2026, 1, 1),
                "open": 300,
                "high": 303,
                "low": 297,
                "close": 302,
                "volume": 30,
            },
            {
                "symbol": "DOW",
                "date": date(2026, 1, 1),
                "open": 400,
                "high": 404,
                "low": 396,
                "close": 403,
                "volume": 40,
            },
        ]

    def fake_bond_yields(start_date, end_date):
        assert start_date == date(2026, 1, 1)
        assert end_date == date(2026, 1, 2)
        return [
            {
                "symbol": "KR10Y",
                "date": date(2026, 1, 1),
                "open": None,
                "high": None,
                "low": None,
                "close": 3.2,
                "volume": None,
            },
            {
                "symbol": "US10Y",
                "date": date(2026, 1, 1),
                "open": None,
                "high": None,
                "low": None,
                "close": 4.4,
                "volume": None,
            },
        ]

    exit_code = sync_market_indices.run(
        args,
        krx_fetcher=fake_krx,
        us_fetcher=fake_us,
        bond_yield_fetcher=fake_bond_yields,
    )

    assert exit_code == 0
    engine = sync_market_indices.get_engine(database_url)
    with session_scope(engine) as session:
        rows = session.scalars(select(MarketIndexPrice).order_by(MarketIndexPrice.symbol)).all()

    assert [(row.symbol, row.close) for row in rows] == [
        ("DOW", 403),
        ("KOSPI", 100),
        ("KR10Y", 3.2),
        ("NASDAQ", 201),
        ("SP500", 302),
        ("US10Y", 4.4),
    ]


def test_us_10y_yield_normalizer_handles_yahoo_index_scale():
    assert sync_market_indices._normalize_us_10y_yield(44.5) == 4.45
    assert sync_market_indices._normalize_us_10y_yield(4.45) == 4.45
    assert sync_market_indices._normalize_us_10y_yield(None) is None
