from pathlib import Path

from src.trading.exit_state import ExitStateStore


def test_exit_state_store_round_trips_position_state(tmp_path: Path):
    store = ExitStateStore(tmp_path / "exit_state.json")

    state = store.get_or_create(
        ticker="005930",
        entry_price=100_000,
        qty=10,
        entry_date="2026-05-19",
    )
    state.profit_take_done = True
    state.trailing_qty = 2
    state.breakeven_qty = 3
    state.peak_price = 125_000
    store.save_position(state)

    loaded = store.load()["005930"]
    assert loaded.profit_take_done is True
    assert loaded.trailing_qty == 2
    assert loaded.breakeven_qty == 3
    assert loaded.peak_price == 125_000
