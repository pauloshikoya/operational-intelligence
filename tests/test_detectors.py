# tests/test_detectors.py

import pytest
from detection import zscore_detector, cusum_detector, combiner


# ── Z-Score tests ─────────────────────────────────────────────────────────────

def test_zscore_normal_value_scores_low():
    result = zscore_detector.detect({"z_score": 0.5})
    assert result["score"] < 0.2


def test_zscore_high_value_scores_high():
    result = zscore_detector.detect({"z_score": 3.5})
    assert result["score"] > 0.8


def test_zscore_direction_up_when_positive():
    result = zscore_detector.detect({"z_score": 2.5})
    assert result["direction"] == "up"


def test_zscore_direction_down_when_negative():
    result = zscore_detector.detect({"z_score": -2.5})
    assert result["direction"] == "down"


def test_zscore_symmetric():
    """Score for +z should equal score for -z (direction doesn't affect score)."""
    pos = zscore_detector.detect({"z_score":  3.0})["score"]
    neg = zscore_detector.detect({"z_score": -3.0})["score"]
    assert abs(pos - neg) < 0.001


# ── CUSUM tests ───────────────────────────────────────────────────────────────

def test_cusum_insufficient_history():
    result = cusum_detector.detect([100.0, 101.0], mean=100.0, std=1.0)
    assert result["score"] == 0.0


def test_cusum_stable_series_scores_low():
    values = [100.0] * 20
    result = cusum_detector.detect(values, mean=100.0, std=1.0)
    assert result["score"] < 0.2


def test_cusum_sustained_rise_scores_high():
    # Gradual rise of 0.5 per step
    values = [100.0 + (i * 0.5) for i in range(20)]
    result = cusum_detector.detect(values, mean=100.0, std=1.0)
    assert result["score"] > 0.5


def test_cusum_sustained_fall_scores_high():
    values = [100.0 - (i * 0.5) for i in range(20)]
    result = cusum_detector.detect(values, mean=100.0, std=1.0)
    assert result["score"] > 0.5


# ── Combiner tests ────────────────────────────────────────────────────────────

def test_combiner_all_zero_not_anomaly():
    z  = {"score": 0.0, "signal": "", "direction": "neutral"}
    c  = {"score": 0.0, "signal": "", "direction": "neutral"}
    i  = {"score": 0.0, "signal": ""}
    result = combiner.combine(z, c, i)
    assert result["is_anomaly"] == False


def test_combiner_all_high_is_anomaly():
    z  = {"score": 0.9, "signal": "High z-score", "direction": "up"}
    c  = {"score": 0.9, "signal": "Sustained drift", "direction": "up"}
    i  = {"score": 0.9, "signal": "IF anomaly"}
    result = combiner.combine(z, c, i)
    assert result["is_anomaly"] == True
    assert result["severity"] in ("high", "critical")


def test_combiner_weights_sum_respected():
    """Final score should be the weighted average of individual scores."""
    z  = {"score": 1.0, "signal": "", "direction": "up"}
    c  = {"score": 0.0, "signal": "", "direction": "neutral"}
    i  = {"score": 0.0, "signal": ""}
    result = combiner.combine(z, c, i)
    # Only z-score fires: 1.0 * 0.35 = 0.35, below noise floor → 0
    # Actually above noise floor (0.20), so score = 0.35
    assert result["final_score"] == pytest.approx(0.35, abs=0.01)


def test_combiner_critical_severity():
    z  = {"score": 1.0, "signal": "Extreme spike", "direction": "up"}
    c  = {"score": 1.0, "signal": "Extreme drift",  "direction": "up"}
    i  = {"score": 1.0, "signal": "IF extreme"}
    result = combiner.combine(z, c, i)
    assert result["severity"] == "critical"
    assert result["final_score"] == pytest.approx(1.0, abs=0.01)