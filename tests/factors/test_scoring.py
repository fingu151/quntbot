import pandas as pd

from src.factors.scoring import combine_scores, score_series


def test_score_series_gives_higher_score_to_lower_values_when_lower_is_better():
    values = pd.Series({"cheap": 5.0, "expensive": 20.0})

    scores = score_series(values, higher_is_better=False, method="zscore")

    assert scores["cheap"] > scores["expensive"]


def test_score_series_gives_higher_score_to_higher_values_when_higher_is_better():
    values = pd.Series({"winner": 0.30, "loser": -0.10})

    scores = score_series(values, higher_is_better=True, method="zscore")

    assert scores["winner"] > scores["loser"]


def test_score_series_returns_neutral_scores_for_constant_values():
    values = pd.Series({"a": 10.0, "b": 10.0, "c": 10.0})

    scores = score_series(values, higher_is_better=True, method="zscore")

    assert scores.to_dict() == {"a": 0.0, "b": 0.0, "c": 0.0}


def test_score_series_treats_non_positive_values_as_missing_when_requested():
    values = pd.Series({"valid": 10.0, "zero": 0.0, "negative": -3.0})

    scores = score_series(
        values,
        higher_is_better=False,
        method="zscore",
        require_positive=True,
    )

    assert pd.notna(scores["valid"])
    assert pd.isna(scores["zero"])
    assert pd.isna(scores["negative"])


def test_combine_scores_uses_weights_and_skips_missing_components():
    frame = pd.DataFrame(
        {
            "value_score": {"a": 1.0, "b": None},
            "quality_score": {"a": 0.0, "b": 0.0},
            "momentum_score": {"a": 2.0, "b": 3.0},
        }
    )

    combined = combine_scores(
        frame,
        weights={"value_score": 1.0, "quality_score": 1.0, "momentum_score": 2.0},
    )

    assert combined["a"] == 5.0
    assert combined["b"] == 6.0


def test_combine_scores_can_scale_weighted_total_to_100_points():
    frame = pd.DataFrame(
        {
            "value_score": {"a": 1.0, "b": 0.5},
            "quality_score": {"a": 0.0, "b": 0.5},
        }
    )

    combined = combine_scores(
        frame,
        weights={"value_score": 3.0, "quality_score": 1.0},
        scale_to=100.0,
    )

    assert combined["a"] == 75.0
    assert combined["b"] == 50.0
