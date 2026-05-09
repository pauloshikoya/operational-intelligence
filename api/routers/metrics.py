# api/routers/metrics.py

"""
Metrics endpoints.

GET /metrics              — all tracked metrics with latest feature values
GET /metrics/{name}/series — time-series data for one metric (for charts)
"""

import json
from typing import Optional
from fastapi import APIRouter, Depends, Query
from api.dependencies import get_db, get_redis, verify_api_key

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get(
    "",
    summary="List all metrics",
    description=(
        "Returns every tracked metric with its latest computed features. "
        "Reads from Redis cache first (fast), falls back to DB."
    ),
)
def list_metrics(
    redis_client = Depends(get_redis),
    conn         = Depends(get_db),
    _api_key     = Depends(verify_api_key),
):
    # Try Redis first — this is what makes the dashboard feel fast
    keys = redis_client.keys("features:*")

    if keys:
        metrics = []
        for key in sorted(keys):
            raw = redis_client.get(key)
            if raw:
                metrics.append(json.loads(raw))
        return {
            "metrics": metrics,
            "source":  "cache",
            "count":   len(metrics),
        }

    # Redis miss — fall back to database
    # This happens when the feature engine hasn't run yet
    sql = """
        SELECT DISTINCT ON (source, metric_name)
            source,
            metric_name,
            value_raw,
            value_7d_avg,
            value_7d_stddev,
            z_score,
            pct_change_1d,
            pct_change_7d,
            computed_at
        FROM features
        ORDER BY source, metric_name, computed_at DESC
    """
    with conn.cursor() as cur:
        cur.execute(sql)
        rows = cur.fetchall()

    return {
        "metrics": [dict(r) for r in rows],
        "source":  "database",
        "count":   len(rows),
    }


@router.get(
    "/{metric_name}/series",
    summary="Get time-series for a metric",
    description=(
        "Returns raw data points for a metric over a time range. "
        "Used to render charts in the dashboard."
    ),
)
def get_metric_series(
    metric_name: str,
    hours:   int           = Query(168,  description="Hours of history (default 168 = 7 days)"),
    source:  Optional[str] = Query(None, description="Filter by source"),
    conn     = Depends(get_db),
    _api_key = Depends(verify_api_key),
):
    conditions = [
        "metric_name ILIKE %s",
        "ingested_at > NOW() - INTERVAL '%s hours'",
    ]
    params = [f"%{metric_name}%", hours]

    if source:
        conditions.append("source = %s")
        params.append(source)

    where = " AND ".join(conditions)

    # Raw values for the chart line
    raw_sql = f"""
        SELECT value, unit, ingested_at
        FROM raw_data
        WHERE {where}
        ORDER BY ingested_at ASC
        LIMIT 500
    """

    # Anomalies overlay — markers on the chart
    anomaly_sql = """
        SELECT id, anomaly_score, severity, triggered_at, narrative
        FROM anomalies
        WHERE metric_name ILIKE %s
          AND triggered_at > NOW() - INTERVAL '%s hours'
          AND suppressed = FALSE
        ORDER BY triggered_at ASC
    """

    with conn.cursor() as cur:
        cur.execute(raw_sql, params)
        series = cur.fetchall()

        cur.execute(anomaly_sql, [f"%{metric_name}%", hours])
        anomalies = cur.fetchall()

    return {
        "metric_name": metric_name,
        "series":      [dict(r) for r in series],
        "anomalies":   [dict(a) for a in anomalies],
        "point_count": len(series),
    }