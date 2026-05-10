"""
Auth service — JWT validation + session management.
FAULT_MODE: healthy | slow | error | cert_expiry
"""
import asyncio
import os
import random
import time
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, HTTPException, Response
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

FAULT_MODE = os.getenv("FAULT_MODE", "healthy")
SERVICE_VERSION = os.getenv("SERVICE_VERSION", "v1")

AUTH_REQUESTS = Counter("auth_requests_total", "Auth requests", ["status", "method"])
AUTH_LATENCY = Histogram("auth_request_duration_seconds", "Auth latency",
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5])
CERT_EXPIRY_SECONDS = None

app = FastAPI(title="auth-service", version=SERVICE_VERSION)

_sessions: dict = {}


@app.post("/validate")
async def validate_token(token: str = "demo-token"):
    start = time.monotonic()
    try:
        if FAULT_MODE == "slow":
            await asyncio.sleep(random.uniform(0.8, 2.5))

        if FAULT_MODE == "error" and random.random() < 0.4:
            AUTH_REQUESTS.labels(status="503", method="validate").inc()
            raise HTTPException(status_code=503, detail="Auth service degraded")

        if FAULT_MODE == "cert_expiry":
            # Auth is still working but cert expires soon — warning in headers
            AUTH_REQUESTS.labels(status="200", method="validate").inc()
            return {
                "valid": True,
                "user_id": f"user-{uuid.uuid4().hex[:6]}",
                "warning": "TLS certificate expires in 2 hours",
                "expires_at": (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(),
            }

        session_id = uuid.uuid4().hex
        _sessions[session_id] = time.time()
        AUTH_REQUESTS.labels(status="200", method="validate").inc()
        return {"valid": True, "session_id": session_id, "user_id": f"user-{uuid.uuid4().hex[:6]}"}
    finally:
        AUTH_LATENCY.observe(time.monotonic() - start)


@app.get("/health")
async def health():
    cert_warning = None
    if FAULT_MODE == "cert_expiry":
        cert_warning = "certificate expiring in 2h"
    return {"status": "ok", "version": SERVICE_VERSION, "cert_warning": cert_warning}


@app.get("/ready")
async def ready():
    if FAULT_MODE == "error":
        # Still pass readiness in error mode (for realistic symptom: requests go through but fail)
        pass
    return {"status": "ready"}


@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
