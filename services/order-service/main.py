"""
Order service — creates orders, depends on payment + auth + notification.
Shows cascading failure symptoms when dependencies degrade.
"""
import asyncio
import os
import random
import time
import uuid

import httpx
from fastapi import FastAPI, HTTPException, Response
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

PAYMENT_URL = os.getenv("PAYMENT_URL", "http://payment-service.production.svc.cluster.local/process")
AUTH_URL = os.getenv("AUTH_URL", "http://auth-service.production.svc.cluster.local/validate")
NOTIFICATION_URL = os.getenv("NOTIFICATION_URL", "http://notification-service.production.svc.cluster.local/notify")
FAULT_MODE = os.getenv("FAULT_MODE", "healthy")

ORDERS_TOTAL = Counter("orders_total", "Total orders", ["status"])
ORDER_LATENCY = Histogram(
    "order_request_duration_seconds", "Order processing latency",
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)
DEPENDENCY_ERRORS = Counter("order_dependency_errors_total", "Dependency errors", ["dependency"])

app = FastAPI(title="order-service")


@app.post("/order")
async def create_order(amount: float = 49.99, currency: str = "USD"):
    start = time.monotonic()
    order_id = f"ORD-{uuid.uuid4().hex[:8].upper()}"

    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            # Step 1: validate auth
            try:
                auth_resp = await client.post(AUTH_URL, params={"token": "demo-token"})
                if auth_resp.status_code != 200:
                    DEPENDENCY_ERRORS.labels(dependency="auth-service").inc()
                    raise HTTPException(status_code=503, detail="Authentication failed")
            except (httpx.ConnectError, httpx.TimeoutException):
                DEPENDENCY_ERRORS.labels(dependency="auth-service").inc()
                # Fail gracefully for demo — auth unreachable counts as degraded not dead
                pass

            # Step 2: process payment
            try:
                pay_resp = await client.post(
                    PAYMENT_URL, params={"amount": amount, "currency": currency}
                )
                if pay_resp.status_code != 200:
                    DEPENDENCY_ERRORS.labels(dependency="payment-service").inc()
                    ORDERS_TOTAL.labels(status="payment_failed").inc()
                    raise HTTPException(status_code=502, detail="Payment processing failed")
            except (httpx.ConnectError, httpx.TimeoutException) as e:
                DEPENDENCY_ERRORS.labels(dependency="payment-service").inc()
                ORDERS_TOTAL.labels(status="payment_timeout").inc()
                raise HTTPException(status_code=504, detail=f"Payment service timeout: {e}")

            # Step 3: notify (fire and forget)
            try:
                await asyncio.wait_for(
                    client.post(NOTIFICATION_URL, params={"channel": "email", "message": f"Order {order_id} confirmed"}),
                    timeout=0.5
                )
            except Exception:
                pass  # notification failure is non-blocking

        ORDERS_TOTAL.labels(status="success").inc()
        ORDER_LATENCY.observe(time.monotonic() - start)
        return {"order_id": order_id, "status": "confirmed", "amount": amount, "currency": currency}

    except HTTPException:
        ORDER_LATENCY.observe(time.monotonic() - start)
        raise


@app.get("/health")
async def health():
    return {"status": "ok", "fault_mode": FAULT_MODE}


@app.get("/ready")
async def ready():
    return {"status": "ready"}


@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
