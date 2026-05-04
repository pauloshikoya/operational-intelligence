# tests/test_features.py

import pytest
from processing.feature_engine import compute_features


# ── Helper ────────────────────────────────────────────────────────────────────

def make_values(nums: list[float]) -> list[dict]:
    """
    Convert a plain list of numbers into the format
    compute_features() expects.
    """
    from datetime import datetime, timezone, timedelta
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return [
        {"value": n, "ingested_at": base + timedelta(hours=i)}
        for i, n in enumerate(nums)
    ]


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_returns_none_with_single_value():
    """Need at least 2 values to compute features."""
    result = compute_features(make_values([100.0]))
    assert result is None


def test_z_score_zero_when_all_values_identical():
    """If all values are the same, z-score should be 0."""
    values = make_values([50.0, 50.0, 50.0, 50.0, 50.0])
    result = compute_features(values)
    assert result is not None
    assert result["z_score"] == 0.0


def test_positive_z_score_when_latest_above_average():
    """
    If the latest value is well above the historical average,
    z-score should be positive.
    """
    # 9 stable values at 100, then a spike to 200
    values = make_values([100.0] * 9 + [200.0])
    result = compute_features(values)
    assert result is not None
    assert result["z_score"] > 0


def test_negative_z_score_when_latest_below_average():
    """If the latest value crashes below average, z-score is negative."""
    values = make_values([100.0] * 9 + [10.0])
    result = compute_features(values)
    assert result is not None
    assert result["z_score"] < 0


def test_pct_change_1d_positive_when_rising():
    """1-day % change should be positive when value went up."""
    values = make_values([100.0, 110.0])
    result = compute_features(values)
    assert result is not None
    assert result["pct_change_1d"] == pytest.approx(10.0, rel=0.01)


def test_pct_change_1d_negative_when_falling():
    """1-day % change should be negative when value dropped."""
    values = make_values([100.0, 90.0])
    result = compute_features(values)
    assert result is not None
    assert result["pct_change_1d"] == pytest.approx(-10.0, rel=0.01)


def test_average_is_correct():
    """7-day average should be the mean of all provided values."""
    values = make_values([10.0, 20.0, 30.0, 40.0, 50.0])
    result = compute_features(values)
    assert result is not None
    assert result["value_7d_avg"] == pytest.approx(30.0, rel=0.01)


def test_latest_value_is_last_item():
    """value_raw should always be the most recent (last) value."""
    values = make_values([10.0, 20.0, 99.0])
    result = compute_features(values)
    assert result is not None
    assert result["value_raw"] == 99.0


def test_large_spike_produces_high_z_score():
    """
    A value 3+ standard deviations above the mean
    should trigger a z-score above 2.5 — anomaly territory.
    """
    # Stable at 100, then massive spike
    values = make_values([100.0] * 20 + [300.0])
    result = compute_features(values)
    assert result is not None
    assert result["z_score"] > 2.5