# api/routers/anomalies.py

"""
Anomalies endpoints.

GET /anomalies        — paginated list with filters
GET /anomalies/{id}   — single anomaly with full narrative
"""

import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from api.dependencies import get_db, verify_api_key

router = APIRouter(prefix="/anomalies", tags=["anomalies"])


@router.get(
    "",
    summary="List anomalies",
    description=(
        "Returns detected anomalies, newest first. "
        "Filter by severity, source, metric, or time range."
    ),
)
def list_anomalies(
    # ── Filters ───────────────────────────────────────────────────────────
    severity:    Optional[str]  = Query(None,  description="Filter by severity: low, medium, high, critical"),
    source:      Optional[str]  = Query(None,  description="Filter by data source e.g. alpha_vantage"),
    metric_name: Optional[str]  = Query(None,  description="Filter by metric name e.g. crude_oil_wti"),
    hours:       Optional[int]  = Query(24,    description="How many hours back to look (default 24)"),
    min_score:   Optional[float]= Query(0.0,   description="Minimum anomaly score 0.0–1.0"),
    has_narrative: Optional[bool]= Query(None, description="Filter to only anomalies with AI narratives"),
    # ── Pagination ────────────────────────────────────────────────────────
    limit:  int = Query(50,  ge=1, le=200, description="Max results to return"),
    offset: int = Query(0,   ge=0,         description="Offset for pagination"),
    # ── Auth + DB ─────────────────────────────────────────────────────────
    conn      = Depends(get_db),
    _api_key  = Depends(verify_api_key),
):
    # Build the WHERE clause dynamically based on provided filters
    conditions = [
        "triggered_at > NOW() - INTERVAL '%s hours'" ,
        "anomaly_score >= %s",
        "suppressed = FALSE",
    ]
    params = [hours, min_score]

    if severity:
        conditions.append("severity = %s")
        params.append(severity)

    if source:
        conditions.append("source = %s")
        params.append(source)

    if metric_name:
        conditions.append("metric_name ILIKE %s")
        params.append(f"%{metric_name}%")

    if has_narrative is True:
        conditions.append("narrative IS NOT NULL")
    elif has_narrative is False:
        conditions.append("narrative IS NULL")

    where = " AND ".join(conditions)

    sql = f"""
        SELECT
            id,
            source,
            metric_name,
            anomaly_score,
            severity,
            narrative,
            triggered_at,
            is_active,
            -- Extract just the signals array for the list view
            narrative_json -> 'signals' AS signals
        FROM anomalies
        WHERE {where}
        ORDER BY triggered_at DESC
        LIMIT %s OFFSET %s
    """
    params.extend([limit, offset])

    with conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()

    # Get total count for pagination metadata
    count_sql = f"SELECT COUNT(*) FROM anomalies WHERE {where}"
    with conn.cursor() as cur:
        cur.execute(count_sql, params[:-2])   # exclude limit/offset
        total = cur.fetchone()["count"]

    return {
        "anomalies": [dict(r) for r in rows],
        "pagination": {
            "total":  total,
            "limit":  limit,
            "offset": offset,
            "has_more": (offset + limit) < total,
        }
    }


@router.get(
    "/{anomaly_id}",
    summary="Get anomaly detail",
    description="Returns a single anomaly with full AI narrative and detection detail.",
)
def get_anomaly(
    anomaly_id: int,
    conn     = Depends(get_db),
    _api_key = Depends(verify_api_key),
):
    sql = """
        SELECT
            a.*,
            -- Join with recent feature data for context
            f.value_7d_avg,
            f.value_7d_stddev,
            f.pct_change_1d,
            f.pct_change_7d
        FROM anomalies a
        LEFT JOIN LATERAL (
            SELECT value_7d_avg, value_7d_stddev,
                   pct_change_1d, pct_change_7d
            FROM features
            WHERE source      = a.source
              AND metric_name = a.metric_name
              AND computed_at <= a.triggered_at
            ORDER BY computed_at DESC
            LIMIT 1
        ) f ON TRUE
        WHERE a.id = %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, (anomaly_id,))
        row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail=f"Anomaly {anomaly_id} not found")

    # Also fetch the 14 raw data points around the anomaly time
    # so the dashboard can render a chart with the anomaly marked
    history_sql = """
        SELECT value, unit, ingested_at
        FROM raw_data
        WHERE source      = %s
          AND metric_name = %s
          AND ingested_at BETWEEN %s - INTERVAL '7 days'
                              AND %s + INTERVAL '1 day'
        ORDER BY ingested_at ASC
        LIMIT 30
    """
    with conn.cursor() as cur:
        cur.execute(history_sql, (
            row["source"],
            row["metric_name"],
            row["triggered_at"],
            row["triggered_at"],
        ))
        history = cur.fetchall()

    result = dict(row)
    result["value_history"] = [dict(h) for h in history]
    return result