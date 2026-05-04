# detection/iforest_detector.py

"""
Isolation Forest Anomaly Detector
───────────────────────────────────
Detects multivariate anomalies — unusual combinations of
features that look normal individually.

How it works:
    Isolation Forest builds an ensemble of random decision trees.
    Normal points require many splits to isolate (they're buried
    in dense clusters). Anomalies are isolated quickly (they're
    in sparse regions of the feature space).

    The algorithm returns a score where:
        score close to 1   →  very likely anomaly
        score close to 0   →  normal
        score around 0.5   →  borderline

Why this matters:
    Imagine copper prices are up 5% (unusual but not extreme),
    AND oil prices are up 8% (unusual but not extreme),
    AND two port weather risk scores are elevated (unusual but not extreme).
    Each individual z-score might be 1.5 — not alarming alone.
    But Isolation Forest sees the combination as highly anomalous.
    This is exactly the kind of correlated supply chain stress
    that matters most operationally.

Best at catching:  correlated multi-metric anomalies, novel patterns
Requires:          at least 20 data points to train meaningfully
"""

import logging
import numpy as np
from sklearn.ensemble import IsolationForest

logger = logging.getLogger("detector.iforest")

# contamination: what fraction of training data we expect to be anomalous
# 0.05 = we expect ~5% of historical data to contain anomalies
# This affects the decision threshold inside sklearn
CONTAMINATION = 0.05


def build_feature_vector(features: dict) -> list[float]:
    """
    Extract the numeric features we want Isolation Forest to consider.

    We deliberately pick features that capture different aspects:
    - value_raw:       the actual current value
    - z_score:         how far from normal
    - pct_change_1d:   short-term momentum
    - pct_change_7d:   medium-term trend
    - value_7d_stddev: current volatility regime

    We exclude value_7d_avg because it's already captured by z_score.
    """
    return [
        float(features.get("value_raw",       0.0)),
        float(features.get("z_score",         0.0)),
        float(features.get("pct_change_1d",   0.0)),
        float(features.get("pct_change_7d",   0.0)),
        float(features.get("value_7d_stddev", 0.0)),
    ]


def detect(historical_features: list[dict],
           current_features: dict) -> dict:
    """
    Train an Isolation Forest on historical features and
    score the current observation.

    Args:
        historical_features: list of feature dicts from the past 30 days
                             Each dict has the same keys as current_features
        current_features:    the most recent feature dict to score

    Returns:
        dict with score, raw_if_score, signal
    """
    # Need enough history to build a meaningful forest
    if len(historical_features) < 20:
        logger.debug(
            f"Only {len(historical_features)} historical points — "
            f"need 20+ for Isolation Forest"
        )
        return {
            "score":        0.0,
            "raw_if_score": 0.0,
            "signal":       "Insufficient history for Isolation Forest (need 20+)",
        }

    # Build the training matrix — one row per historical observation
    X_train = np.array([
        build_feature_vector(f) for f in historical_features
    ])

    # The current observation we want to score
    X_current = np.array([build_feature_vector(current_features)])

    # Train the forest on historical data
    # random_state=42 makes results reproducible
    model = IsolationForest(
        n_estimators=100,       # 100 trees — good balance of accuracy vs speed
        contamination=CONTAMINATION,
        random_state=42,
        n_jobs=-1,              # use all CPU cores
    )
    model.fit(X_train)

    # score_samples returns negative values:
    #   more negative = more anomalous
    #   typical range: roughly -0.7 to -0.3
    raw_score = model.score_samples(X_current)[0]

    # Convert to 0–1 scale where 1 = most anomalous
    # sklearn's decision_function threshold is approximately -0.5
    # We map: raw_score=-0.7 → anomaly_score≈0.9
    #         raw_score=-0.5 → anomaly_score≈0.5
    #         raw_score=-0.3 → anomaly_score≈0.1
    anomaly_score = max(0.0, min(1.0, (-raw_score - 0.3) / 0.4))
    anomaly_score = round(anomaly_score, 4)

    # Determine prediction: -1 = anomaly, 1 = normal
    prediction = model.predict(X_current)[0]

    if prediction == -1:
        signal = (
            f"Isolation Forest flagged as ANOMALOUS "
            f"(raw score={raw_score:.3f})"
        )
    else:
        signal = (
            f"Isolation Forest: normal "
            f"(raw score={raw_score:.3f})"
        )

    logger.debug(
        f"Isolation Forest: raw={raw_score:.3f} "
        f"score={anomaly_score:.3f} prediction={prediction}"
    )

    return {
        "score":        anomaly_score,
        "raw_if_score": round(raw_score, 4),
        "signal":       signal,
    }