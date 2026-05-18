"""Persistent PAPER exit state for staged position exits."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from loguru import logger


@dataclass
class PositionExitState:
    ticker: str
    entry_price: float
    qty: int
    entry_date: str
    profit_take_done: bool = False
    trailing_qty: int = 0
    breakeven_qty: int = 0
    peak_price: float = 0.0


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
                states[str(ticker)] = PositionExitState(
                    ticker=str(payload.get("ticker") or ticker),
                    entry_price=float(payload["entry_price"]),
                    qty=int(payload["qty"]),
                    entry_date=str(payload["entry_date"]),
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
            return state

        state = PositionExitState(
            ticker=ticker,
            entry_price=float(entry_price),
            qty=int(qty),
            entry_date=entry_date,
            peak_price=float(entry_price),
        )
        states[ticker] = state
        self.save(states)
        return state

    def save_position(self, state: PositionExitState) -> None:
        states = self.load()
        states[state.ticker] = state
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
