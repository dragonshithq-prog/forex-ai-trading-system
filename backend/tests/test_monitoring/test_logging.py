"""Tests for structlog configuration."""

from __future__ import annotations

import json
import logging
import sys
from io import StringIO

import pytest
import structlog


class TestConfigureLogging:
    """Tests for the logging configuration."""

    def test_configure_logging_json_format(self):
        """JSON format should produce valid JSON log output."""
        from forex_trading.shared.monitoring.logging import configure_logging

        # Capture stdout
        captured = StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured

        try:
            configure_logging(log_level="DEBUG", log_format="json")

            log = structlog.get_logger("test_logger")
            log.info("test_message", key="value")

            sys.stdout = old_stdout
            output = captured.getvalue().strip()

            # structlog wraps stdlib so the event field is a stringified JSON object.
            # Find the line whose event contains "test_message" and parse it.
            lines = [l for l in output.split("\n") if l.strip()]
            parsed = None
            for line in lines:
                candidate = json.loads(line)
                event_str = candidate.get("event", "")
                if isinstance(event_str, str):
                    try:
                        inner = json.loads(event_str)
                        if inner.get("event") == "test_message":
                            parsed = inner
                            break
                    except (json.JSONDecodeError, TypeError):
                        pass
            assert parsed is not None, f"No valid test_message line in output: {output}"
            assert parsed["key"] == "value"
            assert "timestamp" in parsed
            assert parsed["level"] == "info"
        finally:
            sys.stdout = old_stdout

    def test_configure_logging_console_format(self):
        """Console format should produce readable output."""
        from forex_trading.shared.monitoring.logging import configure_logging

        captured = StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured

        try:
            configure_logging(log_level="INFO", log_format="console")

            log = structlog.get_logger("console_test")
            log.info("console_message")

            sys.stdout = old_stdout
            output = captured.getvalue()
            assert "console_message" in output
        finally:
            sys.stdout = old_stdout

    def test_configure_logging_with_context(self):
        """Context variables should be included in log output."""
        from forex_trading.shared.monitoring.logging import configure_logging

        captured = StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured

        try:
            configure_logging(log_level="INFO", log_format="json")

            structlog.contextvars.bind_contextvars(correlation_id="test-123")
            log = structlog.get_logger("ctx_test")
            log.info("context_message")

            sys.stdout = old_stdout
            output = captured.getvalue().strip()

            # Look for the context_message line (not the logging_configured line)
            lines = [l for l in output.split("\n") if l.strip()]
            last_line = lines[-1]
            parsed = json.loads(last_line)
            assert parsed["correlation_id"] == "test-123"
        finally:
            sys.stdout = old_stdout
            structlog.contextvars.clear_contextvars()

    def test_noisy_loggers_suppressed(self):
        """Noisy third-party loggers should be set to a higher level."""
        from forex_trading.shared.monitoring.logging import configure_logging

        configure_logging(log_level="DEBUG", log_format="json")

        for noisy_name in ("uvicorn.access", "httpx", "aiokafka"):
            noisy_logger = logging.getLogger(noisy_name)
            assert noisy_logger.level >= logging.WARNING

    def test_root_logger_configured(self):
        """Root logger should use structlog format."""
        from forex_trading.shared.monitoring.logging import configure_logging

        configure_logging(log_level="INFO", log_format="json")

        root = logging.getLogger()
        assert len(root.handlers) > 0

    def test_log_level_enforcement(self):
        """Log messages below the configured level should not appear."""
        from forex_trading.shared.monitoring.logging import configure_logging

        captured = StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured

        try:
            configure_logging(log_level="WARNING", log_format="json")

            log = structlog.get_logger("level_test")
            log.debug("should_not_appear")
            log.info("should_not_appear_either")
            log.warning("should_appear")

            sys.stdout = old_stdout
            output = captured.getvalue()
            assert "should_appear" in output
            assert "should_not_appear" not in output
        finally:
            sys.stdout = old_stdout
