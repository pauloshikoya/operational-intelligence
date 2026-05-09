# api/routers/ask.py

"""
Scenario explorer endpoint.

POST /ask  — ask a natural language question about the data

This is a simple but powerful feature. The analyst types:
  "What happened with energy prices in the last 7 days?"
  "Which metrics are most anomalous right now?"
  "Is the Rotterdam port disruption related to the oil spike?"

We pull relevant context from the DB and ask Claude to answer
using only that data — no hallucination, grounded responses.
"""

import os
import json
import logging
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
import anthropic
import psycopg2.extras

from api.dependencies import get_db, verify_api_key

load_dotenv()
logger  = logging.getLogger("api.ask")
router  = APIRouter(prefix="/ask", tags=["ask"])
client  = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


class AskRequest(BaseModel):
    question: str
    hours:    int = 24    # how many hours of context to include


def build_data_context(conn, hours: int) -> str:
    """
    Pull a concise data snapshot from the DB to ground Claude's answer.
    We deliberately keep this compact — we want a focused answer,
    not a full anomaly narration.
    """
    # Recent anomalies
    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                metric_name, anomaly_score, severity,
                narrative, triggered_at
            FROM anomalies
            WHERE triggered_at > NOW() - INTERVAL '%s hours'
              AND suppressed = FALSE
            ORDER BY anomaly_score DESC
            LIMIT 10
        """, (hours,))
        anomalies = [dict(r) for r in cur.fetchall()]

    # Current metric states
    with conn.cursor() as cur:
        cur.execute("""
            SELECT DISTINCT ON (metric_name)
                metric_name, value_raw, z_score,
                pct_change_1d, pct_change_7d, computed_at
            FROM features
            WHERE computed_at > NOW() - INTERVAL '2 hours'
            ORDER BY metric_name, computed_at DESC
        """)
        metrics = [dict(r) for r in cur.fetchall()]

    # Format compactly
    anomaly_text = "No anomalies detected in this period."
    if anomalies:
        lines = []
        for a in anomalies:
            ts = a["triggered_at"]
            if hasattr(ts, "isoformat"):
                ts = ts.isoformat()
            summary = a["narrative"][:100] if a["narrative"] else "No narrative yet"
            lines.append(
                f"  {a['metric_name']:35s} "
                f"score={a['anomaly_score']:.2f}  "
                f"severity={a['severity']:8s}  "
                f"at={ts}\n"
                f"    summary: {summary}"
            )
        anomaly_text = "\n".join(lines)

    metric_text = "No metric data available."
    if metrics:
        lines = []
        for m in metrics:
            lines.append(
                f"  {m['metric_name']:35s} "
                f"value={float(m['value_raw'] or 0):>8.3f}  "
                f"z={float(m['z_score'] or 0):+.2f}  "
                f"1d={float(m['pct_change_1d'] or 0):+.1f}%  "
                f"7d={float(m['pct_change_7d'] or 0):+.1f}%"
            )
        metric_text = "\n".join(lines)

    return f"""
CURRENT METRIC STATE:
{metric_text}

RECENT ANOMALIES (last {hours} hours):
{anomaly_text}
"""


@router.post(
    "",
    summary="Ask a question about the data",
    description=(
        "Ask a natural language question. Claude answers using "
        "only data from your pipeline — no hallucination."
    ),
)
def ask_question(
    body:    AskRequest,
    conn     = Depends(get_db),
    _api_key = Depends(verify_api_key),
):
    if len(body.question.strip()) < 5:
        raise HTTPException(
            status_code=400,
            detail="Question too short"
        )

    if len(body.question) > 500:
        raise HTTPException(
            status_code=400,
            detail="Question too long (max 500 chars)"
        )

    # Build data context
    data_context = build_data_context(conn, body.hours)

    prompt = f"""You are an operational intelligence analyst.
Answer the following question using ONLY the data provided below.
If the data doesn't contain enough information to answer, say so explicitly.
Be concise and precise. Reference specific metrics and values.

DATA CONTEXT:
{data_context}

QUESTION: {body.question}

Answer in 2-4 sentences. Be direct. Reference specific numbers from the data."""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=400,
            temperature=0.1,    # very low — we want factual, not creative
            messages=[{"role": "user", "content": prompt}],
        )
        answer = response.content[0].text.strip()

    except Exception as e:
        logger.error(f"Claude API error in /ask: {e}")
        raise HTTPException(
            status_code=503,
            detail="AI service temporarily unavailable"
        )

    return {
        "question":     body.question,
        "answer":       answer,
        "context_hours": body.hours,
        "tokens_used":  response.usage.input_tokens + response.usage.output_tokens,
    }