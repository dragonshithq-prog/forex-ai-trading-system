"""Smoke test: API health endpoint returns 200."""

import httpx
import pytest

pytestmark = pytest.mark.smoke

API_BASE = "http://localhost:8000"


class TestApiHealth:
    """Verify all health endpoints respond correctly."""

    async def _get(self, path: str) -> httpx.Response:
        async with httpx.AsyncClient(base_url=API_BASE, timeout=10.0) as client:
            return await client.get(path)

    @pytest.mark.asyncio
    async def test_health_root(self):
        """GET /health returns 200 with status 'healthy'."""
        resp = await self._get("/health")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        data = resp.json()
        assert data["status"] == "healthy", f"Expected 'healthy', got {data['status']}"

    @pytest.mark.asyncio
    async def test_health_live(self):
        """GET /health/live returns 200 with status 'alive'."""
        resp = await self._get("/health/live")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "alive"

    @pytest.mark.asyncio
    async def test_health_ready(self):
        """GET /health/ready returns 200 (ok or degraded)."""
        resp = await self._get("/health/ready")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("ok", "degraded"), f"Unexpected status: {data['status']}"
        assert "checks" in data, "Missing 'checks' in readiness response"

    @pytest.mark.asyncio
    async def test_health_detailed(self):
        """GET /health/detailed returns version and environment."""
        resp = await self._get("/health/detailed")
        assert resp.status_code == 200
        data = resp.json()
        assert "version" in data
        assert "environment" in data

    @pytest.mark.asyncio
    async def test_api_health(self):
        """GET /api/v1/health returns 200."""
        resp = await self._get("/api/v1/health")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_metrics_endpoint(self):
        """GET /metrics returns 200 (Prometheus metrics)."""
        async with httpx.AsyncClient(base_url=API_BASE, timeout=10.0) as client:
            resp = await client.get("/metrics")
            # Prometheus might not be mounted; 404 is acceptable
            assert resp.status_code in (200, 404)

    @pytest.mark.asyncio
    async def test_health_returns_within_timeout(self):
        """Health endpoint responds within 2 seconds."""
        import time
        async with httpx.AsyncClient(base_url=API_BASE, timeout=10.0) as client:
            start = time.monotonic()
            resp = await client.get("/health")
            elapsed = time.monotonic() - start
            assert resp.status_code == 200
            assert elapsed < 2.0, f"Health check too slow: {elapsed:.2f}s"
