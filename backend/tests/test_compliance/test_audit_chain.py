"""Tests for immutable audit log enhancements — SHA-256 chain linking,
tamper detection, and external witness.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from forex_trading.shared.security.audit import (
    AuditChainManager,
    ChainVerificationResult,
    WitnessBackend,
    S3WitnessBackend,
    AuditService,
    audit_service,
    audit_chain_manager,
)
from forex_trading.shared.database.models_compliance import AuditLogChain


class TestAuditChainManager:
    """Tests for the SHA-256 chain linking manager."""

    @pytest.fixture
    def chain_manager(self):
        return AuditChainManager()

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    def test_compute_entry_hash(self, chain_manager):
        """Entry hash should be deterministic."""
        content = {"id": "test-id", "action": "test.action"}
        hash1 = chain_manager._compute_entry_hash(content)
        hash2 = chain_manager._compute_entry_hash(content)
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 hex digest length

    def test_compute_entry_hash_with_previous(self, chain_manager):
        """Hash with previous should differ from without."""
        content = {"id": "test-id", "action": "test.action"}
        hash_with_prev = chain_manager._compute_entry_hash(
            content, previous_hash="abc123",
        )
        hash_without = chain_manager._compute_entry_hash(content)
        assert hash_with_prev != hash_without

    def test_hash_includes_all_fields(self, chain_manager):
        """Hash should change if any field changes."""
        content1 = {"id": "test-id", "action": "test.action", "details": {"key": "value"}}
        content2 = {"id": "test-id", "action": "test.action", "details": {"key": "changed"}}
        assert chain_manager._compute_entry_hash(content1) != chain_manager._compute_entry_hash(content2)

    def test_hash_deterministic_with_sort_keys(self, chain_manager):
        """Hash should be deterministic regardless of key order."""
        content1 = {"b": 2, "a": 1}
        content2 = {"a": 1, "b": 2}
        assert chain_manager._compute_entry_hash(content1) == chain_manager._compute_entry_hash(content2)

    def test_build_entry_content(self, chain_manager):
        """Building entry content should extract all relevant fields."""
        mock_entry = MagicMock()
        mock_entry.id = uuid4()
        mock_entry.user_id = uuid4()
        mock_entry.action = "test.action"
        mock_entry.resource_type = "test"
        mock_entry.resource_id = "123"
        mock_entry.details = {"key": "value"}
        mock_entry.ip_address = "192.168.1.1"
        mock_entry.timestamp = datetime.now(timezone.utc)

        content = chain_manager._build_entry_content(mock_entry)
        assert content["action"] == "test.action"
        assert content["resource_type"] == "test"
        assert content["details"]["key"] == "value"

    async def test_link_entry_first(self, chain_manager, mock_db):
        """First chain entry should have no previous hash."""
        mock_prev_result = MagicMock()
        mock_prev_result.scalars.return_value.first.return_value = None
        mock_prev_result.scalars.return_value.all.return_value = []

        async def execute_side_effect(*args, **kwargs):
            return mock_prev_result

        mock_db.execute = execute_side_effect

        audit_log_id = uuid4()
        content = {"id": str(audit_log_id), "action": "test"}

        chain_entry = await chain_manager.link_entry(mock_db, audit_log_id, content)
        assert chain_entry.chain_index == 0
        assert chain_entry.previous_hash is None
        assert chain_entry.current_hash is not None

    async def test_link_entry_subsequent(self, chain_manager, mock_db):
        """Subsequent chain entries should reference previous hash."""
        previous_entry = MagicMock(spec=AuditLogChain)
        previous_entry.chain_index = 0
        previous_entry.current_hash = "previous_hash_value"

        mock_prev_result = MagicMock()
        mock_prev_result.scalars.return_value.first.return_value = previous_entry
        mock_prev_result.scalars.return_value.all.return_value = []

        async def execute_side_effect(*args, **kwargs):
            return mock_prev_result

        mock_db.execute = execute_side_effect

        audit_log_id = uuid4()
        content = {"id": str(audit_log_id), "action": "test"}

        chain_entry = await chain_manager.link_entry(mock_db, audit_log_id, content)
        assert chain_entry.chain_index == 1
        assert chain_entry.previous_hash == "previous_hash_value"

    async def test_verify_chain_intact(self, chain_manager, mock_db):
        """Verifying an intact chain should have no issues."""
        # Create simulated chain entries
        entry1_id = uuid4()
        entry2_id = uuid4()
        fixed_ts = datetime.now(timezone.utc)

        content1 = {"id": str(entry1_id), "action": "first", "details": {}, "user_id": None,
                     "resource_type": "test", "resource_id": None, "ip_address": None,
                     "timestamp": fixed_ts.isoformat()}
        content2 = {"id": str(entry2_id), "action": "second", "details": {}, "user_id": None,
                     "resource_type": "test", "resource_id": None, "ip_address": None,
                     "timestamp": fixed_ts.isoformat()}

        hash1 = chain_manager._compute_entry_hash(content1)
        hash2 = chain_manager._compute_entry_hash(content2, previous_hash=hash1)

        # Mock chain entries
        mock_chain1 = MagicMock(spec=AuditLogChain)
        mock_chain1.chain_index = 0
        mock_chain1.audit_log_id = entry1_id
        mock_chain1.previous_hash = None
        mock_chain1.current_hash = hash1

        mock_chain2 = MagicMock(spec=AuditLogChain)
        mock_chain2.chain_index = 1
        mock_chain2.audit_log_id = entry2_id
        mock_chain2.previous_hash = hash1
        mock_chain2.current_hash = hash2

        # Mock audit log entries
        mock_audit1 = MagicMock()
        mock_audit1.id = entry1_id
        mock_audit1.user_id = None
        mock_audit1.action = "first"
        mock_audit1.resource_type = "test"
        mock_audit1.resource_id = None
        mock_audit1.details = {}
        mock_audit1.ip_address = None
        mock_audit1.timestamp = fixed_ts

        mock_audit2 = MagicMock()
        mock_audit2.id = entry2_id
        mock_audit2.user_id = None
        mock_audit2.action = "second"
        mock_audit2.resource_type = "test"
        mock_audit2.resource_id = None
        mock_audit2.details = {}
        mock_audit2.ip_address = None
        mock_audit2.timestamp = fixed_ts

        chain_result = MagicMock()
        chain_result.scalars.return_value.all.return_value = [mock_chain1, mock_chain2]

        who_called = {"call_count": 0}

        async def execute_side_effect(query):
            who_called["call_count"] += 1
            q_str = str(query).lower()
            if "audit_log_chain" in q_str:
                return chain_result
            else:
                # Return audit log
                audit_result = MagicMock()
                if who_called["call_count"] <= 2:
                    audit_result.scalars.return_value.first.return_value = mock_audit1
                else:
                    audit_result.scalars.return_value.first.return_value = mock_audit2
                return audit_result

        mock_db.execute = execute_side_effect

        result = await chain_manager.verify_chain(mock_db)
        assert result.is_intact is True
        assert len(result.issues) == 0

    async def test_verify_chain_broken(self, chain_manager, mock_db):
        """Verifying a tampered chain should report issues."""
        entry_id = uuid4()

        content = {"id": str(entry_id), "action": "original", "details": {}, "user_id": None,
                    "resource_type": "test", "resource_id": None, "ip_address": None,
                    "timestamp": datetime.now(timezone.utc).isoformat()}

        correct_hash = chain_manager._compute_entry_hash(content)
        wrong_hash = hashlib.sha256(b"tampered").hexdigest()

        mock_chain = MagicMock(spec=AuditLogChain)
        mock_chain.chain_index = 0
        mock_chain.audit_log_id = entry_id
        mock_chain.previous_hash = None
        mock_chain.current_hash = wrong_hash  # Wrong hash

        chain_result = MagicMock()
        chain_result.scalars.return_value.all.return_value = [mock_chain]

        mock_audit = MagicMock()
        mock_audit.id = entry_id
        mock_audit.user_id = None
        mock_audit.action = "original"
        mock_audit.resource_type = "test"
        mock_audit.resource_id = None
        mock_audit.details = {}
        mock_audit.ip_address = None
        mock_audit.timestamp = datetime.now(timezone.utc)

        async def execute_side_effect(query):
            q_str = str(query).lower()
            if "audit_log_chain" in q_str:
                return chain_result
            audit_result = MagicMock()
            audit_result.scalars.return_value.first.return_value = mock_audit
            return audit_result

        mock_db.execute = execute_side_effect

        result = await chain_manager.verify_chain(mock_db)
        assert result.is_intact is False
        assert len(result.issues) > 0
        assert "hash MISMATCH" in result.issues[0]

    async def test_verify_entry_valid(self, chain_manager, mock_db):
        """Verify a single valid entry should return True."""
        entry_id = uuid4()
        fixed_ts = datetime.now(timezone.utc)
        content = {"id": str(entry_id), "action": "test", "details": {}, "user_id": None,
                    "resource_type": "t", "resource_id": None, "ip_address": None,
                    "timestamp": fixed_ts.isoformat()}
        correct_hash = chain_manager._compute_entry_hash(content)

        mock_chain = MagicMock(spec=AuditLogChain)
        mock_chain.previous_hash = None
        mock_chain.current_hash = correct_hash

        mock_audit = MagicMock()
        mock_audit.id = entry_id
        mock_audit.user_id = None
        mock_audit.action = "test"
        mock_audit.resource_type = "t"
        mock_audit.resource_id = None
        mock_audit.details = {}
        mock_audit.ip_address = None
        mock_audit.timestamp = fixed_ts

        chain_result = MagicMock()
        chain_result.scalars.return_value.first.return_value = mock_chain

        audit_result = MagicMock()
        audit_result.scalars.return_value.first.return_value = mock_audit

        async def execute_side_effect(query):
            q_str = str(query).lower()
            if "audit_log_chain" in q_str:
                return chain_result
            return audit_result

        mock_db.execute = execute_side_effect

        result = await chain_manager.verify_entry(mock_db, entry_id)
        assert result is True

    async def test_verify_entry_missing_chain(self, chain_manager, mock_db):
        """Verify entry with no chain record should return False."""
        chain_result = MagicMock()
        chain_result.scalars.return_value.first.return_value = None
        mock_db.execute.return_value = chain_result

        result = await chain_manager.verify_entry(mock_db, uuid4())
        assert result is False


class TestS3WitnessBackend:
    """Tests for the S3 witness backend."""

    def test_init(self):
        backend = S3WitnessBackend(bucket="test-bucket", prefix="audit/")
        assert backend.bucket == "test-bucket"
        assert backend.prefix == "audit/"

    async def test_witness_local_fallback(self):
        """Without aioboto3, should use local file fallback."""
        backend = S3WitnessBackend(bucket="test-bucket")
        witness_id = await backend.witness("test_hash_value", 42)
        assert witness_id is not None
        assert "test-bucket" in witness_id


class TestAuditServiceEnhanced:
    """Tests for the enhanced AuditService with chain linking."""

    @pytest.fixture
    def service(self):
        return AuditService()

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    async def test_record_with_chain_linking(self, service, mock_db):
        """Record should create chain link automatically."""
        mock_entry = MagicMock()
        mock_entry.id = uuid4()
        mock_entry.user_id = uuid4()
        mock_entry.action = "test.action"
        mock_entry.resource_type = "test"
        mock_entry.resource_id = None
        mock_entry.details = {}
        mock_entry.ip_address = None
        mock_entry.timestamp = datetime.now(timezone.utc)

        # First call to execute returns no previous chain
        chain_result = MagicMock()
        chain_result.scalars.return_value.first.return_value = None
        chain_result.scalars.return_value.all.return_value = []

        async def execute_side_effect(*args, **kwargs):
            return chain_result

        mock_db.execute = execute_side_effect
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        entry = await service.record(
            mock_db,
            user_id=uuid4(),
            action="test.action",
            resource_type="test",
        )
        assert entry is not None

    async def test_get_entries_with_chain_info(self, service, mock_db):
        """Get entries with include_chain_info should add chain metadata."""
        mock_entry = MagicMock()
        mock_entry.id = uuid4()
        mock_entry.user_id = None
        mock_entry.action = "test.action"
        mock_entry.resource_type = "test"
        mock_entry.resource_id = None
        mock_entry.details = {}
        mock_entry.ip_address = None
        mock_entry.timestamp = datetime.now(timezone.utc)

        entries_result = MagicMock()
        entries_result.scalars.return_value.all.return_value = [mock_entry]

        chain_result = MagicMock()
        chain_result.scalars.return_value.first.return_value = None

        async def execute_side_effect(query):
            q_str = str(query).lower()
            if "chain" in q_str or "audit_log_chain" in q_str:
                return chain_result
            return entries_result

        mock_db.execute = execute_side_effect

        entries = await service.get_entries(mock_db, include_chain_info=True)
        assert len(entries) == 1

    async def test_get_chain_status(self, service, mock_db):
        """Chain status should return current chain metrics."""
        mock_latest = MagicMock()
        mock_latest.chain_index = 42
        mock_latest.current_hash = "abc123"
        mock_latest.witness_timestamp = datetime.now(timezone.utc)
        mock_latest.witness_location = "s3://bucket/key"

        chain_result = MagicMock()
        chain_result.scalars.return_value.first.return_value = mock_latest

        count_result = MagicMock()
        count_result.scalar_one.return_value = 100

        async def execute_side_effect(query):
            q_str = str(query).lower()
            if "order by" in q_str or "desc" in q_str:
                return chain_result
            return count_result

        mock_db.execute = execute_side_effect

        status = await service.get_chain_status(mock_db)
        assert status["latest_chain_index"] == 42
        assert status["latest_hash"] == "abc123"
        assert status["total_audit_logs"] == 100

    async def test_get_entries_for_regulator(self, service, mock_db):
        """Regulator query should include chain status."""
        entries_result = MagicMock()
        entries_result.scalars.return_value.all.return_value = []

        count_result = MagicMock()
        count_result.scalar_one.return_value = 0

        async def execute_side_effect(query):
            q_str = str(query).lower()
            if "count" in q_str:
                return count_result
            # For chain status
            latest_result = MagicMock()
            latest_result.scalars.return_value.first.return_value = None
            return latest_result

        mock_db.execute = execute_side_effect

        result = await service.get_entries_for_regulator(mock_db, limit=10)
        assert "chain_status" in result
        assert "entries" in result
        assert "request" in result


class TestGlobalAuditService:
    """Tests for the global audit_service instance."""

    def test_global_instance_exists(self):
        assert audit_service is not None
        assert isinstance(audit_service, AuditService)

    def test_chain_manager_attached(self):
        assert audit_chain_manager is not None
        assert isinstance(audit_chain_manager, AuditChainManager)
