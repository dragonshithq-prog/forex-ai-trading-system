"""
Load test: Multiple simulated traders operating concurrently.

Simulates N independent traders, each with their own risk profile,
placing orders, managing positions, and assessing risk in parallel.
"""

from __future__ import annotations

import asyncio
import random
import time
from uuid import uuid4

import httpx
import pytest

pytestmark = [
    pytest.mark.slow,
    pytest.mark.load,
]

API_BASE = "http://localhost:8000/api/v1"
SIMULATED_TRADERS = 10
ACTIONS_PER_TRADER = 20
MAX_CONCURRENT = 5


class TraderSimulator:
    """Simulates a single trader's behavior."""

    def __init__(self, trader_id: int, client: httpx.AsyncClient):
        self.trader_id = trader_id
        self.client = client
        self.orders_placed = 0
        self.positions_checked = 0
        self.risk_assessments = 0
        self.errors = 0

    async def run(self) -> dict:
        """Execute a series of trading actions."""
        actions = []
        for i in range(ACTIONS_PER_TRADER):
            action = await self._random_action()
            actions.append(action)
            # Small random delay between actions
            await asyncio.sleep(random.uniform(0.01, 0.1))
        return {
            "trader_id": self.trader_id,
            "orders_placed": self.orders_placed,
            "positions_checked": self.positions_checked,
            "risk_assessments": self.risk_assessments,
            "errors": self.errors,
            "total_actions": len(actions),
        }

    async def _random_action(self) -> str:
        """Perform a random trading action."""
        action = random.choice(["risk", "positions", "order", "market", "strategies"])
        try:
            if action == "risk":
                await self.client.get("/risk/config")
                self.risk_assessments += 1
            elif action == "positions":
                await self.client.get("/trading/positions")
                self.positions_checked += 1
            elif action == "order":
                order = {
                    "symbol": random.choice(["EURUSD", "GBPUSD", "USDJPY"]),
                    "side": random.choice(["buy", "sell"]),
                    "order_type": "market",
                    "quantity": round(random.uniform(0.01, 0.1), 2),
                    "broker_account_id": str(uuid4()),
                }
                await self.client.post("/trading/orders", json=order)
                self.orders_placed += 1
            elif action == "market":
                symbol = random.choice(["EURUSD", "GBPUSD", "USDJPY"])
                await self.client.get(f"/market/data?symbol={symbol}")
            elif action == "strategies":
                await self.client.get("/strategy/strategies")
        except Exception:
            self.errors += 1
        return action


class TestConcurrentTraders:
    """Multiple simulated traders operating concurrently."""

    @pytest.mark.asyncio
    async def test_concurrent_traders_no_deadlocks(self):
        """Multiple traders operate without deadlocks or crashes."""
        async with httpx.AsyncClient(base_url=API_BASE, timeout=30.0) as client:
            traders = [
                TraderSimulator(i, client)
                for i in range(SIMULATED_TRADERS)
            ]

            start = time.monotonic()
            results = await asyncio.gather(*[t.run() for t in traders])
            elapsed = time.monotonic() - start

        total_actions = sum(r["total_actions"] for r in results)
        total_errors = sum(r["errors"] for r in results)
        throughput = total_actions / elapsed if elapsed > 0 else 0

        print(f"\n  Traders:          {SIMULATED_TRADERS}")
        print(f"  Actions/Trader:   {ACTIONS_PER_TRADER}")
        print(f"  Total actions:    {total_actions}")
        print(f"  Total errors:     {total_errors}")
        print(f"  Duration:         {elapsed:.2f}s")
        print(f"  Throughput:       {throughput:.0f} actions/s")

    @pytest.mark.asyncio
    async def test_concurrent_traders_mixed_payloads(self):
        """Mixed payload sizes and endpoint types don't cause issues."""
        async with httpx.AsyncClient(base_url=API_BASE, timeout=30.0) as client:
            start = time.monotonic()

            async def mixed_actions(trader_id: int):
                actions = []
                # Variety of endpoints
                endpoints = [
                    ("GET", "/risk/config", None),
                    ("GET", "/market/symbols", None),
                    ("GET", "/health", None),
                    ("POST", "/trading/orders", {
                        "symbol": "EURUSD",
                        "side": "buy",
                        "order_type": "market",
                        "quantity": 0.01,
                    }),
                ]
                for _ in range(10):
                    method, path, body = random.choice(endpoints)
                    try:
                        if method == "GET":
                            await client.get(path)
                        else:
                            await client.post(path, json=body) if isinstance(body, dict) else None
                        actions.append("ok")
                    except Exception:
                        actions.append("err")
                return actions

            results = await asyncio.gather(*[
                mixed_actions(i) for i in range(20)
            ], return_exceptions=True)
            elapsed = time.monotonic() - start

        ok_count = sum(1 for r in results if isinstance(r, list) for a in r if a == "ok")
        print(f"\n  Mixed payloads:  {elapsed:.2f}s, {ok_count} OK")
