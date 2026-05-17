import pytest

import config
from config import COST, DART, FACTOR, DartConfig


def test_default_tax_rates_use_2026_securities_transaction_tax():
    assert COST.tax_rate_kospi == pytest.approx(0.0020)
    assert COST.tax_rate_kosdaq == pytest.approx(0.0020)


def test_default_dart_limits_are_conservative_env_backed_values():
    assert DART.requests_per_minute == 60
    assert DART.daily_quota == 10000


def test_default_kis_request_timeout_is_positive():
    assert config.KIS.request_timeout_sec == 10


def test_default_factor_scoring_method_uses_rank_to_limit_outlier_dominance():
    assert FACTOR.scoring_method == "rank"


def test_default_factor_weights_reduce_yield_and_redistribute_to_core_factors():
    redistributed = 1.0 + (0.25 / 3)

    assert FACTOR.value_weight == pytest.approx(redistributed)
    assert FACTOR.quality_weight == pytest.approx(redistributed)
    assert FACTOR.momentum_weight == pytest.approx(redistributed)
    assert FACTOR.yield_weight == pytest.approx(0.25)


def test_default_telegram_signal_fetch_limit_covers_recent_channel_chatter():
    assert config.TELEGRAM_SIGNAL.fetch_limit >= 20


def test_default_busanstock_weight_is_auxiliary():
    assert 0 < FACTOR.busanstock_weight <= 0.3


def test_default_investor_flow_weight_is_auxiliary():
    assert 0 < FACTOR.investor_flow_weight <= 0.3


def test_default_research_report_weight_is_auxiliary():
    assert 0 < FACTOR.research_report_weight <= 0.3


def test_default_research_report_source_uses_hankyung_consensus():
    assert config.RESEARCH_REPORT.enabled is True
    assert config.RESEARCH_REPORT.source == "hankyung_consensus"
    assert config.RESEARCH_REPORT.broker == "한경 컨센서스"
    assert config.RESEARCH_REPORT.url == "https://consensus.hankyung.com/"


def test_validate_warns_when_dart_key_or_limits_are_missing(monkeypatch):
    monkeypatch.setattr(
        config,
        "DART",
        DartConfig(api_key="", requests_per_minute=0, daily_quota=0),
    )
    monkeypatch.setattr(
        config,
        "KIS",
        config.KISConfig(request_timeout_sec=0),
    )

    warnings = config.validate()

    assert any("DART_API_KEY" in warning for warning in warnings)
    assert any("DART" in warning and "limit" in warning.lower() for warning in warnings)
    assert any("KIS" in warning and "timeout" in warning.lower() for warning in warnings)
