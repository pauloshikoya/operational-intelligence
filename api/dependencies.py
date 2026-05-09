# api/dependencies.py

"""
Shared dependencies for all API routes.

FastAPI's dependency injection system calls these functions
automatically for every request that needs them. They handle:
  - Database connection pooling
  - Redis client
  - API key authentication

Using dependency injection means:
  - Every route gets a fresh, valid connection
  - Connections are always closed after the request
  - Auth is enforced in one place, not scattered across routes
"""

import os
import redis
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from fastapi import Header, HTTPException, status

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
REDIS_URL    = os.getenv("REDIS_URL", "redis://localhost:6379")

# ── API key auth ───────────────────────────────────────────────────────────────
# Simple static key for portfolio use.
# In production this would be a database of keys with scopes and expiry.
API_KEY = os.getenv("API_KEY", "dev-key-change-in-production")


def verify_api_key(x_api_key: str = Header(...)):
    """
    FastAPI dependency that checks the X-Api-Key header.
    Add this to any route you want protected:

        @router.get("/endpoint")
        def endpoint(key = Depends(verify_api_key)):
            ...
    """
    if x_api_key != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    return x_api_key


def get_db():
    """
    Database connection dependency.
    Opens a connection, yields it to the route handler,
    then closes it — even if the route raises an exception.

    Usage in a route:
        def my_route(conn = Depends(get_db)):
            ...
    """
    conn = psycopg2.connect(
        DATABASE_URL,
        cursor_factory=psycopg2.extras.RealDictCursor
    )
    try:
        yield conn
    finally:
        conn.close()


def get_redis():
    """
    Redis client dependency.
    Returns a connected client. Connection is managed by
    the redis-py connection pool automatically.
    """
    client = redis.from_url(REDIS_URL, decode_responses=True)
    try:
        yield client
    finally:
        client.close()