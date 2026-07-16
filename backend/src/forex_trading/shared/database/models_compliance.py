"""Compliance & Auditing database models.

Tables:
  - consent_records: User consent for data processing
  - pii_inventory: PII field registry for data subject access
  - data_retention_purges: Audit trail of data purges
  - audit_log_chain: SHA-256 chain-linking metadata for immutable audit
  - data_classification_rules: Classification rules for data types
  - risk_disclosures: Generated risk disclaimer history
  - regulatory_reports: Generated regulatory report history
  - archive_manifest: Cold-storage archive references for purged data
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from forex_trading.shared.database.base import BaseModel


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ConsentType(str, enum.Enum):
    """Types of consent that can be recorded."""
    TERMS_OF_SERVICE = "terms_of_service"
    PRIVACY_POLICY = "privacy_policy"
    RISK_DISCLOSURE = "risk_disclosure"
    DATA_PROCESSING = "data_processing"
    MARKETING = "marketing"
    THIRD_PARTY_SHARING = "third_party_sharing"
    COOKIES = "cookies"
    TRADING_AUTHORIZATION = "trading_authorization"


class ConsentStatus(str, enum.Enum):
    """Status of a consent record."""
    GRANTED = "granted"
    WITHDRAWN = "withdrawn"
    EXPIRED = "expired"


class PIICategory(str, enum.Enum):
    """PII data sensitivity categories."""
    PUBLIC = "public"
    INTERNAL = "internal"
    SENSITIVE = "sensitive"
    RESTRICTED = "restricted"


class DataRetentionCategory(str, enum.Enum):
    """Categories of data subject to retention policies."""
    TRADES = "trades"
    DECISIONS = "decisions"
    AUDIT_LOGS = "audit_logs"
    NOTIFICATIONS = "notifications"
    SESSIONS = "sessions"
    PI_DATA = "pi_data"
    CONSENT = "consent"
    RISK_DISCLOSURES = "risk_disclosures"
    REGULATORY_REPORTS = "regulatory_reports"


class ClassificationLevel(str, enum.Enum):
    """Data classification levels."""
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


class PurgeStatus(str, enum.Enum):
    """Status of a data purge operation."""
    PENDING = "pending"
    ARCHIVED = "archived"
    DELETED = "deleted"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# Consent Records
# ---------------------------------------------------------------------------


class ConsentRecord(BaseModel):
    """Record of user consent for data processing activities.

    Required for GDPR Art. 6-7 compliance. Tracks when, how, and what
    the user consented to, including the IP and user agent at time of
    consent.
    """

    __tablename__ = "consent_records"
    __table_args__ = (
        Index("idx_consent_user_type", "user_id", "consent_type"),
        Index("idx_consent_status", "status", "created_at"),
    )

    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    consent_type: Mapped[ConsentType] = mapped_column(
        Enum(ConsentType),
        nullable=False,
    )
    status: Mapped[ConsentStatus] = mapped_column(
        Enum(ConsentStatus),
        default=ConsentStatus.GRANTED,
        nullable=False,
    )
    ip_address: Mapped[Optional[str]] = mapped_column(
        String(45),
        nullable=True,
    )
    user_agent: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
    )
    consent_version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="1.0",
    )
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    withdrawn_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    metadata_json: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
    )


# ---------------------------------------------------------------------------
# PII Inventory
# ---------------------------------------------------------------------------


class PIIInventory(BaseModel):
    """Registry of PII fields across the system for DSAR compliance.

    Used for data subject access requests (DSAR) and right to erasure
    (GDPR Art. 17).
    """

    __tablename__ = "pii_inventory"
    __table_args__ = (
        Index("idx_pii_category", "category"),
        Index("idx_pii_table_field", "table_name", "field_name", unique=True),
    )

    table_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    field_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    category: Mapped[PIICategory] = mapped_column(
        Enum(PIICategory),
        nullable=False,
    )
    description: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
    )
    is_required: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    retention_days: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    masking_rule: Mapped[Optional[str]] = mapped_column(
        String(200),
        nullable=True,
    )


# ---------------------------------------------------------------------------
# Data Retention Purge Audit Trail
# ---------------------------------------------------------------------------


class DataRetentionPurge(BaseModel):
    """Audit trail of data purges performed by the retention manager.

    Every purge operation (archive + delete) is recorded here for
    compliance auditing.
    """

    __tablename__ = "data_retention_purges"
    __table_args__ = (
        Index("idx_purge_category_status", "category", "status"),
        Index("idx_purge_timestamp", "purged_at"),
    )

    category: Mapped[DataRetentionCategory] = mapped_column(
        Enum(DataRetentionCategory),
        nullable=False,
    )
    status: Mapped[PurgeStatus] = mapped_column(
        Enum(PurgeStatus),
        nullable=False,
    )
    records_purged: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    older_than_days: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    archive_path: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
    )
    archive_size_bytes: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    archive_hash: Mapped[Optional[str]] = mapped_column(
        String(128),
        nullable=True,
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    purged_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    purged_by: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )
    was_dry_run: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )


# ---------------------------------------------------------------------------
# Audit Log Chain — SHA-256 linking
# ---------------------------------------------------------------------------


class AuditLogChain(BaseModel):
    """SHA-256 chain-linking metadata for immutable audit log.

    Stores the previous hash for each audit log entry to form a
    verifiable chain.  This is separate from the audit_logs table
    to avoid modifying the existing schema.
    """

    __tablename__ = "audit_log_chain"
    __table_args__ = (
        Index("idx_chain_audit_id", "audit_log_id", unique=True),
        Index("idx_chain_prev_hash", "previous_hash"),
    )

    audit_log_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("audit_logs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    previous_hash: Mapped[Optional[str]] = mapped_column(
        String(128),
        nullable=True,
    )
    current_hash: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        unique=True,
    )
    chain_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    witness_tx_id: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
    )
    witness_location: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
    )
    witness_timestamp: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


# ---------------------------------------------------------------------------
# Regulatory Reports
# ---------------------------------------------------------------------------


class RegulatoryReport(BaseModel):
    """Generated regulatory report history.

    Tracks what reports were generated, when, and for whom.
    """

    __tablename__ = "regulatory_reports"
    __table_args__ = (
        Index("idx_reg_report_type_period", "report_type", "period_start"),
        Index("idx_reg_report_user", "user_id"),
    )

    user_id: Mapped[Optional[UUID]] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    report_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    report_format: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
    )
    period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    period_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    file_path: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
    )
    file_size_bytes: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    content_hash: Mapped[Optional[str]] = mapped_column(
        String(128),
        nullable=True,
    )
    parameters: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


# ---------------------------------------------------------------------------
# Risk Disclosures
# ---------------------------------------------------------------------------


class RiskDisclosure(BaseModel):
    """Generated risk disclosure record.

    Stores the full text of risk disclaimers generated for users,
    including jurisdiction-specific content.
    """

    __tablename__ = "risk_disclosures"
    __table_args__ = (
        Index("idx_disclosure_user", "user_id"),
        Index("idx_disclosure_type", "disclosure_type"),
    )

    user_id: Mapped[Optional[UUID]] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    disclosure_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    jurisdiction: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    content_hash: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )
    version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    language: Mapped[str] = mapped_column(
        String(10),
        default="en",
        nullable=False,
    )
    acknowledged: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


# ---------------------------------------------------------------------------
# Archive Manifest
# ---------------------------------------------------------------------------


class ArchiveManifest(BaseModel):
    """Cold-storage archive references for purged data.

    Allows recovery of expired data that has been archived before
    permanent deletion.
    """

    __tablename__ = "archive_manifest"
    __table_args__ = (
        Index("idx_archive_category", "category"),
        Index("idx_archive_created", "archived_at"),
    )

    category: Mapped[DataRetentionCategory] = mapped_column(
        Enum(DataRetentionCategory),
        nullable=False,
    )
    storage_location: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )
    storage_format: Mapped[str] = mapped_column(
        String(50),
        default="json.gz",
        nullable=False,
    )
    record_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    data_start_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    data_end_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    archive_hash: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )
    file_size_bytes: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    retention_purge_id: Mapped[Optional[UUID]] = mapped_column(
        Uuid,
        ForeignKey("data_retention_purges.id", ondelete="SET NULL"),
        nullable=True,
    )
    archived_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    metadata_json: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
    )


# ---------------------------------------------------------------------------
# Data Classification Rules
# ---------------------------------------------------------------------------


class DataClassificationRule(BaseModel):
    """Rules for automatic data classification based on data type/table."""

    __tablename__ = "data_classification_rules"
    __table_args__ = (
        Index("idx_class_rule_table_field", "table_name", "field_name"),
    )

    table_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    field_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    classification_level: Mapped[ClassificationLevel] = mapped_column(
        Enum(ClassificationLevel),
        nullable=False,
    )
    rationale: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
    )
    handling_procedure: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
