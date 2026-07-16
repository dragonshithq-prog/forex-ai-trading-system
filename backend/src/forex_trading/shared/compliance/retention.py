"""Data Retention Policies — Configurable retention, automatic purging,
archival before deletion, dry-run mode, and purge audit trail.

Supports configurable retention periods per data category:
  - trades, decisions, audit_logs, notifications, sessions, pi_data,
    consent, risk_disclosures, regulatory_reports
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from forex_trading.shared.compliance.classification import DataClassification
from forex_trading.shared.database.models_compliance import (
    ArchiveManifest,
    DataRetentionCategory,
    DataRetentionPurge,
    PurgeStatus,
)
from forex_trading.shared.security.audit import audit_service

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default retention period map (in days)
# ---------------------------------------------------------------------------

DEFAULT_RETENTION_DAYS: dict[DataRetentionCategory, int] = {
    DataRetentionCategory.TRADES: 2555,           # 7 years (MiFID II)
    DataRetentionCategory.DECISIONS: 1825,         # 5 years
    DataRetentionCategory.AUDIT_LOGS: 2555,        # 7 years
    DataRetentionCategory.NOTIFICATIONS: 365,      # 1 year
    DataRetentionCategory.SESSIONS: 90,            # 90 days
    DataRetentionCategory.PI_DATA: 730,            # 2 years (GDPR max)
    DataRetentionCategory.CONSENT: 2555,           # 7 years
    DataRetentionCategory.RISK_DISCLOSURES: 2555,  # 7 years
    DataRetentionCategory.REGULATORY_REPORTS: 2555, # 7 years
}

# SQL queries for purging each category
PURGE_QUERIES: dict[DataRetentionCategory, str] = {
    DataRetentionCategory.TRADES: """
        DELETE FROM {table}
        WHERE created_at < :cutoff_date
    """,
    DataRetentionCategory.DECISIONS: """
        DELETE FROM ai_decisions
        WHERE created_at < :cutoff_date
    """,
    DataRetentionCategory.AUDIT_LOGS: """
        DELETE FROM audit_logs
        WHERE timestamp < :cutoff_date
    """,
    DataRetentionCategory.NOTIFICATIONS: """
        DELETE FROM notifications
        WHERE created_at < :cutoff_date
    """,
    DataRetentionCategory.SESSIONS: """
        DELETE FROM user_sessions
        WHERE created_at < :cutoff_date
    """,
    DataRetentionCategory.PI_DATA: """
        DELETE FROM pii_inventory
        WHERE created_at < :cutoff_date
    """,
    DataRetentionCategory.CONSENT: """
        DELETE FROM consent_records
        WHERE created_at < :cutoff_date
    """,
    DataRetentionCategory.RISK_DISCLOSURES: """
        DELETE FROM risk_disclosures
        WHERE generated_at < :cutoff_date
    """,
    DataRetentionCategory.REGULATORY_REPORTS: """
        DELETE FROM regulatory_reports
        WHERE generated_at < :cutoff_date
    """,
}

# Categories that map to dynamic table names
TABLE_SPECIFIC: dict[DataRetentionCategory, str] = {
    DataRetentionCategory.TRADES: "orders",
    DataRetentionCategory.PI_DATA: "pii_inventory",
}


@dataclass
class RetentionPolicy:
    """Configuration for data retention per category.

    Override any category's retention period from the defaults.
    """

    retention_days: dict[DataRetentionCategory, int] = field(
        default_factory=lambda: dict(DEFAULT_RETENTION_DAYS)
    )
    archive_enabled: bool = True
    archive_directory: str = "~/.forex_trading/archives"
    dry_run: bool = False

    def get_retention_days(self, category: DataRetentionCategory) -> int:
        """Return the configured retention period for a category."""
        return self.retention_days.get(category, DEFAULT_RETENTION_DAYS[category])

    def get_cutoff_date(self, category: DataRetentionCategory) -> datetime:
        """Return the cutoff datetime for purging this category."""
        days = self.get_retention_days(category)
        return datetime.now(timezone.utc) - timedelta(days=days)


class RetentionManager:
    """Manage data retention — purge expired data with optional archival.

    Every purge is audited and recorded in the ``data_retention_purges`` table.
    Supports dry-run mode for review before actual deletion.
    """

    def __init__(
        self,
        policy: RetentionPolicy | None = None,
    ) -> None:
        self.policy = policy or RetentionPolicy()

    async def purge_category(
        self,
        db: AsyncSession,
        category: DataRetentionCategory,
        *,
        dry_run: bool | None = None,
        purged_by: str | None = None,
    ) -> DataRetentionPurge:
        """Purge expired data for a single category.

        If ``archive_enabled`` in policy, data is first exported to cold
        storage.  In dry-run mode, nothing is deleted — only a preview
        count is returned.

        Returns the :class:`DataRetentionPurge` record.
        """
        is_dry_run = dry_run if dry_run is not None else self.policy.dry_run
        cutoff = self.policy.get_cutoff_date(category)

        # Archive before purge if enabled
        archive_path: str | None = None
        archive_hash: str | None = None
        archive_size: int | None = None

        if self.policy.archive_enabled and not is_dry_run:
            archive_path, archive_hash, archive_size = await self._archive_data(
                db, category, cutoff,
            )

        # Count records to purge
        count = await self._count_expired(db, category, cutoff)
        purge_record = DataRetentionPurge(
            category=category,
            status=PurgeStatus.PENDING,
            records_purged=count,
            older_than_days=self.policy.get_retention_days(category),
            archive_path=archive_path,
            archive_hash=archive_hash,
            archive_size_bytes=archive_size,
            was_dry_run=is_dry_run,
            purged_by=purged_by,
        )
        db.add(purge_record)

        if not is_dry_run and count > 0:
            try:
                await self._execute_purge(db, category, cutoff)
                purge_record.status = PurgeStatus.DELETED
            except Exception as exc:
                purge_record.status = PurgeStatus.FAILED
                purge_record.error_message = str(exc)
                logger.exception("Purge failed for category %s", category)
        elif is_dry_run:
            purge_record.status = PurgeStatus.PENDING

        await db.commit()
        await db.refresh(purge_record)

        # Audit the purge operation
        await audit_service.record(
            db,
            user_id=None,
            action="compliance.retention.purge",
            resource_type="data_retention",
            resource_id=str(purge_record.id),
            details={
                "category": category.value,
                "records_purged": count,
                "older_than_days": self.policy.get_retention_days(category),
                "dry_run": is_dry_run,
                "status": purge_record.status.value,
            },
            ip_address=None,
        )

        return purge_record

    async def purge_all(
        self,
        db: AsyncSession,
        *,
        dry_run: bool | None = None,
        purged_by: str | None = None,
    ) -> list[DataRetentionPurge]:
        """Purge expired data for ALL categories.

        Returns a list of :class:`DataRetentionPurge` records, one per
        category.
        """
        results: list[DataRetentionPurge] = []
        for category in DataRetentionCategory:
            result = await self.purge_category(
                db, category, dry_run=dry_run, purged_by=purged_by,
            )
            results.append(result)
        return results

    async def review_expired(
        self,
        db: AsyncSession,
        category: DataRetentionCategory | None = None,
    ) -> dict[str, int]:
        """Review (dry-run count) expired records per category.

        Use this for reporting before executing a purge.
        """
        cutoff = self.policy.get_cutoff_date(category) if category else None
        categories = [category] if category else list(DataRetentionCategory)

        counts: dict[str, int] = {}
        for cat in categories:
            c = cutoff if cutoff else self.policy.get_cutoff_date(cat)
            count = await self._count_expired(db, cat, c)
            counts[cat.value] = count
        return counts

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _count_expired(
        self,
        db: AsyncSession,
        category: DataRetentionCategory,
        cutoff: datetime,
    ) -> int:
        """Count records older than cutoff for a given category."""
        if category == DataRetentionCategory.TRADES:
            result = await db.execute(
                select(text("COUNT(*)")).select_from(text("orders")).where(
                    text("created_at < :cutoff")
                ),
                {"cutoff": cutoff},
            )
        elif category == DataRetentionCategory.DECISIONS:
            result = await db.execute(
                select(text("COUNT(*)")).select_from(text("ai_decisions")).where(
                    text("created_at < :cutoff")
                ),
                {"cutoff": cutoff},
            )
        elif category == DataRetentionCategory.AUDIT_LOGS:
            result = await db.execute(
                select(text("COUNT(*)")).select_from(text("audit_logs")).where(
                    text("timestamp < :cutoff")
                ),
                {"cutoff": cutoff},
            )
        elif category == DataRetentionCategory.NOTIFICATIONS:
            result = await db.execute(
                select(text("COUNT(*)")).select_from(text("notifications")).where(
                    text("created_at < :cutoff")
                ),
                {"cutoff": cutoff},
            )
        elif category == DataRetentionCategory.SESSIONS:
            result = await db.execute(
                select(text("COUNT(*)")).select_from(text("user_sessions")).where(
                    text("created_at < :cutoff")
                ),
                {"cutoff": cutoff},
            )
        elif category == DataRetentionCategory.PI_DATA:
            result = await db.execute(
                select(text("COUNT(*)")).select_from(text("pii_inventory")).where(
                    text("created_at < :cutoff")
                ),
                {"cutoff": cutoff},
            )
        elif category == DataRetentionCategory.CONSENT:
            result = await db.execute(
                select(text("COUNT(*)")).select_from(text("consent_records")).where(
                    text("created_at < :cutoff")
                ),
                {"cutoff": cutoff},
            )
        elif category == DataRetentionCategory.RISK_DISCLOSURES:
            result = await db.execute(
                select(text("COUNT(*)")).select_from(text("risk_disclosures")).where(
                    text("generated_at < :cutoff")
                ),
                {"cutoff": cutoff},
            )
        elif category == DataRetentionCategory.REGULATORY_REPORTS:
            result = await db.execute(
                select(text("COUNT(*)")).select_from(text("regulatory_reports")).where(
                    text("generated_at < :cutoff")
                ),
                {"cutoff": cutoff},
            )
        else:
            return 0
        return result.scalar_one()

    async def _execute_purge(
        self,
        db: AsyncSession,
        category: DataRetentionCategory,
        cutoff: datetime,
    ) -> int:
        """Actually delete expired records."""
        table_map = {
            DataRetentionCategory.TRADES: "orders",
            DataRetentionCategory.DECISIONS: "ai_decisions",
            DataRetentionCategory.AUDIT_LOGS: "audit_logs",
            DataRetentionCategory.NOTIFICATIONS: "notifications",
            DataRetentionCategory.SESSIONS: "user_sessions",
            DataRetentionCategory.PI_DATA: "pii_inventory",
            DataRetentionCategory.CONSENT: "consent_records",
            DataRetentionCategory.RISK_DISCLOSURES: "risk_disclosures",
            DataRetentionCategory.REGULATORY_REPORTS: "regulatory_reports",
        }

        date_col_map = {
            DataRetentionCategory.AUDIT_LOGS: "timestamp",
            DataRetentionCategory.RISK_DISCLOSURES: "generated_at",
            DataRetentionCategory.REGULATORY_REPORTS: "generated_at",
        }

        table = table_map.get(category)
        date_col = date_col_map.get(category, "created_at")

        if not table:
            return 0

        sql = f"DELETE FROM {table} WHERE {date_col} < :cutoff"
        result = await db.execute(text(sql), {"cutoff": cutoff})
        await db.commit()
        return result.rowcount

    async def _archive_data(
        self,
        db: AsyncSession,
        category: DataRetentionCategory,
        cutoff: datetime,
    ) -> tuple[str, str, int]:
        """Export expired records to cold storage before deletion.

        Returns (file_path, sha256_hash, size_bytes).
        """
        archive_dir = os.path.expanduser(self.policy.archive_directory)
        os.makedirs(archive_dir, exist_ok=True)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"{category.value}_{timestamp}.json.gz"
        filepath = os.path.join(archive_dir, filename)

        # Collect expired records
        records = await self._collect_records(db, category, cutoff)

        # Serialize and compress
        content = json.dumps(records, default=str, indent=2).encode("utf-8")
        sha256 = hashlib.sha256(content).hexdigest()

        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode="wb") as f:
            f.write(content)
        compressed = buf.getvalue()

        with open(filepath, "wb") as f:
            f.write(compressed)

        # Create archive manifest record
        data_start = cutoff - timedelta(days=self.policy.get_retention_days(category))
        manifest = ArchiveManifest(
            category=category,
            storage_location=filepath,
            storage_format="json.gz",
            record_count=len(records),
            data_start_date=data_start,
            data_end_date=cutoff,
            archive_hash=sha256,
            file_size_bytes=len(compressed),
        )
        db.add(manifest)
        await db.flush()

        return filepath, sha256, len(compressed)

    async def _collect_records(
        self,
        db: AsyncSession,
        category: DataRetentionCategory,
        cutoff: datetime,
    ) -> list[dict[str, Any]]:
        """Collect expired records for archival."""
        table_map = {
            DataRetentionCategory.TRADES: "orders",
            DataRetentionCategory.DECISIONS: "ai_decisions",
            DataRetentionCategory.AUDIT_LOGS: "audit_logs",
            DataRetentionCategory.NOTIFICATIONS: "notifications",
            DataRetentionCategory.SESSIONS: "user_sessions",
            DataRetentionCategory.PI_DATA: "pii_inventory",
            DataRetentionCategory.CONSENT: "consent_records",
            DataRetentionCategory.RISK_DISCLOSURES: "risk_disclosures",
            DataRetentionCategory.REGULATORY_REPORTS: "regulatory_reports",
        }
        date_col_map = {
            DataRetentionCategory.AUDIT_LOGS: "timestamp",
            DataRetentionCategory.RISK_DISCLOSURES: "generated_at",
            DataRetentionCategory.REGULATORY_REPORTS: "generated_at",
        }

        table = table_map.get(category)
        date_col = date_col_map.get(category, "created_at")
        if not table:
            return []

        sql = f"SELECT * FROM {table} WHERE {date_col} < :cutoff"
        result = await db.execute(text(sql), {"cutoff": cutoff})
        rows = result.mappings().all()
        return [dict(row) for row in rows]


# Global default retention manager
retention_manager = RetentionManager()
