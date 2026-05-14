from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import pandas as pd

from src.data.quality_provider import DartFssFundamentalsProvider


class FakeCorp:
    def __init__(self, *, stock_code, corp_code):
        self.stock_code = stock_code
        self.corp_code = corp_code


class FakeCorpList:
    def __init__(self, corps):
        self._corps = corps

    def __iter__(self):
        return iter(self._corps)


class FakeDartModule:
    def __init__(self):
        self.api_key = None
        self.corp_list = FakeCorpList(
            [
                FakeCorp(stock_code="005930", corp_code="00126380"),
                FakeCorp(stock_code="000660", corp_code="00164779"),
                FakeCorp(stock_code=None, corp_code="99999999"),
            ]
        )
        self.fs = MagicMock()
        self.fs.extract.return_value = {"placeholder": True}

    def set_api_key(self, api_key):
        self.api_key = api_key

    def get_corp_list(self):
        return self.corp_list


class FakeFinanceApi:
    def __init__(self):
        self.calls = []

    def fnltt_singl_acnt(self, *, corp_code, bsns_year, reprt_code):
        self.calls.append((corp_code, bsns_year, reprt_code))
        account = {
            "revenue": "\ub9e4\ucd9c\uc561",
            "operating_income": "\uc601\uc5c5\uc774\uc775",
            "net_income": "\ub2f9\uae30\uc21c\uc774\uc775(\uc190\uc2e4)",
            "equity": "\uc790\ubcf8\ucd1d\uacc4",
            "liabilities": "\ubd80\ucc44\ucd1d\uacc4",
        }
        report_values = {
            ("2023", "11011"): {"equity": "90", "liabilities": "40"},
            ("2024", "11013"): {
                "revenue": "100",
                "operating_income": "10",
                "net_income": "5",
                "equity": "100",
                "liabilities": "45",
            },
            ("2024", "11012"): {
                "revenue": "110",
                "operating_income": "11",
                "net_income": "6",
                "equity": "110",
                "liabilities": "50",
            },
            ("2024", "11014"): {
                "revenue": "120",
                "operating_income": "12",
                "net_income": "7",
                "equity": "120",
                "liabilities": "52",
            },
            ("2024", "11011"): {
                "revenue": "460",
                "operating_income": "46",
                "net_income": "26",
                "equity": "130",
                "liabilities": "54",
            },
        }
        values = report_values[(bsns_year, reprt_code)]
        rows = []
        for key, value in values.items():
            rows.append(
                {
                    "fs_div": "CFS",
                    "sj_div": "BS" if key in {"equity", "liabilities"} else "IS",
                    "account_nm": account[key],
                    "thstrm_amount": value,
                }
            )
        return {"status": "000", "message": "OK", "list": rows}


class FakeFinanceApiWithOFSOnlyFirstQuarter(FakeFinanceApi):
    def fnltt_singl_acnt(self, *, corp_code, bsns_year, reprt_code):
        response = super().fnltt_singl_acnt(
            corp_code=corp_code,
            bsns_year=bsns_year,
            reprt_code=reprt_code,
        )
        if (bsns_year, reprt_code) == ("2024", "11013"):
            for row in response["list"]:
                row["fs_div"] = "OFS"
        return response


class FakeFinanceApiWithAssetsInsteadOfEquityFirstQuarter(FakeFinanceApi):
    def fnltt_singl_acnt(self, *, corp_code, bsns_year, reprt_code):
        response = super().fnltt_singl_acnt(
            corp_code=corp_code,
            bsns_year=bsns_year,
            reprt_code=reprt_code,
        )
        if (bsns_year, reprt_code) == ("2024", "11013"):
            rows = []
            for row in response["list"]:
                if row["account_nm"] == "\uc790\ubcf8\ucd1d\uacc4":
                    rows.append({**row, "account_nm": "\uc790\uc0b0\ucd1d\uacc4", "thstrm_amount": "145"})
                else:
                    rows.append(row)
            response["list"] = rows
        return response


class FakeApiWithFinance:
    def __init__(self):
        self.filings = FakeFilings()
        self.finance = FakeFinanceApi()


class FakeDartModuleWithBrokenExtract(FakeDartModule):
    def __init__(self):
        super().__init__()
        self.api = FakeApiWithFinance()
        self.fs.extract.side_effect = TypeError("dart-fss merge failed")


class FakeDartModuleWithSingleAccountAndFilings(FakeDartModuleWithBrokenExtract):
    def __init__(self):
        super().__init__()
        self.api = FakeApiWithFinanceAndFilings()


class FakeCorpCode:
    def get_corp_code(self):
        return [
            {
                "corp_code": "00126380",
                "corp_name": "삼성전자",
                "corp_eng_name": "SAMSUNG ELECTRONICS",
                "stock_code": "005930",
                "modify_date": "20240101",
            },
            {
                "corp_code": "99999999",
                "corp_name": "비상장",
                "corp_eng_name": "UNLISTED",
                "stock_code": None,
                "modify_date": "20240101",
            },
        ]


class FakeFilings:
    def __init__(self):
        self.corp_code = FakeCorpCode()


class FakeFilingsWithSearch(FakeFilings):
    def __init__(self):
        super().__init__()
        self.calls = []

    def search_filings(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "status": "000",
            "message": "OK",
            "list": [
                {
                    "corp_code": "00126380",
                    "report_nm": "분기보고서 (2024.03)",
                    "rcept_dt": "20240516",
                },
                {
                    "corp_code": "00126380",
                    "report_nm": "반기보고서 (2024.06)",
                    "rcept_dt": "20240814",
                },
                {
                    "corp_code": "00126380",
                    "report_nm": "분기보고서 (2024.09)",
                    "rcept_dt": "20241114",
                },
                {
                    "corp_code": "00126380",
                    "report_nm": "사업보고서 (2024.12)",
                    "rcept_dt": "20250318",
                },
            ],
        }


class FakeApiWithFinanceAndFilings:
    def __init__(self):
        self.filings = FakeFilingsWithSearch()
        self.finance = FakeFinanceApi()


class FakeApi:
    def __init__(self):
        self.filings = FakeFilings()


class FakeDartModuleWithBrokenCorpList(FakeDartModule):
    def __init__(self):
        super().__init__()
        self.api = FakeApi()

    def get_corp_list(self):
        raise TypeError("Corp.__init__() got an unexpected keyword argument 'corp_eng_name'")


class FakeCache:
    def __init__(self, cache_dir):
        self._cache_dir = cache_dir

    def cache_dir(self):
        return self._cache_dir


class FakeUtils:
    def __init__(self, cache_dir):
        self.cache = FakeCache(cache_dir)


class FakeRateLimiter:
    def __init__(self):
        self.calls = 0

    def acquire(self):
        self.calls += 1


class FakeFinancialStatement:
    def __init__(self, *, bs, is_, cis=None):
        self._statements = {"bs": bs, "is": is_, "cis": cis}

    def show(self, tp):
        return self._statements[tp]


def test_dart_provider_sets_api_key_and_builds_stock_code_mapping():
    dart = FakeDartModule()
    rate_limiter = FakeRateLimiter()

    provider = DartFssFundamentalsProvider(
        api_key="test-api-key",
        rate_limiter=rate_limiter,
        dart_module=dart,
    )

    assert dart.api_key == "test-api-key"
    assert provider.stock_to_corp_code == {
        "005930": "00126380",
        "000660": "00164779",
    }


def test_dart_provider_falls_back_to_raw_corp_code_when_corp_list_schema_changes():
    provider = DartFssFundamentalsProvider(
        api_key="test-api-key",
        rate_limiter=FakeRateLimiter(),
        dart_module=FakeDartModuleWithBrokenCorpList(),
    )

    assert provider.stock_to_corp_code == {"005930": "00126380"}


def test_dart_provider_refreshes_corp_code_cache_when_requested():
    cache_dir = Path("data/test_corp_code_cache")
    cache_dir.mkdir(parents=True, exist_ok=True)
    dart = FakeDartModule()
    dart.utils = FakeUtils(str(cache_dir))
    zip_path = cache_dir / "CORPCODE.zip"
    xml_path = cache_dir / "CORPCODE.xml"
    zip_path.write_text("cached zip")
    xml_path.write_text("cached xml")
    keep_path = cache_dir / "other.txt"
    keep_path.write_text("keep")

    DartFssFundamentalsProvider(
        api_key="test-api-key",
        rate_limiter=FakeRateLimiter(),
        dart_module=dart,
        refresh_corp_list=True,
    )

    assert not zip_path.exists()
    assert not xml_path.exists()
    assert keep_path.exists()
    keep_path.unlink()
    cache_dir.rmdir()


def test_dart_provider_returns_empty_rows_for_unmapped_ticker_without_rate_limit():
    dart = FakeDartModule()
    rate_limiter = FakeRateLimiter()
    provider = DartFssFundamentalsProvider(
        api_key="test-api-key",
        rate_limiter=rate_limiter,
        dart_module=dart,
    )

    rows = provider.get_quality_metrics("999999", year_from=2024, year_to=2025)

    assert rows == []
    assert rate_limiter.calls == 0
    dart.fs.extract.assert_not_called()


def test_dart_provider_acquires_rate_limit_and_extracts_for_mapped_ticker():
    dart = FakeDartModule()
    rate_limiter = FakeRateLimiter()
    provider = DartFssFundamentalsProvider(
        api_key="test-api-key",
        rate_limiter=rate_limiter,
        dart_module=dart,
    )

    rows = provider.get_quality_metrics("005930", year_from=2024, year_to=2025)

    assert rows == []
    assert rate_limiter.calls == 1
    dart.fs.extract.assert_called_once_with(
        "00126380",
        bgn_de="20240101",
        report_tp="quarter",
        cumulative=False,
        progressbar=False,
    )


def test_dart_provider_falls_back_to_single_account_api_when_extract_merge_fails():
    dart = FakeDartModuleWithBrokenExtract()
    rate_limiter = FakeRateLimiter()
    provider = DartFssFundamentalsProvider(
        api_key="test-api-key",
        rate_limiter=rate_limiter,
        dart_module=dart,
    )

    rows = provider.get_quality_metrics("005930", year_from=2024, year_to=2024)

    assert len(rows) == 4
    assert rows[-1] == {
        "ticker": "005930",
        "fiscal_year": 2024,
        "fiscal_quarter": 4,
        "roe": pytest.approx(26.0 / 110.0),
        "operating_margin": pytest.approx(46.0 / 460.0),
        "debt_ratio": pytest.approx(54.0 / 130.0),
        "published_at": None,
    }
    assert dart.api.finance.calls == [
        ("00126380", "2023", "11011"),
        ("00126380", "2024", "11013"),
        ("00126380", "2024", "11012"),
        ("00126380", "2024", "11014"),
        ("00126380", "2024", "11011"),
    ]
    assert rate_limiter.calls == 6


def test_dart_provider_adds_published_dates_from_dart_filing_search():
    dart = FakeDartModuleWithSingleAccountAndFilings()
    rate_limiter = FakeRateLimiter()
    provider = DartFssFundamentalsProvider(
        api_key="test-api-key",
        rate_limiter=rate_limiter,
        dart_module=dart,
    )

    rows = provider.get_quality_metrics("005930", year_from=2024, year_to=2024)

    assert [row["published_at"] for row in rows] == [
        date(2024, 5, 16),
        date(2024, 8, 14),
        date(2024, 11, 14),
        date(2025, 3, 18),
    ]
    assert dart.api.filings.calls == [
        {
            "corp_code": "00126380",
            "bgn_de": "20240101",
            "end_de": "20251231",
            "last_reprt_at": "Y",
            "pblntf_ty": "A",
            "sort": "date",
            "sort_mth": "desc",
            "page_no": 1,
            "page_count": 100,
        }
    ]
    assert rate_limiter.calls == 7


def test_dart_provider_uses_ofs_single_account_rows_when_cfs_rows_are_absent():
    dart = FakeDartModuleWithBrokenExtract()
    dart.api.finance = FakeFinanceApiWithOFSOnlyFirstQuarter()
    rate_limiter = FakeRateLimiter()
    provider = DartFssFundamentalsProvider(
        api_key="test-api-key",
        rate_limiter=rate_limiter,
        dart_module=dart,
    )

    rows = provider.get_quality_metrics("005930", year_from=2024, year_to=2024)

    assert [(row["fiscal_year"], row["fiscal_quarter"]) for row in rows] == [
        (2024, 1),
        (2024, 2),
        (2024, 3),
        (2024, 4),
    ]
    assert rows[0]["roe"] == pytest.approx(5.0 / 95.0)
    assert rows[0]["operating_margin"] == pytest.approx(10.0 / 100.0)
    assert rows[0]["debt_ratio"] == pytest.approx(45.0 / 100.0)


def test_dart_provider_derives_missing_equity_from_assets_and_liabilities():
    dart = FakeDartModuleWithBrokenExtract()
    dart.api.finance = FakeFinanceApiWithAssetsInsteadOfEquityFirstQuarter()
    rate_limiter = FakeRateLimiter()
    provider = DartFssFundamentalsProvider(
        api_key="test-api-key",
        rate_limiter=rate_limiter,
        dart_module=dart,
    )

    rows = provider.get_quality_metrics("005930", year_from=2024, year_to=2024)

    assert rows[0]["roe"] == pytest.approx(5.0 / 95.0)
    assert rows[0]["debt_ratio"] == pytest.approx(45.0 / 100.0)


def test_dart_provider_uses_single_account_api_to_fill_missing_primary_metrics():
    dart = FakeDartModuleWithBrokenExtract()
    dart.fs.extract.side_effect = None
    dart.fs.extract.return_value = {
        "income_statement": [
            {
                "fiscal_year": 2024,
                "fiscal_quarter": 1,
                "revenue": 100.0,
                "operating_income": 10.0,
                "net_income": 5.0,
            },
            {
                "fiscal_year": 2024,
                "fiscal_quarter": 2,
                "revenue": 110.0,
                "operating_income": 11.0,
                "net_income": 6.0,
            },
            {
                "fiscal_year": 2024,
                "fiscal_quarter": 3,
                "revenue": 120.0,
                "operating_income": 12.0,
                "net_income": 7.0,
            },
            {
                "fiscal_year": 2024,
                "fiscal_quarter": 4,
                "revenue": 130.0,
                "operating_income": 13.0,
                "net_income": 8.0,
            },
        ],
        "balance_sheet": [
            {
                "fiscal_year": 2023,
                "fiscal_quarter": 4,
                "equity": 90.0,
                "liabilities": 40.0,
            },
            {
                "fiscal_year": 2024,
                "fiscal_quarter": 1,
                "equity": 100.0,
            },
            {
                "fiscal_year": 2024,
                "fiscal_quarter": 2,
                "equity": 110.0,
            },
            {
                "fiscal_year": 2024,
                "fiscal_quarter": 3,
                "equity": 120.0,
            },
            {
                "fiscal_year": 2024,
                "fiscal_quarter": 4,
                "equity": 130.0,
                "liabilities": 54.0,
            },
        ],
    }
    rate_limiter = FakeRateLimiter()
    provider = DartFssFundamentalsProvider(
        api_key="test-api-key",
        rate_limiter=rate_limiter,
        dart_module=dart,
    )

    rows = provider.get_quality_metrics("005930", year_from=2024, year_to=2024)

    assert [row["debt_ratio"] for row in rows] == [
        pytest.approx(45.0 / 100.0),
        pytest.approx(50.0 / 110.0),
        pytest.approx(52.0 / 120.0),
        pytest.approx(54.0 / 130.0),
    ]
    assert dart.api.finance.calls == [
        ("00126380", "2023", "11011"),
        ("00126380", "2024", "11013"),
        ("00126380", "2024", "11012"),
        ("00126380", "2024", "11014"),
        ("00126380", "2024", "11011"),
    ]
    assert rate_limiter.calls == 6


def test_dart_provider_replaces_suspicious_primary_metrics_from_single_account_api():
    dart = FakeDartModuleWithBrokenExtract()
    dart.fs.extract.side_effect = None
    dart.fs.extract.return_value = {
        "income_statement": [
            {
                "fiscal_year": 2024,
                "fiscal_quarter": 1,
                "revenue": 100.0,
                "operating_income": 99.0,
                "net_income": 99.0,
            },
        ],
        "balance_sheet": [
            {
                "fiscal_year": 2024,
                "fiscal_quarter": 1,
                "equity": 100.0,
                "liabilities": -20.0,
            },
        ],
    }
    provider = DartFssFundamentalsProvider(
        api_key="test-api-key",
        rate_limiter=FakeRateLimiter(),
        dart_module=dart,
    )

    rows = provider.get_quality_metrics("005930", year_from=2024, year_to=2024)

    assert rows[0] == {
        "ticker": "005930",
        "fiscal_year": 2024,
        "fiscal_quarter": 1,
        "roe": pytest.approx(5.0 / 95.0),
        "operating_margin": pytest.approx(10.0 / 100.0),
        "debt_ratio": pytest.approx(45.0 / 100.0),
        "published_at": None,
    }


def test_dart_provider_adds_missing_periods_and_replaces_tiny_debt_ratio():
    dart = FakeDartModuleWithBrokenExtract()
    dart.fs.extract.side_effect = None
    dart.fs.extract.return_value = {
        "income_statement": [
            {
                "fiscal_year": 2024,
                "fiscal_quarter": 2,
                "revenue": 110.0,
                "operating_income": 99.0,
                "net_income": 99.0,
            },
        ],
        "balance_sheet": [
            {
                "fiscal_year": 2024,
                "fiscal_quarter": 2,
                "equity": 110.0,
                "liabilities": 0.11,
            },
        ],
    }
    provider = DartFssFundamentalsProvider(
        api_key="test-api-key",
        rate_limiter=FakeRateLimiter(),
        dart_module=dart,
    )

    rows = provider.get_quality_metrics("005930", year_from=2024, year_to=2024)

    assert [(row["fiscal_year"], row["fiscal_quarter"]) for row in rows] == [
        (2024, 1),
        (2024, 2),
        (2024, 3),
        (2024, 4),
    ]
    assert rows[1]["roe"] == pytest.approx(11.0 / 100.0)
    assert rows[1]["operating_margin"] == pytest.approx(21.0 / 210.0)
    assert rows[1]["debt_ratio"] == pytest.approx(50.0 / 110.0)


def test_dart_provider_adds_missing_periods_when_primary_rows_are_complete():
    dart = FakeDartModuleWithBrokenExtract()
    dart.fs.extract.side_effect = None
    dart.fs.extract.return_value = {
        "income_statement": [
            {
                "fiscal_year": 2024,
                "fiscal_quarter": 4,
                "revenue": 460.0,
                "operating_income": 46.0,
                "net_income": 26.0,
            },
        ],
        "balance_sheet": [
            {
                "fiscal_year": 2024,
                "fiscal_quarter": 4,
                "equity": 130.0,
                "liabilities": 54.0,
            },
        ],
    }
    provider = DartFssFundamentalsProvider(
        api_key="test-api-key",
        rate_limiter=FakeRateLimiter(),
        dart_module=dart,
    )

    rows = provider.get_quality_metrics("005930", year_from=2024, year_to=2024)

    assert [(row["fiscal_year"], row["fiscal_quarter"]) for row in rows] == [
        (2024, 1),
        (2024, 2),
        (2024, 3),
        (2024, 4),
    ]
    assert rows[0]["roe"] == pytest.approx(5.0 / 95.0)
    assert rows[-1]["roe"] == pytest.approx(26.0 / 130.0)


def test_dart_provider_parses_quality_metrics_from_normalized_extract_payload():
    dart = FakeDartModule()
    dart.fs.extract.return_value = {
        "income_statement": [
            {
                "fiscal_year": 2024,
                "fiscal_quarter": 1,
                "revenue": 100.0,
                "operating_income": 10.0,
                "net_income": 5.0,
            },
            {
                "fiscal_year": 2024,
                "fiscal_quarter": 2,
                "revenue": 110.0,
                "operating_income": 11.0,
                "net_income": 6.0,
            },
            {
                "fiscal_year": 2024,
                "fiscal_quarter": 3,
                "revenue": 120.0,
                "operating_income": 12.0,
                "net_income": 7.0,
            },
            {
                "fiscal_year": 2024,
                "fiscal_quarter": 4,
                "revenue": 130.0,
                "operating_income": 13.0,
                "net_income": 8.0,
            },
        ],
        "balance_sheet": [
            {
                "fiscal_year": 2023,
                "fiscal_quarter": 4,
                "equity": 90.0,
                "liabilities": 40.0,
            },
            {
                "fiscal_year": 2024,
                "fiscal_quarter": 4,
                "equity": 130.0,
                "liabilities": 54.0,
                "published_at": date(2025, 3, 31),
            },
        ],
    }
    rate_limiter = FakeRateLimiter()
    provider = DartFssFundamentalsProvider(
        api_key="test-api-key",
        rate_limiter=rate_limiter,
        dart_module=dart,
    )

    rows = provider.get_quality_metrics("005930", year_from=2024, year_to=2024)

    assert rows == [
        {
            "ticker": "005930",
            "fiscal_year": 2024,
            "fiscal_quarter": 4,
            "roe": pytest.approx(26.0 / 110.0),
            "operating_margin": pytest.approx(46.0 / 460.0),
            "debt_ratio": pytest.approx(54.0 / 130.0),
            "published_at": date(2025, 3, 31),
        }
    ]
    assert rate_limiter.calls == 1


def test_dart_provider_parses_quality_metrics_from_financial_statement_dataframes():
    income_df = pd.DataFrame(
        [
            ["매출액", "100", "110", "120", "130"],
            ["영업이익", "10", "11", "12", "13"],
            ["당기순이익", "5", "6", "7", "8"],
        ],
        columns=pd.MultiIndex.from_tuples(
            [
                ("Income statement(Unit: KRW)", "label_ko"),
                ("20240101-20240331", ("연결재무제표", "3개월")),
                ("20240401-20240630", ("연결재무제표", "3개월")),
                ("20240701-20240930", ("연결재무제표", "3개월")),
                ("20241001-20241231", ("연결재무제표", "3개월")),
            ]
        ),
    )
    balance_df = pd.DataFrame(
        [
            ["자본총계", "90", "130"],
            ["부채총계", "40", "54"],
        ],
        columns=pd.MultiIndex.from_tuples(
            [
                ("Statement of financial position(Unit: KRW)", "label_ko"),
                ("20231231", ("연결재무제표", "금액")),
                ("20241231", ("연결재무제표", "금액")),
            ]
        ),
    )
    dart = FakeDartModule()
    dart.fs.extract.return_value = FakeFinancialStatement(bs=balance_df, is_=income_df)
    provider = DartFssFundamentalsProvider(
        api_key="test-api-key",
        rate_limiter=FakeRateLimiter(),
        dart_module=dart,
    )

    rows = provider.get_quality_metrics("005930", year_from=2024, year_to=2024)

    assert rows == [
        {
            "ticker": "005930",
            "fiscal_year": 2024,
            "fiscal_quarter": 4,
            "roe": pytest.approx(26.0 / 110.0),
            "operating_margin": pytest.approx(46.0 / 460.0),
            "debt_ratio": pytest.approx(54.0 / 130.0),
            "published_at": None,
        }
    ]


def test_dart_provider_prefers_consolidated_disclosure_columns_from_dart_dataframes():
    revenue = "\ub9e4\ucd9c\uc561"
    operating_income = "\uc601\uc5c5\uc774\uc775"
    net_income = "\ub2f9\uae30\uc21c\uc774\uc775"
    consolidated = "\uc5f0\uacb0\uc7ac\ubb34\uc81c\ud45c"
    disclosure = "\uacf5\uc2dc\uae08\uc561"
    segment = "DS \ubd80\ubb38"
    operating_segment = "\uc601\uc5c5\ubd80\ubb38"
    common_stock = "\ubcf4\ud1b5\uc8fc"
    equity = "\uc790\ubcf8\ucd1d\uacc4"
    liabilities = "\ubd80\ucc44\ucd1d\uacc4"

    income_df = pd.DataFrame(
        [
            [revenue, "100", "999", "110", "120", "130", "999"],
            [operating_income, "10", "999", "11", "12", "13", "999"],
            [net_income, "5", "999", "6", "7", "8", "999"],
        ],
        columns=pd.MultiIndex.from_tuples(
            [
                ("Income statement(Unit: KRW)", "label_ko"),
                ("20240101-20240331", (consolidated, disclosure)),
                ("20240101-20240331", (segment, operating_segment, consolidated)),
                ("20240401-20240630", (consolidated, disclosure)),
                ("20240701-20240930", (consolidated, disclosure)),
                ("20241001-20241231", (consolidated, disclosure)),
                ("20241001-20241231", (consolidated, common_stock)),
            ]
        ),
    )
    balance_df = pd.DataFrame(
        [
            [equity, "90", "130", "999"],
            [liabilities, "40", "54", "999"],
        ],
        columns=pd.MultiIndex.from_tuples(
            [
                ("Statement of financial position(Unit: KRW)", "label_ko"),
                ("20231231", (consolidated, disclosure)),
                ("20241231", (consolidated, disclosure)),
                ("20241231", (consolidated, "\uae30\ud0c0\uae08\uc735\uc790\uc0b0")),
            ]
        ),
    )
    dart = FakeDartModule()
    dart.fs.extract.return_value = FakeFinancialStatement(bs=balance_df, is_=income_df)
    provider = DartFssFundamentalsProvider(
        api_key="test-api-key",
        rate_limiter=FakeRateLimiter(),
        dart_module=dart,
    )

    rows = provider.get_quality_metrics("005930", year_from=2024, year_to=2024)

    assert rows == [
        {
            "ticker": "005930",
            "fiscal_year": 2024,
            "fiscal_quarter": 4,
            "roe": pytest.approx(26.0 / 110.0),
            "operating_margin": pytest.approx(46.0 / 460.0),
            "debt_ratio": pytest.approx(54.0 / 130.0),
            "published_at": None,
        }
    ]


def test_dart_provider_falls_back_to_comprehensive_income_statement_dataframe():
    income_df = pd.DataFrame(
        [
            ["\uc601\uc5c5\uc218\uc775", "100", "110", "120", "130"],
            ["\uc601\uc5c5\uc774\uc775", "10", "11", "12", "13"],
            ["\ub2f9\uae30\uc21c\uc774\uc775", "5", "6", "7", "8"],
        ],
        columns=pd.MultiIndex.from_tuples(
            [
                ("Comprehensive income statement(Unit: KRW)", "label_ko"),
                ("20240101-20240331", ("\uc5f0\uacb0\uc7ac\ubb34\uc81c\ud45c", "\uacf5\uc2dc\uae08\uc561")),
                ("20240401-20240630", ("\uc5f0\uacb0\uc7ac\ubb34\uc81c\ud45c", "\uacf5\uc2dc\uae08\uc561")),
                ("20240701-20240930", ("\uc5f0\uacb0\uc7ac\ubb34\uc81c\ud45c", "\uacf5\uc2dc\uae08\uc561")),
                ("20241001-20241231", ("\uc5f0\uacb0\uc7ac\ubb34\uc81c\ud45c", "\uacf5\uc2dc\uae08\uc561")),
            ]
        ),
    )
    balance_df = pd.DataFrame(
        [
            ["\uc790\ubcf8\ucd1d\uacc4", "90", "130"],
            ["\ubd80\ucc44\ucd1d\uacc4", "40", "54"],
        ],
        columns=pd.MultiIndex.from_tuples(
            [
                ("Statement of financial position(Unit: KRW)", "label_ko"),
                ("20231231", ("\uc5f0\uacb0\uc7ac\ubb34\uc81c\ud45c", "\uacf5\uc2dc\uae08\uc561")),
                ("20241231", ("\uc5f0\uacb0\uc7ac\ubb34\uc81c\ud45c", "\uacf5\uc2dc\uae08\uc561")),
            ]
        ),
    )
    dart = FakeDartModule()
    dart.fs.extract.return_value = FakeFinancialStatement(
        bs=balance_df,
        is_=None,
        cis=income_df,
    )
    provider = DartFssFundamentalsProvider(
        api_key="test-api-key",
        rate_limiter=FakeRateLimiter(),
        dart_module=dart,
    )

    rows = provider.get_quality_metrics("005930", year_from=2024, year_to=2024)

    assert rows == [
        {
            "ticker": "005930",
            "fiscal_year": 2024,
            "fiscal_quarter": 4,
            "roe": pytest.approx(26.0 / 110.0),
            "operating_margin": pytest.approx(46.0 / 460.0),
            "debt_ratio": pytest.approx(54.0 / 130.0),
            "published_at": None,
        }
    ]
