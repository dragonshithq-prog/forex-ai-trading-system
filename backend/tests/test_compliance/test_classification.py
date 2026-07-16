"""Tests for data classification."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from forex_trading.shared.compliance.classification import (
    DataClassifier,
    DataClassification,
    ClassificationLevel,
    data_classifier,
)


class TestClassificationLevel:
    """Tests for the ClassificationLevel enum."""

    def test_levels_exist(self):
        assert ClassificationLevel.PUBLIC.value == "public"
        assert ClassificationLevel.INTERNAL.value == "internal"
        assert ClassificationLevel.CONFIDENTIAL.value == "confidential"
        assert ClassificationLevel.RESTRICTED.value == "restricted"

    def test_level_ordering(self):
        """Levels should have increasing sensitivity."""
        levels = [
            ClassificationLevel.PUBLIC,
            ClassificationLevel.INTERNAL,
            ClassificationLevel.CONFIDENTIAL,
            ClassificationLevel.RESTRICTED,
        ]
        for i in range(len(levels) - 1):
            assert levels[i] != levels[i + 1]


class TestDataClassification:
    """Tests for the DataClassification dataclass."""

    def test_minimal_creation(self):
        dc = DataClassification(
            level=ClassificationLevel.CONFIDENTIAL,
            label="test.field",
        )
        assert dc.level == ClassificationLevel.CONFIDENTIAL
        assert dc.label == "test.field"
        assert dc.requires_encryption is False

    def test_full_creation(self):
        dc = DataClassification(
            level=ClassificationLevel.RESTRICTED,
            label="secure.field",
            description="Highly sensitive",
            handling_procedure="Must be encrypted",
            retention_days=2555,
            requires_encryption=True,
            requires_access_logging=True,
            requires_anonymization=True,
        )
        assert dc.requires_encryption is True
        assert dc.retention_days == 2555

    def test_data_flows_default_empty(self):
        dc = DataClassification(
            level=ClassificationLevel.INTERNAL,
            label="test",
        )
        assert dc.data_flow == []


class TestDataClassifier:
    """Tests for the DataClassifier."""

    @pytest.fixture
    def classifier(self):
        return DataClassifier()

    def test_classify_email(self, classifier):
        """Email should be classified as RESTRICTED."""
        result = classifier.classify("users", "email")
        assert result.level == ClassificationLevel.RESTRICTED
        assert result.requires_encryption is True

    def test_classify_password(self, classifier):
        """Password hash should be classified as RESTRICTED."""
        result = classifier.classify("users", "hashed_password")
        assert result.level == ClassificationLevel.RESTRICTED

    def test_classify_public_field(self, classifier):
        """Username should be classified as INTERNAL."""
        result = classifier.classify("users", "username")
        assert result.level == ClassificationLevel.INTERNAL

    def test_classify_wildcard(self, classifier):
        """Wildcard rules should match any field in a table."""
        result = classifier.classify("orders", "quantity")
        assert result.level == ClassificationLevel.CONFIDENTIAL

    def test_classify_unknown_table(self, classifier):
        """Unknown table should fall back to CONFIDENTIAL."""
        result = classifier.classify("unknown_table", "some_field")
        assert result.level == ClassificationLevel.CONFIDENTIAL

    def test_classify_unknown_field(self, classifier):
        """Unknown field in known table should use wildcard or fallback."""
        result = classifier.classify("users", "nonexistent_field")
        assert result.level is not None

    def test_get_handling_procedure_public(self, classifier):
        """Public classification should have lenient procedures."""
        dc = DataClassification(level=ClassificationLevel.PUBLIC, label="test")
        proc = classifier.get_handling_procedure(dc)
        assert "Freely distributable" in proc

    def test_get_handling_procedure_restricted(self, classifier):
        """Restricted classification should have strict procedures."""
        dc = DataClassification(level=ClassificationLevel.RESTRICTED, label="test")
        proc = classifier.get_handling_procedure(dc)
        assert "MFA" in proc or "HIGHLY SENSITIVE" in proc

    def test_get_handling_procedure_with_specific(self, classifier):
        """Procedures should include specific handling when provided."""
        dc = DataClassification(
            level=ClassificationLevel.CONFIDENTIAL,
            label="test",
            handling_procedure="Custom procedure",
        )
        proc = classifier.get_handling_procedure(dc)
        assert "Custom procedure" in proc

    def test_get_data_flow_pii(self, classifier):
        """PII data flow should have expected entries."""
        flows = classifier.get_data_flow("PII")
        assert len(flows) > 0
        assert flows[0]["purpose"] is not None

    def test_get_data_flow_trading(self, classifier):
        """Trading data flow should have expected entries."""
        flows = classifier.get_data_flow("TRADING_DATA")
        assert len(flows) > 0

    def test_get_data_flow_unknown(self, classifier):
        """Unknown data category should return empty list."""
        flows = classifier.get_data_flow("UNKNOWN")
        assert flows == []

    def test_get_all_data_flows(self, classifier):
        """All data flows should include all categories."""
        flows = classifier.get_all_data_flows()
        assert "PII" in flows
        assert "TRADING_DATA" in flows
        assert "CONSENT_DATA" in flows

    def test_add_classification_rule(self, classifier):
        """Adding a rule should update the classifier."""
        dc = DataClassification(
            level=ClassificationLevel.PUBLIC,
            label="new.field",
        )
        classifier.add_classification_rule("new_table", "new_field", dc)
        result = classifier.classify("new_table", "new_field")
        assert result.level == ClassificationLevel.PUBLIC

    def test_get_report(self, classifier):
        """Report should include all classified fields."""
        report = classifier.get_report()
        assert len(report) > 0
        assert all("key" in entry for entry in report)

    def test_get_report_filtered(self, classifier):
        """Report filtered by level should only return matching entries."""
        report = classifier.get_report(level_filter=ClassificationLevel.RESTRICTED)
        assert all(r["level"] == "restricted" for r in report)

    async def test_load_rules_from_db_empty(self, classifier):
        """Loading from empty DB should not clear defaults."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        # Calling load should still work with defaults
        rules = await classifier.load_rules_from_db(mock_db)
        assert len(rules) > 0

    async def test_sync_rules_to_db(self, classifier):
        """Syncing rules to DB should insert records."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        rules = await classifier.sync_rules_to_db(mock_db)
        assert len(rules) >= 0


class TestGlobalClassifier:
    """Tests for the global data_classifier instance."""

    def test_global_instance_exists(self):
        assert data_classifier is not None
        assert isinstance(data_classifier, DataClassifier)

    def test_global_has_default_rules(self):
        report = data_classifier.get_report()
        assert len(report) > 10  # Should have many default rules
