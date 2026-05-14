from datetime import date
from types import SimpleNamespace

from src.data.database import create_tables, get_engine, session_scope
from src.data.repositories import upsert_telegram_signals


def _enabled_config():
    return SimpleNamespace(
        enabled=True,
        api_id=12345,
        api_hash="secret_hash",
        channel="secret_channel",
    )


def _disabled_config():
    return SimpleNamespace(
        enabled=False,
        api_id=0,
        api_hash="",
        channel="",
    )


def test_run_blocks_when_telegram_signal_config_is_missing(capsys):
    import scripts.smoke_test_telegram_signals as smoke

    result = smoke.run(smoke.parse_args(["--as-of-date", "2026-05-06"]), config=_disabled_config())

    output = capsys.readouterr().out
    assert result == 1
    assert "telegram_signal_enabled=false" in output
    assert "missing=TELEGRAM_API_ID,TELEGRAM_API_HASH,TELEGRAM_SIGNAL_CHANNEL" in output


def test_run_fetches_and_reports_signal_rows_without_printing_secrets(capsys):
    import scripts.smoke_test_telegram_signals as smoke

    engine = get_engine("sqlite:///:memory:")

    def engine_factory(database_url=None):
        return engine

    def fake_fetcher(engine, as_of_date):
        create_tables(engine)
        with session_scope(engine) as session:
            return upsert_telegram_signals(
                session,
                [
                    {
                        "message_date": as_of_date,
                        "ticker": "005930",
                        "signal_type": "positive",
                        "star_rating": 3,
                        "raw_score": 3.0,
                        "target_price": 90000.0,
                        "message_id": 77,
                    },
                    {
                        "message_date": as_of_date,
                        "ticker": "035420",
                        "signal_type": "warning",
                        "star_rating": 0,
                        "raw_score": -1.0,
                        "target_price": None,
                        "message_id": 77,
                    },
                ],
            )

    result = smoke.run(
        smoke.parse_args(["--as-of-date", "2026-05-06"]),
        config=_enabled_config(),
        engine_factory=engine_factory,
        signal_fetcher=fake_fetcher,
    )

    output = capsys.readouterr().out
    assert result == 0
    assert "telegram_signal_enabled=true" in output
    assert "signal_rows_stored=2" in output
    assert "latest_signal_date=2026-05-06" in output
    assert "latest_signal_count=2" in output
    assert "orders_submitted=0" in output
    assert "secret_hash" not in output
    assert "secret_channel" not in output
