import pytest

from src.trading.allocation import compute_score_weights


def test_compute_score_weights_respects_min_and_max_caps():
    scores = [
        ("AAA", 100.0),
        ("BBB", 80.0),
        ("CCC", 60.0),
        ("DDD", 40.0),
    ]

    weights = compute_score_weights(scores, min_weight=0.03, max_weight=0.15)

    assert set(weights) == {"AAA", "BBB", "CCC", "DDD"}
    assert all(0.03 <= value <= 0.15 for value in weights.values())
    assert weights["AAA"] >= weights["BBB"] >= weights["CCC"] >= weights["DDD"]
    assert sum(weights.values()) == pytest.approx(0.60)


def test_compute_score_weights_normalizes_when_caps_do_not_bind():
    scores = [("AAA", 3.0), ("BBB", 2.0), ("CCC", 1.0)]

    weights = compute_score_weights(scores, min_weight=0.01, max_weight=0.80)

    assert sum(weights.values()) == pytest.approx(1.0)
    assert weights["AAA"] > weights["BBB"] > weights["CCC"]


def test_compute_score_weights_handles_equal_scores():
    scores = [("AAA", 5.0), ("BBB", 5.0), ("CCC", 5.0)]

    weights = compute_score_weights(scores, min_weight=0.03, max_weight=0.50)

    assert weights == pytest.approx({"AAA": 1 / 3, "BBB": 1 / 3, "CCC": 1 / 3})


def test_compute_score_weights_rejects_invalid_caps():
    with pytest.raises(ValueError, match="min_weight"):
        compute_score_weights([("AAA", 1.0)], min_weight=-0.01, max_weight=0.15)

    with pytest.raises(ValueError, match="max_weight"):
        compute_score_weights([("AAA", 1.0)], min_weight=0.03, max_weight=0.0)
