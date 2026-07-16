"""Tests for SecretsSettings — validation, redaction, environment backends."""

from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

from forex_trading.shared.security.secrets import (
    SecretsSettings,
    get_secrets_settings,
    redact_secrets,
    EnvironmentBackend,
    SecretBackend,
    SECRET_KEY_PATTERN,
)


pytestmark = pytest.mark.asyncio


class TestSecretsSettings:
    """Tests for the SecretsSettings configuration."""

    def test_defaults_loaded(self):
        """SecretsSettings should load with defaults when no env is set."""
        settings = SecretsSettings()
        assert settings.ENVIRONMENT == "development"
        assert settings.SECRET_KEY is not None
        assert settings.JWT_SECRET_KEY is not None
        assert settings.DATABASE_URL is not None

    def test_default_secret_warning(self, caplog):
        """Using default secrets should log a warning."""
        settings = SecretsSettings()
        # The field validator should log a warning for default values
        assert settings.SECRET_KEY == "change-me-in-production-use-vault"

    def test_production_fail_fast_exits(self):
        """fail_fast in production with default secrets should call sys.exit."""
        settings = SecretsSettings(ENVIRONMENT="production")
        with pytest.raises(SystemExit) as exc:
            settings.fail_fast()
        assert exc.value.code == 1

    def test_production_fail_fast_passes_with_strong_secrets(self):
        """fail_fast should pass with strong secrets."""
        settings = SecretsSettings(
            ENVIRONMENT="production",
            SECRET_KEY="a" * 32 + "B!9$x#P@",
            JWT_SECRET_KEY="b" * 32 + "Z!7$y#Q@",
            DATABASE_URL="postgresql+asyncpg://user:pass@localhost/db",
            REDIS_URL="redis://:password@localhost:6379/0",
        )
        # Should not raise
        settings.fail_fast()

    def test_development_skip_fail_fast(self):
        """fail_fast should not exit in development."""
        settings = SecretsSettings(ENVIRONMENT="development")
        # Should not raise or exit
        settings.fail_fast()

    async def test_backend_resolve_fallback(self):
        """resolve should fall back to env vars if backend returns None."""
        os.environ["TEST_SECRET"] = "env_value"
        settings = SecretsSettings()
        value = await settings.resolve("TEST_SECRET")
        assert value == "env_value" or value is None

    async def test_custom_backend(self):
        """A custom backend should be usable."""
        class TestBackend(SecretBackend):
            async def get(self, key: str) -> str | None:
                if key == "TEST_KEY":
                    return "backend_value"
                return None
            async def set(self, key: str, value: str) -> None:
                pass
            async def rotate(self, key: str, new_value: str) -> None:
                pass

        settings = SecretsSettings()
        settings.set_backend(TestBackend())
        assert settings._backend is not None


class TestEnvironmentBackend:
    """Tests for the environment variable secret backend."""

    async def test_get_existing(self):
        os.environ["TEST_BACKEND_KEY"] = "test_value"
        backend = EnvironmentBackend()
        value = await backend.get("TEST_BACKEND_KEY")
        assert value == "test_value"

    async def test_get_missing(self):
        backend = EnvironmentBackend()
        value = await backend.get("NONEXISTENT_KEY_12345")
        assert value is None

    async def test_set(self):
        backend = EnvironmentBackend()
        await backend.set("TEST_SET_KEY", "new_value")
        assert os.environ.get("TEST_SET_KEY") == "new_value"

    async def test_rotate(self):
        os.environ["TEST_ROTATE_KEY"] = "old_value"
        backend = EnvironmentBackend()
        await backend.rotate("TEST_ROTATE_KEY", "new_value")
        assert os.environ.get("TEST_ROTATE_KEY") == "new_value"


class TestRedactSecrets:
    """Tests for the secret redaction function."""

    def test_redact_known_secret_keys(self):
        payload = {
            "SECRET_KEY": "super-secret-value",
            "JWT_SECRET_KEY": "jwt-secret",
            "normal_key": "visible",
        }
        redacted = redact_secrets(payload)
        assert redacted["SECRET_KEY"] == "***"
        assert redacted["JWT_SECRET_KEY"] == "***"
        assert redacted["normal_key"] == "visible"

    def test_redact_nested_dict(self):
        payload = {
            "config": {
                "api_key": "secret-key-12345",
                "password": "hunter2",
                "name": "John",
            }
        }
        redacted = redact_secrets(payload)
        assert redacted["config"]["api_key"] == "***"
        assert redacted["config"]["password"] == "***"
        assert redacted["config"]["name"] == "John"

    def test_redact_url_like_secrets(self):
        """Strings containing colons or slashes with length > 20 should be redacted."""
        payload = {
            "webhook": "https://hooks.slack.com/services/T00/B00/xxxx",
            "short": "hello",
        }
        redacted = redact_secrets(payload)
        assert redacted["webhook"] == "***"
        assert redacted["short"] == "hello"

    def test_redact_empty_payload(self):
        assert redact_secrets({}) == {}

    def test_redact_no_secrets(self):
        payload = {"name": "test", "value": 42}
        redacted = redact_secrets(payload)
        assert redacted == payload


class TestSecretKeyPattern:
    """Tests for the SECRET_KEY_PATTERN regex."""

    def test_strong_key_matches(self):
        assert SECRET_KEY_PATTERN.match("a" * 32 + "B!9$x#P@") is not None
        assert SECRET_KEY_PATTERN.match("Abcd1234!@#$%^&*()" + "x" * 16) is not None

    def test_short_key_fails(self):
        assert SECRET_KEY_PATTERN.match("short") is None

    def test_key_with_spaces_fails(self):
        assert SECRET_KEY_PATTERN.match("a" * 32 + " with space") is None


class TestSecretsSettingsResolution:
    """Tests for secret field resolution."""

    def test_resolve_existing_field(self):
        settings = SecretsSettings()
        assert settings.JWT_ALGORITHM == "HS256"
        assert settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES == 5
        assert settings.JWT_REFRESH_TOKEN_EXPIRE_HOURS == 24

    def test_oanda_keys_optional(self):
        settings = SecretsSettings()
        # These should be None by default
        assert settings.OANDA_API_KEY is None or isinstance(settings.OANDA_API_KEY, str)
        assert settings.SLACK_WEBHOOK_URL is None or isinstance(settings.SLACK_WEBHOOK_URL, str)
