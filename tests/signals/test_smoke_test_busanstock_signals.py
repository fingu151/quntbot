from datetime import date

from src.data.database import create_tables, get_engine, session_scope
from src.data.repositories import upsert_stocks


_HTML = """
<html>
<head><title>트비 주식뉴스 어그리게이터 리포트 · 2026-05-09</title></head>
<body>
<p>매수 (1) 기아</p>
<p>기아 유진 17만→30만 ▲76%</p>
</body>
</html>
"""


def test_run_reports_busanstock_signal_rows(capsys):
    import scripts.smoke_test_busanstock_signals as smoke

    engine = get_engine("sqlite:///:memory:")
    create_tables(engine)
    with session_scope(engine) as session:
        upsert_stocks(session, [{"ticker": "000270", "name": "기아", "market": "KOSPI"}])

    result = smoke.run(
        smoke.parse_args(["--as-of-date", "2026-05-09"]),
        engine_factory=lambda database_url=None: engine,
        signal_fetcher=lambda engine, as_of_date: 2,
        latest_counter=lambda engine, as_of_date: (date(2026, 5, 9), 2),
    )

    output = capsys.readouterr().out
    assert result == 0
    assert "busanstock_signal_rows_stored=2" in output
    assert "latest_busanstock_signal_date=2026-05-09" in output
    assert "latest_busanstock_signal_count=2" in output
    assert "orders_submitted=0" in output
