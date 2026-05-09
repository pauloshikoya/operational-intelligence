# tests/test_api.py

import json
from unittest.mock import MagicMock, patch, PropertyMock
from fastapi.testclient import TestClient
from api.main import app

client  = TestClient(app)
API_KEY = "dev-key-change-in-production"
HEADERS = {"X-Api-Key": API_KEY}


# ── Mock helpers ───────────────────────────────────────────────────────────────

def make_cursor(fetchall=None, fetchone=None):
    """Build a mock cursor with preset return values."""
    cursor = MagicMock()
    cursor.fetchall.return_value = fetchall or []
    cursor.fetchone.return_value = fetchone or {"count": 0}
    return cursor


def make_conn(cursor):
    """Build a mock connection that yields the given cursor."""
    conn = MagicMock()
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
    conn.cursor.return_value.__exit__  = MagicMock(return_value=False)
    return conn


def make_redis(keys=None, get_value=None):
    """Build a mock Redis client."""
    r = MagicMock()
    r.keys.return_value  = keys or []
    r.get.return_value   = get_value
    r.ping.return_value  = True
    r.setex.return_value = True
    return r


# ── Root ──────────────────────────────────────────────────────────────────────

def test_root():
    r = client.get("/")
    assert r.status_code == 200
    data = r.json()
    assert "name"    in data
    assert "version" in data
    assert "docs"    in data


# ── Health ────────────────────────────────────────────────────────────────────

def test_health_returns_200():
    """Health uses real DB — just check structure, not exact values."""
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert "overall"    in data
    assert "database"   in data
    assert "redis"      in data
    assert "checked_at" in data
    # database should be green since Docker is running
    assert data["database"]["status"] == "green"


# ── Auth ──────────────────────────────────────────────────────────────────────

def test_anomalies_requires_auth():
    r = client.get("/anomalies")
    assert r.status_code == 422


def test_anomalies_rejects_wrong_key():
    r = client.get("/anomalies", headers={"X-Api-Key": "wrong-key"})
    assert r.status_code == 401


# ── Anomalies — use real DB (Docker is running) ───────────────────────────────

def test_anomalies_returns_list():
    """Real DB call — just check response shape."""
    r = client.get("/anomalies", headers=HEADERS)
    assert r.status_code == 200
    data = r.json()
    assert "anomalies"  in data
    assert "pagination" in data
    assert isinstance(data["anomalies"], list)


def test_anomalies_filter_by_severity():
    """Filter should work without error — result may be empty list."""
    r = client.get("/anomalies?severity=high", headers=HEADERS)
    assert r.status_code == 200
    data = r.json()
    assert "anomalies" in data
    # If any returned, they must all be high severity
    for a in data["anomalies"]:
        assert a["severity"] == "high"


def test_anomaly_not_found():
    r = client.get("/anomalies/999999", headers=HEADERS)
    assert r.status_code == 404


def test_anomalies_pagination_fields():
    """Pagination metadata must always be present."""
    r = client.get("/anomalies?limit=5&offset=0", headers=HEADERS)
    assert r.status_code == 200
    p = r.json()["pagination"]
    assert "total"    in p
    assert "limit"    in p
    assert "offset"   in p
    assert "has_more" in p
    assert p["limit"]  == 5
    assert p["offset"] == 0


# ── Metrics — use real DB ──────────────────────────────────────────────────────

def test_metrics_returns_list():
    """Real DB/Redis call — check response shape."""
    r = client.get("/metrics", headers=HEADERS)
    assert r.status_code == 200
    data = r.json()
    assert "metrics" in data
    assert "source"  in data
    assert "count"   in data
    assert data["source"] in ("cache", "database")
    assert isinstance(data["metrics"], list)


def test_metric_series_endpoint():
    """Series endpoint should return correct shape."""
    r = client.get("/metrics/crude_oil_wti/series", headers=HEADERS)
    assert r.status_code == 200
    data = r.json()
    assert "metric_name" in data
    assert "series"      in data
    assert "anomalies"   in data
    assert isinstance(data["series"],    list)
    assert isinstance(data["anomalies"], list)


# ── Ask ───────────────────────────────────────────────────────────────────────

def test_ask_requires_auth():
    r = client.post("/ask", json={"question": "What is happening?"})
    assert r.status_code == 422


def test_ask_rejects_short_question():
    r = client.post("/ask", json={"question": "hi"}, headers=HEADERS)
    assert r.status_code == 400


def test_ask_returns_answer():
    """Mock Claude but use real DB for context building."""
    mock_response         = MagicMock()
    mock_response.content = [MagicMock(text="Crude oil is elevated above historical average.")]
    mock_response.usage   = MagicMock(input_tokens=100, output_tokens=50)

    with patch("api.routers.ask.client.messages.create",
               return_value=mock_response):
        r = client.post(
            "/ask",
            json={"question": "What metrics are most anomalous right now?"},
            headers=HEADERS,
        )

    assert r.status_code == 200
    data = r.json()
    assert "answer"        in data
    assert "question"      in data
    assert "tokens_used"   in data
    assert len(data["answer"]) > 5