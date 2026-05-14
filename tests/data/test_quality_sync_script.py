from __future__ import annotations

from pathlib import Path
import subprocess
import sys

import pytest
from sqlalchemy.orm import Session

from scripts.sync_phase1_quality import parse_args, run
from scripts.sync_phase1_quality import (
    load_exception_sets,
    select_quality_sync_tickers,
    validate_quality_metrics,
)
from src.data.database import create_tables, get_engine
from src.data.models import QualityMetric, Stock


def test_parse_args_accepts_quality_sync_options():
    args = parse_args(
        [
            "--year-from",
            "2023",
            "--year-to",
            "2024",
            "--database-url",
            "sqlite:///:memory:",
            "--api-key",
            "test-key",
            "--requests-per-minute",
            "30",
            "--daily-quota",
            "500",
            "--ticker",
            "005930",
            "--ticker",
            "000660",
        ]
    )

    assert args.year_from == 2023
    assert args.year_to == 2024
    assert args.database_url == "sqlite:///:memory:"
    assert args.api_key == "test-key"
    assert args.requests_per_minute == 30
    assert args.daily_quota == 500
    assert args.tickers == ["005930", "000660"]
    assert args.refresh_corp_list is False


def test_parse_args_accepts_comma_separated_tickers_and_refresh_corp_list():
    args = parse_args(
        [
            "--api-key",
            "test-key",
            "--tickers",
            "005930,000660",
            "--refresh-corp-list",
        ]
    )

    assert args.tickers == ["005930", "000660"]
    assert args.refresh_corp_list is True


def test_parse_args_accepts_exception_aware_batch_options():
    args = parse_args(
        [
            "--api-key",
            "test-key",
            "--year-from",
            "2024",
            "--year-to",
            "2025",
            "--single-account-only",
            "--only-unsynced",
            "--limit",
            "100",
            "--validate",
            "--exceptions-file",
            "custom.json",
        ]
    )

    assert args.single_account_only is True
    assert args.only_unsynced is True
    assert args.limit == 100
    assert args.validate is True
    assert args.exceptions_file == "custom.json"


def test_parse_args_rejects_reversed_year_range():
    with pytest.raises(SystemExit):
        parse_args(["--year-from", "2025", "--year-to", "2024"])


def test_run_builds_provider_and_prints_quality_sync_summary(capsys):
    captured = {}

    def fake_rate_limiter_factory(**kwargs):
        captured["rate_limiter_kwargs"] = kwargs
        return "fake-rate-limiter"

    def fake_provider_factory(**kwargs):
        captured["provider_kwargs"] = kwargs
        return "fake-provider"

    def fake_sync_func(*, engine, provider, year_from, year_to, tickers=None):
        captured["sync_provider"] = provider
        captured["sync_year_from"] = year_from
        captured["sync_year_to"] = year_to
        captured["sync_tickers"] = tickers
        return {"status": "success", "metric_count": 12}

    args = parse_args(
        [
            "--year-from",
            "2023",
            "--year-to",
            "2024",
            "--database-url",
            "sqlite:///:memory:",
            "--api-key",
            "test-key",
            "--requests-per-minute",
            "30",
            "--daily-quota",
            "500",
            "--ticker",
            "005930",
        ]
    )

    exit_code = run(
        args,
        rate_limiter_factory=fake_rate_limiter_factory,
        provider_factory=fake_provider_factory,
        sync_func=fake_sync_func,
    )

    captured_out = capsys.readouterr().out
    assert exit_code == 0
    assert captured["rate_limiter_kwargs"] == {
        "requests_per_minute": 30,
        "daily_quota": 500,
    }
    assert captured["provider_kwargs"] == {
        "api_key": "test-key",
        "rate_limiter": "fake-rate-limiter",
        "refresh_corp_list": False,
    }
    assert captured["sync_provider"] == "fake-provider"
    assert captured["sync_year_from"] == 2023
    assert captured["sync_year_to"] == 2024
    assert captured["sync_tickers"] == ["005930"]
    assert "status=success" in captured_out
    assert "metric_count=12" in captured_out


def test_run_requires_api_key_when_provider_is_not_injected():
    args = parse_args(
        [
            "--year-from",
            "2024",
            "--year-to",
            "2024",
            "--database-url",
            "sqlite:///:memory:",
            "--api-key",
            "",
        ]
    )

    with pytest.raises(ValueError, match="DART_API_KEY"):
        run(args)


def test_select_quality_sync_tickers_excludes_synced_and_known_no_source():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    with Session(engine) as session:
        session.add_all(
            [
                Stock(ticker="005930", name="Samsung", market="KOSPI", is_active=True),
                Stock(ticker="000660", name="SK Hynix", market="KOSPI", is_active=True),
                Stock(ticker="088980", name="Macquarie", market="KOSPI", is_active=True),
                Stock(ticker="999999", name="Inactive", market="KOSPI", is_active=False),
                QualityMetric(
                    ticker="005930",
                    fiscal_year=2024,
                    fiscal_quarter=1,
                    roe=0.1,
                    operating_margin=0.2,
                    debt_ratio=0.3,
                ),
            ]
        )
        session.commit()

    assert select_quality_sync_tickers(
        engine,
        only_unsynced=True,
        limit=None,
        exclude_known_no_source=True,
        exceptions=load_exception_sets(),
    ) == ["000660"]


def test_load_exception_sets_reads_json_file():
    temp_dir = Path(".tmp")
    temp_dir.mkdir(exist_ok=True)
    exceptions_file = temp_dir / "test_quality_sync_exceptions.json"
    try:
        exceptions_file.write_text(
            """
{
  "no_source": ["088980"],
  "partial_source_absence": ["062040"],
  "partial_metric_source_absence": ["003720"],
  "financial_null_operating_margin": ["016360"],
  "low_debt_source_backed": ["454910"]
}
""".strip(),
            encoding="utf-8",
        )

        exceptions = load_exception_sets(exceptions_file)
    finally:
        exceptions_file.unlink(missing_ok=True)

    assert exceptions.no_source == {"088980"}
    assert exceptions.partial_source_absence == {"062040"}
    assert exceptions.partial_metric_source_absence == {"003720"}
    assert exceptions.financial_null_operating_margin == {"016360"}
    assert exceptions.low_debt_source_backed == {"454910"}


def test_validate_quality_metrics_reports_unexpected_issues():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    with Session(engine) as session:
        session.add(Stock(ticker="005930", name="Samsung", market="KOSPI", is_active=True))
        session.add(
            QualityMetric(
                ticker="005930",
                fiscal_year=2024,
                fiscal_quarter=1,
                roe=None,
                operating_margin=0.2,
                debt_ratio=0.3,
            )
        )
        session.commit()

    report = validate_quality_metrics(engine, exceptions=load_exception_sets())

    assert report.coverage == (1, 1)
    assert report.unexpected_issue_count == 1
    assert report.issues[0].ticker == "005930"
    assert "rows=1" in report.issues[0].issues
    assert "roe=0/1" in report.issues[0].issues


def test_validate_quality_metrics_accepts_complete_eight_quarter_rows():
    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    with Session(engine) as session:
        session.add(Stock(ticker="005930", name="Samsung", market="KOSPI", is_active=True))
        for year in [2024, 2025]:
            for quarter in [1, 2, 3, 4]:
                session.add(
                    QualityMetric(
                        ticker="005930",
                        fiscal_year=year,
                        fiscal_quarter=quarter,
                        roe=0.1,
                        operating_margin=0.2,
                        debt_ratio=0.3,
                    )
                )
        session.commit()

    report = validate_quality_metrics(engine, exceptions=load_exception_sets())

    assert report.unexpected_issue_count == 0
    assert report.issues == []


def test_script_can_be_executed_directly_with_help():
    completed = subprocess.run(
        [sys.executable, "scripts/sync_phase1_quality.py", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "Sync Phase 1 DART quality metrics into SQLite." in completed.stdout


def test_script_exits_with_clear_error_when_api_key_is_missing():
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/sync_phase1_quality.py",
            "--api-key",
            "",
            "--database-url",
            "sqlite:///:memory:",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 2
    assert "DART_API_KEY is required" in completed.stderr
    assert "Traceback" not in completed.stderr
