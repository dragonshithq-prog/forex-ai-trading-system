# =============================================================================
# Forex AI Trading Platform — Backend Dockerfile (Production Multi-Stage)
# =============================================================================
# Stage 1 (builder)  : Install system deps + build Python wheels
# Stage 2 (final)    : Minimal image with only wheels + source, non-root user
# =============================================================================

# ── Stage 1: Builder ─────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

# Build-time labels
ARG BUILD_DATE
ARG GIT_SHA
LABEL org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.revision="${GIT_SHA}" \
      org.opencontainers.image.title="forex-trading-backend-builder" \
      org.opencontainers.image.description="Forex AI Trading Platform — Backend Builder"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_NO_CACHE=1

# Install build dependencies (only in builder stage)
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        g++ \
        libpq-dev \
        libffi-dev \
        libssl-dev \
        curl \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install uv — fast Python package installer
RUN curl -LsSf https://astral.sh/uv/install.sh | sh && \
    mv /root/.local/bin/uv /usr/local/bin/uv && \
    mv /root/.local/bin/uvx /usr/local/bin/uvx

WORKDIR /build

# Copy dependency manifest first (layer-cache optimisation)
COPY pyproject.toml README.md* ./
COPY uv.lock* ./

# Build wheels for all production dependencies (no dev extras)
RUN uv pip compile pyproject.toml --all-extras --output-file requirements-all.txt 2>/dev/null || \
    uv pip compile pyproject.toml --output-file requirements-all.txt && \
    pip wheel --no-cache-dir --wheel-dir /build/wheels -r requirements-all.txt && \
    # Also build the package itself as a wheel
    pip wheel --no-cache-dir --wheel-dir /build/wheels --no-deps .

# ── Stage 2: Final Production Image ──────────────────────────────────────────
FROM python:3.12-slim AS final

ARG BUILD_DATE
ARG GIT_SHA
LABEL org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.revision="${GIT_SHA}" \
      org.opencontainers.image.title="forex-trading-backend" \
      org.opencontainers.image.description="Forex AI Trading Platform — Backend API" \
      org.opencontainers.image.vendor="Forex Trading Platform"

# Harden environment
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONFAULTHANDLER=1 \
    PORT=8000 \
    WORKERS=4 \
    LOG_LEVEL=info

# Install only runtime system libraries (no build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        libffi8 \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get purge -y --auto-remove

# Create non-root user before copying any files
RUN groupadd --gid 10001 appgroup && \
    useradd --uid 10001 --gid appgroup \
            --no-create-home --shell /sbin/nologin \
            appuser

WORKDIR /app

# Copy pre-built wheels from builder stage
COPY --from=builder /build/wheels /tmp/wheels

# Install wheels (no index, offline) — fast and reproducible
RUN pip install --no-cache-dir --no-index --find-links /tmp/wheels /tmp/wheels/*.whl && \
    rm -rf /tmp/wheels

# Copy application source code
COPY --chown=appuser:appgroup src ./src

# Create required runtime directories with correct ownership
RUN mkdir -p /app/logs /app/tmp && \
    chown -R appuser:appgroup /app

# Switch to non-root user
USER appuser

EXPOSE 8000

# Health check (uses the /health endpoint)
HEALTHCHECK --interval=15s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Production-grade uvicorn startup
CMD ["sh", "-c", \
     "python -m gunicorn forex_trading.main:app \
      --workers ${WORKERS:-4} \
      --worker-class uvicorn.workers.UvicornWorker \
      --bind 0.0.0.0:${PORT:-8000} \
      --timeout 120 \
      --keepalive 5 \
      --max-requests 1000 \
      --max-requests-jitter 100 \
      --proxy-headers \
      --forwarded-allow-ips='*' \
      --access-logfile - \
      --error-logfile - \
      --log-level ${LOG_LEVEL:-info}"]
