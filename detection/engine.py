# detection/engine.py

"""
Detection Engine — Main Orchestrator
──────────────────────────────────────
Runs continuously, pulling the latest features for every metric,
running all three detectors, combining scores, and persisting
anomalies to the database and Redpanda.

Flow per metric:
    1. Fetch latest features from Redis (fast path)
    2. Fetch historical features from TimescaleDB (for CUSUM + IForest)
    3. Run Z-Score detector
    4. Run CUSUM detector
    5. Run Isolation Forest detector
    6. Combine scores
    7. If anomaly: check suppression (don't re-alert on active anomaly)
    8. If not suppressed: write to anomalies table + Redpanda topic
"""

import json
import time
import logging
import redis as redis_lib
import psycopg2.extras
from datetime import datetime, timezone
from confluent_kafka import Producer

from ingestion.config import (
    DATABASE_URL,
    KAFKA_PRODUCER_CONFIG,
    TOPIC_ANOMALIES,
)
from ingestion.db import get_connection

from detection import zscore_detector
from detection import cusum_detector
from detection import iforest_detector
from detection import combiner

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("detection.engine")

RUN_INTERVAL        = 120    # run detection every 2 minutes
SUPPRESSION_WINDOW  = 7200   # suppress re-alerts for 2 hours (seconds)
HISTORY_DAYS        = 30     # days of history to feed into detectors


# ── Data fetchers ─────────────────────────────────────────────────────────────

def get_all_metrics(conn) -> list[dict]:
    """Get every distinct (source, metric_name) with recent features."""
    sql = """
        SELECT DISTINCT source, metric_name
        FROM features
        WHERE computed_at > NOW() - INTERVAL '1 hour'
        ORDER BY source, metric_name
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql)
        return cur.fetchall()


def get_latest_features(conn, source: str, metric_name: str) -> dict | None:
    """Get the single most recently computed feature row for a metric."""
    sql = """
        SELECT *
        FROM features
        WHERE source      = %s
          AND metric_name = %s
        ORDER BY computed_at DESC
        LIMIT 1
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, (source, metric_name))
        row = cur.fetchone()
        return dict(row) if row else None


def get_historical_features(conn, source: str,
                             metric_name: str) -> list[dict]:
    """
    Get the last HISTORY_DAYS days of feature rows for a metric.
    Used to train Isolation Forest and feed CUSUM.
    Ordered oldest first.
    """
    sql = """
        SELECT *
        FROM features
        WHERE source      = %s
          AND metric_name = %s
          AND computed_at > NOW() - INTERVAL '%s days'
        ORDER BY computed_at ASC
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, (source, metric_name, HISTORY_DAYS))
        return [dict(r) for r in cur.fetchall()]


def get_raw_values_recent(conn, source: str,
                           metric_name: str) -> list[float]:
    """
    Get recent raw values as a plain list of floats.
    Used by CUSUM which needs a value series, not feature dicts.
    """
    sql = """
        SELECT value
        FROM raw_data
        WHERE source      = %s
          AND metric_name = %s
          AND ingested_at > NOW() - INTERVAL '%s days'
        ORDER BY ingested_at ASC
    """
    with conn.cursor() as cur:
        cur.execute(sql, (source, metric_name, HISTORY_DAYS))
        return [float(row[0]) for row in cur.fetchall()]


# ── Suppression check ─────────────────────────────────────────────────────────

def is_suppressed(conn, source: str, metric_name: str) -> bool:
    """
    Check if this metric already has an active anomaly within
    the suppression window.

    Returns True if we should NOT fire a new alert.
    This prevents alert storms where the same event triggers
    hundreds of identical alerts.
    """
    sql = """
        SELECT COUNT(*)
        FROM anomalies
        WHERE source      = %s
          AND metric_name = %s
          AND is_active   = TRUE
          AND suppressed  = FALSE
          AND triggered_at > NOW() - INTERVAL '%s seconds'
    """
    with conn.cursor() as cur:
        cur.execute(sql, (source, metric_name, SUPPRESSION_WINDOW))
        count = cur.fetchone()[0]
        return count > 0


# ── Anomaly persistence ───────────────────────────────────────────────────────

def save_anomaly(conn, source: str, metric_name: str,
                 combined: dict, detector_results: dict) -> int:
    """
    Write a confirmed anomaly to the database.

    Returns the new anomaly's ID (used to publish to Redpanda).
    """
    sql = """
        INSERT INTO anomalies
            (source, metric_name, anomaly_score,
             z_score_contrib, cusum_contrib, iforest_contrib,
             narrative_json)
        VALUES
            (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """

    # Store the full detection detail in narrative_json
    # The LLM narrator (Day 5) will read this to write its report
    detection_detail = {
        "severity":      combined["severity"],
        "dominant":      combined["dominant"],
        "signals":       combined["signals"],
        "contributing":  combined["contributing"],
        "zscore_detail": detector_results["zscore"],
        "cusum_detail":  detector_results["cusum"],
        "iforest_detail":detector_results["iforest"],
    }

    with conn.cursor() as cur:
        cur.execute(sql, (
            source,
            metric_name,
            combined["final_score"],
            combined["contributing"]["zscore_contrib"],
            combined["contributing"]["cusum_contrib"],
            combined["contributing"]["iforest_contrib"],
            psycopg2.extras.Json(detection_detail),
        ))
        anomaly_id = cur.fetchone()[0]
    conn.commit()
    return anomaly_id


def publish_anomaly_event(producer, anomaly_id: int,
                          source: str, metric_name: str,
                          combined: dict, current_features: dict):
    """
    Publish the anomaly to the Redpanda anomaly-events topic.
    The API layer subscribes to this for real-time dashboard updates.
    """
    event = {
        "anomaly_id":    anomaly_id,
        "source":        source,
        "metric_name":   metric_name,
        "anomaly_score": combined["final_score"],
        "severity":      combined["severity"],
        "dominant":      combined["dominant"],
        "signals":       combined["signals"],
        "current_value": current_features.get("value_raw"),
        "z_score":       current_features.get("z_score"),
        "pct_change_1d": current_features.get("pct_change_1d"),
        "triggered_at":  datetime.now(timezone.utc).isoformat(),
    }
    producer.produce(
        topic=TOPIC_ANOMALIES,
        key=metric_name,
        value=json.dumps(event),
    )
    producer.flush()


# ── Per-metric detection ──────────────────────────────────────────────────────

def run_detection_for_metric(conn, source: str,
                              metric_name: str) -> dict | None:
    """
    Run the full detection pipeline for one metric.

    Returns:
        The combined result dict if an anomaly was detected,
        None if the metric is normal or was suppressed.
    """
    # ── 1. Fetch data ──────────────────────────────────────────────────────
    current   = get_latest_features(conn, source, metric_name)
    if not current:
        return None

    historical = get_historical_features(conn, source, metric_name)
    raw_values = get_raw_values_recent(conn, source, metric_name)

    mean = float(current.get("value_7d_avg",    0.0))
    std  = float(current.get("value_7d_stddev", 0.0))

    # ── 2. Run detectors ───────────────────────────────────────────────────
    z_result  = zscore_detector.detect(current)
    c_result  = cusum_detector.detect(raw_values, mean, std)
    if_result = iforest_detector.detect(historical, current)

    # ── 3. Combine ─────────────────────────────────────────────────────────
    combined = combiner.combine(z_result, c_result, if_result)

    # ── 4. Log summary ─────────────────────────────────────────────────────
    logger.info(
        f"{metric_name:35s} | "
        f"score={combined['final_score']:.3f} | "
        f"sev={combined['severity']:8s} | "
        f"z={z_result['score']:.2f} "
        f"c={c_result['score']:.2f} "
        f"if={if_result['score']:.2f}"
    )

    if not combined["is_anomaly"]:
        return None

    # ── 5. Check suppression ───────────────────────────────────────────────
    if is_suppressed(conn, source, metric_name):
        logger.info(
            f"  ↳ SUPPRESSED — active anomaly exists within "
            f"{SUPPRESSION_WINDOW//3600}h window"
        )
        return None

    return {
        "combined":          combined,
        "current_features":  current,
        "detector_results": {
            "zscore":  z_result,
            "cusum":   c_result,
            "iforest": if_result,
        }
    }


# ── Main loop ─────────────────────────────────────────────────────────────────

def run():
    """
    Main detection engine loop.
    Runs detection for every known metric every RUN_INTERVAL seconds.
    """
    conn     = get_connection()
    producer = Producer(KAFKA_PRODUCER_CONFIG)

    logger.info("Detection engine started")

    while True:
        logger.info("═══════ Detection cycle starting ═══════")
        cycle_start = time.time()

        metrics       = get_all_metrics(conn)
        anomalies_found = 0

        if not metrics:
            logger.info("No metrics with recent features found — waiting...")
            time.sleep(RUN_INTERVAL)
            continue

        for row in metrics:
            source      = row["source"]
            metric_name = row["metric_name"]

            try:
                result = run_detection_for_metric(conn, source, metric_name)

                if result is None:
                    continue

                # ── Anomaly confirmed — persist it ─────────────────────────
                anomaly_id = save_anomaly(
                    conn, source, metric_name,
                    result["combined"],
                    result["detector_results"],
                )

                publish_anomaly_event(
                    producer, anomaly_id,
                    source, metric_name,
                    result["combined"],
                    result["current_features"],
                )

                anomalies_found += 1

                logger.warning(
                    f"🚨 ANOMALY DETECTED: {metric_name} | "
                    f"score={result['combined']['final_score']:.3f} | "
                    f"severity={result['combined']['severity']} | "
                    f"id={anomaly_id}"
                )
                for signal in result["combined"]["signals"]:
                    logger.warning(f"   ↳ {signal}")

            except Exception as e:
                logger.error(
                    f"Detection failed for {metric_name}: {e}",
                    exc_info=True
                )
                continue

        elapsed = round(time.time() - cycle_start, 2)
        logger.info(
            f"═══════ Cycle done in {elapsed}s | "
            f"metrics={len(metrics)} | "
            f"anomalies={anomalies_found} | "
            f"sleeping {RUN_INTERVAL}s ═══════"
        )
        time.sleep(RUN_INTERVAL)


if __name__ == "__main__":
    run()