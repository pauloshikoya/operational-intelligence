# detection/zscore_detector.py

"""
Z-Score Anomaly Detector
────────────────────────
Detects point anomalies — a single value that is unusually far
from the historical mean.

How it works:
    z = (current_value - historical_mean) / historical_stddev

    z = 0    → exactly average, completely normal
    z = 1    → 1 standard deviation from mean, slightly unusual
    z = 2    → 2 standard deviations, moderately unusual (~5% of values)
    z = 3+   → 3+ standard deviations, very unusual (~0.3% of values)

We convert z to a 0–1 score using a sigmoid-like scaling so it
plays nicely with the other detectors.

Best at catching:  sudden price spikes, flash crashes, data errors
Misses:            slow gradual drifts that never spike
"""

import math
import logging

logger = logging.getLogger("detector.zscore")


def score(z_score: float) -> float:
    """
    Convert a raw z-score into a 0.0–1.0 anomaly score.

    Mapping:
        |z| = 0.0  →  score = 0.00  (perfectly normal)
        |z| = 1.0  →  score = 0.12  (slightly unusual)
        |z| = 2.0  →  score = 0.50  (moderately anomalous)
        |z| = 2.5  →  score = 0.71  (quite anomalous)
        |z| = 3.0  →  score = 0.86  (very anomalous)
        |z| = 4.0  →  score = 0.96  (extreme)

    We use the absolute value because we care about both
    unusually high AND unusually low values.

    The formula: 1 - exp(-0.5 * z^2)
    This is derived from the normal distribution — a value with
    |z|=2 is in the outer 5% of a normal distribution, so its
    anomaly score should be meaningfully high.
    """
    abs_z = abs(z_score)

    # Clamp to avoid float overflow on extreme values
    abs_z = min(abs_z, 10.0)

    anomaly_score = 1.0 - math.exp(-0.5 * (abs_z ** 2))

    return round(anomaly_score, 4)


def detect(features: dict) -> dict:
    """
    Run z-score detection on a feature dict.

    Args:
        features: dict containing at minimum 'z_score' key

    Returns:
        dict with:
            score      (float 0–1)
            z_score    (the raw z-score used)
            signal     (human-readable description of what was found)
            direction  ('up', 'down', or 'neutral')
    """
    z = float(features.get("z_score", 0.0))
    anomaly_score = score(z)

    # Determine direction of the anomaly
    if z > 0.5:
        direction = "up"
        signal = f"Value is {abs(z):.1f} std devs ABOVE historical average"
    elif z < -0.5:
        direction = "down"
        signal = f"Value is {abs(z):.1f} std devs BELOW historical average"
    else:
        direction = "neutral"
        signal = "Value is within normal range"

    logger.debug(
        f"Z-score detection: z={z:.3f} "
        f"score={anomaly_score:.3f} direction={direction}"
    )

    return {
        "score":     anomaly_score,
        "z_score":   z,
        "signal":    signal,
        "direction": direction,
    }