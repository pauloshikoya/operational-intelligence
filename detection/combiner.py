# detection/combiner.py

"""
Score Combiner
──────────────
Takes the individual scores from each detector and combines
them into a single final anomaly score.

Why weighted average (not max or sum)?
    - Max would be too sensitive: one noisy detector could
      always trigger alerts even if the others disagree
    - Sum would double-count: if all three fire on the same signal
      you'd always get score=1.0
    - Weighted average respects each detector's contribution while
      letting the ensemble vote

Weight rationale:
    Z-score (0.35):          Fast, reliable, low false positive rate.
                             Good first signal. Gets the most weight.
    CUSUM (0.40):            Slightly higher weight because sustained
                             drifts are operationally more significant
                             than point spikes. A spike can reverse.
                             A sustained drift usually means something real.
    Isolation Forest (0.25): Lower weight because it needs more data
                             and can be noisy early in data collection.
                             Valuable for catching things the others miss.

These weights can be tuned. In production you'd run backtests
to find optimal weights for your specific domain.
"""

import logging

logger = logging.getLogger("detector.combiner")

# Weights must sum to 1.0
WEIGHTS = {
    "zscore":  0.35,
    "cusum":   0.40,
    "iforest": 0.25,
}

# Threshold above which we generate an alert
ALERT_THRESHOLD = 0.55

# Minimum threshold below which we never alert
# (prevents noise from near-zero scores)
NOISE_FLOOR = 0.20


def combine(zscore_result: dict,
            cusum_result: dict,
            iforest_result: dict) -> dict:
    """
    Combine three detector results into a final anomaly assessment.

    Args:
        zscore_result:  output dict from zscore_detector.detect()
        cusum_result:   output dict from cusum_detector.detect()
        iforest_result: output dict from iforest_detector.detect()

    Returns:
        dict with:
            final_score     (float 0–1, the combined anomaly score)
            is_anomaly      (bool, True if score >= ALERT_THRESHOLD)
            severity        ('low', 'medium', 'high', 'critical')
            contributing    (dict showing each detector's contribution)
            dominant        (which detector contributed most)
            signals         (list of human-readable signal strings)
    """
    z_score  = zscore_result.get("score",  0.0)
    c_score  = cusum_result.get("score",   0.0)
    if_score = iforest_result.get("score", 0.0)

    # Weighted average
    final_score = (
        z_score  * WEIGHTS["zscore"]  +
        c_score  * WEIGHTS["cusum"]   +
        if_score * WEIGHTS["iforest"]
    )
    final_score = round(final_score, 4)

    # Apply noise floor — if all scores are tiny, treat as zero
    if final_score < NOISE_FLOOR:
        final_score = 0.0

    # Determine severity band
    if final_score >= 0.85:
        severity = "critical"
    elif final_score >= 0.70:
        severity = "high"
    elif final_score >= 0.55:
        severity = "medium"
    elif final_score >= 0.30:
        severity = "low"
    else:
        severity = "normal"

    is_anomaly = final_score >= ALERT_THRESHOLD

    # Work out which detector is driving the score most
    contributions = {
        "zscore":  round(z_score  * WEIGHTS["zscore"],  4),
        "cusum":   round(c_score  * WEIGHTS["cusum"],   4),
        "iforest": round(if_score * WEIGHTS["iforest"], 4),
    }
    dominant = max(contributions, key=contributions.get)

    # Collect meaningful signals (ignore noise-level signals)
    signals = []
    if z_score > 0.3:
        signals.append(zscore_result.get("signal", ""))
    if c_score > 0.3:
        signals.append(cusum_result.get("signal", ""))
    if if_score > 0.3:
        signals.append(iforest_result.get("signal", ""))

    logger.info(
        f"Combined score={final_score:.3f} "
        f"[z={z_score:.2f} c={c_score:.2f} if={if_score:.2f}] "
        f"severity={severity} anomaly={is_anomaly}"
    )

    return {
        "final_score":   final_score,
        "is_anomaly":    is_anomaly,
        "severity":      severity,
        "contributing": {
            "zscore_score":    round(z_score,  4),
            "cusum_score":     round(c_score,  4),
            "iforest_score":   round(if_score, 4),
            "zscore_contrib":  contributions["zscore"],
            "cusum_contrib":   contributions["cusum"],
            "iforest_contrib": contributions["iforest"],
        },
        "dominant":  dominant,
        "signals":   [s for s in signals if s],
    }