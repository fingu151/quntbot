from __future__ import annotations

import ast
import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from scripts.public_portfolio_dashboard import (
    FACTOR_LABELS,
    _holdings_rows,
    format_krw,
    format_pct,
    load_snapshot,
    render_dashboard,
    snapshot_is_stale,
)


KST = ZoneInfo("Asia/Seoul")


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _sample_snapshot() -> dict:
    return {
        "schema_version": 1,
        "generated_at": "2026-05-12T09:00:00+09:00",
        "source": {"dashboard_calls_kis": False},
        "summary": {
            "holding_count": 1,
            "total_market_value": 720000,
            "total_cost": 700000,
            "total_profit_loss": 20000,
            "total_profit_loss_rate": 2.86,
        },
        "positions": [
            {
                "ticker": "005930",
                "name": "Samsung Electronics",
                "qty": 10,
                "avg_price": 70000,
                "current_price": 72000,
                "market_value": 720000,
                "profit_loss": 20000,
                "profit_loss_rate": 2.86,
                "rationale": {
                    "order_reason": "target allocation buy",
                    "rank": 1,
                    "total_score": 1.2345,
                    "factor_scores": {"quality": 0.2, "momentum": 0.3},
                    "market_context": {
                        "quality": {"roe": 0.12},
                        "investor_flow": {"foreign_net_buy": 1000000.0},
                    },
                    "signals": [
                        {
                            "source": "busanstock",
                            "detail": "TP up",
                            "raw_score": 1.0,
                        }
                    ],
                },
            }
        ],
        "warnings": ["missing_rationale:000660"],
    }


def test_format_helpers_render_public_values() -> None:
    assert format_krw(1234567) == "1,234,567 KRW"
    assert format_krw(None) == "-"
    assert format_pct(2.864) == "2.86%"
    assert format_pct(None) == "-"


def test_public_dashboard_korean_labels_are_valid_utf8_text() -> None:
    assert FACTOR_LABELS == {
        "value": "Value · 가치",
        "quality": "Quality · 품질",
        "momentum": "Momentum · 모멘텀",
        "yield": "Yield · 배당",
        "telegram": "Telegram",
        "busanstock": "Busanstock",
        "investor_flow": "Flow · 수급",
        "research_report": "Research",
    }

    row = _holdings_rows(_sample_snapshot()["positions"])[0]

    assert list(row) == [
        "종목코드",
        "종목명",
        "수량",
        "평균단가",
        "현재가",
        "평가액",
        "평가손익",
        "수익률",
    ]


def test_load_snapshot_reports_missing_file(tmp_path: Path) -> None:
    result = load_snapshot(tmp_path / "missing.json")

    assert result["status"] == "missing"
    assert "snapshot" not in result


def test_load_snapshot_reports_malformed_json(tmp_path: Path) -> None:
    path = tmp_path / "public_portfolio_snapshot.json"
    path.write_text("{", encoding="utf-8")

    result = load_snapshot(path)

    assert result["status"] == "invalid"
    assert result["error"]


def test_load_snapshot_returns_valid_payload(tmp_path: Path) -> None:
    path = tmp_path / "public_portfolio_snapshot.json"
    payload = _sample_snapshot()
    _write_json(path, payload)

    result = load_snapshot(path)

    assert result == {"status": "ok", "snapshot": payload}


def test_snapshot_is_stale_uses_generated_timestamp_age() -> None:
    snapshot = {"generated_at": "2026-05-12T09:00:00+09:00"}

    assert (
        snapshot_is_stale(
            snapshot,
            now=datetime(2026, 5, 13, 8, 0, tzinfo=KST),
            max_age_hours=24,
        )
        is False
    )
    assert (
        snapshot_is_stale(
            snapshot,
            now=datetime(2026, 5, 13, 10, 0, tzinfo=KST),
            max_age_hours=24,
        )
        is True
    )


@pytest.mark.parametrize("snapshot", [{}, {"generated_at": "not-a-date"}])
def test_snapshot_is_stale_treats_missing_or_invalid_timestamp_as_stale(
    snapshot: dict,
) -> None:
    assert snapshot_is_stale(snapshot, now=datetime(2026, 5, 12, tzinfo=KST)) is True


def test_dashboard_module_does_not_import_trading_or_kis_helpers() -> None:
    source = Path("scripts/public_portfolio_dashboard.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden = {"KisClient", "TradingEngine", "execute_rebalance"}

    imported_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported_names.update(alias.name for alias in node.names)
            if node.module:
                imported_names.add(node.module)
        elif isinstance(node, ast.Import):
            imported_names.update(alias.name for alias in node.names)

    assert forbidden.isdisjoint(imported_names)


def test_render_dashboard_shows_read_only_summary_positions_and_warnings(monkeypatch):
    calls: list[tuple[str, tuple, dict]] = []

    class FakeColumn:
        def __enter__(self):
            calls.append(("column_enter", (), {}))
            return self

        def __exit__(self, exc_type, exc, tb):
            calls.append(("column_exit", (), {}))
            return False

        def __getattr__(self, name):
            def _inner(*args, **kwargs):
                calls.append((name, args, kwargs))
            return _inner

    class FakeExpander:
        def __enter__(self):
            calls.append(("expander_enter", (), {}))
            return self

        def __exit__(self, exc_type, exc, tb):
            calls.append(("expander_exit", (), {}))
            return False

    def record(name):
        def _inner(*args, **kwargs):
            calls.append((name, args, kwargs))
            if name == "columns":
                count = len(args[0]) if isinstance(args[0], list) else args[0]
                return [FakeColumn() for _ in range(count)]
            if name == "expander":
                return FakeExpander()
            return None

        return _inner

    fake_streamlit = SimpleNamespace(
        set_page_config=record("set_page_config"),
        title=record("title"),
        caption=record("caption"),
        success=record("success"),
        warning=record("warning"),
        metric=record("metric"),
        columns=record("columns"),
        subheader=record("subheader"),
        dataframe=record("dataframe"),
        expander=record("expander"),
        markdown=record("markdown"),
        json=record("json"),
        plotly_chart=record("plotly_chart"),
    )
    monkeypatch.setitem(__import__("sys").modules, "streamlit", fake_streamlit)

    render_dashboard(_sample_snapshot())

    rendered_text = "\n".join(str(arg) for _, args, _ in calls for arg in args)
    assert "Public Portfolio Dashboard" in rendered_text
    assert "Read-only snapshot" in rendered_text
    assert "2026-05-12T09:00:00+09:00" in rendered_text
    assert "missing_rationale:000660" in rendered_text
    assert "htable" in rendered_text
    assert "Equity Curve" in rendered_text
    assert any("target allocation buy" in str(args) for _, args, _ in calls)
    assert "ROE" in rendered_text
    assert "Investor Flow" in rendered_text
