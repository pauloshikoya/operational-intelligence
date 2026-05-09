# api/routers/health.py

"""
Health endpoint.

GET /health  — system status, pipeline health, data freshness

This endpoint is important for three reasons:
1. Your dashboard shows a live system health panel
2. Interviewers will ask "how do you know if your pipeline is healthy?"
   This is your answer.
3. In production this would be polled by monitoring systems
"""

from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from api.dependencies import get_db, get_redis

router = APIRouter(prefix="/health", tags=["health"])


def check_data_freshness(conn, source: str, max_age_minutes: int) -> dict:
    """
    Check when a data source last successfully ingested data.
    Returns a status dict with green/amber/red health indicator.
    """
    sql = """
        SELECT MAX(ingested_at) AS last_ingested
        FROM raw_data
        WHERE source = %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, (source,))
        row = cur.fetchone()

    last = row["last_ingested"] if row else None

    if last is None:
        return {"status": "red", "message": "No data received yet", "last_ingested": None}

    # Make last timezone-aware if it isn't already
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)

    age_minutes = (datetime.now(timezone.utc) - last).total_seconds() / 60

    if age_minutes <= max_age_minutes:
        status = "green"
        message = f"Healthy — last ingested {age_minutes:.0f} min ago"
    elif age_minutes <= max_age_minutes * 2:
        status = "amber"
        message = f"Delayed — last ingested {age_minutes:.0f} min ago"
    else:
        status = "red"
        message = f"Stale — last ingested {age_minutes:.0f} min ago"

    return {
        "status":        status,
        "message":       message,
        "last_ingested": last.isoformat(),
        "age_minutes":   round(age_minutes, 1),
    }


@router.get(
    "",
    summary="System health",
    description="Returns health status of all pipeline components.",
)
def get_health(
    conn         = Depends(get_db),
    redis_client = Depends(get_redis),
):
    health = {}

    # ── Database ───────────────────────────────────────────────────────────
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
        health["database"] = {"status": "green", "message": "Connected"}
    except Exception as e:
        health["database"] = {"status": "red", "message": str(e)}

    # ── Redis ──────────────────────────────────────────────────────────────
    try:
        redis_client.ping()
        cached_keys = len(redis_client.keys("features:*"))
        health["redis"] = {
            "status":      "green",
            "message":     "Connected",
            "cached_keys": cached_keys,
        }
    except Exception as e:
        health["redis"] = {"status": "red", "message": str(e)}

    # ── Data sources ───────────────────────────────────────────────────────
    health["data_sources"] = {
        "alpha_vantage": check_data_freshness(conn, "alpha_vantage", max_age_minutes=15),
        "open_meteo":    check_data_freshness(conn, "open_meteo",    max_age_minutes=20),
    }

    # ── Pipeline stats (last 24 hours) ─────────────────────────────────────
    with conn.cursor() as cur:
        cur.execute("""
            SELECT COUNT(*) AS raw_count
            FROM raw_data
            WHERE ingested_at > NOW() - INTERVAL '24 hours'
        """)
        raw_count = cur.fetchone()["raw_count"]

        cur.execute("""
            SELECT COUNT(*) AS feature_count
            FROM features
            WHERE computed_at > NOW() - INTERVAL '24 hours'
        """)
        feature_count = cur.fetchone()["feature_count"]

        cur.execute("""
            SELECT
                COUNT(*)                                          AS total,
                COUNT(*) FILTER (WHERE severity = 'critical')    AS critical,
                COUNT(*) FILTER (WHERE severity = 'high')        AS high,
                COUNT(*) FILTER (WHERE severity = 'medium')      AS medium,
                COUNT(*) FILTER (WHERE narrative IS NOT NULL)    AS narrated
            FROM anomalies
            WHERE triggered_at > NOW() - INTERVAL '24 hours'
              AND suppressed = FALSE
        """)
        anomaly_stats = dict(cur.fetchone())

    health["pipeline_24h"] = {
        "raw_data_points":    raw_count,
        "feature_computations": feature_count,
        "anomalies":          anomaly_stats,
    }

    # ── Overall status ─────────────────────────────────────────────────────
    # Red if database or Redis is down — everything else is degraded not fatal
    all_statuses = [
        health["database"]["status"],
        health["redis"]["status"],
    ]
    if "red" in all_statuses:
        overall = "red"
    elif "amber" in all_statuses:
        overall = "amber"
    else:
        overall = "green"

    health["overall"]    = overall
    health["checked_at"] = datetime.now(timezone.utc).isoformat()

    return health