# processing/feature_engine.py

import time
import logging
import psycopg2
import psycopg2.extras
from datetime import datetime, timezone, timedelta
from ingestion.config import DATABASE_URL
from ingestion.db import get_connection

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("feature_engine")


# ── How far back to look when computing features ──────────────────────────────
LOOKBACK_DAYS = 30    # use 30 days of history for rolling calculations
RUN_INTERVAL  = 120   # re-run feature computation every 2 minutes


# ── Raw data queries ──────────────────────────────────────────────────────────

def get_distinct_metrics(conn) -> list[dict]:
    """
    Find every unique (source, metric_name) pair that has data.
    We'll compute features for each one.
    """
    sql = """
        SELECT DISTINCT source, metric_name
        FROM raw_data
        ORDER BY source, metric_name
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql)
        return cur.fetchall()


def get_recent_values(conn, source: str, metric_name: str,
                      days: int = LOOKBACK_DAYS) -> list[dict]:
    """
    Fetch the last N days of raw values for one metric,
    ordered oldest first (so index 0 = oldest, index -1 = newest).

    Returns list of dicts with 'value' and 'ingested_at' keys.
    """
    sql = """
        SELECT value, ingested_at
        FROM raw_data
        WHERE source      = %s
          AND metric_name = %s
          AND ingested_at > NOW() - INTERVAL '%s days'
        ORDER BY ingested_at ASC
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, (source, metric_name, days))
        return cur.fetchall()


# ── Feature computation ───────────────────────────────────────────────────────

def compute_features(values: list[dict]) -> dict | None:
    """
    Given a time-ordered list of raw values, compute all features.

    Args:
        values: list of dicts, each with 'value' (Decimal) and 'ingested_at'
                Ordered oldest → newest.

    Returns:
        dict of computed features, or None if not enough data
    """
    # Need at least 2 data points to compute changes
    if len(values) < 2:
        logger.debug("Not enough data points to compute features (need >= 2)")
        return None

    # Extract just the numeric values as floats for calculation
    nums = [float(row["value"]) for row in values]

    latest = nums[-1]    # most recent value

    # ── Rolling 7-day stats ───────────────────────────────────────────────────
    # Use all available values (up to 30 days) for the window
    # In early data collection, this might be fewer than 7 days — that's OK
    window = nums  # use all available data as the window

    avg    = sum(window) / len(window)
    # Standard deviation — measure of how much values vary
    variance  = sum((x - avg) ** 2 for x in window) / len(window)
    std_dev   = variance ** 0.5

    # ── Z-score ───────────────────────────────────────────────────────────────
    # How many standard deviations is the current value from the mean?
    # Z-score of 0 = exactly average
    # Z-score of 2 = 2 standard deviations above average (unusual)
    # Z-score of 3+ = very unusual, likely an anomaly
    if std_dev > 0:
        z_score = (latest - avg) / std_dev
    else:
        # std_dev of 0 means all values are identical — no variation at all
        z_score = 0.0

    # ── Percentage changes ────────────────────────────────────────────────────
    # 1-day change: compare latest to the value just before it
    prev_1d = nums[-2] if len(nums) >= 2 else None
    if prev_1d and prev_1d != 0:
        pct_change_1d = ((latest - prev_1d) / abs(prev_1d)) * 100
    else:
        pct_change_1d = 0.0

    # 7-day change: compare latest to value ~7 data points ago
    # Using index -8 (7 steps back) if we have enough data
    idx_7d = max(0, len(nums) - 8)
    prev_7d = nums[idx_7d]
    if prev_7d != 0:
        pct_change_7d = ((latest - prev_7d) / abs(prev_7d)) * 100
    else:
        pct_change_7d = 0.0

    return {
        "value_raw":       latest,
        "value_7d_avg":    round(avg, 6),
        "value_7d_stddev": round(std_dev, 6),
        "z_score":         round(z_score, 4),
        "pct_change_1d":   round(pct_change_1d, 4),
        "pct_change_7d":   round(pct_change_7d, 4),
    }


# ── Feature persistence ───────────────────────────────────────────────────────

def upsert_features(conn, source: str, metric_name: str, features: dict):
    """
    Write computed features to the features table.

    We insert a new row each time this runs — giving us a history
    of how features evolved over time, which is useful for debugging
    and for showing your methodology in interviews.
    """
    sql = """
        INSERT INTO features
            (source, metric_name, value_raw, value_7d_avg,
             value_7d_stddev, z_score, pct_change_1d, pct_change_7d)
        VALUES
            (%s, %s, %s, %s, %s, %s, %s, %s)
    """
    with conn.cursor() as cur:
        cur.execute(sql, (
            source,
            metric_name,
            features["value_raw"],
            features["value_7d_avg"],
            features["value_7d_stddev"],
            features["z_score"],
            features["pct_change_1d"],
            features["pct_change_7d"],
        ))
    conn.commit()


# ── Redis cache writer ────────────────────────────────────────────────────────

def cache_latest_features(redis_client, source: str,
                           metric_name: str, features: dict):
    """
    Write the latest features to Redis for fast dashboard lookups.

    Key format: features:{source}:{metric_name}
    We set an expiry of 1 hour — if the pipeline stops, stale
    data automatically disappears rather than misleading users.
    """
    import json
    key = f"features:{source}:{metric_name}"
    redis_client.setex(
        key,
        3600,    # expire after 1 hour
        json.dumps({
            **features,
            "source":      source,
            "metric_name": metric_name,
            "cached_at":   datetime.now(timezone.utc).isoformat(),
        })
    )


# ── Main loop ─────────────────────────────────────────────────────────────────

def run():
    """
    Feature engine main loop.

    Every RUN_INTERVAL seconds:
    1. Find all metrics that have raw data
    2. Compute features for each metric
    3. Write features to TimescaleDB
    4. Cache latest features in Redis
    """
    import redis as redis_lib

    conn         = get_connection()
    redis_client = redis_lib.from_url("redis://localhost:6379", decode_responses=True)

    logger.info("Feature engine started")

    while True:
        logger.info("── Running feature computation cycle ──")

        metrics = get_distinct_metrics(conn)

        if not metrics:
            logger.info("No metrics found yet — waiting for data to arrive")
            time.sleep(RUN_INTERVAL)
            continue

        logger.info(f"Computing features for {len(metrics)} metrics")

        computed = 0
        skipped  = 0

        for row in metrics:
            source      = row["source"]
            metric_name = row["metric_name"]

            # Fetch recent history for this metric
            values = get_recent_values(conn, source, metric_name)

            if not values:
                skipped += 1
                continue

            # Compute features
            features = compute_features(values)

            if features is None:
                skipped += 1
                continue

            # Persist to TimescaleDB
            upsert_features(conn, source, metric_name, features)

            # Cache in Redis for fast reads
            cache_latest_features(redis_client, source, metric_name, features)

            logger.info(
                f"  {metric_name}: "
                f"z={features['z_score']:+.2f}  "
                f"avg={features['value_7d_avg']:.3f}  "
                f"1d_chg={features['pct_change_1d']:+.2f}%"
            )
            computed += 1

        logger.info(
            f"Cycle done — computed: {computed} | skipped: {skipped}. "
            f"Sleeping {RUN_INTERVAL}s..."
        )
        time.sleep(RUN_INTERVAL)


if __name__ == "__main__":
    run()