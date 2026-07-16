"""Consent Management — User consent records, withdrawal handling,
consent audit trail, and cookie/consent banner data structures.

Supports GDPR Art. 6-7 (lawful basis for processing) and ePrivacy
Directive (cookie consent).
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from forex_trading.shared.database.models_compliance import (
    ConsentRecord,
    ConsentStatus,
    ConsentType,
)
from forex_trading.shared.security.audit import audit_service
import structlog

logger = structlog.get_logger()


@dataclass
class ConsentBannerConfig:
    """Configuration for consent/Cookie banner presentation.

    This data structure is used to render the appropriate consent
    banner based on the user's jurisdiction.
    """

    show_banner: bool = True
    title: str = "Cookie & Data Processing Consent"
    description: str = (
        "We use cookies and process your personal data to provide "
        "and improve our trading services. Please review your options."
    )
    consent_types: list[dict[str, Any]] = field(default_factory=lambda: [
        {
            "type": "necessary",
            "label": "Necessary",
            "description": "Required for platform operation",
            "required": True,
            "default": True,
        },
        {
            "type": "functional",
            "label": "Functional",
            "description": "Remember your preferences",
            "required": False,
            "default": True,
        },
        {
            "type": "analytics",
            "label": "Analytics",
            "description": "Help us improve our service",
            "required": False,
            "default": False,
        },
        {
            "type": "marketing",
            "label": "Marketing",
            "description": "Send you relevant offers",
            "required": False,
            "default": False,
        },
    ])
    privacy_policy_url: str = "/privacy-policy"
    terms_url: str = "/terms-of-service"
    cookie_policy_url: str = "/cookie-policy"
    version: str = "1.0"
    jurisdiction_specific: dict[str, Any] = field(default_factory=dict)


class ConsentManager:
    """Manage user consent lifecycle — record, withdraw, audit.

    All consent operations are audited via the existing audit service.
    """

    async def record_consent(
        self,
        db: AsyncSession,
        user_id: UUID,
        consent_type: ConsentType | str,
        *,
        ip_address: str | None = None,
        user_agent: str | None = None,
        consent_version: str = "1.0",
        metadata_json: dict[str, Any] | None = None,
    ) -> ConsentRecord:
        """Record a new consent grant.

        If a previous consent of the same type exists and is active,
        it will be marked as withdrawn before the new one is created.
        """
        if isinstance(consent_type, str):
            consent_type = ConsentType(consent_type)

        # Withdraw any existing active consent of this type
        result = await db.execute(
            select(ConsentRecord).where(
                ConsentRecord.user_id == user_id,
                ConsentRecord.consent_type == consent_type,
                ConsentRecord.status == ConsentStatus.GRANTED,
            )
        )
        existing = result.scalars().all()
        now = datetime.now(timezone.utc)
        for record in existing:
            record.status = ConsentStatus.WITHDRAWN
            record.withdrawn_at = now

        # Create new consent record
        record = ConsentRecord(
            user_id=user_id,
            consent_type=consent_type,
            status=ConsentStatus.GRANTED,
            ip_address=ip_address,
            user_agent=user_agent,
            consent_version=consent_version,
            granted_at=now,
            metadata_json=metadata_json,
        )
        db.add(record)
        await db.commit()
        await db.refresh(record)

        # Audit
        await audit_service.record(
            db,
            user_id=user_id,
            action="compliance.consent.grant",
            resource_type="consent",
            resource_id=str(record.id),
            details={
                "consent_type": consent_type.value if isinstance(consent_type, ConsentType) else consent_type,
                "consent_version": consent_version,
                "ip_address": ip_address,
            },
            ip_address=ip_address,
        )

        return record

    async def withdraw_consent(
        self,
        db: AsyncSession,
        user_id: UUID,
        consent_type: ConsentType | str,
        *,
        reason: str | None = None,
    ) -> ConsentRecord | None:
        """Withdraw user consent for a specific type.

        If the user has no active consent of this type, returns None.
        """
        if isinstance(consent_type, str):
            consent_type = ConsentType(consent_type)

        result = await db.execute(
            select(ConsentRecord).where(
                ConsentRecord.user_id == user_id,
                ConsentRecord.consent_type == consent_type,
                ConsentRecord.status == ConsentStatus.GRANTED,
            ).order_by(ConsentRecord.granted_at.desc())
        )
        record = result.scalars().first()
        if not record:
            logger.warning(
                "No active consent to withdraw",
                user_id=str(user_id),
                consent_type=consent_type,
            )
            return None

        now = datetime.now(timezone.utc)
        record.status = ConsentStatus.WITHDRAWN
        record.withdrawn_at = now
        if reason:
            record.metadata_json = record.metadata_json or {}
            record.metadata_json["withdrawal_reason"] = reason

        await db.commit()
        await db.refresh(record)

        # Audit
        await audit_service.record(
            db,
            user_id=user_id,
            action="compliance.consent.withdraw",
            resource_type="consent",
            resource_id=str(record.id),
            details={
                "consent_type": consent_type.value if isinstance(consent_type, ConsentType) else consent_type,
                "reason": reason,
            },
            ip_address=None,
        )

        return record

    async def withdraw_all_consent(
        self,
        db: AsyncSession,
        user_id: UUID,
        *,
        reason: str | None = None,
    ) -> list[ConsentRecord]:
        """Withdraw ALL active consents for a user (GDPR Art. 7(3))."""
        result = await db.execute(
            select(ConsentRecord).where(
                ConsentRecord.user_id == user_id,
                ConsentRecord.status == ConsentStatus.GRANTED,
            )
        )
        records = result.scalars().all()

        now = datetime.now(timezone.utc)
        for record in records:
            record.status = ConsentStatus.WITHDRAWN
            record.withdrawn_at = now
            if reason:
                record.metadata_json = record.metadata_json or {}
                record.metadata_json["withdrawal_reason"] = reason

        await db.commit()

        # Audit each withdrawal
        for record in records:
            await audit_service.record(
                db,
                user_id=user_id,
                action="compliance.consent.withdraw_all",
                resource_type="consent",
                resource_id=str(record.id),
                details={
                    "consent_type": record.consent_type.value if hasattr(record.consent_type, "value") else record.consent_type,
                    "reason": reason,
                },
                ip_address=None,
            )

        return records

    async def check_consent(
        self,
        db: AsyncSession,
        user_id: UUID,
        consent_type: ConsentType | str,
    ) -> bool:
        """Check if a user has valid (granted, not expired) consent.

        Returns True if the user has an active, non-expired consent
        of the specified type.
        """
        if isinstance(consent_type, str):
            consent_type = ConsentType(consent_type)

        now = datetime.now(timezone.utc)
        result = await db.execute(
            select(ConsentRecord).where(
                ConsentRecord.user_id == user_id,
                ConsentRecord.consent_type == consent_type,
                ConsentRecord.status == ConsentStatus.GRANTED,
                (ConsentRecord.expires_at.is_(None)) | (ConsentRecord.expires_at > now),
            ).limit(1)
        )
        return result.scalars().first() is not None

    async def get_consent_history(
        self,
        db: AsyncSession,
        user_id: UUID,
        consent_type: ConsentType | None = None,
    ) -> list[dict[str, Any]]:
        """Get full consent history for a user."""
        query = select(ConsentRecord).where(
            ConsentRecord.user_id == user_id,
        ).order_by(ConsentRecord.granted_at.desc())

        if consent_type:
            query = query.where(ConsentRecord.consent_type == consent_type)

        result = await db.execute(query)
        records = result.scalars().all()

        return [
            {
                "id": str(r.id),
                "consent_type": r.consent_type.value if hasattr(r.consent_type, "value") else r.consent_type,
                "status": r.status.value if hasattr(r.status, "value") else r.status,
                "version": r.consent_version,
                "granted_at": r.granted_at.isoformat() if r.granted_at else None,
                "withdrawn_at": r.withdrawn_at.isoformat() if r.withdrawn_at else None,
                "expires_at": r.expires_at.isoformat() if r.expires_at else None,
                "ip_address": r.ip_address,
                "user_agent": r.user_agent,
            }
            for r in records
        ]

    async def get_consent_summary(
        self,
        db: AsyncSession,
        user_id: UUID,
    ) -> dict[str, Any]:
        """Get a summary of all consent statuses for a user."""
        result = await db.execute(
            select(ConsentRecord).where(
                ConsentRecord.user_id == user_id,
                ConsentRecord.status == ConsentStatus.GRANTED,
            )
        )
        grants = result.scalars().all()

        now = datetime.now(timezone.utc)
        active_consents = {}
        for g in grants:
            if g.expires_at is None or g.expires_at > now:
                ct = g.consent_type.value if hasattr(g.consent_type, "value") else g.consent_type
                active_consents[ct] = {
                    "status": "active",
                    "version": g.consent_version,
                    "granted_at": g.granted_at.isoformat() if g.granted_at else None,
                }

        return {
            "user_id": str(user_id),
            "has_trading_authorization": await self.check_consent(
                db, user_id, ConsentType.TRADING_AUTHORIZATION
            ),
            "has_risk_disclosure": await self.check_consent(
                db, user_id, ConsentType.RISK_DISCLOSURE
            ),
            "has_terms": await self.check_consent(
                db, user_id, ConsentType.TERMS_OF_SERVICE
            ),
            "active_consents": active_consents,
        }

    def get_banner_config(
        self,
        jurisdiction: str = "default",
    ) -> ConsentBannerConfig:
        """Get consent banner configuration, possibly jurisdiction-specific.

        Different jurisdictions may require different consent types
        or banner text (e.g., GDPR in EU, LGPD in Brazil, CCPA in California).
        """
        config = ConsentBannerConfig()

        # Jurisdiction-specific overrides
        if jurisdiction.upper() == "EU":
            config.title = "GDPR Cookie & Data Consent"
            config.description = (
                "We use cookies and process your personal data in accordance "
                "with the General Data Protection Regulation (GDPR). "
                "Please review your consent options."
            )
            config.jurisdiction_specific = {
                "regulation": "GDPR",
                "requires_legitimate_interest": True,
                "cookie_lifetime_days": 365,
                "requires_renewal": True,
                "renewal_interval_days": 180,
            }
        elif jurisdiction.upper() in ("US", "CA", "CALIFORNIA"):
            config.title = "CCPA/CPRA Privacy Notice"
            config.description = (
                "We collect and process your personal information as described "
                "in our Privacy Policy. Under the California Consumer Privacy Act "
                "(CCPA), you have the right to opt out of the sale of your data."
            )
            config.jurisdiction_specific = {
                "regulation": "CCPA",
                "right_to_opt_out": True,
                "right_to_delete": True,
                "right_to_know": True,
            }
        elif jurisdiction.upper() == "BR":
            config.title = "LGPD Consentimento"
            config.description = (
                "Nós utilizamos cookies e processamos seus dados pessoais "
                "de acordo com a Lei Geral de Proteção de Dados (LGPD)."
            )
            config.jurisdiction_specific = {
                "regulation": "LGPD",
            }

        return config


# Global default consent manager
consent_manager = ConsentManager()
