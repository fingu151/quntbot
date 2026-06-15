import json
from datetime import date

from src.trading.rebalance_policy import (
    compute_rebalance_sell_eligible_tickers,
    load_rebalance_protected_tickers,
)


def test_compute_rebalance_sell_eligible_skips_profit_taken_protected_tickers():
    eligible = compute_rebalance_sell_eligible_tickers(
        holdings=[
            {"ticker": "005930", "qty": 7},
            {"ticker": "000660", "qty": 5},
            {"ticker": "035420", "qty": 3},
        ],
        buffer_tickers={"035420"},
        entry_dates={},
        db_engine=object(),
        as_of_date=date(2026, 6, 15),
        min_holding_trading_days=0,
        protected_tickers={"005930"},
    )

    assert eligible == ["000660"]


def test_load_rebalance_protected_tickers_returns_active_profit_taken_states(tmp_path):
    path = tmp_path / "exit_state.json"
    path.write_text(
        json.dumps(
            {
                "005930": {
                    "ticker": "005930",
                    "entry_price": 100_000,
                    "original_qty": 10,
                    "entry_date": "2026-05-19",
                    "profit_take_done": True,
                    "trailing_qty": 3,
                    "breakeven_qty": 4,
                    "peak_price": 130_000,
                    "last_updated": "2026-05-19T00:00:00+00:00",
                },
                "000660": {
                    "ticker": "000660",
                    "entry_price": 200_000,
                    "original_qty": 5,
                    "entry_date": "2026-05-19",
                    "profit_take_done": True,
                    "trailing_qty": 0,
                    "breakeven_qty": 0,
                    "peak_price": 230_000,
                    "last_updated": "2026-05-19T00:00:00+00:00",
                },
                "035420": {
                    "ticker": "035420",
                    "entry_price": 180_000,
                    "original_qty": 3,
                    "entry_date": "2026-05-19",
                    "profit_take_done": False,
                    "trailing_qty": 0,
                    "breakeven_qty": 0,
                    "peak_price": 180_000,
                    "last_updated": "2026-05-19T00:00:00+00:00",
                },
            }
        ),
        encoding="utf-8",
    )

    assert load_rebalance_protected_tickers(path) == {"005930"}
