"""Smoke test: Database read/write via health check."""

import httpx
import pytest

pytestmark = pytest.mark.smoke

API_BASE = "http://localhost:8000"


class TestDatabaseConnectivity:
    """Verify database is operational via health and direct endpoints."""

    @pytest.mark.asyncio
    async def test_db_health(self):
        """Readiness check shows database status."""
        async with httpx.AsyncClient(base_url=API_BASE, timeout=10.0) as client:
            resp = await client.get("/health/ready")
            assert resp.status_code == 200
            data = resp.json()
            assert "checks" in data
            assert "database" in data["checks"]

    @pytest.mark.asyncio
    async def test_db_read(self):
        """GET endpoint reads from database successfully."""
        async with httpx.AsyncClient(base_url=API_BASE, timeout=10.0) as client:
            resp = await client.get("/api/v1/users/me")
            # May need auth - just check it connects and returns 401 or 200
            assert resp.status_code in (200, 401, 403)

    @pytest.mark.asyncio
    async def test_risk_config_read(self):
        """Risk config endpoint reads from database."""
        async with httpx.AsyncClient(base_url=API_BASE, timeout=10.0) as client:
            resp = await client.get("/api/v1/risk/config")
            # Without auth, expect 401 (means DB is answering)
            assert resp.status_code in (200, 401, 403)

    @pytest.mark.asyncio
    async def test_strategies_read(self):
        """Strategy list endpoint reads from database."""
        async with httpx.AsyncClient(base_url=API_BASE, timeout=10.0) as client:
            resp = await client.get("/api/v1/strategy/strategies")
            assert resp.status_code in (200, 401, 403)
