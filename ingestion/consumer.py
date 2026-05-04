# ingestion/consumer.py

import json
import time
import logging
import psycopg2.extras
from confluent_kafka import Consumer, KafkaError, KafkaException
from ingestion.config import (
    KAFKA_CONSUMER_CONFIG,
    TOPIC_COMMODITY,
    TOPIC_WEATHER,
    DATABASE_URL,
)
from ingestion.db import get_connection, insert_raw_data

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("consumer")


# ── Validation ────────────────────────────────────────────────────────────────

# These are the fields every message MUST have.
# If any are missing, we reject the message and log it.
REQUIRED_FIELDS = {"source", "domain", "metric_name", "value", "ingested_at"}


def validate_message(data: dict) -> tuple[bool, str]:
    """
    Check a parsed message has everything we need.

    Returns:
        (True, "ok")              if valid
        (False, "reason string")  if invalid
    """
    # Check all required fields exist
    missing = REQUIRED_FIELDS - data.keys()
    if missing:
        return False, f"Missing fields: {missing}"

    # Check value is actually a number
    try:
        float(data["value"])
    except (TypeError, ValueError):
        return False, f"Value is not numeric: {data['value']}"

    # Check value is not absurd (basic sanity check)
    value = float(data["value"])
    if value < -1_000_000 or value > 1_000_000_000:
        return False, f"Value out of sane range: {value}"

    return True, "ok"


# ── Message handler ───────────────────────────────────────────────────────────

def handle_message(data: dict, conn) -> bool:
    """
    Process one validated message — write it to the database.

    Args:
        data : the parsed and validated message dict
        conn : open database connection

    Returns:
        True if written successfully, False if it failed
    """
    try:
        insert_raw_data(
            conn=conn,
            source=data["source"],
            domain=data["domain"],
            metric_name=data["metric_name"],
            value=float(data["value"]),
            unit=data.get("unit"),          # optional field
            raw_json=data.get("raw"),       # full raw payload
        )
        return True

    except Exception as e:
        logger.error(f"DB write failed for {data.get('metric_name')}: {e}")
        # Roll back so the connection is in a clean state for the next message
        conn.rollback()
        return False


# ── Dead letter log ───────────────────────────────────────────────────────────

def log_dead_letter(raw_value: bytes, reason: str):
    """
    Log messages we couldn't process to a file.
    This is called a 'dead letter queue' pattern.
    In production this would go to a separate Kafka topic.
    For now, a log file is fine.
    """
    with open("logs/dead_letters.log", "a") as f:
        f.write(json.dumps({
            "reason":    reason,
            "raw":       raw_value.decode("utf-8", errors="replace"),
            "timestamp": time.time(),
        }) + "\n")


# ── Main consumer loop ────────────────────────────────────────────────────────

def run():
    """
    Main consumer loop.

    Subscribes to all data topics, reads messages one by one,
    validates them, writes to DB, and commits offsets.

    Runs forever until interrupted with Ctrl+C.
    """

    # Make sure logs directory exists
    import os
    os.makedirs("logs", exist_ok=True)

    consumer = Consumer(KAFKA_CONSUMER_CONFIG)

    # Subscribe to both data topics
    topics = [TOPIC_COMMODITY, TOPIC_WEATHER]
    consumer.subscribe(topics)
    logger.info(f"Consumer subscribed to: {topics}")

    # Open one long-lived database connection
    # We reuse this across messages for efficiency
    conn = get_connection()
    logger.info("Database connection established")

    processed = 0    # count of successfully processed messages
    failed    = 0    # count of failed messages

    try:
        while True:
            # poll() waits up to 1 second for a new message
            # Returns None if no message arrived in that time
            msg = consumer.poll(timeout=1.0)

            if msg is None:
                # No message yet — just loop and wait
                continue

            # KafkaError on the message itself means something
            # went wrong at the broker level
            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    # We've read to the end of the partition — not an error
                    # Just means we're caught up and waiting for new messages
                    logger.debug(
                        f"Reached end of partition: "
                        f"{msg.topic()} [{msg.partition()}]"
                    )
                else:
                    # Real error — log it and keep going
                    logger.error(f"Kafka error: {msg.error()}")
                continue

            # ── Parse ─────────────────────────────────────────
            try:
                data = json.loads(msg.value().decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                logger.error(f"Could not parse message: {e}")
                log_dead_letter(msg.value(), f"parse_error: {e}")
                # Commit anyway so we don't get stuck on this message
                consumer.commit(msg)
                failed += 1
                continue

            # ── Validate ──────────────────────────────────────
            valid, reason = validate_message(data)
            if not valid:
                logger.warning(
                    f"Invalid message rejected ({reason}): "
                    f"{data.get('metric_name', 'unknown')}"
                )
                log_dead_letter(msg.value(), reason)
                consumer.commit(msg)
                failed += 1
                continue

            # ── Write to database ─────────────────────────────
            success = handle_message(data, conn)

            if success:
                # Only commit offset AFTER successful DB write
                # This guarantees at-least-once delivery:
                # if the DB write fails, we'll retry this message
                consumer.commit(msg)
                processed += 1
                logger.info(
                    f"✓ {data['metric_name']} = {data['value']} "
                    f"[{data['source']}] "
                    f"(total processed: {processed})"
                )
            else:
                # Don't commit — message will be redelivered
                logger.warning(
                    f"✗ Failed to process {data.get('metric_name')} "
                    f"— will retry"
                )
                failed += 1

                # Brief pause to avoid hammering a broken DB connection
                time.sleep(2)

                # Try to reconnect to DB in case connection dropped
                try:
                    conn.close()
                except Exception:
                    pass
                conn = get_connection()

    except KeyboardInterrupt:
        logger.info("Shutting down consumer...")

    finally:
        # Always clean up properly
        consumer.close()
        conn.close()
        logger.info(
            f"Consumer stopped. "
            f"Processed: {processed} | Failed: {failed}"
        )


if __name__ == "__main__":
    run()