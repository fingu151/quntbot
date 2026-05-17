from __future__ import annotations

from argparse import Namespace
from datetime import date

import pytest

from scripts.compare_research_report_factor_impact import (
    FactorImpactRow,
    compare_factor_scores,
    format_factor_impact_markdown,
    parse_args,
)
from src.factors.models import FactorScore


def _score(
    ticker: str,
    *,
    total_score: float,
    rank: int,
    research_report_score: float = 0.0,
) -> FactorScore:
    return FactorScore(
        ticker=ticker,
        name=f"{ticker} Name",
        market="KOSPI",
        as_of_date=date(2026, 5, 14),
        value_score=1.0,
        quality_score=1.0,
        momentum_score=1.0,
        yield_score=1.0,
        telegram_score=0.0,
        total_score=total_score,
        rank=rank,
        busanstock_score=0.0,
        investor_flow_score=0.0,
        research_report_score=research_report_score,
    )


def test_compare_factor_scores_keeps_only_research_impacted_tickers():
    without_research = [
        _score("AAA", total_score=80.0, rank=1),
        _score("BBB", total_score=70.0, rank=2),
    ]
    with_research = [
        _score("BBB", total_score=72.5, rank=1, research_report_score=1.0),
        _score("AAA", total_score=80.0, rank=2),
    ]

    rows = compare_factor_scores(without_research, with_research)

    assert rows == [
        FactorImpactRow(
            ticker="BBB",
            name="BBB Name",
            before_rank=2,
            after_rank=1,
            rank_delta=1,
            before_score=70.0,
            after_score=72.5,
            score_delta=2.5,
            research_report_score=1.0,
        )
    ]


def test_format_factor_impact_markdown_includes_read_only_guard():
    markdown = format_factor_impact_markdown(
        [
            FactorImpactRow(
                ticker="AAA",
                name="Pipe | Name",
                before_rank=3,
                after_rank=2,
                rank_delta=1,
                before_score=55.0,
                after_score=56.25,
                score_delta=1.25,
                research_report_score=0.8,
            )
        ],
        as_of_date=date(2026, 5, 14),
        source="mirae_asset",
        broker=None,
        research_start_date=date(2026, 1, 1),
        score_count=10,
        research_signal_count=1,
        top_n=20,
        title="Custom Research Factor Impact",
    )

    assert markdown.startswith("# Custom Research Factor Impact")
    assert "- orders_submitted: `0`" in markdown
    assert "- research_start_date: `2026-01-01`" in markdown
    assert "Pipe \\| Name" in markdown
    assert "| AAA |" in markdown
    assert "+1.2500" in markdown


def test_parse_args_rejects_non_positive_top_n():
    with pytest.raises(SystemExit):
        parse_args(["--top-n", "0"])
