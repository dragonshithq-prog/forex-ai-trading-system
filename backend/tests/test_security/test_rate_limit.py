"""Tests for Redis sliding window rate limiter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from forex_trading.core.rate_limit import (
    RateLimiter,
    RateLimitRule,
    RateLimitMiddleware,
    _route_matches,
    _get_client_ip,
    _redis_key,
)


class TestRouteMatching:
    """Tests for the route pattern matching function."""

    def test_wildcard_matches_all(self):
        assert _route_matches("*", "/api/v1/anything") is True
        assert _route_matches("*", "/health") is True

    def test_prefix_matching(self):
        assert _route_matches("/api/v1/trading/*", "/api/v1/trading/orders") is True
        assert _route_matches("/api/v1/trading/*", "/api/v1/trading/positions") is True
        assert _route_matches("/api/v1/trading/*", "/api/v1/trading") is True

    def test_exact_matching(self):
        assert _route_matches("/api/v1/auth/login", "/api/v1/auth/login") is True
        assert _route_matches("/api/v1/auth/login", "/api/v1/auth/register") is False

    def test_no_match(self):
        assert _route_matches("/api/v1/trading/*", "/api/v1/market/data") is False


class TestRedisKey:
    """Tests for Redis key generation."""

    def test_redis_key_format(self):
        rule = RateLimitRule(route="/api/v1/trading/*", max_requests=30)
        key = _redis_key(rule, "user:test-user")
        assert key.startswith("rl:")
        assert "/api/v1/trading/*" in key
        assert "user:test-user" in key


class TestClientIpExtraction:
    """Tests for client IP extraction."""

    def test_from_forwarded_header(self):
        request = MagicMock()
        request.headers = {"X-Forwarded-For": "203.0.113.1, 198.51.100.1"}
        request.client = None
        ip = _get_client_ip(request)
        assert ip == "203.0.113.1"

    def test_from_real_ip_header(self):
        request = MagicMock()
        request.headers = {"X-Real-IP": "192.168.1.1"}
        request.client = None
        ip = _get_client_ip(request)
        assert ip == "192.168.1.1"

    def test_from_client(self):
        request = MagicMock()
        request.headers = {}
        request.client.host = "10.0.0.1"
        ip = _get_client_ip(request)
        assert ip == "10.0.0.1"

    def test_fallback_to_unknown(self):
        request = MagicMock()
        request.headers = {}
        request.client = None
        ip = _get_client_ip(request)
        assert ip == "unknown"


class TestRateLimiter:
    """Tests for the RateLimiter (with mocked Redis)."""

    async def test_initialize_and_close(self):
        """Rate limiter should initialize and close cleanly."""
        limiter = RateLimiter(redis_url="redis://localhost:6379/0")
        limiter._redis = AsyncMock()
        limiter._redis.close = AsyncMock()

        # Should not raise
        await limiter.close()

    async def test_check_skips_health_paths(self):
        """Health check paths should be skipped."""
        limiter = RateLimiter()
        request = MagicMock()
        request.url.path = "/health"
        request.method = "GET"

        result = await limiter.check(request)
        assert result is None

    async def test_check_skips_metrics_path(self):
        """Metrics path should be skipped."""
        limiter = RateLimiter()
        request = MagicMock()
        request.url.path = "/metrics"
        request.method = "GET"

        result = await limiter.check(request)
        assert result is None

    async def test_check_allows_valid_request(self):
        """Valid requests within limits should be allowed."""
        limiter = RateLimiter()
        limiter._redis = AsyncMock()
        limiter._redis.zremrangebyscore = AsyncMock()
        limiter._redis.zcard = AsyncMock(return_value=5)  # 5 requests so far
        limiter._redis.zadd = AsyncMock()
        limiter._redis.expire = AsyncMock()

        request = MagicMock()
        request.url.path = "/api/v1/trading/orders"
        request.method = "GET"
        request.headers = {}
        request.client.host = "10.0.0.1"
        request.state.user_id = None

        # Should not raise because 5 < max 30
        result = await limiter.check(request)
        assert result is None

    async def test_check_blocks_excessive_requests(self):
        """Requests exceeding the limit should raise HTTPException."""
        limiter = RateLimiter()
        limiter._redis = AsyncMock()
        limiter._redis.zremrangebyscore = AsyncMock()
        limiter._redis.zcard = AsyncMock(return_value=60)  # Max is 60
        limiter._redis.zrange = AsyncMock(return_value=[("req1", 100.0)])

        request = MagicMock()
        request.url.path = "/api/v1/market/data"
        request.method = "GET"
        request.headers = {}
        request.client.host = "10.0.0.1"
        request.state.user_id = None

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await limiter.check(request)
        assert exc_info.value.status_code == 429

    async def test_check_with_user_id(self):
        """Rate limiting should work with user-based identifiers."""
        limiter = RateLimiter()
        limiter._redis = AsyncMock()
        limiter._redis.zremrangebyscore = AsyncMock()
        limiter._redis.zcard = AsyncMock(return_value=5)
        limiter._redis.zadd = AsyncMock()
        limiter._redis.expire = AsyncMock()

        request = MagicMock()
        request.url.path = "/api/v1/trading/orders"
        request.method = "GET"
        request.headers = {}
        request.client.host = "10.0.0.1"
        request.state.user_id = uuid4()

        result = await limiter.check(request)
        assert result is None

    async def test_get_remaining(self):
        """get_remaining should return quota information."""
        limiter = RateLimiter()
        limiter._redis = AsyncMock()
        limiter._redis.zcard = AsyncMock(return_value=5)

        request = MagicMock()
        request.url.path = "/api/v1/trading/orders"
        request.headers = {}
        request.client.host = "10.0.0.1"
        request.state.user_id = None

        remaining = await limiter.get_remaining(request)
        assert len(remaining) > 0
        for info in remaining.values():
            assert "remaining" in info
            assert "limit" in info
            assert "window_seconds" in info


class TestRateLimitMiddleware:
    """Tests for the FastAPI rate limit middleware."""

    async def test_middleware_passes_through(self):
        """Middleware should pass requests through when rate limiter is None."""
        from starlette.types import ASGIApp
        app = MagicMock(spec=ASGIApp)
        middleware = RateLimitMiddleware(app, rate_limiter=None)

        request = MagicMock()
        call_next = AsyncMock()
        response = await middleware.dispatch(request, call_next)
        assert response is not None
        call_next.assert_called_once()


# Need uuid4 for the test
from uuid import uuid4


class TestRateLimitRule:
    """Tests for RateLimitRule configuration."""

    def test_default_rule_creation(self):
        rule = RateLimitRule(route="/api/v1/trading/*", max_requests=30)
        assert rule.route == "/api/v1/trading/*"
        assert rule.max_requests == 30
        assert rule.window_seconds == 60  # Default
        assert rule.by_user is True
        assert rule.by_ip is True

    def test_custom_window(self):
        rule = RateLimitRule(route="/api/v1/auth/login", max_requests=10, window_seconds=30, by_user=False)
        assert rule.window_seconds == 30
        assert rule.by_user is False
