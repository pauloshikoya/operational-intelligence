# api/main.py

"""
FastAPI application entry point.

Wires together all routers, configures CORS (so your React
dashboard can call the API), and adds global middleware for
logging and error handling.
"""

import logging
import time
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.routers import anomalies, metrics, health, stream, ask

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("api")

# ── App definition ─────────────────────────────────────────────────────────────
app = FastAPI(
    title="Operational Intelligence API",
    description=(
        "Real-time supply chain anomaly detection and AI narration. "
        "Detects anomalies across commodity prices and logistics data, "
        "generating structured intelligence reports using Claude."
    ),
    version="1.0.0",
    docs_url="/docs",        # Swagger UI at /docs
    redoc_url="/redoc",      # ReDoc at /redoc
)

# ── CORS ───────────────────────────────────────────────────────────────────────
# Allows the React dashboard (running on localhost:5173) to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",    # Vite dev server
        "http://localhost:3000",    # Alternative dev port
        "https://*.vercel.app",     # Vercel deployment
        "https://operational-intelligence-liard.vercel.app",      # your main domain
        "https://operational-intelligence-ippw7t70w-pauloshikoyas-projects.vercel.app",  # your preview URL

    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Request logging middleware ─────────────────────────────────────────────────
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log every request with method, path, and response time."""
    start = time.time()
    response = await call_next(request)
    duration = round((time.time() - start) * 1000, 1)
    logger.info(
        f"{request.method} {request.url.path} "
        f"→ {response.status_code} "
        f"({duration}ms)"
    )
    return response

# ── Global error handler ───────────────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch unhandled exceptions and return a clean JSON error."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "type": type(exc).__name__},
    )

# ── Routers ────────────────────────────────────────────────────────────────────
app.include_router(anomalies.router)
app.include_router(metrics.router)
app.include_router(health.router)
app.include_router(stream.router)
app.include_router(ask.router)

# ── Root endpoint ──────────────────────────────────────────────────────────────
@app.get("/", tags=["root"])
def root():
    return {
        "name":        "Operational Intelligence API",
        "version":     "1.0.0",
        "docs":        "/docs",
        "health":      "/health",
        "description": "Supply chain anomaly detection + AI narration",
    }