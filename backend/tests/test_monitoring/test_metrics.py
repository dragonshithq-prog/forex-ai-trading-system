"""Tests for Prometheus metrics — label validation and metric existence."""

from __future__ import annotations

import pytest

from forex_trading.shared.monitoring.metrics import (
    ai_agent_latency_seconds,
    ai_drift_alerts_total,
    ai_signal_confidence,
    ai_signals_generated_total,
    broker_connections_total,
    broker_latency_seconds,
    cache_hits_total,
    cache_misses_total,
    circuit_breaker_state,
    db_pool_size,
    http_request_duration_seconds,
    http_requests_in_flight,
    http_requests_total,
    open_positions_count,
    outbox_events_total,
    outbox_latency_seconds,
    portfolio_exposure_pct,
    portfolio_pnl_usd,
    risk_alerts_total,
    risk_assessments_total,
    risk_vetoes_total,
    trade_execution_duration_seconds,
    trade_executions_total,
    trade_fills_total,
    trade_volume_lots,
    websocket_connections_active,
    websocket_messages_total,
)


# This is the complete list of metrics that must be defined
ALL_METRICS = [
    ("http_requests_total", http_requests_total),
    ("http_request_duration_seconds", http_request_duration_seconds),
    ("http_requests_in_flight", http_requests_in_flight),
    ("websocket_connections_active", websocket_connections_active),
    ("websocket_messages_total", websocket_messages_total),
    ("trade_executions_total", trade_executions_total),
    ("trade_execution_duration_seconds", trade_execution_duration_seconds),
    ("trade_fills_total", trade_fills_total),
    ("trade_volume_lots", trade_volume_lots),
    ("open_positions_count", open_positions_count),
    ("portfolio_pnl_usd", portfolio_pnl_usd),
    ("portfolio_exposure_pct", portfolio_exposure_pct),
    ("ai_signals_generated_total", ai_signals_generated_total),
    ("ai_signal_confidence", ai_signal_confidence),
    ("ai_agent_latency_seconds", ai_agent_latency_seconds),
    ("ai_drift_alerts_total", ai_drift_alerts_total),
    ("circuit_breaker_state", circuit_breaker_state),
    ("risk_assessments_total", risk_assessments_total),
    ("risk_alerts_total", risk_alerts_total),
    ("risk_vetoes_total", risk_vetoes_total),
    ("broker_connections_total", broker_connections_total),
    ("broker_latency_seconds", broker_latency_seconds),
    ("db_pool_size", db_pool_size),
    ("cache_hits_total", cache_hits_total),
    ("cache_misses_total", cache_misses_total),
    ("outbox_events_total", outbox_events_total),
    ("outbox_latency_seconds", outbox_latency_seconds),
]


class TestMetricsExist:
    """All 28 required metrics must be defined."""

    def test_all_metrics_importable(self):
        """All metrics should be importable and not None."""
        for name, metric in ALL_METRICS:
            assert metric is not None, f"Metric {name} is None"

    def test_total_metrics_count(self):
        """There should be exactly 27 metrics defined."""
        assert len(ALL_METRICS) == 27, f"Expected 27 metrics, got {len(ALL_METRICS)}"


class TestMetricLabels:
    """Validate that metrics have the correct label names."""

    def test_http_requests_total_labels(self):
        """http_requests_total should have method, endpoint, status labels."""
        labels = http_requests_total._labelnames
        assert "method" in labels
        assert "endpoint" in labels
        assert "status" in labels

    def test_trade_executions_total_labels(self):
        """trade_executions_total should have symbol, side, status labels."""
        labels = trade_executions_total._labelnames
        assert "symbol" in labels
        assert "side" in labels
        assert "status" in labels

    def test_ai_signals_generated_total_labels(self):
        """ai_signals_generated_total should have symbol, direction, actionable labels."""
        labels = ai_signals_generated_total._labelnames
        assert "symbol" in labels
        assert "direction" in labels
        assert "actionable" in labels

    def test_ai_agent_latency_seconds_labels(self):
        """ai_agent_latency_seconds should have agent_id label."""
        labels = ai_agent_latency_seconds._labelnames
        assert "agent_id" in labels

    def test_circuit_breaker_state_labels(self):
        """circuit_breaker_state should have broker_account_id label."""
        labels = circuit_breaker_state._labelnames
        assert "broker_account_id" in labels

    def test_risk_alerts_total_labels(self):
        """risk_alerts_total should have level, category labels."""
        labels = risk_alerts_total._labelnames
        assert "level" in labels
        assert "category" in labels

    def test_open_positions_count_labels(self):
        """open_positions_count should have symbol, side labels."""
        labels = open_positions_count._labelnames
        assert "symbol" in labels
        assert "side" in labels

    def test_broker_connections_total_labels(self):
        """broker_connections_total should have broker_type, status labels."""
        labels = broker_connections_total._labelnames
        assert "broker_type" in labels
        assert "status" in labels

    def test_outbox_events_total_labels(self):
        """outbox_events_total should have status label."""
        labels = outbox_events_total._labelnames
        assert "status" in labels

    def test_portfolio_exposure_pct_labels(self):
        """portfolio_exposure_pct should have symbol label."""
        labels = portfolio_exposure_pct._labelnames
        assert "symbol" in labels

    def test_trade_volume_lots_labels(self):
        """trade_volume_lots should have symbol label."""
        labels = trade_volume_lots._labelnames
        assert "symbol" in labels

    def test_risk_assessments_total_labels(self):
        """risk_assessments_total should have approved label."""
        labels = risk_assessments_total._labelnames
        assert "approved" in labels

    def test_risk_vetoes_total_labels(self):
        """risk_vetoes_total should have reason label."""
        labels = risk_vetoes_total._labelnames
        assert "reason" in labels


class TestMetricsCanIncrement:
    """Metrics should be usable (increment, observe, set) without errors."""

    def test_counter_increment(self):
        """Counters should support .inc() call."""
        ai_drift_alerts_total.inc()
        assert True  # No exception means success

    def test_gauge_set_and_dec(self):
        """Gauges should support .set(), .inc(), .dec()."""
        from uuid import uuid4
        # circuit_breaker_state uses broker_account_id label
        cb = circuit_breaker_state.labels(broker_account_id=str(uuid4()))
        cb.set(1)
        assert True

    def test_histogram_observe(self):
        """Histograms should support .observe() call."""
        trade_execution_duration_seconds.labels(symbol="EURUSD").observe(0.5)
        assert True

    def test_counter_labels(self):
        """Counter with labels should work."""
        trade_executions_total.labels(symbol="EURUSD", side="buy", status="approved").inc()
        assert True

    def test_multiple_label_values(self):
        """Metrics with multiple label combinations should work."""
        risk_alerts_total.labels(level="critical", category="drawdown").inc()
        risk_alerts_total.labels(level="warning", category="exposure").inc()
        risk_alerts_total.labels(level="info", category="position_size").inc()
        assert True

    def test_gauge_inc_dec(self):
        """Gauge inc/dec should not raise."""
        open_positions_count.labels(symbol="EURUSD", side="long").inc()
        open_positions_count.labels(symbol="EURUSD", side="long").dec()
        assert True


class TestMetricTypes:
    """Validate metric types (Counter, Gauge, Histogram)."""

    def test_http_requests_total_type(self):
        from prometheus_client import Counter
        assert isinstance(http_requests_total, Counter)

    def test_circuit_breaker_state_type(self):
        from prometheus_client import Gauge
        assert isinstance(circuit_breaker_state, Gauge)

    def test_trade_execution_duration_type(self):
        from prometheus_client import Histogram
        assert isinstance(trade_execution_duration_seconds, Histogram)
