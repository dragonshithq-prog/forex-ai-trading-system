"""
Load test: API throughput for order placement and market data endpoints.

Uses httpx for async HTTP calls — simulates high-frequency trading API usage.
Can be run standalone or with pytest markers:
    pytest tests/load/test_api_throughput.py -v --slow
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from uuid import uuid4

import httpx
import pytest

pytestmark = [
    pytest.mark.slow,
    pytest.mark.load,
]

API_BASE = "http://localhost:8000/api/v1"

# Adjust based on environment
CONCURRENT_USERS = 50
OPS_PER_USER = 20
THROUGHPUT_MIN_OPS = 50  # Minimum operations per second


class TestOrderPlacementThroughput:
    """Measure order placement throughput under concurrency."""

    @pytest.fixture(scope="class")
    def auth_token(self) -> str | None:
        """Get an auth token for load testing (or None to skip)."""
        try:
            import asyncio
            async def _get_token():
                async with httpx.AsyncClient(base_url=API_BASE, timeout=10.0) as client:
                    resp = await client.post("/auth/login", json={
                        "username": "loadtest",
                        "password": "LoadTestPass123!",
                    })
                    if resp.status_code == 200:
                        return resp.json()["access_token"]
                    return None
            return asyncio.run(_get_token())
        except Exception:
            return None

    @pytest.mark.asyncio
    async def test_order_placement_throughput(self):
        """Measure order placement throughput — must exceed minimum ops/s."""
        total_ops = CONCURRENT_USERS * OPS_PER_USER

        async def place_order(client: httpx.AsyncClient, user_id: int) -> float:
            start = time.monotonic()
            order = {
                "symbol": "EURUSD",
                "side": "buy" if user_id % 2 == 0 else "sell",
                "order_type": "market",
                "quantity": 0.01,
                "broker_account_id": str(uuid4()),
            }
            try:
                resp = await client.post("/trading/orders", json=order)
                _ = resp.status_code  # Just measure, don't assert
            except Exception:
                pass
            return time.monotonic() - start

        async with httpx.AsyncClient(base_url=API_BASE, timeout=30.0) as client:
            start = time.monotonic()

            # Fire all requests concurrently
            tasks = []
            for i in range(CONCURRENT_USERS):
                for _ in range(OPS_PER_USER):
                    tasks.append(place_order(client, i))

            latencies = await asyncio.gather(*tasks)
            elapsed = time.monotonic() - start

        throughput = total_ops / elapsed if elapsed > 0 else 0
        avg_latency = (sum(latencies) / len(latencies)) * 1000 if latencies else 0
        p99_latency = sorted(latencies)[int(len(latencies) * 0.99)] * 1000 if latencies else 0
        min_latency = min(latencies) * 1000 if latencies else 0
        max_latency = max(latencies) * 1000 if latencies else 0

        print(f"\n  Throughput:  {throughput:.0f} ops/s")
        print(f"  Total ops:   {total_ops}")
        print(f"  Duration:    {elapsed:.2f}s")
        print(f"  Avg latency: {avg_latency:.1f}ms")
        print(f"  P99 latency: {p99_latency:.1f}ms")
        print(f"  Min latency: {min_latency:.1f}ms")
        print(f"  Max latency: {max_latency:.1f}ms")

        assert throughput >= THROUGHPUT_MIN_OPS, \
            f"Throughput too low: {throughput:.0f} ops/s (min: {THROUGHPUT_MIN_OPS})"

    @pytest.mark.asyncio
    async def test_market_data_throughput(self):
        """Measure market data endpoint throughput."""
        symbols = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD"]
        n = 100

        async with httpx.AsyncClient(base_url=API_BASE, timeout=10.0) as client:
            start = time.monotonic()
            tasks = []
            for _ in range(n):
                for sym in symbols:
                    tasks.append(client.get(f"/market/data?symbol={sym}"))
            responses = await asyncio.gather(*tasks, return_exceptions=True)
            elapsed = time.monotonic() - start

        success = sum(1 for r in responses if isinstance(r, httpx.Response) and r.status_code < 500)
        throughput = len(tasks) / elapsed if elapsed > 0 else 0

        print(f"\n  Market data throughput: {throughput:.0f} req/s")
        print(f"  Successful: {success}/{len(tasks)}")
        print(f"  Duration:   {elapsed:.2f}s")

    @pytest.mark.asyncio
    async def test_mixed_workload_throughput(self):
        """Mixed workload (health + market + trading)."""
        n = 50

        async def mixed_workload(client: httpx.AsyncClient, idx: int):
            ops = [
                client.get("/health"),
                client.get("/health/live"),
                client.get("/health/ready"),
                client.get("/api/v1/market/symbols"),
                client.get(f"/api/v1/market/data?symbol=EURUSD"),
            ]
            return await asyncio.gather(*ops, return_exceptions=True)

        async with httpx.AsyncClient(base_url=API_BASE[:-4], timeout=15.0) as client:
            start = time.monotonic()
            results = await asyncio.gather(*[mixed_workload(client, i) for i in range(n)])
            elapsed = time.monotonic() - start

        total_ops = sum(len(r) for r in results)
        throughput = total_ops / elapsed if elapsed > 0 else 0

        print(f"\n  Mixed workload: {throughput:.0f} req/s")
        print(f"  Total requests: {total_ops}")
        print(f"  Duration: {elapsed:.2f}s")
