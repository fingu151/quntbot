from datetime import date

from src.data.database import create_tables, get_engine, session_scope
from src.data.repositories import upsert_daily_prices, upsert_investor_flows


def test_run_reports_ready_investor_flow_scores(capsys):
    import scripts.smoke_test_investor_flows as smoke

    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    with session_scope(engine) as session:
        upsert_daily_prices(
            session,
            [
                {
                    "ticker": "005930",
                    "date": date(2026, 5, 11),
                    "close": 100,
                    "trading_value": 10_000_000_000,
                },
                {
                    "ticker": "000660",
                    "date": date(2026, 5, 11),
                    "close": 100,
                    "trading_value": 10_000_000_000,
                },
            ],
        )
        upsert_investor_flows(
            session,
            [
                {
                    "ticker": "005930",
                    "date": date(2026, 5, 11),
                    "individual_net_buy": 800_000_000,
                    "foreign_net_buy": -400_000_000,
                    "institution_net_buy": -300_000_000,
                },
                {
                    "ticker": "000660",
                    "date": date(2026, 5, 11),
                    "individual_net_buy": -500_000_000,
                    "foreign_net_buy": 300_000_000,
                    "institution_net_buy": 200_000_000,
                },
            ],
        )

    result = smoke.run(
        smoke.parse_args(["--as-of-date", "2026-05-11"]),
        engine_factory=lambda database_url=None: engine,
    )

    output = capsys.readouterr().out
    assert result == 0
    assert "investor_flow_rows_total=2" in output
    assert "latest_investor_flow_date=2026-05-11" in output
    assert "latest_investor_flow_count=2" in output
    assert "investor_flow_scored_count=2" in output
    assert "retail_only_penalty_count=1" in output
    assert "smart_money_positive_count=1" in output
    assert "orders_submitted=0" in output


def test_run_fails_when_investor_flow_rows_are_missing(capsys):
    import scripts.smoke_test_investor_flows as smoke

    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)

    result = smoke.run(
        smoke.parse_args(["--as-of-date", "2026-05-11"]),
        engine_factory=lambda database_url=None: engine,
    )

    output = capsys.readouterr().out
    assert result == 1
    assert "investor_flow_rows_total=0" in output
    assert "latest_investor_flow_date=none" in output
    assert "latest_investor_flow_count=0" in output
    assert "investor_flow_scored_count=0" in output
    assert "orders_submitted=0" in output
