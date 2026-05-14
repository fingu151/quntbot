from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
import re
from typing import Any

from loguru import logger

from src.data.rate_limiter import RateLimiter

Period = tuple[int, int]

INCOME_ROWS_KEYS = ("income_statement", "is")
BALANCE_ROWS_KEYS = ("balance_sheet", "bs")
REVENUE_KEYS = ("revenue", "sales", "매출액")
OPERATING_INCOME_KEYS = ("operating_income", "operating_profit", "영업이익")
NET_INCOME_KEYS = ("net_income", "profit_loss", "당기순이익")
EQUITY_KEYS = ("equity", "total_equity", "자본총계")
LIABILITIES_KEYS = ("liabilities", "total_liabilities", "부채총계")
ASSETS_KEYS = ("assets", "total_assets", "자산총계")
PUBLISHED_AT_KEYS = ("published_at", "report_date")
SINGLE_ACCOUNT_REPORT_CODES = {
    1: "11013",
    2: "11012",
    3: "11014",
    4: "11011",
}
SINGLE_ACCOUNT_INCOME_FIELDS = ("revenue", "operating_income", "net_income")


class DartFssFundamentalsProvider:
    def __init__(
        self,
        *,
        api_key: str,
        rate_limiter: RateLimiter,
        dart_module: Any | None = None,
        refresh_corp_list: bool = False,
    ) -> None:
        if dart_module is None:
            import dart_fss as dart_module

        self._dart = dart_module
        self._rate_limiter = rate_limiter
        self._dart.set_api_key(api_key)
        if refresh_corp_list:
            self._refresh_corp_list_cache()
        self._stock_to_corp_code = self._build_stock_to_corp_code()

    @property
    def stock_to_corp_code(self) -> dict[str, str]:
        return dict(self._stock_to_corp_code)

    def get_quality_metrics(
        self,
        ticker: str,
        *,
        year_from: int,
        year_to: int,
    ) -> list[dict[str, Any]]:
        corp_code = self._stock_to_corp_code.get(ticker)
        if corp_code is None:
            logger.warning(f"DART corp_code not found for ticker={ticker}")
            return []

        self._rate_limiter.acquire()
        try:
            payload = self._dart.fs.extract(
                corp_code,
                bgn_de=f"{year_from}0101",
                report_tp="quarter",
                cumulative=False,
                progressbar=False,
            )
        except Exception as exc:
            logger.warning(
                f"DART financial statement extract failed for ticker={ticker}; "
                f"falling back to single-account API: {exc}"
            )
            payload = self._payload_from_single_account_api(
                corp_code=corp_code,
                year_from=year_from,
                year_to=year_to,
            )
            if payload is None:
                raise
        rows = _parse_quality_metric_rows(
            ticker=ticker,
            payload=payload,
            year_from=year_from,
            year_to=year_to,
        )
        if _needs_quality_metric_supplement(rows, year_from=year_from, year_to=year_to):
            supplemental_payload = self._payload_from_single_account_api(
                corp_code=corp_code,
                year_from=year_from,
                year_to=year_to,
            )
            if supplemental_payload is not None:
                supplemental_rows = _parse_quality_metric_rows(
                    ticker=ticker,
                    payload=supplemental_payload,
                    year_from=year_from,
                    year_to=year_to,
                )
                rows = _merge_missing_quality_metric_values(rows, supplemental_rows)
        return rows

    def _payload_from_single_account_api(
        self,
        *,
        corp_code: str,
        year_from: int,
        year_to: int,
    ) -> dict[str, list[dict[str, Any]]] | None:
        finance_api = getattr(getattr(self._dart, "api", None), "finance", None)
        single_account_api = getattr(finance_api, "fnltt_singl_acnt", None)
        if not callable(single_account_api):
            return None

        balance_rows: list[dict[str, Any]] = []
        income_rows: list[dict[str, Any]] = []
        published_dates = self._published_dates_by_period_from_filings_api(
            corp_code=corp_code,
            year_from=year_from,
            year_to=year_to,
        )

        prior_balance = self._single_account_period_row(
            single_account_api=single_account_api,
            corp_code=corp_code,
            year=year_from - 1,
            quarter=4,
            include_income=False,
        )
        if prior_balance is not None:
            balance_rows.append(prior_balance)

        for year in range(year_from, year_to + 1):
            year_income_rows: list[dict[str, Any]] = []
            for quarter, report_code in SINGLE_ACCOUNT_REPORT_CODES.items():
                row = self._single_account_period_row(
                    single_account_api=single_account_api,
                    corp_code=corp_code,
                    year=year,
                    quarter=quarter,
                    include_income=True,
                )
                if row is None:
                    continue
                if quarter == 4:
                    _convert_annual_income_to_fourth_quarter(
                        row=row,
                        earlier_quarters=year_income_rows,
                    )
                balance_rows.append(
                    {
                        "fiscal_year": row["fiscal_year"],
                        "fiscal_quarter": row["fiscal_quarter"],
                        "equity": row.get("equity"),
                        "liabilities": row.get("liabilities"),
                        "published_at": published_dates.get(
                            (row["fiscal_year"], row["fiscal_quarter"])
                        ),
                    }
                )
                income_rows.append(
                    {
                        "fiscal_year": row["fiscal_year"],
                        "fiscal_quarter": row["fiscal_quarter"],
                        "revenue": row.get("revenue"),
                        "operating_income": row.get("operating_income"),
                        "net_income": row.get("net_income"),
                    }
                )
                if quarter < 4:
                    year_income_rows.append(row)

        if not balance_rows or not income_rows:
            return None
        return {
            "balance_sheet": balance_rows,
            "income_statement": income_rows,
        }

    def _published_dates_by_period_from_filings_api(
        self,
        *,
        corp_code: str,
        year_from: int,
        year_to: int,
    ) -> dict[Period, date]:
        filings_api = getattr(getattr(self._dart, "api", None), "filings", None)
        search_filings = getattr(filings_api, "search_filings", None)
        if not callable(search_filings):
            return {}

        self._rate_limiter.acquire()
        try:
            response = search_filings(
                corp_code=corp_code,
                bgn_de=f"{year_from}0101",
                end_de=f"{year_to + 1}1231",
                last_reprt_at="Y",
                pblntf_ty="A",
                sort="date",
                sort_mth="desc",
                page_no=1,
                page_count=100,
            )
        except Exception as exc:
            logger.warning(
                f"DART filing search failed for corp_code={corp_code}: {exc}"
            )
            return {}

        filing_rows = response.get("list") if isinstance(response, dict) else None
        if not isinstance(filing_rows, list):
            return {}

        dates_by_period: dict[Period, date] = {}
        for row in filing_rows:
            if not isinstance(row, dict):
                continue
            period = _period_from_filing_row(row)
            published_at = _date_from_row(row, ("rcept_dt", "rcept_date", "published_at"))
            if period is None or published_at is None:
                continue
            year, _ = period
            if year_from <= year <= year_to and period not in dates_by_period:
                dates_by_period[period] = published_at
        return dates_by_period

    def _single_account_period_row(
        self,
        *,
        single_account_api: Any,
        corp_code: str,
        year: int,
        quarter: int,
        include_income: bool,
    ) -> dict[str, Any] | None:
        self._rate_limiter.acquire()
        try:
            response = single_account_api(
                corp_code=corp_code,
                bsns_year=str(year),
                reprt_code=SINGLE_ACCOUNT_REPORT_CODES[quarter],
            )
        except Exception as exc:
            logger.warning(
                f"DART single-account API failed for corp_code={corp_code} "
                f"year={year} quarter={quarter}: {exc}"
            )
            return None

        rows = response.get("list") if isinstance(response, dict) else None
        if not isinstance(rows, list):
            return None

        target: dict[str, Any] = {
            "fiscal_year": year,
            "fiscal_quarter": quarter,
        }
        statement_rows = [row for row in rows if isinstance(row, dict)]
        cfs_rows = [row for row in statement_rows if row.get("fs_div") == "CFS"]
        selected_rows = cfs_rows or [
            row for row in statement_rows if row.get("fs_div") == "OFS"
        ]
        for row in selected_rows:
            if not isinstance(row, dict):
                continue
            field = _field_from_single_account_row(row)
            if field is None:
                continue
            if not include_income and field in SINGLE_ACCOUNT_INCOME_FIELDS:
                continue
            if field not in target:
                target[field] = _number_from_single_account_row(row)

        if target.get("equity") is None:
            assets = target.get("assets")
            liabilities = target.get("liabilities")
            if assets is not None and liabilities is not None:
                target["equity"] = assets - liabilities

        if len(target) == 2:
            return None
        return target

    def _build_stock_to_corp_code(self) -> dict[str, str]:
        mapping: dict[str, str] = {}
        try:
            for corp in self._dart.get_corp_list():
                stock_code = getattr(corp, "stock_code", None)
                corp_code = getattr(corp, "corp_code", None)
                if stock_code and corp_code:
                    mapping[str(stock_code)] = str(corp_code)
        except TypeError as exc:
            if "unexpected keyword argument" not in str(exc):
                raise
            logger.warning(
                "dart-fss CorpList schema mismatch; falling back to raw CORPCODE.xml rows"
            )
            for corp in self._get_raw_corp_code_rows():
                stock_code = corp.get("stock_code")
                corp_code = corp.get("corp_code")
                if stock_code and corp_code:
                    mapping[str(stock_code)] = str(corp_code)
        return mapping

    def _get_raw_corp_code_rows(self) -> list[dict[str, Any]]:
        corp_code_api = getattr(
            getattr(getattr(getattr(self._dart, "api", None), "filings", None), "corp_code", None),
            "get_corp_code",
            None,
        )
        if callable(corp_code_api):
            rows = corp_code_api()
            return [row for row in rows if isinstance(row, dict)]

        from dart_fss.api.filings.corp_code import get_corp_code

        rows = get_corp_code()
        return [row for row in rows if isinstance(row, dict)]

    def _refresh_corp_list_cache(self) -> None:
        cache_dir_func = getattr(getattr(getattr(self._dart, "utils", None), "cache", None), "cache_dir", None)
        if not callable(cache_dir_func):
            logger.warning("DART cache directory helper not available; corp list cache not refreshed")
            return

        cache_dir = Path(cache_dir_func())
        for filename in ("CORPCODE.zip", "CORPCODE.xml"):
            path = cache_dir / filename
            if path.exists():
                path.unlink()


def _parse_quality_metric_rows(
    *,
    ticker: str,
    payload: Any,
    year_from: int,
    year_to: int,
) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        payload = _payload_from_financial_statement(payload)
    if not isinstance(payload, dict):
        return []

    income_rows = _rows_for_keys(payload, INCOME_ROWS_KEYS)
    balance_rows = _rows_for_keys(payload, BALANCE_ROWS_KEYS)
    if not income_rows or not balance_rows:
        return []

    normalized_income = [_normalize_income_row(row) for row in income_rows]
    normalized_balance = [_normalize_balance_row(row) for row in balance_rows]
    normalized_income = [row for row in normalized_income if row is not None]
    normalized_balance = [row for row in normalized_balance if row is not None]

    income_by_period = {row["period"]: row for row in normalized_income}
    balance_by_period = {row["period"]: row for row in normalized_balance}

    rows: list[dict[str, Any]] = []
    for period in sorted(balance_by_period):
        year, quarter = period
        if year < year_from or year > year_to:
            continue

        income_window = [
            income_by_period[income_period]
            for income_period in sorted(income_by_period)
            if income_period <= period
        ][-4:]
        if not income_window:
            continue

        balance = balance_by_period[period]
        equity = balance.get("equity")
        liabilities = balance.get("liabilities")
        revenue_sum = _sum_values(income_window, "revenue")
        operating_income_sum = _sum_values(income_window, "operating_income")
        net_income_sum = _sum_values(income_window, "net_income")
        average_equity = _average_equity(
            period=period,
            income_window=income_window,
            balance_by_period=balance_by_period,
            current_equity=equity,
        )

        rows.append(
            {
                "ticker": ticker,
                "fiscal_year": year,
                "fiscal_quarter": quarter,
                "roe": _safe_div(net_income_sum, average_equity),
                "operating_margin": _safe_div(operating_income_sum, revenue_sum),
                "debt_ratio": _safe_div(liabilities, equity),
                "published_at": balance.get("published_at"),
            }
        )
    return rows


def _needs_quality_metric_supplement(
    rows: list[dict[str, Any]],
    *,
    year_from: int,
    year_to: int,
) -> bool:
    metric_keys = ("roe", "operating_margin", "debt_ratio")
    expected_periods = {
        (year, quarter)
        for year in range(year_from, year_to + 1)
        for quarter in range(1, 5)
    }
    actual_periods = {
        (row["fiscal_year"], row["fiscal_quarter"])
        for row in rows
    }
    if not expected_periods.issubset(actual_periods):
        return True
    return any(
        any(row.get(key) is None for key in metric_keys)
        or _has_suspicious_quality_metric(row)
        for row in rows
    )


def _has_suspicious_quality_metric(row: dict[str, Any]) -> bool:
    debt_ratio = row.get("debt_ratio")
    return debt_ratio is not None and debt_ratio < 0.05


def _merge_missing_quality_metric_values(
    primary_rows: list[dict[str, Any]],
    supplemental_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    supplemental_by_period = {
        (row["fiscal_year"], row["fiscal_quarter"]): row
        for row in supplemental_rows
    }
    metric_keys = ("roe", "operating_margin", "debt_ratio", "published_at")
    merged_rows: list[dict[str, Any]] = []
    primary_periods: set[Period] = set()
    for row in primary_rows:
        merged = dict(row)
        period = (row["fiscal_year"], row["fiscal_quarter"])
        primary_periods.add(period)
        supplemental = supplemental_by_period.get(
            period
        )
        if supplemental is not None:
            replace_row = _has_suspicious_quality_metric(merged)
            for key in metric_keys:
                if (replace_row or merged.get(key) is None) and supplemental.get(key) is not None:
                    merged[key] = supplemental[key]
        merged_rows.append(merged)
    for row in supplemental_rows:
        period = (row["fiscal_year"], row["fiscal_quarter"])
        if period not in primary_periods:
            merged_rows.append(dict(row))
    merged_rows.sort(key=lambda row: (row["fiscal_year"], row["fiscal_quarter"]))
    return merged_rows


def _field_from_single_account_row(row: dict[str, Any]) -> str | None:
    account_name = str(row.get("account_nm", ""))
    if row.get("sj_div") == "IS":
        if "\ub9e4\ucd9c\uc561" in account_name or account_name in {"\uc218\uc775", "\uc601\uc5c5\uc218\uc775"}:
            return "revenue"
        if "\uc601\uc5c5\uc774\uc775" in account_name:
            return "operating_income"
        if "\ub2f9\uae30\uc21c\uc774\uc775" in account_name:
            return "net_income"
    if row.get("sj_div") == "BS":
        if "\uc790\uc0b0\ucd1d\uacc4" in account_name:
            return "assets"
        if "\uc790\ubcf8\ucd1d\uacc4" in account_name:
            return "equity"
        if "\ubd80\ucc44\ucd1d\uacc4" in account_name:
            return "liabilities"
    return None


def _number_from_single_account_row(row: dict[str, Any]) -> float | None:
    value = row.get("thstrm_amount")
    if value is None or value == "":
        return None
    if isinstance(value, str):
        value = value.replace(",", "").strip()
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _convert_annual_income_to_fourth_quarter(
    *,
    row: dict[str, Any],
    earlier_quarters: list[dict[str, Any]],
) -> None:
    for field in SINGLE_ACCOUNT_INCOME_FIELDS:
        annual_value = row.get(field)
        if annual_value is None:
            continue
        earlier_sum = _sum_values(earlier_quarters, field)
        if earlier_sum is not None:
            row[field] = annual_value - earlier_sum


def _rows_for_keys(payload: dict[str, Any], keys: tuple[str, ...]) -> list[dict[str, Any]]:
    for key in keys:
        rows = payload.get(key)
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    return []


def _payload_from_financial_statement(payload: Any) -> dict[str, list[dict[str, Any]]] | None:
    show = getattr(payload, "show", None)
    if not callable(show):
        return None
    try:
        balance_df = show("bs")
        income_df = show("is")
        if income_df is None:
            income_df = show("cis")
    except Exception as exc:
        logger.warning(f"Failed to read DART financial statement tables: {exc}")
        return None

    return {
        "balance_sheet": _rows_from_financial_statement_dataframe(
            balance_df,
            statement_type="balance",
        ),
        "income_statement": _rows_from_financial_statement_dataframe(
            income_df,
            statement_type="income",
        ),
    }


def _rows_from_financial_statement_dataframe(
    df: Any,
    *,
    statement_type: str,
) -> list[dict[str, Any]]:
    if df is None or not hasattr(df, "columns") or not hasattr(df, "iterrows"):
        return []

    label_column = _find_label_column(df.columns)
    if label_column is None:
        return []

    rows_by_period: dict[Period, dict[str, Any]] = {}
    value_columns = [column for column in df.columns if column != label_column]
    for column in sorted(value_columns, key=_statement_column_sort_key):
        if column == label_column:
            continue
        period = _period_from_column(column)
        if period is None:
            continue

        target = rows_by_period.setdefault(
            period,
            {
                "fiscal_year": period[0],
                "fiscal_quarter": period[1],
            },
        )
        for _, row in df.iterrows():
            field = _field_from_account_label(row[label_column], statement_type)
            if field is None:
                continue
            if field not in target or _is_missing_value(target[field]):
                target[field] = row[column]

    return list(rows_by_period.values())


def _statement_column_sort_key(column: Any) -> tuple[Period, int, str]:
    period = _period_from_column(column) or (9999, 4)
    return period, _statement_column_priority(column), repr(column)


def _statement_column_priority(column: Any) -> int:
    parts = _flatten_column_parts(column)
    non_period_parts = [part for part in parts if _period_from_column(part) is None]

    consolidated = "\uc5f0\uacb0\uc7ac\ubb34\uc81c\ud45c"
    disclosure = "\uacf5\uc2dc\uae08\uc561"
    forbidden_parts = {
        "DS \ubd80\ubb38",
        "DX \ubd80\ubb38",
        "SDC",
        "Harman",
        "\uc601\uc5c5\ubd80\ubb38",
        "\uc911\uc694\ud55c \uc870\uc815\uc0ac\ud56d",
        "\ubcf4\ud1b5\uc8fc",
        "\uc6b0\uc120\uc8fc",
    }

    if disclosure in non_period_parts:
        return 0
    if non_period_parts == [consolidated]:
        return 1
    if any(part in forbidden_parts for part in non_period_parts):
        return 100
    if consolidated in non_period_parts:
        return 50
    return 75


def _is_missing_value(value: Any) -> bool:
    if value is None or value == "":
        return True
    return value != value


def _find_label_column(columns: Any) -> Any | None:
    for column in columns:
        if any(part == "label_ko" for part in _flatten_column_parts(column)):
            return column
    return None


def _period_from_column(column: Any) -> Period | None:
    for part in _flatten_column_parts(column):
        match = re.search(r"(\d{8})(?:-(\d{8}))?", part)
        if match is None:
            continue
        date_text = match.group(2) or match.group(1)
        try:
            end_date = datetime.strptime(date_text, "%Y%m%d").date()
        except ValueError:
            return None
        quarter = (end_date.month - 1) // 3 + 1
        if quarter < 1 or quarter > 4:
            return None
        return end_date.year, quarter
    return None


def _flatten_column_parts(value: Any) -> list[str]:
    if isinstance(value, tuple):
        parts: list[str] = []
        for item in value:
            parts.extend(_flatten_column_parts(item))
        return parts
    if value is None:
        return []
    return [str(value)]


def _field_from_account_label(label: Any, statement_type: str) -> str | None:
    raw_label = str(label)
    if statement_type == "income":
        if "\ub9e4\ucd9c\uc561" in raw_label or raw_label in {"\uc218\uc775", "\uc601\uc5c5\uc218\uc775"}:
            return "revenue"
        if "\uc601\uc5c5\uc774\uc775" in raw_label:
            return "operating_income"
        if any(
            alias in raw_label
            for alias in (
                "\ub2f9\uae30\uc21c\uc774\uc775",
                "\ubd84\uae30\uc21c\uc774\uc775",
                "\ubc18\uae30\uc21c\uc774\uc775",
            )
        ):
            return "net_income"
    if statement_type == "balance":
        if "\uc790\ubcf8\ucd1d\uacc4" in raw_label:
            return "equity"
        if "\ubd80\ucc44\ucd1d\uacc4" in raw_label:
            return "liabilities"

    key = _clean_account_label(label)
    if statement_type == "income":
        if "매출액" in key or key in {"수익", "영업수익"}:
            return "revenue"
        if "영업이익" in key:
            return "operating_income"
        if "당기순이익" in key:
            return "net_income"
    if statement_type == "balance":
        if "자본총계" in key:
            return "equity"
        if "부채총계" in key:
            return "liabilities"
    return None


def _clean_account_label(label: Any) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]", "", str(label))


def _normalize_income_row(row: dict[str, Any]) -> dict[str, Any] | None:
    period = _period_from_row(row)
    if period is None:
        return None
    return {
        "period": period,
        "revenue": _number_from_row(row, REVENUE_KEYS),
        "operating_income": _number_from_row(row, OPERATING_INCOME_KEYS),
        "net_income": _number_from_row(row, NET_INCOME_KEYS),
    }


def _normalize_balance_row(row: dict[str, Any]) -> dict[str, Any] | None:
    period = _period_from_row(row)
    if period is None:
        return None
    return {
        "period": period,
        "equity": _number_from_row(row, EQUITY_KEYS),
        "liabilities": _number_from_row(row, LIABILITIES_KEYS),
        "published_at": _date_from_row(row, PUBLISHED_AT_KEYS),
    }


def _period_from_row(row: dict[str, Any]) -> Period | None:
    year = row.get("fiscal_year", row.get("year"))
    quarter = row.get("fiscal_quarter", row.get("quarter"))
    try:
        year_int = int(year)
        quarter_int = int(quarter)
    except (TypeError, ValueError):
        return None
    if quarter_int < 1 or quarter_int > 4:
        return None
    return year_int, quarter_int


def _number_from_row(row: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        if key not in row:
            continue
        value = row[key]
        if value is None or value == "":
            return None
        if value != value:
            return None
        if isinstance(value, str):
            value = value.replace(",", "").strip()
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    return None


def _date_from_row(row: dict[str, Any], keys: tuple[str, ...]) -> date | None:
    for key in keys:
        value = row.get(key)
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            for fmt in ("%Y-%m-%d", "%Y%m%d"):
                try:
                    return datetime.strptime(value, fmt).date()
                except ValueError:
                    pass
    return None


def _period_from_filing_row(row: dict[str, Any]) -> Period | None:
    report_name = str(row.get("report_nm", ""))
    match = re.search(r"\((\d{4})[./-](\d{2})\)", report_name)
    year: int | None = None
    month: int | None = None
    if match is not None:
        year = int(match.group(1))
        month = int(match.group(2))

    if "\uc0ac\uc5c5\ubcf4\uace0\uc11c" in report_name:
        return (year, 4) if year is not None else None
    if "\ubc18\uae30\ubcf4\uace0\uc11c" in report_name:
        return (year, 2) if year is not None else None
    if "\ubd84\uae30\ubcf4\uace0\uc11c" not in report_name:
        return None

    if year is None:
        return None
    if month == 3 or "1\ubd84\uae30" in report_name:
        return year, 1
    if month == 9 or "3\ubd84\uae30" in report_name:
        return year, 3
    return None


def _sum_values(rows: list[dict[str, Any]], key: str) -> float | None:
    values = [row[key] for row in rows if row.get(key) is not None]
    if not values:
        return None
    return float(sum(values))


def _average_equity(
    *,
    period: Period,
    income_window: list[dict[str, Any]],
    balance_by_period: dict[Period, dict[str, Any]],
    current_equity: float | None,
) -> float | None:
    if current_equity is None:
        return None

    if len(income_window) == 4:
        start_period = _previous_period(income_window[0]["period"])
        start_equity = balance_by_period.get(start_period, {}).get("equity")
        if start_equity is not None:
            return (start_equity + current_equity) / 2

    recent_equity = [
        balance["equity"]
        for balance_period, balance in sorted(balance_by_period.items())
        if balance_period <= period and balance.get("equity") is not None
    ][-4:]
    if recent_equity:
        return float(sum(recent_equity)) / len(recent_equity)
    return current_equity


def _previous_period(period: Period) -> Period:
    year, quarter = period
    if quarter == 1:
        return year - 1, 4
    return year, quarter - 1


def _safe_div(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator
