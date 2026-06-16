import json
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
    assert loaded.original_qty == 10
    assert loaded.last_updated
    assert loaded.profit_take_done is True
    assert loaded.trailing_qty == 2
    assert loaded.breakeven_qty == 3
    assert loaded.peak_price == 125_000


def test_exit_state_store_loads_legacy_qty_field(tmp_path: Path):
    path = tmp_path / "exit_state.json"
    path.write_text(
        json.dumps(
            {
                "005930": {
                    "ticker": "005930",
                    "entry_price": 100_000,
                    "qty": 10,
                    "entry_date": "2026-05-19",
                    "profit_take_done": True,
                    "trailing_qty": 2,
                    "breakeven_qty": 3,
                    "peak_price": 125_000,
                }
            }
        ),
        encoding="utf-8",
    )

    loaded = ExitStateStore(path).load()["005930"]

    assert loaded.original_qty == 10
    assert loaded.profit_take_done is True


def test_save_position_refreshes_last_updated(tmp_path: Path):
    store = ExitStateStore(tmp_path / "exit_state.json")
    state = store.get_or_create(
        ticker="005930",
        entry_price=100_000,
        qty=10,
        entry_date="2026-05-19",
    )
    state.last_updated = "2026-05-19T00:00:00+00:00"

    store.save_position(state)

    assert store.load()["005930"].last_updated != "2026-05-19T00:00:00+00:00"


def test_delete_removes_position_state(tmp_path: Path):
    store = ExitStateStore(tmp_path / "exit_state.json")
    store.get_or_create(
        ticker="005930",
        entry_price=100_000,
        qty=10,
        entry_date="2026-05-19",
    )

    store.delete("005930")

    assert "005930" not in store.load()


def test_get_or_create_resets_stale_state_when_entry_price_changes(tmp_path: Path):
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

    rebuilt = store.get_or_create(
        ticker="005930",
        entry_price=110_000,
        qty=10,
        entry_date="2026-05-20",
    )

    assert rebuilt.entry_price == 110_000
    assert rebuilt.original_qty == 10
    assert rebuilt.entry_date == "2026-05-20"
    assert rebuilt.profit_take_done is False
    assert rebuilt.trailing_qty == 0
    assert rebuilt.breakeven_qty == 0
    assert rebuilt.peak_price == 110_000


def test_get_or_create_resets_stale_state_when_qty_is_rebuilt(tmp_path: Path):
    store = ExitStateStore(tmp_path / "exit_state.json")
    state = store.get_or_create(
        ticker="005930",
        entry_price=100_000,
        qty=5,
        entry_date="2026-05-19",
    )
    state.profit_take_done = True
    state.trailing_qty = 1
    state.breakeven_qty = 2
    state.peak_price = 125_000
    store.save_position(state)

    rebuilt = store.get_or_create(
        ticker="005930",
        entry_price=100_000,
        qty=10,
        entry_date="2026-05-20",
    )

    assert rebuilt.original_qty == 10
    assert rebuilt.profit_take_done is False
    assert rebuilt.trailing_qty == 0
    assert rebuilt.breakeven_qty == 0
    assert rebuilt.peak_price == 100_000


def test_get_or_create_preserves_state_when_qty_is_partially_reduced(tmp_path: Path):
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

    preserved = store.get_or_create(
        ticker="005930",
        entry_price=100_000,
        qty=5,
        entry_date="2026-05-20",
    )

    assert preserved.original_qty == 10
    assert preserved.entry_date == "2026-05-19"
    assert preserved.profit_take_done is True
    assert preserved.trailing_qty == 2
    assert preserved.breakeven_qty == 3
    assert preserved.peak_price == 125_000
