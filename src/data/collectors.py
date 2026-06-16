from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from typing import Any, Protocol

import pandas as pd
import requests
from loguru import logger
from sqlalchemy import Engine
from sqlalchemy import func, select

from config import UNIVERSE
from src.data.database import session_scope
from src.data.models import Stock, SyncRun, utc_now
from src.data.repositories import (
    deactivate_stocks_not_in,
    upsert_daily_prices,
    upsert_fundamentals,
    upsert_investor_flows,
    upsert_stocks,
)


ISSUE_STATUS_BLDS = {
    "managed": "dbms/MDC/STAT/issue/MDCSTAT21401",
    "warning": "dbms/MDC/STAT/issue/MDCSTAT22801",
    "suspended": "dbms/MDC/STAT/issue/MDCSTAT21201",
}

PYKRX_REQUEST_TIMEOUT_SEC = 15


class MarketDataProvider(Protocol):
    def get_universe(self, target_date: date | None = None) -> list[dict[str, Any]]:
        ...

    def get_daily_prices(self, ticker: str, start_date: date, end_date: date) -> list[dict[str, Any]]:
        ...

    def get_fundamentals(self, ticker: str, start_date: date, end_date: date) -> list[dict[str, Any]]:
        ...

    def get_investor_flows(self, ticker: str, start_date: date, end_date: date) -> list[dict[str, Any]]:
        ...


class PykrxMarketDataProvider:
    def __init__(self) -> None:
        _install_pykrx_request_timeout(PYKRX_REQUEST_TIMEOUT_SEC)
        from pykrx import stock

        self.stock = stock
        self._known_etf_tickers: set[str] = set()

    def _resolve_recent_business_date(self) -> str:
        # When date=None, some pykrx versions fail to find a business day if the
        # KRX site response shape changes (IndexError on empty dataframe).
        # Walk back from yesterday up to 14 days, skipping weekends.
        today = date.today()
        for offset in range(1, 15):
            candidate = today - timedelta(days=offset)
            if candidate.weekday() >= 5:  # Saturday=5, Sunday=6
                continue
            return candidate.strftime("%Y%m%d")
        # Fallback: 14 days ago
        return (today - timedelta(days=14)).strftime("%Y%m%d")

    def get_universe(
        self,
        target_date: date | None = None,
        max_lookback_days: int = 14,
    ) -> list[dict[str, Any]]:
        resolved_date = target_date or date.fromisoformat(
            self._resolve_recent_business_date()
        )
        rows: list[dict[str, Any]] = []
        if UNIVERSE.use_kospi:
            rows.extend(
                self._build_market_universe(
                    "KOSPI", resolved_date,
                    UNIVERSE.kospi_top_n, UNIVERSE.liquidity_lookback_days, max_lookback_days,
                )
            )
        if UNIVERSE.use_kosdaq:
            rows.extend(
                self._build_market_universe(
                    "KOSDAQ", resolved_date,
                    UNIVERSE.kosdaq_top_n, UNIVERSE.liquidity_lookback_days, max_lookback_days,
                )
            )
        if getattr(UNIVERSE, "use_etf", False):
            rows.extend(
                self._build_etf_universe(
                    resolved_date,
                    UNIVERSE.etf_top_n,
                    UNIVERSE.liquidity_lookback_days,
                    max_lookback_days,
                )
            )
        return rows

    def _build_etf_universe(
        self,
        target_date: date,
        top_n: int,
        lookback_days: int,
        max_lookback_days: int,
    ) -> list[dict[str, Any]]:
        business_dates = self._get_recent_business_dates(target_date, lookback_days, max_lookback_days)
        if not business_dates:
            return []
        try:
            tickers = list(self.stock.get_etf_ticker_list(_format_date(business_dates[0])))
        except Exception as exc:
            logger.warning(f"ETF 종목 목록 조회 실패 ({business_dates[0]}): {exc}")
            return []

        trading_value_sum: dict[str, float] = {}
        days_counted: dict[str, int] = {}
        for ticker in tickers:
            for business_date in business_dates:
                try:
                    frame = self.stock.get_etf_ohlcv_by_date(
                        _format_date(business_date),
                        _format_date(business_date),
                        ticker,
                    )
                except Exception as exc:
                    logger.warning(f"ETF OHLCV 조회 실패 ({ticker}, {business_date}): {exc}")
                    continue
                if frame.empty or "거래대금" not in frame.columns:
                    continue
                value = frame.iloc[-1]["거래대금"]
                if pd.notna(value) and float(value) > 0:
                    trading_value_sum[ticker] = trading_value_sum.get(ticker, 0.0) + float(value)
                    days_counted[ticker] = days_counted.get(ticker, 0) + 1

        eligible = [
            (ticker, trading_value_sum[ticker] / max(days_counted.get(ticker, 1), 1))
            for ticker in trading_value_sum
            if trading_value_sum[ticker] / max(days_counted.get(ticker, 1), 1)
            >= UNIVERSE.min_avg_trading_value
        ]
        eligible.sort(key=lambda item: item[1], reverse=True)
        result = []
        for ticker, _ in eligible[:top_n]:
            try:
                name = self.stock.get_etf_ticker_name(ticker)
            except Exception:
                name = ticker
            self._known_etf_tickers.add(ticker)
            result.append(
                {
                    "ticker": ticker,
                    "name": name,
                    "market": "ETF",
                    "instrument_type": "ETF",
                    "is_active": True,
                }
            )
        return result

    def _build_market_universe(
        self,
        market: str,
        target_date: date,
        top_n: int,
        lookback_days: int,
        max_lookback_days: int,
    ) -> list[dict[str, Any]]:
        """유동성 기준 상위 종목 선별."""
        business_dates = self._get_recent_business_dates(target_date, lookback_days, max_lookback_days)
        if not business_dates:
            logger.warning(f"{market}: 최근 영업일을 찾지 못했습니다")
            return []

        all_tickers: list[str] = []
        for bdate in business_dates:
            date_str = _format_date(bdate)
            try:
                all_tickers = list(self.stock.get_market_ticker_list(date_str, market=market))
            except Exception as exc:
                logger.warning(f"{market} 종목 목록 조회 실패 ({bdate}): {exc}")
                continue
            if all_tickers:
                break
        if not all_tickers:
            logger.warning(f"{market}: 종목 목록이 비어 있습니다")
            return []

        if UNIVERSE.exclude_preferred:
            all_tickers = [t for t in all_tickers if t[-1] == "0"]

        all_tickers = self._filter_status_eligible_tickers(
            tickers=all_tickers,
            market=market,
            target_date=business_dates[0],
        )
        if not all_tickers:
            logger.warning(f"{market}: 상태 필터 통과 종목이 없습니다")
            return []

        # 영업일별 거래대금 합산 → 평균
        trading_value_sum: dict[str, float] = {}
        days_counted = 0
        for bdate in business_dates:
            try:
                frame = self.stock.get_market_ohlcv_by_ticker(_format_date(bdate), market=market)
            except Exception as exc:
                logger.warning(f"{market} OHLCV 조회 실패 ({bdate}): {exc}")
                continue
            if frame.empty or "거래대금" not in frame.columns:
                continue
            days_counted += 1
            for ticker in all_tickers:
                if ticker in frame.index:
                    val = frame.loc[ticker, "거래대금"]
                    if pd.notna(val) and val > 0:
                        trading_value_sum[ticker] = trading_value_sum.get(ticker, 0.0) + float(val)

        divisor = max(days_counted, 1)
        avg_values: dict[str, float] = {t: v / divisor for t, v in trading_value_sum.items()}

        # 유동성 필터 + 정렬 + 상위 N개
        eligible = [
            (t, avg_values.get(t, 0.0))
            for t in all_tickers
            if avg_values.get(t, 0.0) >= UNIVERSE.min_avg_trading_value
        ]
        eligible.sort(key=lambda x: x[1], reverse=True)
        top_tickers = [t for t, _ in eligible[:top_n]]

        logger.info(
            f"{market}: 전체 {len(all_tickers)}개 → 유동성 기준 {len(eligible)}개 → 상위 {len(top_tickers)}개 선정"
        )

        result = []
        for ticker in top_tickers:
            try:
                name = self.stock.get_market_ticker_name(ticker)
            except Exception:
                name = ticker
            result.append({"ticker": ticker, "name": name, "market": market, "is_active": True})
        return result

    def _filter_status_eligible_tickers(
        self,
        *,
        tickers: list[str],
        market: str,
        target_date: date,
    ) -> list[str]:
        """관리/투자주의/거래정지 종목을 제외한다.

        KRX 상태 조회 자체가 실패하면 exclude_unverifiable_status 정책에 따라
        신규 매수 후보를 비워 보수적으로 대응한다.
        """
        excluded: set[str] = set()
        checks = [
            ("managed", UNIVERSE.exclude_managed, "관리종목"),
            ("warning", UNIVERSE.exclude_warning, "투자주의종목"),
            ("suspended", UNIVERSE.exclude_suspended, "거래정지종목"),
        ]
        for issue_type, enabled, label in checks:
            if not enabled:
                continue
            issue_tickers = self._get_issue_tickers(issue_type, market, target_date)
            if issue_tickers is None:
                logger.warning(f"{market}: {label} 확인 실패")
                if getattr(UNIVERSE, "exclude_unverifiable_status", True):
                    return []
                continue
            matched = set(tickers) & issue_tickers
            if matched:
                logger.info(f"{market}: {label} {len(matched)}개 제외")
            excluded.update(matched)

        if not excluded:
            return tickers
        return [ticker for ticker in tickers if ticker not in excluded]

    def _get_issue_tickers(
        self,
        issue_type: str,
        market: str,
        target_date: date,
    ) -> set[str] | None:
        bld = ISSUE_STATUS_BLDS[issue_type]
        mkt_id = {"KOSPI": "STK", "KOSDAQ": "KSQ"}.get(market, "ALL")
        try:
            frame = _fetch_krx_issue_status(bld, mkt_id, _format_date(target_date))
        except Exception as exc:
            logger.warning(f"{market}: {issue_type} 상태 조회 실패: {exc}")
            return None
        return _extract_tickers_from_issue_frame(frame)

    def _get_recent_business_dates(
        self,
        target_date: date,
        n_days: int,
        max_lookback_days: int,
    ) -> list[date]:
        """target_date 이전(포함) 최근 n_days개 영업일(주말 제외) 반환."""
        result: list[date] = []
        for offset in range(max_lookback_days * 2):
            candidate = target_date - timedelta(days=offset)
            if candidate.weekday() >= 5:
                continue
            result.append(candidate)
            if len(result) >= n_days:
                break
        return result

    def get_daily_prices(self, ticker: str, start_date: date, end_date: date) -> list[dict[str, Any]]:
        if ticker in getattr(self, "_known_etf_tickers", set()):
            frame = self.stock.get_etf_ohlcv_by_date(
                _format_date(start_date),
                _format_date(end_date),
                ticker,
            )
        else:
            frame = self.stock.get_market_ohlcv_by_date(
                _format_date(start_date),
                _format_date(end_date),
                ticker,
                adjusted=True,
            )
        if frame.empty:
            return []
        return _price_frame_to_rows(ticker, frame)

    def get_fundamentals(self, ticker: str, start_date: date, end_date: date) -> list[dict[str, Any]]:
        if ticker in getattr(self, "_known_etf_tickers", set()):
            return []
        frame = self.stock.get_market_fundamental_by_date(
            _format_date(start_date),
            _format_date(end_date),
            ticker,
        )
        if frame.empty:
            return []
        return _fundamental_frame_to_rows(ticker, frame)

    def get_investor_flows(self, ticker: str, start_date: date, end_date: date) -> list[dict[str, Any]]:
        if ticker in getattr(self, "_known_etf_tickers", set()):
            return []
        frame = self.stock.get_market_trading_value_by_date(
            _format_date(start_date),
            _format_date(end_date),
            ticker,
            on="순매수",
        )
        if frame.empty:
            return []
        return _investor_flow_frame_to_rows(ticker, frame)


def sync_phase1_data(
    *,
    engine: Engine,
    provider: MarketDataProvider,
    start_date: date,
    end_date: date,
    max_workers: int = 5,
    universe_date: date | None = None,
    deactivate_missing: bool = True,
) -> dict[str, int]:
    error: Exception | None = None
    result: dict[str, int] | None = None
    with session_scope(engine) as session:
        sync_run = SyncRun(status="running")
        session.add(sync_run)
        session.flush()

        try:
            universe = (
                provider.get_universe(target_date=universe_date)
                if universe_date is not None
                else provider.get_universe()
            )
            if not universe:
                raise RuntimeError("no universe rows collected")
            _validate_universe_markets_before_deactivation(session, universe)
            universe_count = upsert_stocks(session, universe)
            if deactivate_missing:
                deactivate_stocks_not_in(session, [row["ticker"] for row in universe])

            tickers = [row["ticker"] for row in universe]
            price_rows, fundamental_rows, investor_flow_rows = _fetch_market_data_parallel(
                provider=provider,
                tickers=tickers,
                start_date=start_date,
                end_date=end_date,
                max_workers=max_workers,
            )

            price_count = upsert_daily_prices(session, price_rows)
            fundamental_count = upsert_fundamentals(session, fundamental_rows)
            investor_flow_count = upsert_investor_flows(session, investor_flow_rows)
            if price_count == 0 or fundamental_count == 0:
                raise RuntimeError("no market data rows collected")

            sync_run.status = "success"
            sync_run.finished_at = utc_now()
            sync_run.universe_count = universe_count
            sync_run.price_count = price_count
            sync_run.fundamental_count = fundamental_count
            result = {
                "universe_count": universe_count,
                "price_count": price_count,
                "fundamental_count": fundamental_count,
                "investor_flow_count": investor_flow_count,
            }
        except Exception as exc:
            sync_run.status = "failed"
            sync_run.finished_at = utc_now()
            sync_run.error_message = str(exc)
            error = exc

    if error is not None:
        raise error
    if result is None:
        raise RuntimeError("sync finished without a result")
    return result


def _validate_universe_markets_before_deactivation(session: Any, universe: list[dict[str, Any]]) -> None:
    collected_markets = {str(row.get("market") or "").upper() for row in universe}
    expected_markets = []
    if getattr(UNIVERSE, "use_kospi", False):
        expected_markets.append("KOSPI")
    if getattr(UNIVERSE, "use_kosdaq", False):
        expected_markets.append("KOSDAQ")

    missing_existing_markets = []
    for market in expected_markets:
        if market in collected_markets:
            continue
        existing_count = session.scalar(
            select(func.count()).select_from(Stock).where(
                Stock.is_active.is_(True),
                Stock.market == market,
            )
        ) or 0
        if int(existing_count) > 0:
            missing_existing_markets.append(market)

    if missing_existing_markets:
        missing = ", ".join(missing_existing_markets)
        raise RuntimeError(
            f"partial universe rows collected: missing active market rows for {missing}"
        )


def _fetch_market_data_parallel(
    *,
    provider: MarketDataProvider,
    tickers: list[str],
    start_date: date,
    end_date: date,
    max_workers: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """종목별 시세·펀더멘털을 ThreadPoolExecutor로 병렬 수집한다.

    KRX 서버 과부하 방지를 위해 max_workers로 동시 요청 수를 제한한다.
    개별 종목 실패는 경고 로그만 남기고 건너뜀.
    """
    price_rows: list[dict[str, Any]] = []
    fundamental_rows: list[dict[str, Any]] = []
    investor_flow_rows: list[dict[str, Any]] = []
    total = len(tickers)

    def fetch_one(
        ticker: str,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        return (
            provider.get_daily_prices(ticker, start_date, end_date),
            provider.get_fundamentals(ticker, start_date, end_date),
            provider.get_investor_flows(ticker, start_date, end_date),
        )

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fetch_one, t): t for t in tickers}
        done = 0
        for future in as_completed(futures):
            ticker = futures[future]
            try:
                prices, fundamentals, investor_flows = future.result()
                price_rows.extend(prices)
                fundamental_rows.extend(fundamentals)
                investor_flow_rows.extend(investor_flows)
            except Exception as exc:
                logger.warning(f"[수집 실패] {ticker} — {exc}")
            done += 1
            if done % 50 == 0 or done == total:
                logger.info(f"데이터 수집 진행: {done}/{total} 종목 완료")

    price_tickers = {row["ticker"] for row in price_rows}
    fundamental_tickers = {row["ticker"] for row in fundamental_rows}
    missing_fundamentals = sorted(price_tickers - fundamental_tickers)
    if missing_fundamentals:
        sample = ", ".join(missing_fundamentals[:10])
        suffix = "" if len(missing_fundamentals) <= 10 else ", ..."
        logger.warning(
            f"fundamental data missing for {len(missing_fundamentals)} tickers: {sample}{suffix}"
        )

    return price_rows, fundamental_rows, investor_flow_rows


def _format_date(value: date) -> str:
    return value.strftime("%Y%m%d")


def _install_pykrx_request_timeout(timeout_sec: int) -> None:
    current_request = requests.sessions.Session.request
    if getattr(current_request, "_quntbot_pykrx_timeout_wrapper", False):
        return

    def request_with_krx_timeout(
        self: requests.Session,
        method: str,
        url: str | bytes,
        **kwargs: Any,
    ) -> requests.Response:
        if "timeout" not in kwargs and _is_krx_url(url):
            kwargs["timeout"] = timeout_sec
        return current_request(self, method, url, **kwargs)

    request_with_krx_timeout._quntbot_pykrx_timeout_wrapper = True  # type: ignore[attr-defined]
    requests.sessions.Session.request = request_with_krx_timeout


def _is_krx_url(url: str | bytes) -> bool:
    if isinstance(url, bytes):
        url = url.decode("utf-8", errors="ignore")
    return "://data.krx.co.kr/" in url or "://global.krx.co.kr/" in url


def _fetch_krx_issue_status(bld: str, mkt_id: str, trade_date: str) -> pd.DataFrame:
    from pykrx.website.krx.krxio import KrxWebIo

    class _IssueStatus(KrxWebIo):
        @property
        def bld(self) -> str:
            return bld

        def fetch(self) -> pd.DataFrame:
            result = self.read(
                locale="ko_KR",
                mktId=mkt_id,
                trdDd=trade_date,
                share="1",
                money="1",
                csvxls_isNo="false",
            )
            return pd.DataFrame(result.get("output", []))

    return _IssueStatus().fetch()


def _extract_tickers_from_issue_frame(frame: pd.DataFrame) -> set[str]:
    if frame.empty:
        return set()

    tickers: set[str] = set()
    for value in frame.astype(str).to_numpy().ravel():
        for match in re.findall(r"\b\d{6}\b", value):
            tickers.add(match)
    return tickers


def _price_frame_to_rows(ticker: str, frame: pd.DataFrame) -> list[dict[str, Any]]:
    rows = []
    for index, row in frame.iterrows():
        rows.append(
            {
                "ticker": ticker,
                "date": _index_to_date(index),
                "open": _get_optional(row, "시가"),
                "high": _get_optional(row, "고가"),
                "low": _get_optional(row, "저가"),
                "close": _get_optional(row, "종가"),
                "volume": _get_optional(row, "거래량"),
                "trading_value": _get_optional(row, "거래대금"),
                "market_cap": _get_optional(row, "시가총액"),
            }
        )
    return rows


def _fundamental_frame_to_rows(ticker: str, frame: pd.DataFrame) -> list[dict[str, Any]]:
    rows = []
    for index, row in frame.iterrows():
        rows.append(
            {
                "ticker": ticker,
                "date": _index_to_date(index),
                "bps": _get_optional(row, "BPS"),
                "per": _get_optional(row, "PER"),
                "pbr": _get_optional(row, "PBR"),
                "eps": _get_optional(row, "EPS"),
                "div": _get_optional(row, "DIV"),
                "dps": _get_optional(row, "DPS"),
            }
        )
    return rows


def _investor_flow_frame_to_rows(ticker: str, frame: pd.DataFrame) -> list[dict[str, Any]]:
    rows = []
    for index, row in frame.iterrows():
        rows.append(
            {
                "ticker": ticker,
                "date": _index_to_date(index),
                "individual_net_buy": _get_optional_by_alias(row, ["개인"]),
                "foreign_net_buy": _get_optional_by_alias(row, ["외국인합계", "외국인"]),
                "institution_net_buy": _get_optional_by_alias(row, ["기관합계", "기관"]),
            }
        )
    return rows


def _index_to_date(value: Any) -> date:
    if hasattr(value, "date"):
        return value.date()
    return date.fromisoformat(str(value)[:10])


def _get_optional(row: pd.Series, key: str) -> float | None:
    if key not in row or pd.isna(row[key]):
        return None
    return float(row[key])


def _get_optional_by_alias(row: pd.Series, keys: list[str]) -> float | None:
    for key in keys:
        value = _get_optional(row, key)
        if value is not None:
            return value
    return None
