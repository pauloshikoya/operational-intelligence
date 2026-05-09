# detection/context_builder.py

"""
Context Builder
───────────────
Assembles everything Claude needs to write an intelligent,
accurate narrative about an anomaly.

The quality of the narrative depends entirely on the quality
of the context we provide. Garbage in = garbage out.

We gather:
  1. The anomaly itself (score, severity, detector signals)
  2. Current metric value + recent history (7 days of data points)
  3. Statistical context (mean, std dev, z-score, % changes)
  4. Related metrics (other commodities/signals that may be correlated)
  5. Any recent anomalies on the same or related metrics
     (is this part of a broader pattern?)

We deliberately cap context size to avoid token waste.
Claude doesn't need 30 days of minute-by-minute data —
it needs the right data, well structured.
"""

import logging
import psycopg2.extras
from datetime import datetime, timezone

logger = logging.getLogger("context_builder")

# How many recent data points to include in the prompt
RECENT_POINTS_LIMIT = 14   # 2 weeks of daily data points

# How many related anomalies to include for pattern context
RELATED_ANOMALIES_LIMIT = 5


def get_recent_raw_values(conn, source: str,
                           metric_name: str) -> list[dict]:
    """
    Fetch the last RECENT_POINTS_LIMIT raw data points for a metric.
    Returns them oldest-first so Claude can read the trend naturally.
    """
    sql = """
        SELECT
            value,
            unit,
            ingested_at
        FROM raw_data
        WHERE source      = %s
          AND metric_name = %s
        ORDER BY ingested_at DESC
        LIMIT %s
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, (source, metric_name, RECENT_POINTS_LIMIT))
        rows = cur.fetchall()
        # Reverse so oldest is first — natural reading order
        return [dict(r) for r in reversed(rows)]


def get_current_features(conn, source: str,
                          metric_name: str) -> dict | None:
    """Get the most recently computed features for a metric."""
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


def get_related_metrics(conn, source: str,
                         metric_name: str) -> list[dict]:
    """
    Get the latest features for other metrics from the same source.

    This lets Claude say things like:
    "Crude oil is spiking at the same time as natural gas and
     shipping disruption at Rotterdam — suggesting an energy
     supply shock rather than an isolated data error."
    """
    sql = """
        SELECT DISTINCT ON (metric_name)
            metric_name,
            value_raw,
            z_score,
            pct_change_1d,
            pct_change_7d,
            computed_at
        FROM features
        WHERE source      = %s
          AND metric_name != %s
          AND computed_at  > NOW() - INTERVAL '2 hours'
        ORDER BY metric_name, computed_at DESC
        LIMIT 10
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, (source, metric_name))
        return [dict(r) for r in cur.fetchall()]


def get_recent_anomalies_same_metric(conn, source: str,
                                      metric_name: str) -> list[dict]:
    """
    Get recent anomalies on THIS metric.
    Helps Claude understand if this is a recurring pattern
    or a brand new event.
    """
    sql = """
        SELECT
            anomaly_score,
            severity,
            triggered_at,
            narrative_json -> 'signals' AS signals
        FROM anomalies
        WHERE source      = %s
          AND metric_name = %s
          AND triggered_at > NOW() - INTERVAL '7 days'
        ORDER BY triggered_at DESC
        LIMIT 3
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, (source, metric_name))
        return [dict(r) for r in cur.fetchall()]


def get_recent_anomalies_related(conn, source: str,
                                  metric_name: str) -> list[dict]:
    """
    Get recent anomalies on OTHER metrics from the same source.
    Helps Claude identify correlated or cascading events.
    """
    sql = """
        SELECT
            metric_name,
            anomaly_score,
            severity,
            triggered_at
        FROM anomalies
        WHERE source      = %s
          AND metric_name != %s
          AND triggered_at > NOW() - INTERVAL '48 hours'
        ORDER BY triggered_at DESC
        LIMIT %s
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, (source, metric_name, RELATED_ANOMALIES_LIMIT))
        return [dict(r) for r in cur.fetchall()]


def format_value_history(rows: list[dict]) -> str:
    """
    Format raw value history as a compact readable table for the prompt.

    Example output:
        2024-01-08  78.42 USD
        2024-01-09  79.10 USD
        2024-01-10  81.33 USD  ← +2.8% jump
        ...
    """
    if not rows:
        return "No recent data available."

    lines = []
    prev_value = None

    for row in rows:
        value     = float(row["value"])
        unit      = row.get("unit", "")
        timestamp = row["ingested_at"]

        # Format the date
        if hasattr(timestamp, "strftime"):
            date_str = timestamp.strftime("%Y-%m-%d %H:%M")
        else:
            date_str = str(timestamp)[:16]

        # Add a change indicator if we have a previous value
        change_str = ""
        if prev_value is not None and prev_value != 0:
            pct = ((value - prev_value) / abs(prev_value)) * 100
            if abs(pct) > 0.5:
                arrow  = "↑" if pct > 0 else "↓"
                change_str = f"  {arrow} {pct:+.1f}%"

        lines.append(f"  {date_str}  {value:>10.3f} {unit}{change_str}")
        prev_value = value

    return "\n".join(lines)


def format_related_metrics(rows: list[dict]) -> str:
    """
    Format related metrics as a compact summary table.
    """
    if not rows:
        return "No related metrics available."

    lines = []
    for row in rows:
        z    = float(row.get("z_score", 0) or 0)
        d1   = float(row.get("pct_change_1d", 0) or 0)
        d7   = float(row.get("pct_change_7d", 0) or 0)
        val  = float(row.get("value_raw", 0) or 0)
        name = row["metric_name"]
        lines.append(
            f"  {name:35s} "
            f"value={val:>8.3f}  "
            f"z={z:+.2f}  "
            f"1d={d1:+.1f}%  "
            f"7d={d7:+.1f}%"
        )
    return "\n".join(lines)


def build(conn, anomaly_id: int,
          source: str, metric_name: str,
          combined_result: dict,
          detector_results: dict) -> dict:
    """
    Build the complete context package for the LLM narrator.

    Args:
        conn             : database connection
        anomaly_id       : ID of the anomaly being narrated
        source           : data source name
        metric_name      : metric being described
        combined_result  : output from combiner.combine()
        detector_results : dict with zscore/cusum/iforest outputs

    Returns:
        A structured dict containing everything the prompt needs.
        Also returns formatted text sections ready to drop into the prompt.
    """
    logger.info(f"Building context for anomaly {anomaly_id}: {metric_name}")

    # ── Fetch all context data ─────────────────────────────────────────────
    recent_values    = get_recent_raw_values(conn, source, metric_name)
    current_features = get_current_features(conn, source, metric_name)
    related_metrics  = get_related_metrics(conn, source, metric_name)
    past_same        = get_recent_anomalies_same_metric(conn, source, metric_name)
    past_related     = get_recent_anomalies_related(conn, source, metric_name)

    # ── Format sections for the prompt ────────────────────────────────────
    value_history_text   = format_value_history(recent_values)
    related_metrics_text = format_related_metrics(related_metrics)

    past_same_text = "None in the last 7 days."
    if past_same:
        lines = []
        for a in past_same:
            ts = a["triggered_at"]
            if hasattr(ts, "strftime"):
                ts = ts.strftime("%Y-%m-%d %H:%M")
            lines.append(
                f"  {ts}  score={a['anomaly_score']:.3f}  "
                f"severity={a['severity']}"
            )
        past_same_text = "\n".join(lines)

    past_related_text = "No related anomalies in last 48 hours."
    if past_related:
        lines = []
        for a in past_related:
            ts = a["triggered_at"]
            if hasattr(ts, "strftime"):
                ts = ts.strftime("%Y-%m-%d %H:%M")
            lines.append(
                f"  {a['metric_name']:35s} "
                f"score={a['anomaly_score']:.3f}  "
                f"severity={a['severity']}  "
                f"at={ts}"
            )
        past_related_text = "\n".join(lines)

    # ── Detector signal summary ────────────────────────────────────────────
    z_signal  = detector_results["zscore"].get("signal",  "N/A")
    c_signal  = detector_results["cusum"].get("signal",   "N/A")
    if_signal = detector_results["iforest"].get("signal", "N/A")

    z_score_raw = float(current_features.get("z_score", 0) or 0) \
                  if current_features else 0.0
    avg         = float(current_features.get("value_7d_avg", 0) or 0) \
                  if current_features else 0.0
    std         = float(current_features.get("value_7d_stddev", 0) or 0) \
                  if current_features else 0.0
    pct_1d      = float(current_features.get("pct_change_1d", 0) or 0) \
                  if current_features else 0.0
    pct_7d      = float(current_features.get("pct_change_7d", 0) or 0) \
                  if current_features else 0.0
    current_val = float(current_features.get("value_raw", 0) or 0) \
                  if current_features else 0.0

    return {
        # Raw data for programmatic use
        "anomaly_id":          anomaly_id,
        "source":              source,
        "metric_name":         metric_name,
        "anomaly_score":       combined_result["final_score"],
        "severity":            combined_result["severity"],
        "dominant_detector":   combined_result["dominant"],
        "current_value":       current_val,
        "historical_avg":      avg,
        "historical_std":      std,
        "z_score":             z_score_raw,
        "pct_change_1d":       pct_1d,
        "pct_change_7d":       pct_7d,

        # Pre-formatted text blocks for the prompt
        "value_history_text":   value_history_text,
        "related_metrics_text": related_metrics_text,
        "past_same_text":       past_same_text,
        "past_related_text":    past_related_text,
        "z_signal":             z_signal,
        "c_signal":             c_signal,
        "if_signal":            if_signal,
    }