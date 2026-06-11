from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from datetime import date
from pathlib import Path
import sys
from typing import Any

import requests

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import MACRO_RISK
from src.data.database import create_tables, get_engine, session_scope
from src.data.repositories import upsert_macro_indicator_releases


MacroFetchFunction = Callable[[date, date, str], list[dict[str, Any]]]

FRED_SERIES = {
    "CPI": ("CPIAUCSL", "inflation", "index"),
    "CORE_CPI": ("CPILFESL", "inflation", "index"),
    "UNRATE": ("UNRATE", "labor", "pct"),
    "PAYEMS": ("PAYEMS", "labor", "thousand_persons"),
    "FEDFUNDS": ("FEDFUNDS", "rate_policy", "pct"),
}


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync US macro indicator releases.")
    parser.add_argument("--start-date", type=_parse_date, required=True)
    parser.add_argument("--end-date", type=_parse_date, required=True)
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--fred-api-key", default=MACRO_RISK.fred_api_key)
    args = parser.parse_args(argv)
    if args.start_date > args.end_date:
        parser.error("--start-date must be on or before --end-date")
    return args


def run(
    args: argparse.Namespace,
    *,
    fetcher: MacroFetchFunction | None = None,
) -> int:
    engine = get_engine(args.database_url)
    create_tables(engine)
    rows = (fetcher or fetch_fred_macro_indicators)(
        args.start_date,
        args.end_date,
        args.fred_api_key,
    )
    with session_scope(engine) as session:
        count = upsert_macro_indicator_releases(session, rows)
    print(f"Macro indicator sync complete: row_count={count}")
    return 0


def fetch_fred_macro_indicators(
    start_date: date,
    end_date: date,
    api_key: str,
) -> list[dict[str, Any]]:
    if not api_key:
        return []
    rows: list[dict[str, Any]] = []
    for indicator, (series_id, impact_rule, unit) in FRED_SERIES.items():
        url = "https://api.stlouisfed.org/fred/series/observations"
        params = {
            "series_id": series_id,
            "api_key": api_key,
            "file_type": "json",
            "observation_start": start_date.isoformat(),
            "observation_end": end_date.isoformat(),
            # ALFRED vintage params: without these the default realtime period is
            # "today", so every observation's realtime_start becomes the sync date
            # instead of the actual release date (duplicate rows + look-ahead bias).
            # output_type=4 returns the initial release only, whose realtime_start
            # is the original publication date.
            "realtime_start": "1776-07-04",
            "realtime_end": "9999-12-31",
            "output_type": "4",
        }
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        observations = response.json().get("observations") or []
        rows.extend(
            _fred_observations_to_rows(
                indicator=indicator,
                source_url=f"https://fred.stlouisfed.org/series/{series_id}",
                impact_rule=impact_rule,
                unit=unit,
                observations=observations,
            )
        )
    return rows


def _fred_observations_to_rows(
    *,
    indicator: str,
    source_url: str,
    impact_rule: str,
    unit: str,
    observations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    previous_value: float | None = None
    for observation in observations:
        value = _float_or_none(observation.get("value"))
        if value is None:
            continue
        period_date = date.fromisoformat(str(observation["date"]))
        release_date = date.fromisoformat(str(observation.get("realtime_start") or observation["date"]))
        rows.append(
            {
                "indicator": indicator,
                "period_date": period_date,
                "release_date": release_date,
                "value": value,
                "previous_value": previous_value,
                "unit": unit,
                "source": "fred",
                "source_url": source_url,
                "impact_rule": impact_rule,
                "importance": "high",
            }
        )
        previous_value = value
    return rows


def _float_or_none(value: Any) -> float | None:
    try:
        if value in (None, "."):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def main(argv: Sequence[str] | None = None) -> int:
    return run(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
