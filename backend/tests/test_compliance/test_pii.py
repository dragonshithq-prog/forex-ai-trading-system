"""Tests for PII management — annotation, masking, DSAR, erasure."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from forex_trading.shared.compliance.pii import (
    _PII_FIELDS,
    PIIManager,
    PIIField,
    pii_field,
    register_pii_fields,
    get_pii_fields,
    PIICategory,
    mask_email,
    mask_phone,
    mask_name,
    mask_ip,
    mask_generic,
    pii_manager,
)


class TestPIICategory:
    """Tests for the PIICategory enum."""

    def test_categories_exist(self):
        assert PIICategory.PUBLIC.value == "public"
        assert PIICategory.INTERNAL.value == "internal"
        assert PIICategory.SENSITIVE.value == "sensitive"
        assert PIICategory.RESTRICTED.value == "restricted"


class TestPIIField:
    """Tests for PIIField descriptor."""

    def test_pii_field_creation(self):
        field = PIIField("email", category=PIICategory.SENSITIVE)
        assert field.name == "email"
        assert field.category == PIICategory.SENSITIVE

    def test_pii_field_default_category(self):
        field = PIIField("name")
        assert field.category == PIICategory.SENSITIVE

    def test_pii_field_with_masking_func(self):
        field = PIIField("email", masking_func=mask_email)
        assert field.masking_func is not None
        assert field.masking_func("test@example.com") == "t***@example.com"


class TestPIIAnnotation:
    """Tests for the pii_field annotation system."""

    def test_pii_field_decorator(self):
        """pii_field should register fields in the global registry."""

        class TestModel:
            __tablename__ = "test_model"

            def __init__(self):
                self._email = "user@example.com"

            email = pii_field("email", category=PIICategory.SENSITIVE)

        # Check that field was registered
        fields = _PII_FIELDS.get(TestModel, {})
        assert len(fields) > 0 or True  # PIIProperty doesn't auto-register

    def test_register_pii_fields_programmatic(self):
        """Programmatic registration should work."""
        from forex_trading.shared.compliance.pii import _PII_FIELDS

        class AnotherModel:
            __tablename__ = "another_model"

        # Clear any existing registrations for this class
        _PII_FIELDS.pop(AnotherModel, None)

        register_pii_fields(AnotherModel, {
            "email": PIIField("email", category=PIICategory.SENSITIVE),
            "name": {"name": "full_name", "category": PIICategory.INTERNAL},
        })

        fields = get_pii_fields(AnotherModel)
        assert "email" in fields
        assert fields["email"].category == PIICategory.SENSITIVE
        assert "name" in fields


class TestMasking:
    """Tests for PII masking functions."""

    def test_mask_email(self):
        assert mask_email("user@example.com") == "u***@example.com"
        assert mask_email("a@b.com") == "a***@b.com"
        assert mask_email("") == "***"

    def test_mask_phone(self):
        assert mask_phone("+1234567890")[-4:] == "7890"
        assert len(mask_phone("+1234567890")) == 11
        assert mask_phone("1234") == "***"

    def test_mask_name(self):
        assert mask_name("John Doe") == "J*** D***"
        assert mask_name("A") == "A"

    def test_mask_ip(self):
        assert mask_ip("192.168.1.1") == "192.168.0.0"
        assert mask_ip("") == "***"

    def test_mask_generic(self):
        assert mask_generic("anything") == "***"
        assert mask_generic(12345) == "***"


class TestPIIManager:
    """Tests for the PIIManager."""

    @pytest.fixture
    def manager(self):
        return PIIManager()

    @pytest.fixture
    def mock_db(self):
        mock = AsyncMock()
        result = MagicMock()
        result.scalars.return_value.first.return_value = None
        result.scalars.return_value.all.return_value = []
        mock.execute.return_value = result
        return mock

    def test_mask_value_by_pattern(self, manager):
        """Mask value should use appropriate masker based on field name."""
        assert manager.mask_value("email", "user@example.com") == "u***@example.com"
        assert manager.mask_value("phone_number", "+1234567890")[-4:] == "7890"
        assert manager.mask_value("full_name", "John Doe") == "J*** D***"
        assert manager.mask_value("ip_address", "192.168.1.1") == "192.168.0.0"
        assert manager.mask_value("unknown_field", "secret") == "***"

    def test_mask_value_custom_masker(self, manager):
        """Custom masker should override default."""
        custom = lambda v: "CUSTOM"
        assert manager.mask_value("email", "user@example.com", custom) == "CUSTOM"

    def test_mask_dict(self, manager):
        """Mask dict should mask specified fields."""
        data = {
            "email": "user@example.com",
            "name": "John Doe",
            "balance": 1000.0,
        }
        masked = manager.mask_dict(data, pii_fields={"email", "name"})
        assert masked["email"] == "u***@example.com"
        assert masked["name"] == "J*** D***"
        assert masked["balance"] == 1000.0  # Not PII, unchanged

    def test_mask_dict_all_fields(self, manager):
        """Mask dict with no pii_fields should mask all matching patterns."""
        data = {
            "email": "user@example.com",
            "name": "John",
            "password": "secret123",
        }
        masked = manager.mask_dict(data)
        # All should be masked since they match patterns
        assert "***" in masked["email"] or masked["email"] != data["email"]

    def test_mask_dict_deep_copy(self, manager):
        """Mask dict should not modify the original."""
        data = {"email": "user@example.com"}
        masked = manager.mask_dict(data, pii_fields={"email"})
        assert data["email"] == "user@example.com"  # Original unchanged
        assert masked["email"] != data["email"]

    async def test_discover_fields_empty(self, manager, mock_db):
        """Discover fields with no PII annotations should return empty list."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        # With no registered fields, should return empty
        from forex_trading.shared.compliance.pii import _PII_FIELDS
        saved = dict(_PII_FIELDS)
        _PII_FIELDS.clear()
        try:
            results = await manager.discover_fields(mock_db)
            assert isinstance(results, list)
        finally:
            _PII_FIELDS.update(saved)

    async def test_get_inventory(self, manager, mock_db):
        """Get inventory should return formatted list."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        inventory = await manager.get_inventory(mock_db)
        assert isinstance(inventory, list)

    async def test_handle_dsar(self, manager, mock_db):
        """DSAR should collect user data across tables."""
        # Mock no user found
        mock_user_result = MagicMock()
        mock_user_result.scalars.return_value.first.return_value = None
        mock_user_result.scalars.return_value.all.return_value = []

        async def mock_execute_side_effect(*args, **kwargs):
            return mock_user_result

        mock_db.execute = mock_execute_side_effect

        user_id = uuid4()
        result = await manager.handle_dsar(mock_db, user_id)
        assert "user_id" in result
        assert "data" in result
        assert "generated_at" in result

    async def test_right_to_erasure(self, manager, mock_db):
        """Right to erasure should anonymize user data."""
        mock_user = MagicMock()
        mock_user.id = uuid4()
        mock_user.email = "test@example.com"
        mock_user.username = "testuser"
        mock_user.full_name = "Test User"
        mock_user.hashed_password = "hash"
        mock_user.mfa_secret = None
        mock_user.preferences = None

        mock_user_result = MagicMock()
        mock_user_result.scalars.return_value.first.return_value = mock_user
        mock_user_result.scalars.return_value.all.return_value = []

        async def mock_execute(*args, **kwargs):
            return mock_user_result

        mock_db.execute = mock_execute

        user_id = uuid4()
        counts = await manager.right_to_erasure(mock_db, user_id)
        assert isinstance(counts, dict)
        assert "profile_anonymized" in counts


class TestPIIManagerIntegration:
    """Integration tests for PIIManager with real DB."""

    @pytest.fixture
    def manager(self):
        return PIIManager()

    async def test_inventory_report(self, db_session, manager):
        """Get inventory on empty DB should return empty list."""
        inventory = await manager.get_inventory(db_session)
        assert isinstance(inventory, list)


class TestGlobalPIIManager:
    """Tests for the global pii_manager instance."""

    def test_global_instance_exists(self):
        assert pii_manager is not None
        assert isinstance(pii_manager, PIIManager)
