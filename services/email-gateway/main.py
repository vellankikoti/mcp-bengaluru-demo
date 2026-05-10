"""
Email gateway — acts as a rate-limited downstream.
In retry-storm scenario this returns 429s.
FAULT_MODE: healthy | rate_limited
"""
import asyncio
import os
import time
from collections import deque

from fastapi import FastAPI, HTTPException, Response
from prometheus_client import Counter, generate_latest, CONTENT_TYPE_LATEST

FAULT_MODE = os.getenv("FAULT_MODE", "healthy")
RATE_LIMIT_RPS = int(os.getenv("RATE_LIMIT_RPS", "10"))

SEND_COUNTER = Counter("email_gateway_requests_total", "Requests", ["status"])

app = FastAPI(title="email-gateway")
_request_times: deque = deque(maxlen=100)


def _is_rate_limited() -> bool:
    now = time.monotonic()
    _request_times.append(now)
    recent = sum(1 for t in _request_times if now - t < 1.0)
    return recent > RATE_LIMIT_RPS


@app.post("/send")
async def send(channel: str = "email", message: str = ""):
    if FAULT_MODE == "rate_limited" or _is_rate_limited():
        SEND_COUNTER.labels(status="429").inc()
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Retry after 1s.")

    await asyncio.sleep(0.02)
    SEND_COUNTER.labels(status="200").inc()
    return {"status": "sent", "message_id": f"msg-{int(time.time())}"}


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/ready")
async def ready():
    return {"status": "ready"}


@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
