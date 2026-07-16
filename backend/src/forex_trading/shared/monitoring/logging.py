"""Structured logging configuration using structlog.

Call ``configure_logging()`` once at application startup to set up
JSON-formatted structured logging with timestamps, levels, and correlation IDs.
"""

from __future__ import annotations

import logging
import sys

import structlog


def configure_logging(
    log_level: str = "INFO",
    log_format: str = "json",
) -> None:
    """Configure structlog with JSON rendering and standard logging bridge.

    Args:
        log_level: One of DEBUG, INFO, WARNING, ERROR, CRITICAL.
        log_format: ``"json"`` for JSON output, ``"console"`` for colored console.
    """
    level = getattr(logging, log_level.upper(), logging.INFO)

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
    ]

    if log_format == "json":
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(
            colors=sys.stdout.isatty(),
            sort_keys=False,
        )

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.CallsiteParameterAdder(
                parameters=[
                    structlog.processors.CallsiteParameter.FILENAME,
                    structlog.processors.CallsiteParameter.LINENO,
                    structlog.processors.CallsiteParameter.FUNC_NAME,
                ]
            ),
            renderer,
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Route standard library logging through structlog
    stdlib_handler = logging.StreamHandler(sys.stdout)
    stdlib_handler.setLevel(level)
    stdlib_handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            processors=shared_processors + [renderer],
        )
    )

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(stdlib_handler)
    root_logger.setLevel(level)

    # Quieter noisy third-party loggers
    for noisy in ("uvicorn.access", "uvicorn.error", "httpx", "aiokafka"):
        logging.getLogger(noisy).setLevel(max(level, logging.WARNING))

    structlog.get_logger().info(
        "logging_configured",
        log_level=log_level,
        log_format=log_format,
    )
