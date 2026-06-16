"""Persistent PAPER exit state for staged position exits."""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger


@dataclass
class PositionExitState:
    ticker: str
    entry_price: float
    original_qty: int
    entry_date: str
    last_updated: str
    profit_take_done: bool = False
    trailing_qty: int = 0
    breakeven_qty: int = 0
    peak_price: float = 0.0

    @property
    def qty(self) -> int:
        return self.original_qty


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _entry_price_materially_changed(stored: float, current: float) -> bool:
    return not math.isclose(stored, current, rel_tol=1e-6, abs_tol=0.01)


class ExitStateStore:
    """JSON-backed position exit state store."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> dict[str, PositionExitState]:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning(f"exit state load failed: {exc}")
            return {}

        states: dict[str, PositionExitState] = {}
        for ticker, payload in raw.items():
            if not isinstance(payload, dict):
                continue
            try:
                original_qty = payload.get("original_qty", payload.get("qty"))
                states[str(ticker)] = PositionExitState(
                    ticker=str(payload.get("ticker") or ticker),
                    entry_price=float(payload["entry_price"]),
                    original_qty=int(original_qty),
                    entry_date=str(payload["entry_date"]),
                    last_updated=str(
                        payload.get("last_updated")
                        or payload.get("entry_date")
                        or ""
                    ),
                    profit_take_done=bool(payload.get("profit_take_done", False)),
                    trailing_qty=int(payload.get("trailing_qty", 0) or 0),
                    breakeven_qty=int(payload.get("breakeven_qty", 0) or 0),
                    peak_price=float(payload.get("peak_price", 0.0) or 0.0),
                )
            except (KeyError, TypeError, ValueError) as exc:
                logger.warning(
                    f"invalid exit state skipped: ticker={ticker}, error={exc}"
                )
        return states

    def save(self, states: dict[str, PositionExitState]) -> None:
        payload: dict[str, dict[str, Any]] = {
            ticker: asdict(state) for ticker, state in sorted(states.items())
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def get_or_create(
        self,
        *,
        ticker: str,
        entry_price: float,
        qty: int,
        entry_date: str,
    ) -> PositionExitState:
        states = self.load()
        state = states.get(ticker)
        if state is not None:
            if (
                not _entry_price_materially_changed(
                    state.entry_price, float(entry_price)
                )
                and int(qty) <= state.original_qty
            ):
                return state

            logger.info(
                f"resetting exit state for rebuilt position: ticker={ticker}, "
                f"stored_entry={state.entry_price}, current_entry={float(entry_price)}, "
                f"stored_original_qty={state.original_qty}, current_qty={int(qty)}"
            )

        state = PositionExitState(
            ticker=ticker,
            entry_price=float(entry_price),
            original_qty=int(qty),
            entry_date=entry_date,
            last_updated=_utc_now(),
            peak_price=float(entry_price),
        )
        states[ticker] = state
        self.save(states)
        return state

    def save_position(self, state: PositionExitState) -> None:
        states = self.load()
        state.last_updated = _utc_now()
        states[state.ticker] = state
        self.save(states)

    def delete(self, ticker: str) -> None:
        states = self.load()
        if ticker not in states:
            return
        del states[ticker]
        self.save(states)

    def prune(self, held_tickers: set[str]) -> None:
        states = self.load()
        pruned = {
            ticker: state
            for ticker, state in states.items()
            if ticker in held_tickers
        }
        if pruned != states:
            self.save(pruned)
