"""
Payment service — simulates real payment processing with deterministic fault injection.
FAULT_MODE: healthy | oom | slow | error | error_rate
"""
import asyncio
import gc
import os
import random
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Response
from prometheus_client import Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST

FAULT_MODE = os.getenv("FAULT_MODE", "healthy")
FAULT_PROBABILITY = float(os.getenv("FAULT_PROBABILITY", "0.0"))
SERVICE_VERSION = os.getenv("SERVICE_VERSION", "v1")

REQUEST_COUNT = Counter(
    "payment_requests_total", "Total payment requests", ["status", "version"]
)
REQUEST_LATENCY = Histogram(
    "payment_request_duration_seconds", "Request latency",
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
    labelnames=["version"]
)
MEMORY_USAGE = Gauge("payment_memory_simulated_bytes", "Simulated memory usage")
ACTIVE_REQUESTS = Gauge("payment_active_requests", "Active requests in flight")

_leak_buffer: list = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    if FAULT_MODE == "oom":
        asyncio.create_task(_memory_leak_task())
    yield


app = FastAPI(title="payment-service", version=SERVICE_VERSION, lifespan=lifespan)


async def _memory_leak_task():
    """Gradually allocate memory until OOMKill. Realistic heap growth."""
    while True:
        _leak_buffer.append(b"x" * (1024 * 512))  # 512KB per tick
        MEMORY_USAGE.set(len(_leak_buffer) * 512 * 1024)
        await asyncio.sleep(0.5)


@app.post("/process")
async def process_payment(amount: float = 99.99, currency: str = "USD"):
    ACTIVE_REQUESTS.inc()
    start = time.monotonic()
    try:
        if FAULT_MODE == "slow":
            await asyncio.sleep(random.uniform(1.5, 4.0))

        if FAULT_MODE in ("error", "error_rate"):
            if random.random() < max(FAULT_PROBABILITY, 0.3):
                REQUEST_COUNT.labels(status="500", version=SERVICE_VERSION).inc()
                raise HTTPException(status_code=500, detail="Payment processor unavailable")

        # Simulate processing
        await asyncio.sleep(random.uniform(0.01, 0.05))
        txn_id = f"TXN-{uuid.uuid4().hex[:8].upper()}"
        REQUEST_COUNT.labels(status="200", version=SERVICE_VERSION).inc()
        return {"status": "processed", "transaction_id": txn_id, "amount": amount, "currency": currency}
    finally:
        REQUEST_LATENCY.labels(version=SERVICE_VERSION).observe(time.monotonic() - start)
        ACTIVE_REQUESTS.dec()


@app.get("/health")
async def health():
    if FAULT_MODE == "oom" and len(_leak_buffer) > 400:
        raise HTTPException(status_code=503, detail="memory pressure critical")
    return {"status": "ok", "version": SERVICE_VERSION, "fault_mode": FAULT_MODE}


@app.get("/ready")
async def ready():
    return {"status": "ready"}


@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/")
async def root():
    return {"service": "payment-service", "version": SERVICE_VERSION}
