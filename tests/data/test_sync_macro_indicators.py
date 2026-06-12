from datetime import date

from sqlalchemy import select

from scripts import sync_macro_indicators
from src.data.database import session_scope
from src.data.models import MacroIndicatorRelease


def test_parse_args_rejects_reversed_dates():
    try:
        sync_macro_indicators.parse_args(["--start-date", "2026-01-02", "--end-date", "2026-01-01"])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("parse_args should reject reversed dates")


def test_run_upserts_fake_macro_indicator_rows(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'macro.db'}"
    args = sync_macro_indicators.parse_args(
        [
            "--start-date",
            "2026-01-01",
            "--end-date",
            "2026-01-31",
            "--database-url",
            database_url,
            # 실행자의 .env(FRED_API_KEY)에 의존하지 않도록 명시
            "--fred-api-key",
            "",
        ]
    )

    def fake_fetcher(start_date, end_date, api_key):
        assert start_date == date(2026, 1, 1)
        assert end_date == date(2026, 1, 31)
        assert api_key == ""
        return [
            {
                "indicator": "CPI",
                "period_date": date(2026, 1, 1),
                "release_date": date(2026, 1, 15),
                "value": 3.4,
                "previous_value": 3.1,
                "unit": "pct",
                "source": "fred",
                "source_url": "https://fred.stlouisfed.org/series/CPIAUCSL",
                "impact_rule": "inflation",
                "importance": "high",
            }
        ]

    exit_code = sync_macro_indicators.run(args, fetcher=fake_fetcher)

    assert exit_code == 0
    engine = sync_macro_indicators.get_engine(database_url)
    with session_scope(engine) as session:
        rows = session.scalars(select(MacroIndicatorRelease)).all()

    assert len(rows) == 1
    assert rows[0].indicator == "CPI"
    assert rows[0].previous_value == 3.1
    assert rows[0].impact_rule == "inflation"


def test_fetch_fred_requests_initial_release_vintages(monkeypatch):
    """FRED 기본 realtime 기간은 '오늘'이라 release_date가 전부 동기화 실행일이 된다.

    ALFRED 빈티지 파라미터(output_type=4 + 전체 realtime 기간)를 보내야
    realtime_start가 실제 최초 발표일이 된다.
    """
    captured_params = []

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"observations": []}

    def fake_get(url, params=None, timeout=None):
        captured_params.append(params)
        return FakeResponse()

    monkeypatch.setattr(sync_macro_indicators.requests, "get", fake_get)

    rows = sync_macro_indicators.fetch_fred_macro_indicators(
        date(2026, 1, 1), date(2026, 1, 31), "test-key"
    )

    assert rows == []
    assert len(captured_params) == len(sync_macro_indicators.FRED_SERIES)
    for params in captured_params:
        assert params["output_type"] == "4"
        assert params["realtime_start"] == "1776-07-04"
        assert params["realtime_end"] == "9999-12-31"


def test_fred_observations_to_rows_adds_previous_values():
    rows = sync_macro_indicators._fred_observations_to_rows(
        indicator="UNRATE",
        source_url="https://fred.stlouisfed.org/series/UNRATE",
        impact_rule="labor",
        unit="pct",
        observations=[
            {"date": "2026-01-01", "realtime_start": "2026-02-06", "value": "4.0"},
            {"date": "2026-02-01", "realtime_start": "2026-03-06", "value": "4.4"},
            {"date": "2026-03-01", "realtime_start": "2026-04-03", "value": "."},
        ],
    )

    assert rows == [
        {
            "indicator": "UNRATE",
            "period_date": date(2026, 1, 1),
            "release_date": date(2026, 2, 6),
            "value": 4.0,
            "previous_value": None,
            "unit": "pct",
            "source": "fred",
            "source_url": "https://fred.stlouisfed.org/series/UNRATE",
            "impact_rule": "labor",
            "importance": "high",
        },
        {
            "indicator": "UNRATE",
            "period_date": date(2026, 2, 1),
            "release_date": date(2026, 3, 6),
            "value": 4.4,
            "previous_value": 4.0,
            "unit": "pct",
            "source": "fred",
            "source_url": "https://fred.stlouisfed.org/series/UNRATE",
            "impact_rule": "labor",
            "importance": "high",
        },
    ]
