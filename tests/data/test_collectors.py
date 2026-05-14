from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from sqlalchemy import func, select

from src.data import collectors
from src.data.collectors import PykrxMarketDataProvider, sync_phase1_data
from src.data.database import create_tables, get_engine, session_scope
from src.data.models import InvestorFlow, Stock, SyncRun
from src.data.repositories import count_rows


class FakeProvider:
    def get_universe(self):
        return [
            {"ticker": "005930", "name": "삼성전자", "market": "KOSPI"},
            {"ticker": "091990", "name": "셀트리온헬스케어", "market": "KOSDAQ"},
        ]

    def get_daily_prices(self, ticker, start_date, end_date):
        return [
            {
                "ticker": ticker,
                "date": start_date,
                "open": 100,
                "high": 110,
                "low": 90,
                "close": 105,
                "volume": 1000,
            }
        ]

    def get_fundamentals(self, ticker, start_date, end_date):
        return [
            {
                "ticker": ticker,
                "date": end_date,
                "bps": 1000,
                "per": 10,
                "pbr": 1,
                "eps": 100,
                "div": 2,
                "dps": 50,
            }
        ]

    def get_investor_flows(self, ticker, start_date, end_date):
        return [
            {
                "ticker": ticker,
                "date": end_date,
                "individual_net_buy": 100,
                "foreign_net_buy": -50,
                "institution_net_buy": -50,
            }
        ]


def test_sync_phase1_data_stores_universe_prices_fundamentals_and_success_run():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)

    result = sync_phase1_data(
        engine=engine,
        provider=FakeProvider(),
        start_date=date(2026, 5, 1),
        end_date=date(2026, 5, 2),
    )

    with session_scope(engine) as session:
        counts = count_rows(session)
        sync_runs = session.scalars(select(SyncRun)).all()

    assert result == {
        "universe_count": 2,
        "price_count": 2,
        "fundamental_count": 2,
        "investor_flow_count": 2,
    }
    assert counts["stocks"] == 2
    assert counts["daily_prices"] == 2
    assert counts["fundamentals"] == 2
    with session_scope(engine) as session:
        investor_flow_count = session.scalar(select(func.count()).select_from(InvestorFlow))
    assert investor_flow_count == 2
    assert len(sync_runs) == 1
    assert sync_runs[0].status == "success"
    assert sync_runs[0].finished_at is not None


def test_sync_phase1_data_records_failed_run_when_provider_raises():
    class BrokenProvider(FakeProvider):
        def get_universe(self):
            raise RuntimeError("provider down")

    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)

    try:
        sync_phase1_data(
            engine=engine,
            provider=BrokenProvider(),
            start_date=date(2026, 5, 1),
            end_date=date(2026, 5, 2),
        )
    except RuntimeError:
        pass

    with session_scope(engine) as session:
        sync_runs = session.scalars(select(SyncRun)).all()

    assert len(sync_runs) == 1
    assert sync_runs[0].status == "failed"
    assert sync_runs[0].error_message == "provider down"


def test_sync_phase1_data_deactivates_stocks_missing_from_latest_universe():
    class NewUniverseProvider(FakeProvider):
        def get_universe(self):
            return [{"ticker": "005930", "name": "?쇱꽦?꾩옄", "market": "KOSPI"}]

    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    with session_scope(engine) as session:
        session.add(Stock(ticker="000660", name="old", market="KOSPI", is_active=True))

    sync_phase1_data(
        engine=engine,
        provider=NewUniverseProvider(),
        start_date=date(2026, 5, 1),
        end_date=date(2026, 5, 2),
    )

    with session_scope(engine) as session:
        old_stock = session.get(Stock, "000660")
        current_stock = session.get(Stock, "005930")

    assert old_stock is not None
    assert old_stock.is_active is False
    assert current_stock is not None
    assert current_stock.is_active is True


def test_sync_phase1_data_fails_when_no_market_rows_are_collected():
    class EmptyProvider(FakeProvider):
        def get_daily_prices(self, ticker, start_date, end_date):
            return []

        def get_fundamentals(self, ticker, start_date, end_date):
            return []

    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)

    with pytest.raises(RuntimeError, match="no market data rows"):
        sync_phase1_data(
            engine=engine,
            provider=EmptyProvider(),
            start_date=date(2026, 5, 1),
            end_date=date(2026, 5, 2),
        )

    with session_scope(engine) as session:
        sync_run = session.scalars(select(SyncRun)).one()

    assert sync_run.status == "failed"
    assert sync_run.error_message == "no market data rows collected"


def test_sync_phase1_data_does_not_deactivate_existing_stocks_when_universe_is_empty():
    class EmptyUniverseProvider(FakeProvider):
        def get_universe(self):
            return []

    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    with session_scope(engine) as session:
        session.add(Stock(ticker="005930", name="existing", market="KOSPI", is_active=True))

    with pytest.raises(RuntimeError, match="no universe rows"):
        sync_phase1_data(
            engine=engine,
            provider=EmptyUniverseProvider(),
            start_date=date(2026, 5, 1),
            end_date=date(2026, 5, 2),
        )

    with session_scope(engine) as session:
        stock = session.get(Stock, "005930")
        sync_run = session.scalars(select(SyncRun)).one()

    assert stock is not None
    assert stock.is_active is True
    assert sync_run.status == "failed"
    assert sync_run.error_message == "no universe rows collected"


def _make_fake_universe(*, use_kospi=True, use_kosdaq=False, kospi_top_n=10,
                        kosdaq_top_n=10, lookback_days=1, min_value=0,
                        exclude_preferred=True, exclude_managed=False,
                        exclude_warning=False, exclude_suspended=False,
                        exclude_unverifiable_status=True):
    """테스트용 UNIVERSE 설정 MagicMock."""
    fake = MagicMock()
    fake.use_kospi = use_kospi
    fake.use_kosdaq = use_kosdaq
    fake.kospi_top_n = kospi_top_n
    fake.kosdaq_top_n = kosdaq_top_n
    fake.liquidity_lookback_days = lookback_days
    fake.min_avg_trading_value = min_value
    fake.exclude_preferred = exclude_preferred
    fake.exclude_managed = exclude_managed
    fake.exclude_warning = exclude_warning
    fake.exclude_suspended = exclude_suspended
    fake.exclude_unverifiable_status = exclude_unverifiable_status
    return fake


def _ohlcv_df(tickers: list[str], values: list[float]) -> pd.DataFrame:
    return pd.DataFrame({"거래대금": values}, index=tickers)


def test_default_universe_config_uses_liquidity_ranked_kospi_kosdaq():
    assert collectors.UNIVERSE.use_kospi is True
    assert collectors.UNIVERSE.use_kosdaq is True
    assert collectors.UNIVERSE.kospi_top_n == 400
    assert collectors.UNIVERSE.kosdaq_top_n == 200
    assert collectors.UNIVERSE.liquidity_lookback_days == 5
    assert collectors.UNIVERSE.min_avg_trading_value == 5_000_000_000
    assert collectors.UNIVERSE.exclude_unverifiable_status is True


def test_pykrx_provider_excludes_preferred_stocks():
    """우선주(ticker 끝자리 != '0') 제외 확인."""
    provider = PykrxMarketDataProvider.__new__(PykrxMarketDataProvider)
    provider.stock = MagicMock()
    provider.stock.get_market_ticker_list.return_value = ["005930", "005935", "000660", "000665"]
    provider.stock.get_market_ohlcv_by_ticker.return_value = _ohlcv_df(
        ["005930", "005935", "000660", "000665"],
        [10_000_000_000, 10_000_000_000, 10_000_000_000, 10_000_000_000],
    )
    provider.stock.get_market_ticker_name.side_effect = lambda t: f"name-{t}"

    with patch.object(collectors, "UNIVERSE", _make_fake_universe(exclude_preferred=True)):
        rows = provider.get_universe(target_date=date(2026, 5, 6))

    tickers = [r["ticker"] for r in rows]
    assert "005930" in tickers
    assert "000660" in tickers
    assert "005935" not in tickers
    assert "000665" not in tickers


def test_pykrx_provider_selects_top_n_by_avg_trading_value():
    """일평균 거래대금 상위 N개만 선정하는지 확인."""
    provider = PykrxMarketDataProvider.__new__(PykrxMarketDataProvider)
    provider.stock = MagicMock()
    provider.stock.get_market_ticker_list.return_value = [
        "111110", "222220", "333330", "444440", "555550"
    ]
    provider.stock.get_market_ohlcv_by_ticker.return_value = _ohlcv_df(
        ["111110", "222220", "333330", "444440", "555550"],
        [50_000_000_000, 30_000_000_000, 10_000_000_000, 20_000_000_000, 40_000_000_000],
    )
    provider.stock.get_market_ticker_name.side_effect = lambda t: f"name-{t}"

    with patch.object(collectors, "UNIVERSE", _make_fake_universe(
        kospi_top_n=3, exclude_preferred=False
    )):
        rows = provider.get_universe(target_date=date(2026, 5, 6))

    assert len(rows) == 3
    tickers = [r["ticker"] for r in rows]
    assert "111110" in tickers   # 500억 — 1위
    assert "555550" in tickers   # 400억 — 2위
    assert "222220" in tickers   # 300억 — 3위
    assert "444440" not in tickers
    assert "333330" not in tickers


def test_pykrx_provider_walks_back_when_latest_ticker_list_is_empty():
    provider = PykrxMarketDataProvider.__new__(PykrxMarketDataProvider)
    provider.stock = MagicMock()
    provider.stock.get_market_ticker_list.side_effect = [[], ["111110", "222220"]]
    provider.stock.get_market_ohlcv_by_ticker.return_value = _ohlcv_df(
        ["111110", "222220"],
        [50_000_000_000, 30_000_000_000],
    )
    provider.stock.get_market_ticker_name.side_effect = lambda t: f"name-{t}"

    with patch.object(collectors, "UNIVERSE", _make_fake_universe(
        kospi_top_n=2, lookback_days=2, exclude_preferred=False
    )):
        rows = provider.get_universe(target_date=date(2026, 5, 6))

    assert [r["ticker"] for r in rows] == ["111110", "222220"]
    assert provider.stock.get_market_ticker_list.call_count == 2


def test_pykrx_provider_excludes_managed_warning_and_suspended_tickers():
    provider = PykrxMarketDataProvider.__new__(PykrxMarketDataProvider)
    provider.stock = MagicMock()
    provider.stock.get_market_ticker_list.return_value = ["111110", "222220", "333330", "444440"]
    provider.stock.get_market_ohlcv_by_ticker.return_value = _ohlcv_df(
        ["111110", "222220", "333330", "444440"],
        [50_000_000_000, 40_000_000_000, 30_000_000_000, 20_000_000_000],
    )
    provider.stock.get_market_ticker_name.side_effect = lambda t: f"name-{t}"

    issue_sets = {
        "managed": {"222220"},
        "warning": {"333330"},
        "suspended": {"444440"},
    }
    provider._get_issue_tickers = MagicMock(side_effect=lambda issue_type, market, target_date: issue_sets[issue_type])

    with patch.object(collectors, "UNIVERSE", _make_fake_universe(
        kospi_top_n=4,
        exclude_preferred=False,
        exclude_managed=True,
        exclude_warning=True,
        exclude_suspended=True,
    )):
        rows = provider.get_universe(target_date=date(2026, 5, 6))

    assert [r["ticker"] for r in rows] == ["111110"]


def test_pykrx_provider_excludes_all_when_status_cannot_be_verified():
    provider = PykrxMarketDataProvider.__new__(PykrxMarketDataProvider)
    provider.stock = MagicMock()
    provider.stock.get_market_ticker_list.return_value = ["111110", "222220"]
    provider._get_issue_tickers = MagicMock(return_value=None)

    with patch.object(collectors, "UNIVERSE", _make_fake_universe(
        exclude_preferred=False,
        exclude_managed=True,
        exclude_unverifiable_status=True,
    )):
        rows = provider.get_universe(target_date=date(2026, 5, 6))

    assert rows == []


def test_pykrx_provider_excludes_below_min_trading_value():
    """최소 거래대금 미달 종목 제외 확인."""
    provider = PykrxMarketDataProvider.__new__(PykrxMarketDataProvider)
    provider.stock = MagicMock()
    provider.stock.get_market_ticker_list.return_value = ["111110", "222220", "333330"]
    provider.stock.get_market_ohlcv_by_ticker.return_value = _ohlcv_df(
        ["111110", "222220", "333330"],
        [10_000_000_000, 3_000_000_000, 8_000_000_000],  # 100억, 30억, 80억
    )
    provider.stock.get_market_ticker_name.side_effect = lambda t: f"name-{t}"

    with patch.object(collectors, "UNIVERSE", _make_fake_universe(
        min_value=5_000_000_000, exclude_preferred=False
    )):
        rows = provider.get_universe(target_date=date(2026, 5, 6))

    tickers = [r["ticker"] for r in rows]
    assert "111110" in tickers   # 100억 ≥ 50억 → 포함
    assert "333330" in tickers   # 80억 ≥ 50억 → 포함
    assert "222220" not in tickers  # 30억 < 50억 → 제외


def test_pykrx_provider_returns_empty_rows_for_empty_price_frame():
    provider = PykrxMarketDataProvider.__new__(PykrxMarketDataProvider)
    provider.stock = MagicMock()
    provider.stock.get_market_ohlcv_by_date.return_value = pd.DataFrame()

    rows = provider.get_daily_prices("005930", date(2026, 5, 1), date(2026, 5, 2))

    assert rows == []


def test_investor_flow_frame_to_rows_maps_pykrx_columns():
    frame = pd.DataFrame(
        {
            "개인": [1000],
            "외국인합계": [-400],
            "기관합계": [-600],
        },
        index=[pd.Timestamp("2026-05-11")],
    )

    rows = collectors._investor_flow_frame_to_rows("005930", frame)

    assert rows == [
        {
            "ticker": "005930",
            "date": date(2026, 5, 11),
            "individual_net_buy": 1000.0,
            "foreign_net_buy": -400.0,
            "institution_net_buy": -600.0,
        }
    ]


def test_extract_tickers_from_issue_frame_reads_six_digit_codes():
    frame = pd.DataFrame({
        "ISU_SRT_CD": ["111110", "222220"],
        "NOTE": ["20260506 is a date", "name 333330"],
    })

    assert collectors._extract_tickers_from_issue_frame(frame) == {"111110", "222220", "333330"}


def test_fetch_market_data_parallel_warns_when_fundamentals_are_missing():
    class PartiallyMissingFundamentalProvider:
        def get_daily_prices(self, ticker, start_date, end_date):
            return [{"ticker": ticker, "date": start_date, "close": 100}]

        def get_fundamentals(self, ticker, start_date, end_date):
            if ticker == "088980":
                return []
            return [{"ticker": ticker, "date": start_date, "per": 10, "pbr": 1}]

        def get_investor_flows(self, ticker, start_date, end_date):
            return []

    with patch.object(collectors.logger, "warning") as warning:
        prices, fundamentals, investor_flows = collectors._fetch_market_data_parallel(
            provider=PartiallyMissingFundamentalProvider(),
            tickers=["005930", "088980"],
            start_date=date(2026, 5, 1),
            end_date=date(2026, 5, 2),
            max_workers=1,
        )

    assert {row["ticker"] for row in prices} == {"005930", "088980"}
    assert {row["ticker"] for row in fundamentals} == {"005930"}
    assert investor_flows == []
    warning.assert_called_once_with("fundamental data missing for 1 tickers: 088980")


def test_install_pykrx_request_timeout_adds_timeout_for_krx_urls(monkeypatch):
    calls = []

    def fake_request(self, method, url, **kwargs):
        calls.append((method, url, kwargs))
        return object()

    monkeypatch.setattr(collectors.requests.sessions.Session, "request", fake_request)
    collectors._install_pykrx_request_timeout(7)

    session = collectors.requests.Session()
    session.get("https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd")
    session.get("https://example.com/no-timeout")
    session.post(
        "https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd",
        timeout=3,
    )

    assert calls[0][2]["timeout"] == 7
    assert "timeout" not in calls[1][2]
    assert calls[2][2]["timeout"] == 3

    collectors._install_pykrx_request_timeout(11)
    session.get("https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd")

    assert calls[3][2]["timeout"] == 7
