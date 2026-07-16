"""OpenTelemetry tracing configuration.

Call ``configure_tracing()`` once at application startup to initialize
the TracerProvider and instrument key libraries.
"""

from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger()

_tracer_provider: Any = None


def configure_tracing(
    service_name: str = "forex-trading-engine",
    jaeger_endpoint: str | None = None,
    otlp_endpoint: str | None = None,
    instrument_fastapi: bool = True,
    instrument_sqlalchemy: bool = True,
    instrument_httpx: bool = True,
) -> None:
    """Initialize OpenTelemetry tracing.

    Args:
        service_name: Resource service name for trace identification.
        jaeger_endpoint: Jaeger HTTP endpoint (e.g. ``http://localhost:14268/api/traces``).
        otlp_endpoint: OTLP gRPC endpoint (e.g. ``http://localhost:4317``).
        instrument_fastapi: Auto-instrument FastAPI routes.
        instrument_sqlalchemy: Auto-instrument SQLAlchemy queries.
        instrument_httpx: Auto-instrument HTTPX client calls.
    """
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        resource = Resource.create({"service.name": service_name})
        provider = TracerProvider(resource=resource)

        if jaeger_endpoint:
            _add_jaeger_exporter(provider, jaeger_endpoint)
        elif otlp_endpoint:
            _add_otlp_exporter(provider, otlp_endpoint)

        trace.set_tracer_provider(provider)
        global _tracer_provider
        _tracer_provider = provider

        if instrument_fastapi:
            try:
                from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
                logger.info("fastapi_instrumentation_available")
            except ImportError:
                logger.warning("opentelemetry-instrumentation-fastapi not installed")

        if instrument_sqlalchemy:
            try:
                from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
                logger.info("sqlalchemy_instrumentation_available")
            except ImportError:
                logger.warning("opentelemetry-instrumentation-sqlalchemy not installed")

        if instrument_httpx:
            try:
                from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
                logger.info("httpx_instrumentation_available")
            except ImportError:
                logger.warning("opentelemetry-instrumentation-httpx not installed")

        logger.info(
            "tracing_configured",
            service_name=service_name,
            jaeger_endpoint=jaeger_endpoint,
            otlp_endpoint=otlp_endpoint,
        )

    except ImportError as exc:
        logger.warning("tracing_not_available", error=str(exc))


def _add_jaeger_exporter(provider: Any, endpoint: str) -> None:
    try:
        from opentelemetry.exporter.jaeger.thrift import JaegerExporter
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        exporter = JaegerExporter(
            collector_endpoint=endpoint,
        )
        provider.add_span_processor(BatchSpanProcessor(exporter))
        logger.info("jaeger_exporter_configured", endpoint=endpoint)
    except ImportError:
        logger.warning("opentelemetry-exporter-jaeger not installed")


def _add_otlp_exporter(provider: Any, endpoint: str) -> None:
    try:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        logger.info("otlp_exporter_configured", endpoint=endpoint)
    except ImportError:
        logger.warning("opentelemetry-exporter-otlp not installed")


def get_tracer(name: str = "forex_trading") -> Any:
    """Get a tracer instance for manual instrumentation."""
    try:
        from opentelemetry import trace
        return trace.get_tracer(name)
    except ImportError:
        return None


def shutdown_tracing() -> None:
    """Shut down the tracer provider (call during graceful shutdown)."""
    if _tracer_provider is not None:
        try:
            _tracer_provider.shutdown()
            logger.info("tracing_shutdown_complete")
        except Exception as exc:
            logger.warning("tracing_shutdown_error", error=str(exc))
