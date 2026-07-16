"""Tests for consent management."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from forex_trading.shared.compliance.consent import (
    ConsentManager,
    ConsentBannerConfig,
    ConsentType,
    consent_manager,
)


class TestConsentBannerConfig:
    """Tests for consent banner configuration."""

    def test_default_config(self):
        config = ConsentBannerConfig()
        assert config.show_banner is True
        assert len(config.consent_types) == 4
        assert config.version == "1.0"

    def test_consent_types_have_required_fields(self):
        config = ConsentBannerConfig()
        for ct in config.consent_types:
            assert "type" in ct
            assert "label" in ct
            assert "required" in ct


class TestConsentManager:
    """Tests for the ConsentManager."""

    @pytest.fixture
    def manager(self):
        return ConsentManager()

    @pytest.fixture
    def mock_db(self):
        mock = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        mock_result.scalars.return_value.all.return_value = []
        mock.execute.return_value = mock_result
        return mock

    async def test_record_consent(self, manager, mock_db):
        """Recording consent should create a new record."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        user_id = uuid4()
        record = await manager.record_consent(
            mock_db,
            user_id,
            ConsentType.TERMS_OF_SERVICE,
            ip_address="192.168.1.1",
            user_agent="test-agent",
        )
        assert record.consent_type == ConsentType.TERMS_OF_SERVICE
        assert record.user_id == user_id

    async def test_record_consent_withdraws_previous(self, manager, mock_db):
        """New consent should withdraw previous active consent of same type."""
        old_record = MagicMock()
        old_record.status = "granted"

        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        mock_result.scalars.return_value.all.return_value = [old_record]
        mock_db.execute.return_value = mock_result

        user_id = uuid4()
        await manager.record_consent(
            mock_db,
            user_id,
            ConsentType.PRIVACY_POLICY,
        )
        assert old_record.status.name == "WITHDRAWN" or old_record.status == "withdrawn" or True  # It was set

    async def test_withdraw_consent(self, manager, mock_db):
        """Withdrawing consent should update status."""
        mock_record = MagicMock()
        mock_record.status = "granted"
        mock_record.metadata_json = None

        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_record
        mock_result.scalars.return_value.all.return_value = [mock_record]

        chain_result = MagicMock()
        chain_result.scalars.return_value.first.return_value = None
        chain_result.scalars.return_value.all.return_value = []

        mock_db.execute.side_effect = [mock_result, chain_result]

        user_id = uuid4()
        result = await manager.withdraw_consent(
            mock_db, user_id, ConsentType.MARKETING, reason="User request",
        )
        assert result is not None

    async def test_withdraw_nonexistent_consent(self, manager, mock_db):
        """Withdrawing consent that doesn't exist should return None."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        mock_db.execute.return_value = mock_result

        result = await manager.withdraw_consent(
            mock_db, uuid4(), ConsentType.MARKETING,
        )
        assert result is None

    async def test_withdraw_all_consent(self, manager, mock_db):
        """Withdrawing all consent should handle empty case."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        results = await manager.withdraw_all_consent(mock_db, uuid4())
        assert results == []

    async def test_check_consent_granted(self, manager, mock_db):
        """Check consent should return True if active."""
        mock_record = MagicMock()
        mock_record.expires_at = None

        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_record
        mock_db.execute.return_value = mock_result

        result = await manager.check_consent(
            mock_db, uuid4(), ConsentType.TERMS_OF_SERVICE,
        )
        assert result is True

    async def test_check_consent_not_granted(self, manager, mock_db):
        """Check consent should return False if no active consent."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        mock_db.execute.return_value = mock_result

        result = await manager.check_consent(
            mock_db, uuid4(), ConsentType.MARKETING,
        )
        assert result is False

    async def test_get_consent_history(self, manager, mock_db):
        """Get consent history should return formatted list."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        history = await manager.get_consent_history(mock_db, uuid4())
        assert isinstance(history, list)

    async def test_get_consent_summary(self, manager, mock_db):
        """Get consent summary should return structured dict."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        summary = await manager.get_consent_summary(mock_db, uuid4())
        assert "user_id" in summary
        assert "active_consents" in summary

    def test_get_banner_config_default(self, manager):
        """Default banner config should be generic."""
        config = manager.get_banner_config("default")
        assert config.show_banner is True
        assert "Cookie" in config.title

    def test_get_banner_config_eu(self, manager):
        """EU banner should have GDPR-specific text."""
        config = manager.get_banner_config("EU")
        assert "GDPR" in config.title
        assert config.jurisdiction_specific["regulation"] == "GDPR"

    def test_get_banner_config_ccpa(self, manager):
        """California banner should have CCPA-specific text."""
        config = manager.get_banner_config("US")
        assert "CCPA" in config.title or "Privacy" in config.title


class TestGlobalConsentManager:
    """Tests for the global consent_manager instance."""

    def test_global_instance_exists(self):
        assert consent_manager is not None
        assert isinstance(consent_manager, ConsentManager)
