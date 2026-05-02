# ingestion/config.py

import os
from dotenv import load_dotenv

load_dotenv()

# ── Database ──────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL")

# ── Redpanda / Kafka ──────────────────────────────────
KAFKA_BROKER = os.getenv("KAFKA_BROKER", "localhost:9092")

KAFKA_PRODUCER_CONFIG = {
    "bootstrap.servers": KAFKA_BROKER,
    "acks": "all",            # wait for all replicas to confirm
    "retries": 3,             # retry failed sends up to 3 times
    "retry.backoff.ms": 500,  # wait 500ms between retries
}

KAFKA_CONSUMER_CONFIG = {
    "bootstrap.servers": KAFKA_BROKER,
    "group.id": "intelligence-consumer-group",
    "auto.offset.reset": "earliest",   # start from beginning if no offset
    "enable.auto.commit": False,        # we commit manually after DB write
}

# ── Redis ─────────────────────────────────────────────
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

# ── External APIs ─────────────────────────────────────
ALPHA_VANTAGE_KEY = os.getenv("ALPHA_VANTAGE_KEY")
ALPHA_VANTAGE_BASE = "https://www.alphavantage.co/query"

OPEN_METEO_BASE = "https://api.open-meteo.com/v1/forecast"

# ── Topics ────────────────────────────────────────────
TOPIC_COMMODITY   = "commodity-prices"
TOPIC_WEATHER     = "weather-signals"
TOPIC_ANOMALIES   = "anomaly-events"

# ── Polling intervals (seconds) ───────────────────────
COMMODITY_POLL_INTERVAL = 300   # every 5 minutes
WEATHER_POLL_INTERVAL   = 600   # every 10 minutes