from datetime import date
import json
from pathlib import Path
from unittest.mock import MagicMock

from src.data.database import create_tables, get_engine, session_scope
from src.data.repositories import upsert_daily_prices, upsert_market_index_prices
from src.factors.models import FactorScore


def _score(ticker: str, rank: int) -> FactorScore:
    return FactorScore(
        ticker=ticker,
        name=f"Stock {ticker}",
        market="KOSPI",
        as_of_date=date(2026, 5, 8),
        value_score=1.0,
        quality_score=1.0,
        momentum_score=1.0,
        yield_score=1.0,
        technical_score=0.0,
        auxiliary_score=0.0,
        total_score=10.0 - rank,
        rank=rank,
    )


def _client() -> MagicMock:
    client = MagicMock()
    client.get_holdings.return_value = [
        {
            "ticker": "OLD",
            "name": "Old Holding",
            "qty": 3,
            "avg_price": 10000,
            "current_price": 12000,
            "eval_profit_loss": 6000,
            "profit_loss_rate": 20.0,
        }
    ]
    client.get_balance.return_value = {
        "rt_cd": "0",
        "output1": [
            {
                "pdno": "OLD",
                "prdt_name": "Old Holding",
                "hldg_qty": "3",
                "pchs_avg_pric": "10000",
                "prpr": "12000",
                "evlu_pfls_amt": "6000",
                "evlu_pfls_rt": "20.0",
            }
        ],
        "output2": [{"dnca_tot_amt": "100000"}],
    }
    client.get_current_price.return_value = {
        "rt_cd": "0",
        "output": {"stck_prpr": "10000"},
    }
    return client


def _write_exit_state(path: Path, *, ticker: str = "OLD", entry_date: str = "2026-05-06") -> None:
    path.write_text(
        json.dumps(
            {
                ticker: {
                    "ticker": ticker,
                    "entry_price": 10000,
                    "original_qty": 3,
                    "entry_date": entry_date,
                    "last_updated": f"{entry_date}T00:00:00+00:00",
                }
            }
        ),
        encoding="utf-8",
    )


def test_parse_args_accepts_dry_run_options():
    import scripts.dry_run_rebalance as dry_run

    args = dry_run.parse_args([
        "--as-of-date",
        "2026-05-08",
        "--top-n",
        "1",
        "--output-md",
        "report.md",
        "--output-json",
        "report.json",
    ])

    assert args.as_of_date == date(2026, 5, 8)
    assert args.top_n == 1
    assert args.output_md == Path("report.md")
    assert args.output_json == Path("report.json")


def test_parse_args_accepts_latest_db_price_fallback():
    import scripts.dry_run_rebalance as dry_run

    args = dry_run.parse_args([
        "--price-fallback",
        "latest-db",
        "--quote-retries",
        "2",
        "--quote-delay-sec",
        "0.25",
    ])

    assert args.price_fallback == "latest-db"
    assert args.quote_retries == 2
    assert args.quote_delay_sec == 0.25


def test_run_prints_and_writes_rebalance_report_without_orders(tmp_path, capsys):
    import scripts.dry_run_rebalance as dry_run

    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    with session_scope(engine) as session:
        upsert_daily_prices(
            session,
            [
                {"ticker": "OLD", "date": date(2026, 5, 7), "close": 12000},
                {"ticker": "OLD", "date": date(2026, 5, 8), "close": 12000},
            ],
        )
    client = _client()
    report_path = tmp_path / "dry_run.md"
    exit_state_path = tmp_path / "exit_state.json"
    _write_exit_state(exit_state_path)
    args = dry_run.parse_args([
        "--as-of-date",
        "2026-05-08",
        "--top-n",
        "1",
        "--output-md",
        str(report_path),
        "--exit-state-path",
        str(exit_state_path),
    ])

    result = dry_run.run(
        args,
        db_engine=engine,
        client_factory=MagicMock(return_value=client),
        score_func=MagicMock(return_value=[_score("NEW", 1)]),
    )

    output = capsys.readouterr().out
    report = report_path.read_text(encoding="utf-8")

    assert result == 0
    assert "dry_run=true" in output
    assert "target_count=1" in output
    assert "SELL,OLD,3" in output
    assert "BUY,NEW,2" in output
    assert "NEW" in report
    assert "OLD" in report
    assert "| 1 | NEW | Stock NEW | 9.0000 | 15.00% |" in report
    client.get_balance.assert_called_once()
    client.get_holdings.assert_not_called()
    client.place_order.assert_not_called()


def test_run_allows_rebalance_sell_when_entry_state_is_missing(capsys):
    import scripts.dry_run_rebalance as dry_run

    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    client = _client()
    args = dry_run.parse_args([
        "--as-of-date",
        "2026-05-08",
        "--top-n",
        "1",
        "--exit-state-path",
        str(Path("missing_exit_state.json")),
    ])

    result = dry_run.run(
        args,
        db_engine=engine,
        client_factory=MagicMock(return_value=client),
        score_func=MagicMock(return_value=[_score("NEW", 1)]),
    )

    output = capsys.readouterr().out

    assert result == 0
    assert "SELL,OLD,3" in output
    client.place_order.assert_not_called()


def test_run_allows_rebalance_sell_on_recent_entry(tmp_path, capsys):
    import scripts.dry_run_rebalance as dry_run

    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    with session_scope(engine) as session:
        upsert_daily_prices(
            session,
            [
                {"ticker": "OLD", "date": date(2026, 5, 8), "close": 12000},
            ],
        )
    client = _client()
    exit_state_path = tmp_path / "exit_state.json"
    _write_exit_state(exit_state_path, entry_date="2026-05-07")
    args = dry_run.parse_args([
        "--as-of-date",
        "2026-05-08",
        "--top-n",
        "1",
        "--exit-state-path",
        str(exit_state_path),
    ])

    result = dry_run.run(
        args,
        db_engine=engine,
        client_factory=MagicMock(return_value=client),
        score_func=MagicMock(return_value=[_score("NEW", 1)]),
    )

    output = capsys.readouterr().out

    assert result == 0
    assert "SELL,OLD,3" in output
    client.place_order.assert_not_called()


def test_parse_holdings_accepts_decimal_numeric_strings():
    import scripts.dry_run_rebalance as dry_run

    holdings = dry_run._parse_holdings({
        "output1": [
            {
                "pdno": "005930",
                "prdt_name": "?쇱꽦?꾩옄",
                "hldg_qty": "5.0000",
                "pchs_avg_pric": "168027.5860",
                "prpr": "170100.0000",
                "evlu_pfls_amt": "10362.0700",
                "evlu_pfls_rt": "1.23",
            }
        ]
    })

    assert holdings == [
        {
            "ticker": "005930",
            "name": "?쇱꽦?꾩옄",
            "qty": 5,
            "avg_price": 168027,
            "current_price": 170100,
            "eval_profit_loss": 10362,
            "profit_loss_rate": 1.23,
        }
    ]


def test_run_returns_error_when_no_factor_scores(capsys):
    import scripts.dry_run_rebalance as dry_run

    args = dry_run.parse_args(["--as-of-date", "2026-05-08"])

    result = dry_run.run(
        args,
        db_engine="db-engine",
        client_factory=MagicMock(return_value=_client()),
        score_func=MagicMock(return_value=[]),
        create_tables_func=MagicMock(),
    )

    assert result == 1
    assert "No factor scores found" in capsys.readouterr().out


def test_run_returns_error_when_kis_lookup_fails_without_placing_orders(capsys):
    import scripts.dry_run_rebalance as dry_run

    client = _client()
    client.get_balance.side_effect = RuntimeError("temporary KIS failure")
    args = dry_run.parse_args(["--as-of-date", "2026-05-08"])

    result = dry_run.run(
        args,
        db_engine="db-engine",
        client_factory=MagicMock(return_value=client),
        score_func=MagicMock(return_value=[_score("NEW", 1)]),
        create_tables_func=MagicMock(),
    )

    assert result == 1
    assert "KIS lookup failed" in capsys.readouterr().out
    client.place_order.assert_not_called()


def test_run_skips_buy_when_current_price_lookup_fails(capsys):
    import scripts.dry_run_rebalance as dry_run

    client = _client()
    client.get_current_price.side_effect = RuntimeError("quote server failed")
    args = dry_run.parse_args(["--as-of-date", "2026-05-08"])

    result = dry_run.run(
        args,
        db_engine="db-engine",
        client_factory=MagicMock(return_value=client),
        score_func=MagicMock(return_value=[_score("NEW", 1)]),
        create_tables_func=MagicMock(),
    )

    output = capsys.readouterr().out

    assert result == 0
    assert "price_lookup_failed,NEW" in output
    assert "BUY,NEW" not in output
    client.place_order.assert_not_called()


def test_run_uses_latest_db_close_when_quote_fails_and_fallback_enabled(capsys):
    import scripts.dry_run_rebalance as dry_run

    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    with session_scope(engine) as session:
        upsert_daily_prices(
            session,
            [
                {"ticker": "NEW", "date": date(2026, 5, 7), "close": 20000},
                {"ticker": "NEW", "date": date(2026, 5, 8), "close": 10000},
            ],
        )

    client = _client()
    client.get_current_price.side_effect = RuntimeError("quote server failed")
    args = dry_run.parse_args(["--as-of-date", "2026-05-08", "--price-fallback", "latest-db"])

    result = dry_run.run(
        args,
        db_engine=engine,
        client_factory=MagicMock(return_value=client),
        score_func=MagicMock(return_value=[_score("NEW", 1)]),
    )

    output = capsys.readouterr().out

    assert result == 0
    assert "price_fallback,NEW,10000" in output
    assert "SELL,OLD,3" in output
    assert "BUY,NEW,2" in output
    client.place_order.assert_not_called()


def test_run_retries_quote_lookup_before_fallback(capsys):
    import scripts.dry_run_rebalance as dry_run

    client = _client()
    client.get_current_price.side_effect = [
        RuntimeError("temporary quote failure"),
        {"rt_cd": "0", "output": {"stck_prpr": "10000"}},
    ]
    sleeper = MagicMock()
    args = dry_run.parse_args([
        "--as-of-date",
        "2026-05-08",
        "--quote-retries",
        "1",
        "--quote-delay-sec",
        "0.25",
    ])

    result = dry_run.run(
        args,
        db_engine="db-engine",
        client_factory=MagicMock(return_value=client),
        score_func=MagicMock(return_value=[_score("NEW", 1)]),
        create_tables_func=MagicMock(),
        sleeper=sleeper,
    )

    output = capsys.readouterr().out

    assert result == 0
    assert "SELL,OLD,3" in output
    assert "BUY,NEW,2" in output
    assert "price_lookup_failed,NEW" not in output
    assert client.get_current_price.call_count == 2
    sleeper.assert_called_once_with(0.25)


def test_run_records_quote_retry_summary_in_json_and_markdown(tmp_path):
    import scripts.dry_run_rebalance as dry_run

    client = _client()
    client.get_current_price.side_effect = [
        RuntimeError("temporary quote failure"),
        {"rt_cd": "0", "output": {"stck_prpr": "10000"}},
        RuntimeError("quote server failed"),
        RuntimeError("quote server still failed"),
    ]
    report_path = tmp_path / "dry_run.json"
    md_path = tmp_path / "dry_run.md"
    args = dry_run.parse_args([
        "--as-of-date",
        "2026-05-08",
        "--top-n",
        "2",
        "--quote-retries",
        "1",
        "--output-json",
        str(report_path),
        "--output-md",
        str(md_path),
    ])

    result = dry_run.run(
        args,
        db_engine="db-engine",
        client_factory=MagicMock(return_value=client),
        score_func=MagicMock(return_value=[_score("NEW", 1), _score("MISS", 2)]),
        create_tables_func=MagicMock(),
        sleeper=MagicMock(),
    )

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    report = md_path.read_text(encoding="utf-8")

    assert result == 0
    assert payload["price_retry_success_count"] == 1
    assert payload["price_retry_failed_count"] == 1
    assert payload["price_retry_attempts"] == [
        {
            "ticker": "NEW",
            "attempt_count": 2,
            "status": "success",
            "last_error": "temporary quote failure",
        },
        {
            "ticker": "MISS",
            "attempt_count": 2,
            "status": "failed",
            "last_error": "quote server still failed",
        },
    ]
    assert "## Price Retry Summary" in report
    assert "| NEW | success | 2 | temporary quote failure |" in report
    assert "| MISS | failed | 2 | quote server still failed |" in report


def test_run_records_skipped_buy_when_current_price_gap_is_too_large(tmp_path, capsys):
    import scripts.dry_run_rebalance as dry_run

    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    with session_scope(engine) as session:
        upsert_daily_prices(
            session,
            [
                {"ticker": "NEW", "date": date(2026, 5, 7), "close": 10000},
            ],
        )

    client = _client()
    client.get_balance.return_value = {
        "rt_cd": "0",
        "output1": [],
        "output2": [{"dnca_tot_amt": "100000"}],
    }
    client.get_current_price.return_value = {
        "rt_cd": "0",
        "output": {"stck_prpr": "12100"},
    }
    report_path = tmp_path / "dry_run.json"
    md_path = tmp_path / "dry_run.md"
    args = dry_run.parse_args([
        "--as-of-date",
        "2026-05-08",
        "--top-n",
        "1",
        "--output-json",
        str(report_path),
        "--output-md",
        str(md_path),
    ])

    result = dry_run.run(
        args,
        db_engine=engine,
        client_factory=MagicMock(return_value=client),
        score_func=MagicMock(return_value=[_score("NEW", 1)]),
    )

    output = capsys.readouterr().out
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    report = md_path.read_text(encoding="utf-8")

    assert result == 0
    assert "BUY,NEW" not in output
    assert payload["skipped_buy_count"] == 1
    assert payload["skipped_buys"] == [
        {
            "ticker": "NEW",
            "reason": "gap_move_too_large",
            "execution_price": 12100,
            "previous_close": 10000,
            "gap_pct": 0.21,
            "threshold_pct": 0.2,
        }
    ]
    assert "## Skipped Buy Candidates" in report
    assert "| NEW | gap_move_too_large | 12,100 | 10,000 | 21.00% | 20.00% |" in report


def test_run_writes_machine_readable_json_report(tmp_path):
    import scripts.dry_run_rebalance as dry_run

    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    with session_scope(engine) as session:
        upsert_daily_prices(
            session,
            [
                {"ticker": "OLD", "date": date(2026, 5, 7), "close": 12000},
                {"ticker": "OLD", "date": date(2026, 5, 8), "close": 12000},
            ],
        )
    client = _client()
    report_path = tmp_path / "dry_run.json"
    exit_state_path = tmp_path / "exit_state.json"
    _write_exit_state(exit_state_path)
    args = dry_run.parse_args([
        "--as-of-date",
        "2026-05-08",
        "--top-n",
        "1",
        "--output-json",
        str(report_path),
        "--exit-state-path",
        str(exit_state_path),
    ])

    result = dry_run.run(
        args,
        db_engine=engine,
        client_factory=MagicMock(return_value=client),
        score_func=MagicMock(return_value=[_score("NEW", 1)]),
    )

    payload = json.loads(report_path.read_text(encoding="utf-8"))

    assert result == 0
    assert payload["dry_run"] is True
    assert payload["as_of_date"] == "2026-05-08"
    assert payload["price_fallback_count"] == 0
    assert payload["price_lookup_failed_count"] == 0
    assert payload["skipped_buy_count"] == 0
    assert payload["skipped_buys"] == []
    assert payload["orders"][0]["side"] == "SELL"
    assert payload["orders"][1]["side"] == "BUY"
    assert payload["targets"][0]["target_weight"] == 0.15
    client.place_order.assert_not_called()


def test_run_scales_buy_weights_after_positive_us_market_session(tmp_path):
    import scripts.dry_run_rebalance as dry_run

    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    with session_scope(engine) as session:
        upsert_market_index_prices(
            session,
            [
                {"symbol": "NASDAQ", "date": date(2026, 5, 6), "close": 100.0},
                {"symbol": "NASDAQ", "date": date(2026, 5, 7), "close": 102.0},
                {"symbol": "SP500", "date": date(2026, 5, 6), "close": 100.0},
                {"symbol": "SP500", "date": date(2026, 5, 7), "close": 101.6},
                {"symbol": "DOW", "date": date(2026, 5, 6), "close": 100.0},
                {"symbol": "DOW", "date": date(2026, 5, 7), "close": 101.4},
            ],
        )
    client = _client()
    client.get_balance.return_value["output1"] = []
    report_path = tmp_path / "dry_run.json"
    args = dry_run.parse_args([
        "--as-of-date",
        "2026-05-08",
        "--top-n",
        "1",
        "--output-json",
        str(report_path),
    ])

    result = dry_run.run(
        args,
        db_engine=engine,
        client_factory=MagicMock(return_value=client),
        score_func=MagicMock(return_value=[_score("NEW", 1)]),
    )

    payload = json.loads(report_path.read_text(encoding="utf-8"))

    assert result == 0
    assert payload["us_market_risk"]["status"] == "risk_on"
    assert payload["us_market_risk"]["buy_budget_multiplier"] == 1.2
    assert payload["targets"][0]["target_weight"] == 0.18


def test_run_scales_buy_weights_after_bond_yields_rise(tmp_path):
    import scripts.dry_run_rebalance as dry_run

    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    with session_scope(engine) as session:
        upsert_market_index_prices(
            session,
            [
                {"symbol": "KR10Y", "date": date(2026, 5, 6), "close": 3.40},
                {"symbol": "KR10Y", "date": date(2026, 5, 7), "close": 3.57},
                {"symbol": "US10Y", "date": date(2026, 5, 6), "close": 4.30},
                {"symbol": "US10Y", "date": date(2026, 5, 7), "close": 4.47},
            ],
        )
    client = _client()
    client.get_balance.return_value["output1"] = []
    report_path = tmp_path / "dry_run.json"
    args = dry_run.parse_args([
        "--as-of-date",
        "2026-05-08",
        "--top-n",
        "1",
        "--output-json",
        str(report_path),
    ])

    result = dry_run.run(
        args,
        db_engine=engine,
        client_factory=MagicMock(return_value=client),
        score_func=MagicMock(return_value=[_score("NEW", 1)]),
    )

    payload = json.loads(report_path.read_text(encoding="utf-8"))

    assert result == 0
    assert payload["bond_yield_risk"]["status"] == "risk_off"
    assert payload["bond_yield_risk"]["buy_budget_multiplier"] == 0.7
    assert payload["combined_buy_budget_multiplier"] == 0.7
    assert payload["targets"][0]["target_weight"] == 0.105

