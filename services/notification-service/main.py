"""
Notification service — sends email/SMS notifications.
FAULT_MODE: healthy | aggressive_retry | slow
RETRY_TARGET: URL to hammer in aggressive_retry mode
"""
import asyncio
import os
import random
import time

import httpx
from fastapi import FastAPI, HTTPException, Response
from prometheus_client import Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST

FAULT_MODE = os.getenv("FAULT_MODE", "healthy")
RETRY_TARGET = os.getenv("RETRY_TARGET", "http://email-gateway/send")
RETRY_COUNT = int(os.getenv("RETRY_COUNT", "500"))

NOTIFICATIONS_SENT = Counter("notifications_sent_total", "Notifications sent", ["channel", "status"])
RETRY_STORM_ACTIVE = Gauge("notification_retry_storm_active", "1 if retry storm is active")
OUTBOUND_ERRORS = Counter("notification_outbound_errors_total", "Outbound errors", ["target"])
ACTIVE_RETRIES = Gauge("notification_active_retry_goroutines", "Simulated active retry workers")

app = FastAPI(title="notification-service")
_retry_task = None


async def _retry_storm_worker():
    """Simulates aggressive retry loop — hammers downstream without backoff."""
    RETRY_STORM_ACTIVE.set(1)
    ACTIVE_RETRIES.set(50)  # simulate 50 retry workers
    async with httpx.AsyncClient(timeout=0.2) as client:
        for _ in range(RETRY_COUNT):
            try:
                await client.post(RETRY_TARGET, json={"msg": "notify"})
                NOTIFICATIONS_SENT.labels(channel="email", status="200").inc()
            except Exception:
                OUTBOUND_ERRORS.labels(target="email-gateway").inc()
                NOTIFICATIONS_SENT.labels(channel="email", status="error").inc()
            await asyncio.sleep(0.01)  # 100 req/s — realistic storm
    RETRY_STORM_ACTIVE.set(0)
    ACTIVE_RETRIES.set(0)


@app.on_event("startup")
async def startup():
    global _retry_task
    if FAULT_MODE == "aggressive_retry":
        _retry_task = asyncio.create_task(_retry_storm_worker())


@app.post("/notify")
async def send_notification(channel: str = "email", message: str = "Your order is confirmed"):
    start = time.monotonic()

    if FAULT_MODE == "slow":
        await asyncio.sleep(random.uniform(1.0, 3.0))

    # Normal path: try to send
    try:
        async with httpx.AsyncClient(timeout=1.0) as client:
            resp = await client.post(
                RETRY_TARGET, json={"channel": channel, "message": message}
            )
            if resp.status_code == 429:
                OUTBOUND_ERRORS.labels(target="email-gateway").inc()
                raise HTTPException(status_code=503, detail="Rate limited by downstream")
    except httpx.ConnectError:
        # email-gateway may not exist in demo — that's fine, just succeed anyway
        pass
    except HTTPException:
        raise

    NOTIFICATIONS_SENT.labels(channel=channel, status="200").inc()
    return {"status": "sent", "channel": channel}


@app.get("/health")
async def health():
    return {"status": "ok", "fault_mode": FAULT_MODE, "retry_storm": FAULT_MODE == "aggressive_retry"}


@app.get("/ready")
async def ready():
    return {"status": "ready"}


@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
