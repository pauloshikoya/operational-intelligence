# ingestion/db.py

import psycopg2
import psycopg2.extras
import logging
from ingestion.config import DATABASE_URL

logger = logging.getLogger(__name__)


def get_connection():
    """
    Open and return a new database connection.
    Call this each time you need a connection.
    Always close it when done (use 'with' blocks).
    """
    return psycopg2.connect(DATABASE_URL)


def insert_raw_data(conn, source: str, domain: str,
                    metric_name: str, value: float,
                    unit: str = None, raw_json: dict = None):
    """
    Write one raw data point into the raw_data table.

    Args:
        conn        : open database connection
        source      : where data came from, e.g. "alpha_vantage"
        domain      : business domain, e.g. "supply_chain"
        metric_name : what we measured, e.g. "crude_oil_price"
        value       : the numeric value
        unit        : optional unit string, e.g. "USD"
        raw_json    : the full original API response as a dict
    """
    sql = """
        INSERT INTO raw_data
            (source, domain, metric_name, value, unit, raw_json)
        VALUES
            (%s, %s, %s, %s, %s, %s)
    """
    with conn.cursor() as cur:
        cur.execute(sql, (
            source,
            domain,
            metric_name,
            value,
            unit,
            psycopg2.extras.Json(raw_json) if raw_json else None
        ))
    conn.commit()
    logger.debug(f"Inserted raw_data: {source} / {metric_name} = {value}")