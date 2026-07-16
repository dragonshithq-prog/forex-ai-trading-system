"""Sliding window rate limiter backed by Redis.

Supports per-endpoint, per-user, and per-API-key limits.
Returns ``429 Too Many Requests`` with a ``Retry-After`` header when
the limit is exceeded.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import redis.asyncio as redis
from fastapi import HTTPException, Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
import structlog

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Rate limit rule
# ---------------------------------------------------------------------------


@dataclass
class RateLimitRule:
    """A single rate-limit rule.

    Parameters
    ----------
    route : str
        Route pattern (e.g. ``/api/v1/auth/login``).  Supports ``*`` prefix.
    max_requests : int
        Maximum number of requests allowed in the window.
    window_seconds : int
        Sliding window duration in seconds.
    by_user : bool
        If ``True``, limit is applied per-user (requires authenticated user).
    by_ip : bool
        If ``True``, limit is applied per-client IP.
    by_api_key : bool
        If ``True``, limit is applied per-API-key.
    """

    route: str
    max_requests: int
    window_seconds: int = 60
    by_user: bool = True
    by_ip: bool = True
    by_api_key: bool = True


# Default rate limit rules — tuned for a trading API
DEFAULT_RULES: list[RateLimitRule] = [
    # Auth endpoints — strict limits
    RateLimitRule(route="/api/v1/auth/login", max_requests=10, window_seconds=60, by_user=False, by_api_key=False),
    RateLimitRule(route="/api/v1/auth/register", max_requests=3, window_seconds=3600, by_user=False, by_api_key=False),
    RateLimitRule(route="/api/v1/auth/password-reset", max_requests=3, window_seconds=3600, by_user=False, by_api_key=False),
    RateLimitRule(route="/api/v1/auth/refresh", max_requests=20, window_seconds=60, by_user=False, by_api_key=False),
    # Trading endpoints — 30 requests per minute
    RateLimitRule(route="/api/v1/trading/*", max_requests=30, window_seconds=60),
    # Market data — 120 requests per minute (read-heavy)
    RateLimitRule(route="/api/v1/market/*", max_requests=120, window_seconds=60),
    # Broker operations — 20 requests per minute
    RateLimitRule(route="/api/v1/broker/*", max_requests=20, window_seconds=60),
    # Risk endpoints — 30 requests per minute
    RateLimitRule(route="/api/v1/risk/*", max_requests=30, window_seconds=60),
    # Strategy endpoints — 20 requests per minute
    RateLimitRule(route="/api/v1/strategy/*", max_requests=20, window_seconds=60),
    # User management — 30 requests per minute (admin)
    RateLimitRule(route="/api/v1/users/*", max_requests=30, window_seconds=60),
    # Analytics — 20 requests per minute
    RateLimitRule(route="/api/v1/analytics/*", max_requests=20, window_seconds=60),
    # Health checks — 60 requests per minute
    RateLimitRule(route="/health*", max_requests=60, window_seconds=60, by_user=False, by_api_key=False),
    # Default catch-all
    RateLimitRule(route="*", max_requests=60, window_seconds=60),
]

REDIS_KEY_PREFIX = "rl:"


# ---------------------------------------------------------------------------
# Sliding window implementation
# ---------------------------------------------------------------------------


def _redis_key(rule: RateLimitRule, identifier: str) -> str:
    """Build a deterministic Redis key for the rule + identifier."""
    return f"{REDIS_KEY_PREFIX}{rule.route}:{identifier}"


def _route_matches(pattern: str, path: str) -> bool:
    """Check whether *path* matches a route pattern (supports trailing ``*``)."""
    if pattern == "*":
        return True
    if pattern.endswith("*"):
        prefix = pattern.rstrip("*")
        # Strip trailing slash so "/api/v1/trading/*" also matches "/api/v1/trading"
        prefix = prefix.rstrip("/")
        return path.startswith(prefix) and (len(path) == len(prefix) or path[len(prefix)] == "/")
    return path == pattern


def _get_client_ip(request: Request) -> str:
    """Extract the client IP from headers or direct connection."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    client = request.client
    if client:
        return client.host
    return "unknown"


def _get_user_id(request: Request) -> str | None:
    """Extract user identifier from request state or auth headers."""
    if hasattr(request.state, "user_id") and request.state.user_id:
        return str(request.state.user_id)
    if hasattr(request.state, "current_user_id") and request.state.current_user_id:
        return str(request.state.current_user_id)
    return None


def _get_api_key(request: Request) -> str | None:
    """Extract API key from a custom header (``X-API-Key``)."""
    return request.headers.get("X-API-Key")


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------


class RateLimiter:
    """Sliding window rate limiter using Redis sorted sets.

    Usage
    -----
    .. code-block:: python

        rate_limiter = RateLimiter(redis_url="redis://localhost:6379/0")
        await rate_limiter.initialize()
        # ... later, in a middleware:
        await rate_limiter.check(request)
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        rules: list[RateLimitRule] | None = None,
    ) -> None:
        self._redis_url = redis_url
        self._redis: redis.Redis | None = None
        self._rules = rules or DEFAULT_RULES

    async def initialize(self) -> None:
        """Create the Redis connection pool."""
        self._redis = redis.from_url(
            self._redis_url,
            max_connections=20,
            decode_responses=True,
        )
        logger.info("rate_limiter_initialized")

    async def close(self) -> None:
        """Close the Redis connection pool."""
        if self._redis:
            await self._redis.close()
            logger.info("rate_limiter_closed")

    async def _check_sliding_window(
        self,
        rule: RateLimitRule,
        identifier: str,
    ) -> tuple[bool, int]:
        """Check the sliding window for *identifier* under *rule*.

        Returns
        -------
        tuple[bool, int]
            ``(allowed, retry_after_seconds)``
        """
        if not self._redis:
            return True, 0

        key = _redis_key(rule, identifier)
        now = time.time()
        window_start = now - rule.window_seconds

        # Remove entries outside the window
        await self._redis.zremrangebyscore(key, "-inf", window_start)

        # Count entries in the current window
        count = await self._redis.zcard(key)

        if count >= rule.max_requests:
            # Get the oldest entry's timestamp to compute Retry-After
            oldest = await self._redis.zrange(key, 0, 0, withscores=True)
            if oldest:
                retry_after = int(math.ceil(rule.window_seconds - (now - oldest[0][1])))
            else:
                retry_after = rule.window_seconds
            logger.warning(
                "rate_limit_exceeded",
                identifier=identifier,
                route=rule.route,
                count=count,
                max_requests=rule.max_requests,
            )
            return False, max(retry_after, 1)

        # Add current request timestamp
        await self._redis.zadd(key, {str(now): now})
        await self._redis.expire(key, rule.window_seconds * 2)

        return True, 0

    async def check(self, request: Request) -> None:
        """Check all matching rules for *request*.  Raise ``HTTPException``
        on limit exceeded with a ``Retry-After`` header."""
        path = request.url.path
        method = request.method

        # Skip non-API paths
        if path in ("/health", "/health/live", "/health/ready", "/metrics", "/favicon.ico"):
            return None

        identifiers: list[str] = []

        for rule in self._rules:
            if not _route_matches(rule.route, path):
                continue

            # Build identifier(s) for this rule
            rule_ids: list[str] = []
            if rule.by_ip:
                rule_ids.append(f"ip:{_get_client_ip(request)}")
            if rule.by_user:
                user_id = _get_user_id(request)
                if user_id:
                    rule_ids.append(f"user:{user_id}")
            if rule.by_api_key:
                api_key = _get_api_key(request)
                if api_key:
                    rule_ids.append(f"apikey:{api_key[:12]}")

            # If no identifier was resolved, fall back to IP
            if not rule_ids:
                rule_ids.append(f"ip:{_get_client_ip(request)}")

            for identifier in rule_ids:
                allowed, retry_after = await self._check_sliding_window(rule, identifier)
                if not allowed:
                    raise HTTPException(
                        status_code=429,
                        detail={
                            "error": {
                                "code": "RATE_LIMIT_EXCEEDED",
                                "message": f"Too many requests. Try again in {retry_after} seconds.",
                                "retry_after_seconds": retry_after,
                            }
                        },
                        headers={"Retry-After": str(retry_after)},
                    )

        return None

    async def get_remaining(
        self,
        request: Request,
    ) -> dict[str, dict[str, int]]:
        """Return remaining quota for all matching rules.

        Useful for ``X-RateLimit-Remaining`` headers.
        """
        path = request.url.path
        result: dict[str, dict[str, int]] = {}

        for rule in self._rules:
            if not _route_matches(rule.route, path):
                continue

            identifiers: list[str] = []
            if rule.by_ip:
                identifiers.append(f"ip:{_get_client_ip(request)}")
            if rule.by_user:
                user_id = _get_user_id(request)
                if user_id:
                    identifiers.append(f"user:{user_id}")
            if rule.by_api_key:
                api_key = _get_api_key(request)
                if api_key:
                    identifiers.append(f"apikey:{api_key[:12]}")

            for identifier in identifiers:
                key = _redis_key(rule, identifier)
                if self._redis:
                    count = await self._redis.zcard(key) if self._redis else 0
                    remaining = max(0, rule.max_requests - count)
                else:
                    remaining = rule.max_requests
                result[identifier] = {
                    "remaining": remaining,
                    "limit": rule.max_requests,
                    "window_seconds": rule.window_seconds,
                }

        return result


# ---------------------------------------------------------------------------
# FastAPI middleware
# ---------------------------------------------------------------------------


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Apply rate limiting to all incoming requests.

    Usage
    -----
    .. code-block:: python

        app.add_middleware(RateLimitMiddleware, rate_limiter=rate_limiter)
    """

    def __init__(
        self,
        app: ASGIApp,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        super().__init__(app)
        self.rate_limiter = rate_limiter

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if self.rate_limiter is not None:
            try:
                await self.rate_limiter.check(request)
            except HTTPException:
                raise
            except Exception as exc:
                logger.error("rate_limit_check_failed", error=str(exc))

        response = await call_next(request)

        # Add rate limit headers if available
        if self.rate_limiter is not None:
            try:
                remaining = await self.rate_limiter.get_remaining(request)
                # Only add headers if we have meaningful data
                if remaining:
                    # Use the most restrictive remaining count
                    min_remaining = min(v["remaining"] for v in remaining.values())
                    min_limit = min(v["limit"] for v in remaining.values())
                    response.headers["X-RateLimit-Limit"] = str(min_limit)
                    response.headers["X-RateLimit-Remaining"] = str(min_remaining)
            except Exception:
                pass

        return response


# ---------------------------------------------------------------------------
# Convenience instance
# ---------------------------------------------------------------------------

rate_limiter = RateLimiter()
