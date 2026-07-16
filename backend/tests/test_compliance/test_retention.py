"""Tests for data retention policies and purge management."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from forex_trading.shared.compliance.retention import (
    RetentionManager,
    RetentionPolicy,
    DataRetentionCategory,
    DEFAULT_RETENTION_DAYS,
    retention_manager,
)


class TestRetentionPolicy:
    """Tests for the RetentionPolicy dataclass."""

    def test_default_retention_days(self):
        policy = RetentionPolicy()
        assert policy.get_retention_days(DataRetentionCategory.TRADES) == 2555
        assert policy.get_retention_days(DataRetentionCategory.SESSIONS) == 90
        assert policy.get_retention_days(DataRetentionCategory.PI_DATA) == 730

    def test_custom_retention_days(self):
        policy = RetentionPolicy(retention_days={
            DataRetentionCategory.SESSIONS: 30,
        })
        assert policy.get_retention_days(DataRetentionCategory.SESSIONS) == 30
        # Other categories should still use defaults
        assert policy.get_retention_days(DataRetentionCategory.TRADES) == 2555

    def test_cutoff_date(self):
        policy = RetentionPolicy()
        cutoff = policy.get_cutoff_date(DataRetentionCategory.SESSIONS)
        expected = datetime.now(timezone.utc) - timedelta(days=90)
        assert cutoff < expected + timedelta(seconds=1)
        assert cutoff > expected - timedelta(seconds=1)

    def test_default_dry_run(self):
        policy = RetentionPolicy()
        assert policy.dry_run is False

    def test_archive_defaults(self):
        policy = RetentionPolicy()
        assert policy.archive_enabled is True
        assert "archives" in policy.archive_directory


class TestRetentionManager:
    """Tests for the RetentionManager."""

    @pytest.fixture
    def manager(self):
        return RetentionManager()

    @pytest.fixture
    def mock_db(self):
        mock = AsyncMock()
        result = MagicMock()
        result.scalars.return_value.first.return_value = None
        result.scalars.return_value.all.return_value = []
        mock.execute.return_value = result
        return mock

    async def test_purge_category_dry_run(self, manager, mock_db):
        """Dry-run purge should not delete data."""
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 5
        mock_db.execute.return_value = mock_result

        result = await manager.purge_category(
            mock_db, DataRetentionCategory.SESSIONS, dry_run=True,
        )

        assert result.was_dry_run is True
        assert result.records_purged == 5
        assert result.status.value == "pending"

    async def test_purge_category(self, manager, mock_db):
        """Actual purge should delete expired records."""
        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 3
        mock_db.execute.return_value = mock_count

        with patch.object(manager.policy, 'archive_enabled', False):
            result = await manager.purge_category(
                mock_db, DataRetentionCategory.SESSIONS, dry_run=False,
            )

        assert result.was_dry_run is False
        assert result.records_purged == 3

    async def test_purge_all_categories(self, manager, mock_db):
        """Purge all should iterate all categories."""
        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 0

        async def mock_execute(*args, **kwargs):
            return mock_count

        mock_db.execute = mock_execute

        with patch.object(manager.policy, 'archive_enabled', False):
            results = await manager.purge_all(mock_db, dry_run=True)

        assert len(results) == len(list(DataRetentionCategory))

    async def test_review_expired(self, manager, mock_db):
        """Review should return counts per category."""
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 10
        mock_db.execute.return_value = mock_result

        counts = await manager.review_expired(mock_db)
        assert isinstance(counts, dict)
        assert len(counts) == len(list(DataRetentionCategory))

    async def test_purge_category_error_handling(self, manager, mock_db):
        """Purge failure should update status to FAILED."""
        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 5
        chain_result = MagicMock()
        chain_result.scalars.return_value.first.return_value = None
        chain_result.scalars.return_value.all.return_value = []

        mock_db.execute.side_effect = [
            mock_count,  # count
            Exception("DB error"),  # delete
            chain_result,  # audit chain
        ]

        with patch.object(manager.policy, 'archive_enabled', False):
            result = await manager.purge_category(
                mock_db, DataRetentionCategory.SESSIONS, dry_run=False,
            )

        assert result.status.value == "failed"
        assert result.error_message == "DB error"

    async def test_purge_audits_operation(self, manager, mock_db):
        """Purge should create audit log entry."""
        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 0
        mock_db.execute.return_value = mock_count

        with patch.object(manager.policy, 'archive_enabled', False):
            result = await manager.purge_category(
                mock_db, DataRetentionCategory.AUDIT_LOGS, dry_run=True,
                purged_by="test-user",
            )

        assert result.purged_by == "test-user"

    async def test_count_expired_various_categories(self, manager, mock_db):
        """Count expired should handle all categories."""
        for category in DataRetentionCategory:
            mock_result = MagicMock()
            mock_result.scalar_one.return_value = 0
            mock_db.execute.return_value = mock_result

            count = await manager._count_expired(
                mock_db, category, datetime.now(timezone.utc),
            )
            assert count == 0


class TestRetentionManagerIntegration:
    """Integration tests for RetentionManager with real DB.

    These use the async test fixtures from conftest.py.
    """

    @pytest.fixture
    def manager(self):
        return RetentionManager()

    async def test_purge_no_data(self, db_session, manager):
        """Purge with no expired data should succeed."""
        result = await manager.purge_category(
            db_session, DataRetentionCategory.SESSIONS, dry_run=True,
        )
        assert result.records_purged == 0
        assert result.was_dry_run is True

    async def test_review_with_db(self, db_session, manager):
        """Review with empty DB should return zero counts."""
        counts = await manager.review_expired(
            db_session, DataRetentionCategory.SESSIONS,
        )
        assert counts["sessions"] == 0


class TestGlobalRetentionManager:
    """Tests for the global retention_manager instance."""

    def test_global_instance_exists(self):
        assert retention_manager is not None
        assert isinstance(retention_manager, RetentionManager)
