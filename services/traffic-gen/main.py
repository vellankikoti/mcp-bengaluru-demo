"""
Traffic generator — realistic load against all services.
Creates the live Grafana activity that makes the demo look real.
"""
import asyncio
import os
import random
import time

import httpx

ORDER_URL = os.getenv("ORDER_URL", "http://order-service.production.svc.cluster.local/order")
PAYMENT_URL = os.getenv("PAYMENT_URL", "http://payment-service.production.svc.cluster.local/process")
AUTH_URL = os.getenv("AUTH_URL", "http://auth-service.production.svc.cluster.local/validate")
RPS = float(os.getenv("RPS", "5"))

_stats = {"success": 0, "error": 0, "timeout": 0}


async def send_request(client: httpx.AsyncClient):
    endpoint = random.choice([
        (ORDER_URL, {"amount": round(random.uniform(9.99, 499.99), 2), "currency": "USD"}),
        (PAYMENT_URL, {"amount": round(random.uniform(9.99, 299.99), 2), "currency": "USD"}),
        (AUTH_URL, {"token": "demo-token"}),
    ])
    url, params = endpoint
    try:
        resp = await client.post(url, params=params, timeout=5.0)
        if resp.status_code < 400:
            _stats["success"] += 1
        else:
            _stats["error"] += 1
    except httpx.TimeoutException:
        _stats["timeout"] += 1
    except Exception:
        _stats["error"] += 1


async def stats_reporter():
    while True:
        await asyncio.sleep(10)
        total = sum(_stats.values())
        if total > 0:
            print(
                f"[traffic-gen] success={_stats['success']} "
                f"error={_stats['error']} "
                f"timeout={_stats['timeout']} "
                f"error_rate={_stats['error']/total:.1%}",
                flush=True
            )


async def main():
    print(f"[traffic-gen] Starting at {RPS} RPS", flush=True)
    interval = 1.0 / RPS
    asyncio.create_task(stats_reporter())
    async with httpx.AsyncClient() as client:
        while True:
            asyncio.create_task(send_request(client))
            await asyncio.sleep(interval + random.uniform(-0.1, 0.1) * interval)


if __name__ == "__main__":
    asyncio.run(main())
