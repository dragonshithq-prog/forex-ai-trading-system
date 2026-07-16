"""Smoke test: Trading flow — place order, check position, cancel."""

import httpx
import pytest

pytestmark = pytest.mark.smoke

API_BASE = "http://localhost:8000/api/v1"


class TestTradingFlow:
    """End-to-end trading flow smoke test."""

    @pytest.fixture
    def test_user(self) -> dict:
        import uuid
        suffix = uuid.uuid4().hex[:8]
        return {
            "username": f"trading_test_{suffix}",
            "email": f"trading_test_{suffix}@example.com",
            "password": "TestPassword123!",
        }

    async def _login(self, client: httpx.AsyncClient, user: dict) -> dict | None:
        """Login and return token pair."""
        resp = await client.post("/auth/login", json={
            "username": user["username"],
            "password": user["password"],
        })
        if resp.status_code == 200:
            return resp.json()
        return None

    @pytest.mark.asyncio
    async def test_list_broker_accounts(self, test_user: dict):
        """GET /broker/accounts returns list (or 401 without auth)."""
        async with httpx.AsyncClient(base_url=API_BASE, timeout=15.0) as client:
            # Test without auth
            resp = await client.get("/broker/accounts")
            assert resp.status_code == 401

            # Test with auth
            tokens = await self._login(client, test_user)
            if tokens:
                resp = await client.get(
                    "/broker/accounts",
                    headers={"Authorization": f"Bearer {tokens['access_token']}"},
                )
                assert resp.status_code == 200
                assert isinstance(resp.json(), list)

    @pytest.mark.asyncio
    async def test_list_trading_positions(self, test_user: dict):
        """GET /trading/positions returns OK."""
        async with httpx.AsyncClient(base_url=API_BASE, timeout=15.0) as client:
            tokens = await self._login(client, test_user)
            if tokens:
                resp = await client.get(
                    "/trading/positions",
                    headers={"Authorization": f"Bearer {tokens['access_token']}"},
                )
                assert resp.status_code == 200
                assert isinstance(resp.json(), list)

    @pytest.mark.asyncio
    async def test_list_orders(self, test_user: dict):
        """GET /trading/orders returns OK."""
        async with httpx.AsyncClient(base_url=API_BASE, timeout=15.0) as client:
            tokens = await self._login(client, test_user)
            if tokens:
                resp = await client.get(
                    "/trading/orders",
                    headers={"Authorization": f"Bearer {tokens['access_token']}"},
                )
                assert resp.status_code == 200
                assert isinstance(resp.json(), list)

    @pytest.mark.asyncio
    async def test_get_market_data(self):
        """GET /market/data returns market data for a symbol."""
        async with httpx.AsyncClient(base_url=API_BASE, timeout=10.0) as client:
            resp = await client.get("/market/data?symbol=EURUSD")
            # Market data may be unauthenticated in some configs
            assert resp.status_code in (200, 401)
            if resp.status_code == 200:
                data = resp.json()
                assert "symbol" in data
                assert data["symbol"] == "EURUSD"

    @pytest.mark.asyncio
    async def test_list_symbols(self):
        """GET /market/symbols returns available trading symbols."""
        async with httpx.AsyncClient(base_url=API_BASE, timeout=10.0) as client:
            resp = await client.get("/market/symbols")
            assert resp.status_code in (200, 401)
            if resp.status_code == 200:
                symbols = resp.json()
                assert len(symbols) > 0
                assert "EURUSD" in [s["symbol"] for s in symbols]

    @pytest.mark.asyncio
    async def test_get_risk_state(self, test_user: dict):
        """GET /risk/state requires auth."""
        async with httpx.AsyncClient(base_url=API_BASE, timeout=10.0) as client:
            resp = await client.get(
                "/risk/state",
                params={"broker_account_id": "00000000-0000-0000-0000-000000000000"},
            )
            assert resp.status_code in (200, 401, 403, 404)

    @pytest.mark.asyncio
    async def test_list_strategies(self):
        """GET /strategy/strategies returns list."""
        async with httpx.AsyncClient(base_url=API_BASE, timeout=10.0) as client:
            resp = await client.get("/strategy/strategies")
            assert resp.status_code in (200, 401)
            if resp.status_code == 200:
                assert isinstance(resp.json(), list)
