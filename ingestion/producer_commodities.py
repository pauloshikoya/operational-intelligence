# ingestion/producer_commodities.py

import json
import time
import logging
import requests
from datetime import datetime, timezone
from confluent_kafka import Producer
from ingestion.config import (
    ALPHA_VANTAGE_KEY,
    ALPHA_VANTAGE_BASE,
    KAFKA_PRODUCER_CONFIG,
    TOPIC_COMMODITY,
    COMMODITY_POLL_INTERVAL,
)

# ── Logging setup ─────────────────────────────────────────────────────────────
# Every script uses structured logging so you can see exactly what's happening
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("producer.commodities")


# ── Commodities to track ──────────────────────────────────────────────────────
# Alpha Vantage function name → human label
# These are the commodities most sensitive to supply chain disruption
COMMODITIES = {
    "WTI":          "crude_oil_wti",       # West Texas Intermediate crude oil
    "BRENT":        "crude_oil_brent",     # Brent crude oil (global benchmark)
    "NATURAL_GAS":  "natural_gas",         # Energy / manufacturing input
    "COPPER":       "copper",              # Industrial bellwether commodity
    "WHEAT":        "wheat",               # Food supply chain
    "ALUMINUM":     "aluminum",            # Manufacturing / packaging
}


def fetch_commodity(function: str) -> dict | None:
    """
    Fetch the latest price for one commodity from Alpha Vantage.

    Args:
        function: Alpha Vantage commodity function name e.g. "WTI"

    Returns:
        dict with 'date' and 'value' keys, or None if request failed
    """
    params = {
        "function": function,
        "interval": "monthly",    # daily burns API quota; monthly is fine
        "apikey": ALPHA_VANTAGE_KEY,
    }

    try:
        response = requests.get(
            ALPHA_VANTAGE_BASE,
            params=params,
            timeout=10    # fail fast if API is slow
        )
        response.raise_for_status()   # raises exception on 4xx/5xx
        data = response.json()

        # Alpha Vantage wraps data in a "data" array
        # Each item has "date" and "value"
        if "data" not in data or not data["data"]:
            logger.warning(f"No data returned for {function}")
            return None

        latest = data["data"][0]   # most recent entry is first

        return {
            "date":  latest["date"],
            "value": float(latest["value"]),
            "unit":  data.get("unit", "USD"),
        }

    except requests.exceptions.Timeout:
        logger.error(f"Timeout fetching {function}")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Request failed for {function}: {e}")
        return None
    except (KeyError, ValueError) as e:
        logger.error(f"Failed to parse response for {function}: {e}")
        return None


def build_message(function: str, metric_name: str, fetched: dict) -> dict:
    """
    Build a clean, structured message to send to Redpanda.
    Every message has the same shape so consumers can rely on it.

    Args:
        function    : Alpha Vantage function name
        metric_name : our internal label for this metric
        fetched     : the dict returned by fetch_commodity()

    Returns:
        dict — the message payload
    """
    return {
        "source":       "alpha_vantage",
        "domain":       "supply_chain",
        "metric_name":  metric_name,
        "value":        fetched["value"],
        "unit":         fetched["unit"],
        "data_date":    fetched["date"],
        "ingested_at":  datetime.now(timezone.utc).isoformat(),
        "raw": {
            "function": function,
            "value":    fetched["value"],
            "date":     fetched["date"],
        }
    }


def on_delivery(err, msg):
    """
    Callback function — Redpanda calls this after each message is sent.
    Logs success or failure so we know every message's fate.
    """
    if err:
        logger.error(f"Message delivery FAILED: {err}")
    else:
        logger.info(
            f"Message delivered → topic={msg.topic()} "
            f"partition={msg.partition()} offset={msg.offset()}"
        )


def run():
    """
    Main producer loop.
    Runs forever: fetch all commodities → send to Redpanda → wait → repeat.
    """
    producer = Producer(KAFKA_PRODUCER_CONFIG)
    logger.info("Commodity producer started")

    while True:
        logger.info("── Starting commodity fetch cycle ──")

        for function, metric_name in COMMODITIES.items():
            logger.info(f"Fetching {metric_name} ({function})...")

            fetched = fetch_commodity(function)

            if fetched is None:
                logger.warning(f"Skipping {metric_name} — fetch returned None")
                continue

            message = build_message(function, metric_name, fetched)

            # Send to Redpanda
            # key=metric_name ensures messages for the same metric
            # always go to the same partition (ordering guarantee)
            producer.produce(
                topic=TOPIC_COMMODITY,
                key=metric_name,
                value=json.dumps(message),
                callback=on_delivery,
            )

            logger.info(f"Queued: {metric_name} = {fetched['value']} {fetched['unit']}")

            # Small delay between API calls to avoid rate limiting
            time.sleep(2)

        # Flush ensures all queued messages are actually sent
        # before we go to sleep
        producer.flush()
        logger.info(f"Cycle complete. Sleeping {COMMODITY_POLL_INTERVAL}s...")
        time.sleep(COMMODITY_POLL_INTERVAL)


if __name__ == "__main__":
    run()