# ingestion/producer_weather.py

import json
import time
import logging
import requests
from datetime import datetime, timezone
from confluent_kafka import Producer
from ingestion.config import (
    OPEN_METEO_BASE,
    KAFKA_PRODUCER_CONFIG,
    TOPIC_WEATHER,
    WEATHER_POLL_INTERVAL,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("producer.weather")


# ── Key logistics hubs to monitor ─────────────────────────────────────────────
# Weather disruptions at these locations directly impact global supply chains
LOCATIONS = [
    {"name": "rotterdam_port",   "lat": 51.9225, "lon": 4.4792},   # Europe's largest port
    {"name": "shanghai_port",    "lat": 31.2304, "lon": 121.4737}, # World's busiest port
    {"name": "houston_port",     "lat": 29.7604, "lon": -95.3698}, # US Gulf Coast energy hub
    {"name": "suez_region",      "lat": 30.0444, "lon": 31.2357},  # Critical shipping chokepoint
]

# Weather variables that signal supply chain disruption risk
WEATHER_VARIABLES = [
    "windspeed_10m_max",          # high winds shut ports
    "precipitation_sum",           # flooding disrupts logistics
    "temperature_2m_max",          # extreme heat affects storage/transport
    "weathercode",                 # WMO weather code (storms, fog etc)
]


def fetch_weather(location: dict) -> dict | None:
    """
    Fetch current weather for one logistics hub location.

    Args:
        location: dict with 'name', 'lat', 'lon' keys

    Returns:
        dict of weather variables, or None on failure
    """
    params = {
        "latitude":   location["lat"],
        "longitude":  location["lon"],
        "daily":      ",".join(WEATHER_VARIABLES),
        "timezone":   "UTC",
        "forecast_days": 1,     # just today
    }

    try:
        response = requests.get(OPEN_METEO_BASE, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        # Open-Meteo returns arrays — we want index [0] (today)
        daily = data["daily"]
        return {
            "windspeed_max":   daily["windspeed_10m_max"][0],
            "precipitation":   daily["precipitation_sum"][0],
            "temp_max":        daily["temperature_2m_max"][0],
            "weather_code":    daily["weathercode"][0],
            "date":            daily["time"][0],
        }

    except requests.exceptions.RequestException as e:
        logger.error(f"Weather fetch failed for {location['name']}: {e}")
        return None
    except (KeyError, IndexError) as e:
        logger.error(f"Weather parse failed for {location['name']}: {e}")
        return None


def disruption_score(weather: dict) -> float:
    """
    Convert raw weather data into a 0.0–1.0 disruption risk score.
    This is a simple heuristic — we'll replace this with ML later.

    Higher score = higher risk of supply chain disruption at this location.
    """
    score = 0.0

    # Wind: ports close above ~50 km/h sustained winds
    if weather["windspeed_max"] > 60:
        score += 0.4
    elif weather["windspeed_max"] > 40:
        score += 0.2

    # Precipitation: flooding risk above 20mm/day
    if weather["precipitation"] > 30:
        score += 0.3
    elif weather["precipitation"] > 15:
        score += 0.15

    # Temperature extremes affect cold chains and worker safety
    if weather["temp_max"] > 40 or weather["temp_max"] < -10:
        score += 0.2

    # WMO weather codes 95–99 = thunderstorms, 71–77 = heavy snow
    code = weather["weather_code"]
    if 95 <= code <= 99 or 71 <= code <= 77:
        score += 0.3

    return min(score, 1.0)   # cap at 1.0


def run():
    """Main weather producer loop."""
    producer = Producer(KAFKA_PRODUCER_CONFIG)
    logger.info("Weather producer started")

    while True:
        logger.info("── Starting weather fetch cycle ──")

        for location in LOCATIONS:
            logger.info(f"Fetching weather for {location['name']}...")

            weather = fetch_weather(location)
            if weather is None:
                continue

            score = disruption_score(weather)

            message = {
                "source":            "open_meteo",
                "domain":            "supply_chain",
                "metric_name":       f"weather_disruption_{location['name']}",
                "value":             score,          # primary value = disruption score
                "unit":              "risk_score",
                "ingested_at":       datetime.now(timezone.utc).isoformat(),
                "raw": {
                    "location":      location["name"],
                    "lat":           location["lat"],
                    "lon":           location["lon"],
                    "weather_date":  weather["date"],
                    "windspeed_max": weather["windspeed_max"],
                    "precipitation": weather["precipitation"],
                    "temp_max":      weather["temp_max"],
                    "weather_code":  weather["weather_code"],
                    "disruption_score": score,
                }
            }

            producer.produce(
                topic=TOPIC_WEATHER,
                key=location["name"],
                value=json.dumps(message),
                callback=lambda err, msg: logger.info(
                    f"Sent {location['name']} score={score:.2f}"
                ) if not err else logger.error(f"Failed: {err}"),
            )

        producer.flush()
        logger.info(f"Weather cycle complete. Sleeping {WEATHER_POLL_INTERVAL}s...")
        time.sleep(WEATHER_POLL_INTERVAL)


if __name__ == "__main__":
    run()