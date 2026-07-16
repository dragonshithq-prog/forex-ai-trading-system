"""Prometheus metrics definitions for the forex trading system.

All metrics are defined here using the prometheus_client library.
This module is imported by monitoring/__init__.py.
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

# ---- HTTP / API ----
http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    labelnames=["method", "endpoint", "status"],
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    labelnames=["method", "endpoint"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

http_requests_in_flight = Gauge(
    "http_requests_in_flight",
    "Current number of HTTP requests in flight",
    labelnames=["method"],
)

# ---- WebSocket ----
websocket_connections_active = Gauge(
    "websocket_connections_active",
    "Current number of active WebSocket connections",
)

websocket_messages_total = Counter(
    "websocket_messages_total",
    "Total WebSocket messages",
    labelnames=["channel", "direction"],
)

# ---- Trading ----
trade_executions_total = Counter(
    "trade_executions_total",
    "Total trade executions",
    labelnames=["symbol", "side", "status"],
)

trade_execution_duration_seconds = Histogram(
    "trade_execution_duration_seconds",
    "Trade execution duration in seconds",
    labelnames=["symbol"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)

trade_fills_total = Counter(
    "trade_fills_total",
    "Total trade fills",
    labelnames=["symbol", "side"],
)

trade_volume_lots = Counter(
    "trade_volume_lots",
    "Total trading volume in lots",
    labelnames=["symbol"],
)

# ---- Positions ----
open_positions_count = Gauge(
    "open_positions_count",
    "Number of open positions",
    labelnames=["symbol", "side"],
)

portfolio_pnl_usd = Gauge(
    "portfolio_pnl_usd",
    "Portfolio PnL in USD",
    labelnames=["type"],
)

portfolio_exposure_pct = Gauge(
    "portfolio_exposure_pct",
    "Portfolio exposure as percentage of equity",
    labelnames=["symbol"],
)

# ---- AI / ML ----
ai_signals_generated_total = Counter(
    "ai_signals_generated_total",
    "Total AI signals generated",
    labelnames=["symbol", "direction", "actionable"],
)

ai_signal_confidence = Histogram(
    "ai_signal_confidence",
    "AI signal confidence distribution",
    labelnames=["symbol"],
    buckets=(0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
)

ai_agent_latency_seconds = Histogram(
    "ai_agent_latency_seconds",
    "AI agent analysis latency in seconds",
    labelnames=["agent_id"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

ai_drift_alerts_total = Counter(
    "ai_drift_alerts_total",
    "Total AI drift alerts triggered",
    labelnames=[],
)

# ---- Risk ----
circuit_breaker_state = Gauge(
    "circuit_breaker_state",
    "Circuit breaker state (0=closed, 1=open)",
    labelnames=["broker_account_id"],
)

risk_assessments_total = Counter(
    "risk_assessments_total",
    "Total risk assessments performed",
    labelnames=["approved"],
)

risk_alerts_total = Counter(
    "risk_alerts_total",
    "Total risk alerts raised",
    labelnames=["level", "category"],
)

risk_vetoes_total = Counter(
    "risk_vetoes_total",
    "Total risk vetoes applied",
    labelnames=["reason"],
)

# ---- Broker ----
broker_connections_total = Gauge(
    "broker_connections_total",
    "Number of broker connections",
    labelnames=["broker_type", "status"],
)

broker_latency_seconds = Histogram(
    "broker_latency_seconds",
    "Broker operation latency in seconds",
    labelnames=["broker_type", "operation"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

# ---- Database ----
db_pool_size = Gauge(
    "db_pool_size",
    "Database connection pool size",
    labelnames=["state"],
)

# ---- Cache ----
cache_hits_total = Counter(
    "cache_hits_total",
    "Total cache hits",
    labelnames=["cache_name"],
)

cache_misses_total = Counter(
    "cache_misses_total",
    "Total cache misses",
    labelnames=["cache_name"],
)

# ---- Outbox ----
outbox_events_total = Counter(
    "outbox_events_total",
    "Total outbox events processed",
    labelnames=["status"],
)

outbox_latency_seconds = Histogram(
    "outbox_latency_seconds",
    "Outbox event processing latency",
    labelnames=[],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)
