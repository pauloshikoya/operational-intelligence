# api/routers/stream.py

"""
Server-Sent Events (SSE) streaming endpoint.

GET /stream  — real-time anomaly event stream

The dashboard connects to this endpoint once and keeps the
connection open. Every time a new anomaly is detected, we
push an event to all connected clients instantly.

This is how the dashboard's live feed works without polling.

SSE is simpler than WebSockets for one-way server→client
communication, which is all we need here.
"""

import json
import asyncio
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse
import psycopg2
import psycopg2.extras

from api.dependencies import DATABASE_URL

logger = logging.getLogger("api.stream")
router = APIRouter(prefix="/stream", tags=["stream"])

# How often to check for new anomalies (seconds)
POLL_INTERVAL = 5


async def anomaly_event_generator(request):
    """
    Async generator that polls for new anomalies and yields
    SSE events to the connected client.

    The client connects once. We loop, checking for anomalies
    newer than the last one we sent, and push them as events.
    When the client disconnects, the loop exits cleanly.
    """
    last_id   = 0    # track the last anomaly ID we sent
    heartbeat = 0    # counter for periodic heartbeat events

    # Send an initial connection confirmation event
    yield {
        "event": "connected",
        "data": json.dumps({
            "message":      "Stream connected",
            "connected_at": datetime.now(timezone.utc).isoformat(),
        })
    }

    while True:
        # Check if client disconnected
        if await request.is_disconnected():
            logger.info("SSE client disconnected")
            break

        try:
            # Query for anomalies newer than the last one we sent
            conn = psycopg2.connect(
                DATABASE_URL,
                cursor_factory=psycopg2.extras.RealDictCursor
            )

            with conn.cursor() as cur:
                cur.execute("""
                    SELECT
                        id,
                        source,
                        metric_name,
                        anomaly_score,
                        severity,
                        narrative,
                        triggered_at,
                        narrative_json -> 'signals' AS signals
                    FROM anomalies
                    WHERE id > %s
                      AND suppressed = FALSE
                    ORDER BY id ASC
                    LIMIT 10
                """, (last_id,))
                new_anomalies = cur.fetchall()

            conn.close()

            # Push each new anomaly as an SSE event
            for anomaly in new_anomalies:
                row = dict(anomaly)

                # Convert datetime to string for JSON serialisation
                if row.get("triggered_at"):
                    row["triggered_at"] = row["triggered_at"].isoformat()

                yield {
                    "event": "anomaly",
                    "id":    str(row["id"]),
                    "data":  json.dumps(row),
                }
                last_id = max(last_id, row["id"])

        except Exception as e:
            logger.error(f"SSE stream error: {e}")
            yield {
                "event": "error",
                "data":  json.dumps({"error": str(e)}),
            }

        # Send a heartbeat every 30 seconds to keep connection alive
        # Some proxies and browsers close idle connections
        heartbeat += 1
        if heartbeat % (30 // POLL_INTERVAL) == 0:
            yield {
                "event": "heartbeat",
                "data":  json.dumps({
                    "ts":      datetime.now(timezone.utc).isoformat(),
                    "last_id": last_id,
                }),
            }

        await asyncio.sleep(POLL_INTERVAL)


@router.get(
    "",
    summary="Live anomaly stream",
    description=(
        "Server-Sent Events stream. Connect once and receive "
        "anomaly events in real time as they are detected."
    ),
)
async def stream_anomalies(request):
    return EventSourceResponse(anomaly_event_generator(request))