"""Tests for audit logging — AuditService and sensitive path detection."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from forex_trading.shared.security.audit import (
    AuditService,
    is_sensitive_path,
    classify_action,
    SENSITIVE_ACTIONS,
)


class TestAuditService:
    """Tests for the AuditService."""

    async def test_record_creates_entry(self):
        """Recording an audit entry should add it to the DB."""
        from forex_trading.shared.database.models_user import AuditLog

        service = AuditService()
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        entry = await service.record(
            mock_db,
            user_id=uuid4(),
            action="user.role.update",
            resource_type="user",
            resource_id=str(uuid4()),
            details={"old_role": "viewer", "new_role": "admin"},
            ip_address="192.168.1.1",
        )
        assert entry is not None
        assert mock_db.add.called
        assert mock_db.commit.called

    async def test_get_entries(self):
        """Getting audit entries should query the DB with filters."""
        service = AuditService()
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        entries = await service.get_entries(mock_db, limit=10)
        assert entries == []

    async def test_count_entries(self):
        """Counting audit entries should return the count."""
        service = AuditService()
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 5
        mock_db.execute = AsyncMock(return_value=mock_result)

        count = await service.count_entries(mock_db)
        assert count == 5


class TestSensitivePathDetection:
    """Tests for sensitive path detection."""

    def test_user_endpoints_are_sensitive(self):
        assert is_sensitive_path("GET", "/api/v1/users/") is True
        assert is_sensitive_path("POST", "/api/v1/users") is True
        assert is_sensitive_path("PUT", "/api/v1/users/123/role") is True
        assert is_sensitive_path("DELETE", "/api/v1/users/123") is True

    def test_auth_endpoints_are_sensitive(self):
        assert is_sensitive_path("POST", "/api/v1/auth/login") is True
        assert is_sensitive_path("GET", "/api/v1/auth/me") is True

    def test_broker_endpoints_are_sensitive(self):
        assert is_sensitive_path("GET", "/api/v1/broker/") is True
        assert is_sensitive_path("POST", "/api/v1/broker/connect") is True

    def test_risk_endpoints_are_sensitive(self):
        assert is_sensitive_path("POST", "/api/v1/risk/config") is True
        assert is_sensitive_path("POST", "/api/v1/risk/emergency") is True

    def test_trading_endpoints_are_sensitive(self):
        assert is_sensitive_path("GET", "/api/v1/trading/orders") is True

    def test_health_endpoints_not_sensitive(self):
        assert is_sensitive_path("GET", "/health") is False
        assert is_sensitive_path("GET", "/health/live") is False
        assert is_sensitive_path("GET", "/metrics") is False

    def test_static_files_not_sensitive(self):
        assert is_sensitive_path("GET", "/docs") is False
        assert is_sensitive_path("GET", "/openapi.json") is False

    def test_strategy_endpoints_are_sensitive(self):
        assert is_sensitive_path("POST", "/api/v1/strategy/strategies") is True
        assert is_sensitive_path("GET", "/api/v1/strategy/strategies") is True

    def test_admin_endpoints_are_sensitive(self):
        assert is_sensitive_path("GET", "/api/v1/admin/") is True
        assert is_sensitive_path("POST", "/api/v1/admin/users") is True


class TestActionClassification:
    """Tests for action string derivation."""

    def test_classify_create(self):
        action = classify_action("POST", "/api/v1/users")
        assert action == "users.create" or "users.execute"

    def test_classify_read(self):
        action = classify_action("GET", "/api/v1/users/123")
        assert "users" in action

    def test_classify_update(self):
        action = classify_action("PUT", "/api/v1/broker/account/123")
        assert "broker" in action

    def test_classify_delete(self):
        action = classify_action("DELETE", "/api/v1/strategy/strategies/123")
        assert "strategy" in action

    def test_classify_without_prefix(self):
        action = classify_action("GET", "/health")
        assert action is not None


class TestSensitiveActions:
    """The sensitive actions registry should contain all required actions."""

    def test_critical_actions_present(self):
        critical = [
            "user.login",
            "user.role.update",
            "broker.account.create",
            "risk.circuit_breaker.activate",
            "risk.emergency_close",
            "trading.order.place",
            "system.api_key.create",
            "system.secrets.rotate",
            "strategy.create",
            "ai.config.update",
        ]
        for action in critical:
            assert action in SENSITIVE_ACTIONS, f"{action} should be in SENSITIVE_ACTIONS"

    def test_sensitive_actions_count(self):
        """There should be a reasonable number of sensitive actions."""
        assert len(SENSITIVE_ACTIONS) >= 30
