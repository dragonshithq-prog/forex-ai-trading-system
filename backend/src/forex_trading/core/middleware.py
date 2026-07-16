"""Core middleware for request processing.

Provides:
  - Request ID tagging
  - Request timing
  - Security headers (CSP, HSTS with preload, Permissions-Policy, Referrer-Policy)
  - Request size limiting
  - Audit logging for sensitive operations
  - Rate limiting integration
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Callable

from fastapi import FastAPI, HTTPException, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
import structlog

from forex_trading.config import get_settings

logger = structlog.get_logger()
settings = get_settings()


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Add unique request ID to every request."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Use existing ID if provided (e.g. from gateway)
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id

        structlog.contextvars.bind_contextvars(request_id=request_id)

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id

        structlog.contextvars.unbind_contextvars("request_id")
        return response


class TimingMiddleware(BaseHTTPMiddleware):
    """Add request timing headers and log completion."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.perf_counter()

        response = await call_next(request)

        process_time = time.perf_counter() - start_time
        response.headers["X-Process-Time"] = f"{process_time:.4f}"

        logger.info(
            "request_completed",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            process_time=round(process_time, 4),
        )

        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add comprehensive security headers to every response.

    Headers set:
      - X-Content-Type-Options: nosniff
      - X-Frame-Options: DENY
      - X-XSS-Protection: 1; mode=block
      - Strict-Transport-Security: max-age=63072000; includeSubDomains; preload
      - Content-Security-Policy: restrictive default
      - Permissions-Policy: limits feature access
      - Referrer-Policy: strict-origin-when-cross-origin
      - Cache-Control: no-store (for dynamic API responses)
    """

    # CSP directives — adjust as needed for your frontend
    _CSP = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "font-src 'self'; "
        "connect-src 'self' ws: wss:; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "frame-ancestors 'none'; "
        "upgrade-insecure-requests"
    )

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)

        # ---- Standard protection headers ----
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # ---- HSTS with preload (2 years) ----
        response.headers["Strict-Transport-Security"] = (
            "max-age=63072000; includeSubDomains; preload"
        )

        # ---- Content Security Policy ----
        response.headers["Content-Security-Policy"] = self._CSP

        # ---- Permissions Policy (restrict browser features) ----
        response.headers["Permissions-Policy"] = (
            "accelerometer=(), "
            "camera=(), "
            "geolocation=(), "
            "gyroscope=(), "
            "magnetometer=(), "
            "microphone=(), "
            "payment=(), "
            "usb=()"
        )

        # ---- Referrer Policy ----
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # ---- Cache control for dynamic API responses ----
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, proxy-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"

        return response


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """Limit the maximum request body size.

    Returns ``413 Payload Too Large`` if the ``Content-Length`` header
    exceeds the configured limit.
    """

    def __init__(self, app: Any, max_bytes: int = 1_048_576) -> None:
        super().__init__(app)
        self.max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        content_length_str = request.headers.get("Content-Length")
        if content_length_str is not None:
            try:
                content_length = int(content_length_str)
                if content_length > self.max_bytes:
                    logger.warning(
                        "request_size_exceeded",
                        content_length=content_length,
                        max_bytes=self.max_bytes,
                        path=request.url.path,
                    )
                    raise HTTPException(
                        status_code=413,
                        detail={
                            "error": {
                                "code": "PAYLOAD_TOO_LARGE",
                                "message": f"Request body exceeds maximum size of {self.max_bytes} bytes.",
                                "max_bytes": self.max_bytes,
                            }
                        },
                    )
            except ValueError:
                pass

        return await call_next(request)


def setup_middleware(app: FastAPI) -> None:
    """Setup all middleware for the application.

    Order matters:
      1. RequestID (outermost)
      2. Timing
      3. SecurityHeaders
      4. RequestSizeLimit
      5. AuditMiddleware (if configured)
      6. RateLimitMiddleware (if configured)
    """
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(TimingMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestSizeLimitMiddleware, max_bytes=settings.MAX_REQUEST_SIZE_BYTES)

    # Audit middleware is added in main.py when needed
    # Rate limit middleware is added in main.py when needed
