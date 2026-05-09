# detection/narrator.py

"""
LLM Narrator
─────────────
Calls the Claude API to generate structured intelligence
reports for detected anomalies, then writes them back
to the database.

Design decisions:
- We use claude-sonnet-4-5: best balance of quality and speed.
  Opus would be overkill for this structured extraction task.
  Haiku would sometimes produce lower-quality reasoning on complex
  multi-metric patterns.

- We set temperature=0.2: low enough for consistent structured output,
  slightly above 0 to allow natural language variation in phrasing.
  temperature=0 can sometimes produce robotic, repetitive narratives.

- We validate the JSON response before writing to DB. If Claude returns
  malformed JSON (rare but possible), we log the failure and continue
  rather than crashing the whole pipeline.

- We track cost per narration. At ~$3/M input tokens and ~$15/M output
  tokens, each narration costs roughly $0.002-0.005. We log this so
  you can show cost awareness in interviews.
"""

import json
import time
import os
import logging
from dotenv import load_dotenv
import anthropic
import psycopg2.extras
from datetime import datetime, timezone

from ingestion.config import DATABASE_URL
from ingestion.db import get_connection
from detection.context_builder import build as build_context

load_dotenv()  # ensure env vars are loaded
from detection.prompt_builder import build_prompt

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("narrator")

# Narration runs on a separate schedule from detection
# We don't narrate every anomaly immediately — we batch narrations
# to avoid hammering the API and to let duplicate anomalies get
# suppressed before we waste API calls on them
NARRATION_INTERVAL = 180   # check for un-narrated anomalies every 3 min
NARRATION_DELAY    = 60    # wait 60s after anomaly before narrating
                            # (gives suppression logic time to work)


# ── Cost tracking ─────────────────────────────────────────────────────────────

# Approximate token costs for claude-sonnet-4-5
# Update these if Anthropic changes pricing
COST_PER_INPUT_TOKEN  = 3.0   / 1_000_000   # $3 per million input tokens
COST_PER_OUTPUT_TOKEN = 15.0  / 1_000_000   # $15 per million output tokens


def estimate_cost(input_tokens: int, output_tokens: int) -> float:
    return (
        input_tokens  * COST_PER_INPUT_TOKEN +
        output_tokens * COST_PER_OUTPUT_TOKEN
    )


# ── Fetch un-narrated anomalies ───────────────────────────────────────────────

def get_pending_anomalies(conn) -> list[dict]:
    """
    Find anomalies that:
    - Have no narrative yet (narrative IS NULL)
    - Are not suppressed
    - Were triggered at least NARRATION_DELAY seconds ago
      (to let the suppression window close first)
    """
    sql = """
        SELECT
            id,
            source,
            metric_name,
            anomaly_score,
            narrative_json,
            triggered_at
        FROM anomalies
        WHERE narrative   IS NULL
          AND suppressed  = FALSE
          AND triggered_at < NOW() - INTERVAL '%s seconds'
        ORDER BY anomaly_score DESC    -- narrate most severe first
        LIMIT 10                       -- process max 10 per cycle
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, (NARRATION_DELAY,))
        return [dict(r) for r in cur.fetchall()]


# ── Claude API call ───────────────────────────────────────────────────────────

def call_claude(prompt: str, client: anthropic.Anthropic) -> dict:
    """
    Call the Claude API and return the parsed JSON response.

    Args:
        prompt: the fully built prompt string
        client: authenticated Anthropic client

    Returns:
        dict: parsed JSON from Claude's response

    Raises:
        ValueError: if response cannot be parsed as valid JSON
        anthropic.APIError: if the API call fails
    """
    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=4000,
        temperature=0.2,    # low temperature for consistent structured output
        system=(
            "You are a precision operational intelligence analyst. "
            "You respond ONLY with valid JSON. "
            "Never include markdown, code fences, or any text outside "
            "the JSON object. Your JSON must be parseable by json.loads()."
        ),
        messages=[
            {"role": "user", "content": prompt}
        ],
    )

    # ── Extract raw text ───────────────────────────────────────────────────
    raw = response.content[0].text    # do NOT strip yet

    print(f"\nDEBUG — raw length before strip: {len(raw)}")
    print(f"DEBUG — first 50 chars: {repr(raw[:50])}")

    # ── Strip markdown fences explicitly ───────────────────────────────────
    raw = raw.strip()

    if raw.startswith("```"):
        # Remove opening fence line (```json or ```)
        raw = raw.split("\n", 1)[1]        # drop first line
        # Remove closing fence
        if raw.endswith("```"):
            raw = raw[: raw.rfind("```")]  # drop last ```
        raw = raw.strip()

    print(f"DEBUG — raw length after strip: {len(raw)}")
    print(f"DEBUG — first 50 chars after strip: {repr(raw[:50])}")


# ── Response validation ───────────────────────────────────────────────────────

REQUIRED_KEYS = {
    "summary",
    "what_changed",
    "likely_causes",
    "pattern_assessment",
    "recommended_actions",
    "data_sources_used",
    "caveats",
    "severity_reasoning",
}


def validate_narrative(narrative: dict) -> tuple[bool, str]:
    """
    Check the parsed narrative has all required fields
    and minimum content quality.
    """
    missing = REQUIRED_KEYS - narrative.keys()
    if missing:
        return False, f"Missing keys: {missing}"

    if not narrative.get("likely_causes"):
        return False, "likely_causes is empty"

    if not narrative.get("recommended_actions"):
        return False, "recommended_actions is empty"

    if len(narrative.get("caveats", [])) < 1:
        return False, "No caveats provided"

    if len(narrative.get("summary", "")) < 50:
        return False, "Summary too short — likely a low-quality response"

    return True, "ok"


# ── Database write ────────────────────────────────────────────────────────────

def save_narrative(conn, anomaly_id: int, narrative: dict,
                   input_tokens: int, output_tokens: int):
    """
    Write the narrative back to the anomalies table.
    We store both:
    - narrative_json: the full structured JSON (for the API/dashboard)
    - narrative: plain text summary (for quick display and search)
    """

    # Add metadata to the stored JSON so we can audit it later
    narrative_with_meta = {
        **narrative,
        "_meta": {
            "model":         "claude-sonnet-4-5",
            "narrated_at":   datetime.now(timezone.utc).isoformat(),
            "input_tokens":  input_tokens,
            "output_tokens": output_tokens,
            "cost_usd":      estimate_cost(input_tokens, output_tokens),
        }
    }

    sql = """
        UPDATE anomalies
        SET
            narrative      = %s,
            narrative_json = %s
        WHERE id = %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, (
            narrative["summary"],                          # plain text
            psycopg2.extras.Json(narrative_with_meta),    # full JSON
            anomaly_id,
        ))
    conn.commit()
    logger.info(f"Narrative saved for anomaly {anomaly_id}")


# ── Main narration function ───────────────────────────────────────────────────

def narrate_anomaly(conn, anomaly: dict,
                    client: anthropic.Anthropic) -> bool:
    """
    Run the full narration pipeline for one anomaly.

    Returns True if narration succeeded, False if it failed.
    """
    anomaly_id  = anomaly["id"]
    source      = anomaly["source"]
    metric_name = anomaly["metric_name"]

    logger.info(
        f"Narrating anomaly {anomaly_id}: "
        f"{metric_name} (score={anomaly['anomaly_score']:.3f})"
    )

    # ── 1. Reconstruct detector results from stored JSON ──────────────────
    # The detection engine stored detector outputs in narrative_json
    stored = anomaly.get("narrative_json") or {}
    detector_results = {
        "zscore":  stored.get("zscore_detail",  {"signal": "N/A", "score": 0}),
        "cusum":   stored.get("cusum_detail",   {"signal": "N/A", "score": 0}),
        "iforest": stored.get("iforest_detail", {"signal": "N/A", "score": 0}),
    }
    combined_result = {
        "final_score": float(anomaly["anomaly_score"]),
        "severity":    stored.get("severity", "medium"),
        "dominant":    stored.get("dominant",  "zscore"),
        "signals":     stored.get("signals",   []),
    }

    # ── 2. Build context ──────────────────────────────────────────────────
    try:
        context = build_context(
            conn, anomaly_id, source, metric_name,
            combined_result, detector_results,
        )
    except Exception as e:
        logger.error(f"Context build failed for {anomaly_id}: {e}")
        return False

    # ── 3. Build prompt ───────────────────────────────────────────────────
    prompt = build_prompt(context)

    # ── 4. Call Claude ────────────────────────────────────────────────────
    try:
        narrative, input_tokens, output_tokens = call_claude(prompt, client)
    except Exception as e:
        logger.error(f"Claude API call failed for {anomaly_id}: {e}")
        return False

    # ── 5. Validate ───────────────────────────────────────────────────────
    valid, reason = validate_narrative(narrative)
    if not valid:
        logger.error(
            f"Narrative validation failed for {anomaly_id}: {reason}"
        )
        return False

    # ── 6. Save ───────────────────────────────────────────────────────────
    try:
        save_narrative(conn, anomaly_id, narrative,
                       input_tokens, output_tokens)
    except Exception as e:
        logger.error(f"Failed to save narrative for {anomaly_id}: {e}")
        return False

    logger.info(
        f"✓ Narrated anomaly {anomaly_id}: "
        f"{metric_name} | "
        f"{len(narrative['likely_causes'])} causes | "
        f"{len(narrative['recommended_actions'])} actions"
    )

    # Log the summary so you can see it in the terminal
    logger.info(f"  SUMMARY: {narrative['summary'][:120]}...")

    return True


# ── Main loop ─────────────────────────────────────────────────────────────────
def run():
    """
    Narrator main loop.
    Polls for un-narrated anomalies and processes them.
    """
    conn   = get_connection()

    import os
    from dotenv import load_dotenv
    load_dotenv()
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))   # reads ANTHROPIC_API_KEY from env

    logger.info("Narrator started")

    total_narrated = 0
    total_cost     = 0.0

    while True:
        pending = get_pending_anomalies(conn)

        if not pending:
            logger.debug(
                f"No pending anomalies. "
                f"Total narrated: {total_narrated} | "
                f"Total cost: ${total_cost:.4f}"
            )
            time.sleep(NARRATION_INTERVAL)
            continue

        logger.info(f"Found {len(pending)} anomalies to narrate")

        for anomaly in pending:
            success = narrate_anomaly(conn, anomaly, client)

            if success:
                total_narrated += 1
            else:
                # Mark as suppressed so we don't retry forever
                # on consistently failing anomalies
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE anomalies SET suppressed = TRUE "
                        "WHERE id = %s AND narrative IS NULL",
                        (anomaly["id"],)
                    )
                conn.commit()

            # Pause between API calls to respect rate limits
            time.sleep(3)

        time.sleep(NARRATION_INTERVAL)


if __name__ == "__main__":
    run()