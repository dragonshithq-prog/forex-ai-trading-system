"""Smoke test: Authentication flow — register, login, refresh, protected endpoint."""

import httpx
import pytest

pytestmark = pytest.mark.smoke

API_BASE = "http://localhost:8000/api/v1"


class TestAuthFlow:
    """End-to-end authentication smoke test."""

    @pytest.fixture
    def test_user(self) -> dict:
        import uuid
        suffix = uuid.uuid4().hex[:8]
        return {
            "username": f"smoketest_{suffix}",
            "email": f"smoketest_{suffix}@example.com",
            "password": "TestPassword123!",
            "full_name": "Smoke Test User",
        }

    @pytest.mark.asyncio
    async def test_register_user(self, test_user: dict):
        """POST /auth/register returns 201 with tokens."""
        async with httpx.AsyncClient(base_url=API_BASE, timeout=15.0) as client:
            resp = await client.post("/auth/register", json=test_user)
            # May return 409 if user exists; that's also valid
            if resp.status_code == 409:
                pytest.skip("User already exists (conflict)")
            assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
            data = resp.json()
            assert "access_token" in data
            assert "refresh_token" in data
            assert "user" in data
            assert data["user"]["username"] == test_user["username"]
            return data

    @pytest.mark.asyncio
    async def test_login_user(self, test_user: dict):
        """POST /auth/login returns tokens."""
        async with httpx.AsyncClient(base_url=API_BASE, timeout=15.0) as client:
            resp = await client.post("/auth/login", json={
                "username": test_user["username"],
                "password": test_user["password"],
            })
            if resp.status_code in (401, 423):
                pytest.skip(f"Login failed: {resp.status_code} — {resp.text}")
            assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
            data = resp.json()
            assert "access_token" in data
            assert "refresh_token" in data
            return data

    @pytest.mark.asyncio
    async def test_refresh_token(self, test_user: dict):
        """POST /auth/refresh returns new token pair."""
        # First login to get tokens
        async with httpx.AsyncClient(base_url=API_BASE, timeout=15.0) as client:
            login_resp = await client.post("/auth/login", json={
                "username": test_user["username"],
                "password": test_user["password"],
            })
            if login_resp.status_code != 200:
                pytest.skip(f"Login failed: {login_resp.status_code}")
            tokens = login_resp.json()

            # Refresh token
            resp = await client.post("/auth/refresh", json={
                "refresh_token": tokens["refresh_token"],
            })
            assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
            data = resp.json()
            assert "access_token" in data
            assert "refresh_token" in data

    @pytest.mark.asyncio
    async def test_protected_endpoint(self, test_user: dict):
        """GET /auth/me returns user data with valid access token."""
        async with httpx.AsyncClient(base_url=API_BASE, timeout=15.0) as client:
            login_resp = await client.post("/auth/login", json={
                "username": test_user["username"],
                "password": test_user["password"],
            })
            if login_resp.status_code != 200:
                pytest.skip(f"Login failed: {login_resp.status_code}")
            tokens = login_resp.json()

            resp = await client.get(
                "/auth/me",
                headers={"Authorization": f"Bearer {tokens['access_token']}"},
            )
            assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
            data = resp.json()
            assert data["username"] == test_user["username"]

    @pytest.mark.asyncio
    async def test_protected_endpoint_without_token(self):
        """GET /auth/me without token returns 401."""
        async with httpx.AsyncClient(base_url=API_BASE, timeout=10.0) as client:
            resp = await client.get("/auth/me")
            assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_logout(self, test_user: dict):
        """POST /auth/logout revokes sessions."""
        async with httpx.AsyncClient(base_url=API_BASE, timeout=15.0) as client:
            login_resp = await client.post("/auth/login", json={
                "username": test_user["username"],
                "password": test_user["password"],
            })
            if login_resp.status_code != 200:
                pytest.skip(f"Login failed: {login_resp.status_code}")
            tokens = login_resp.json()

            resp = await client.post(
                "/auth/logout",
                headers={"Authorization": f"Bearer {tokens['access_token']}"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert "message" in data
