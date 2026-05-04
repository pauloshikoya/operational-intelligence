# detection/cusum_detector.py

"""
CUSUM (Cumulative Sum) Anomaly Detector
────────────────────────────────────────
Detects sustained shifts — when a metric has been consistently
above or below its average for an extended period.

How it works:
    CUSUM accumulates deviations from the mean over time.
    A single large deviation has moderate impact.
    Repeated small deviations in the same direction accumulate
    into a large CUSUM value, triggering an alert.

    This is what catches "slow boil" anomalies that z-score misses:
    - Oil prices creeping up 0.5% per day for 2 weeks
    - A port's disruption risk rising steadily over 5 days
    - A commodity's 7-day average slowly decoupling from baseline

Parameters:
    k (slack parameter): how much deviation to ignore per step
                         higher k = less sensitive, fewer false alarms
    h (threshold):       CUSUM value that triggers an alert
                         higher h = need more evidence before alerting

Best at catching:  slow drifts, regime changes, trend reversals
Misses:            single-point spikes (z-score handles those)
"""

import logging

logger = logging.getLogger("detector.cusum")

# Tuning parameters
# k=0.5 means we ignore deviations smaller than 0.5 std devs per step
# h=4.0 means we need the equivalent of 4 std devs of accumulated evidence
K_SLACK     = 0.5
H_THRESHOLD = 4.0


def compute_cusum(values: list[float], mean: float,
                  std: float) -> tuple[float, float]:
    """
    Compute the upper and lower CUSUM statistics for a series of values.

    The CUSUM statistic accumulates evidence of sustained deviation.
    We track both upper (values above mean) and lower (values below mean).

    Args:
        values: list of recent values, oldest first
        mean:   historical mean to compare against
        std:    historical standard deviation

    Returns:
        (cusum_upper, cusum_lower) — both are positive numbers
        Higher = more evidence of sustained shift in that direction
    """
    if std == 0:
        return 0.0, 0.0

    cusum_upper = 0.0   # accumulates evidence of upward shift
    cusum_lower = 0.0   # accumulates evidence of downward shift

    for v in values:
        # Standardise the value (how many std devs from mean)
        standardised = (v - mean) / std

        # Upper CUSUM: accumulates when values are above mean
        # max(0, ...) means it resets to 0 when values go back to normal
        cusum_upper = max(0.0, cusum_upper + standardised - K_SLACK)

        # Lower CUSUM: accumulates when values are below mean
        cusum_lower = max(0.0, cusum_lower - standardised - K_SLACK)

    return cusum_upper, cusum_lower


def score_from_cusum(cusum_upper: float, cusum_lower: float) -> float:
    """
    Convert CUSUM statistics to a 0–1 anomaly score.

    We take the maximum of upper and lower (worst case direction),
    then scale using the threshold h.

    score = min(max(upper, lower) / (2 * h), 1.0)

    At h=4.0:
        cusum = 0    → score = 0.00
        cusum = 2    → score = 0.25
        cusum = 4    → score = 0.50  (at threshold)
        cusum = 6    → score = 0.75
        cusum = 8+   → score = 1.00  (capped)
    """
    max_cusum = max(cusum_upper, cusum_lower)
    raw_score = max_cusum / (2 * H_THRESHOLD)
    return round(min(raw_score, 1.0), 4)


def detect(values: list[float], mean: float, std: float) -> dict:
    """
    Run CUSUM detection.

    Args:
        values: recent values for this metric, oldest first
        mean:   historical mean
        std:    historical standard deviation

    Returns:
        dict with score, cusum_upper, cusum_lower, signal, direction
    """
    if len(values) < 3:
        # Not enough history for CUSUM to be meaningful
        return {
            "score":        0.0,
            "cusum_upper":  0.0,
            "cusum_lower":  0.0,
            "signal":       "Insufficient history for CUSUM",
            "direction":    "neutral",
        }

    cusum_upper, cusum_lower = compute_cusum(values, mean, std)
    anomaly_score = score_from_cusum(cusum_upper, cusum_lower)

    # Determine which direction the sustained shift is going
    if cusum_upper > cusum_lower and cusum_upper > H_THRESHOLD:
        direction = "up"
        signal = (
            f"Sustained UPWARD drift detected "
            f"(CUSUM={cusum_upper:.2f}, threshold={H_THRESHOLD})"
        )
    elif cusum_lower > cusum_upper and cusum_lower > H_THRESHOLD:
        direction = "down"
        signal = (
            f"Sustained DOWNWARD drift detected "
            f"(CUSUM={cusum_lower:.2f}, threshold={H_THRESHOLD})"
        )
    else:
        direction = "neutral"
        signal = (
            f"No sustained drift "
            f"(upper={cusum_upper:.2f}, lower={cusum_lower:.2f})"
        )

    logger.debug(
        f"CUSUM: upper={cusum_upper:.3f} lower={cusum_lower:.3f} "
        f"score={anomaly_score:.3f}"
    )

    return {
        "score":       anomaly_score,
        "cusum_upper": round(cusum_upper, 4),
        "cusum_lower": round(cusum_lower, 4),
        "signal":      signal,
        "direction":   direction,
    }