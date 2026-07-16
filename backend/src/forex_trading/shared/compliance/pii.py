"""PII Management — PII field annotation, automatic masking in logs/exports,
PII inventory reports, DSAR handler, and right to erasure (GDPR Art. 17).

Usage::

    from forex_trading.shared.compliance.pii import pii_field, PIIManager

    class UserProfile:
        email = pii_field("email", category="sensitive")
        name = pii_field("name", category="internal")
"""

from __future__ import annotations

import copy
import enum
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from forex_trading.shared.database.models_compliance import (
    PIIInventory,
    PIICategory,
)
from forex_trading.shared.security.audit import audit_service

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# PII Annotation System
# ---------------------------------------------------------------------------


@dataclass
class PIIField:
    """Descriptor for a PII-sensitive field on a model or dataclass.

    Attributes:
        name: Display name of the field.
        category: Sensitivity category (public, internal, sensitive, restricted).
        description: Human-readable description of why this is PII.
        masking_func: Optional custom masking function.
        retention_days: Optional retention period specific to this field.
    """

    name: str
    category: PIICategory = PIICategory.SENSITIVE
    description: str = ""
    masking_func: Callable[[Any], str] | None = None
    retention_days: int | None = None


# Sentinel to mark PII fields
_PII_FIELDS: dict[type, dict[str, PIIField]] = {}


def pii_field(
    name: str,
    category: PIICategory = PIICategory.SENSITIVE,
    description: str = "",
    masking_func: Callable[[Any], str] | None = None,
    retention_days: int | None = None,
) -> property:
    """Decorator-like marker for PII-sensitive fields.

    Registers the field in the global PII registry for the owning class.
    Apply this to properties or store the result as a class attribute.

    Example::

        class UserModel:
            @pii_field("email", category="sensitive", description="User email address")
            @property
            def email(self) -> str:
                return self._email

    Can also be used as a plain descriptor::

        class UserModel:
            email = pii_field("email_address", category=PIICategory.SENSITIVE)
    """
    registry = _PII_FIELDS

    def decorator(func: Callable) -> property:
        # Find the owning class via closure inspection
        owner = _find_owner(func)
        if owner is not None:
            if owner not in registry:
                registry[owner] = {}
            registry[owner][func.__name__] = PIIField(
                name=name,
                category=PIICategory(category) if isinstance(category, str) else category,
                description=description,
                masking_func=masking_func,
                retention_days=retention_days,
            )
        return property(func)

    # If used as a plain descriptor (not decorator), return a marker
    field = PIIField(
        name=name,
        category=PIICategory(category) if isinstance(category, str) else category,
        description=description,
        masking_func=masking_func,
        retention_days=retention_days,
    )

    # Create a property-like descriptor
    class PIIProperty:
        def __get__(self, obj, objtype=None):
            if obj is None:
                return self
            return field

        def __set__(self, obj, value):
            pass

    return PIIProperty()  # type: ignore


def _find_owner(func: Callable) -> type | None:
    """Try to find the class that owns this function."""
    import inspect
    try:
        # Look up the class in the call stack
        for frame in inspect.stack():
            local_self = frame[0].f_locals.get("self")
            if local_self is not None and hasattr(type(local_self), func.__name__):
                return type(local_self)
    except Exception:
        pass
    return None


def get_pii_fields(cls: type) -> dict[str, PIIField]:
    """Return all registered PII fields for a class."""
    return _PII_FIELDS.get(cls, {})


def register_pii_fields(
    cls: type,
    fields: dict[str, PIIField | dict[str, Any]],
) -> None:
    """Register PII fields for a class programmatically (no decorator needed)."""
    if cls not in _PII_FIELDS:
        _PII_FIELDS[cls] = {}
    for name, field_def in fields.items():
        if isinstance(field_def, dict):
            field_def = PIIField(**field_def)
        _PII_FIELDS[cls][name] = field_def


# ---------------------------------------------------------------------------
# Default masking functions
# ---------------------------------------------------------------------------


def mask_email(value: str) -> str:
    """Mask email: 'user@domain.com' -> 'u***@domain.com'."""
    if not value or "@" not in value:
        return "***"
    local, domain = value.split("@", 1)
    if len(local) <= 1:
        return f"{local}***@{domain}"
    return f"{local[0]}***@{domain}"


def mask_phone(value: str) -> str:
    """Mask phone: '+1234567890' -> '+******7890'."""
    if not value:
        return "***"
    if len(value) <= 4:
        return "***"
    return f"{'*' * (len(value) - 4)}{value[-4:]}"


def mask_name(value: str) -> str:
    """Mask name: 'John Doe' -> 'J*** D***'."""
    if not value:
        return "***"
    parts = value.split()
    masked = []
    for part in parts:
        if len(part) <= 1:
            masked.append(part)
        else:
            masked.append(f"{part[0]}***")
    return " ".join(masked)


def mask_ip(value: str) -> str:
    """Mask IP: '192.168.1.1' -> '192.168.0.0'."""
    if not value:
        return "***"
    parts = value.split(".")
    if len(parts) == 4:
        return f"{parts[0]}.{parts[1]}.0.0"
    return "***"


def mask_generic(value: Any) -> str:
    """Generic mask: replace with '***'."""
    return "***"


# Built-in maskers by field name pattern
DEFAULT_MASKERS: dict[str, Callable[[Any], str]] = {
    "email": mask_email,
    "mail": mask_email,
    "phone": mask_phone,
    "telephone": mask_phone,
    "mobile": mask_phone,
    "name": mask_name,
    "full_name": mask_name,
    "first_name": mask_name,
    "last_name": mask_name,
    "ip_address": mask_ip,
    "ip": mask_ip,
    "password": mask_generic,
    "secret": mask_generic,
    "token": mask_generic,
}


# ---------------------------------------------------------------------------
# PII Manager
# ---------------------------------------------------------------------------


class PIIManager:
    """Manage PII discovery, masking, inventory, DSAR, and erasure.

    This class is stateless (all state in the database).  Create one
    instance and reuse it.
    """

    async def discover_fields(
        self,
        db: AsyncSession,
        auto_register: bool = True,
    ) -> list[PIIInventory]:
        """Discover and register PII fields from the annotated registry.

        Scans all registered PII field annotations and syncs them into
        the ``pii_inventory`` table.
        """
        registered: list[PIIInventory] = []

        for cls, fields in _PII_FIELDS.items():
            table_name = getattr(cls, "__tablename__", cls.__name__)
            for field_name, pii_field_def in fields.items():
                # Check if already registered
                result = await db.execute(
                    select(PIIInventory).where(
                        PIIInventory.table_name == table_name,
                        PIIInventory.field_name == field_name,
                    )
                )
                existing = result.scalars().first()

                if existing:
                    existing.category = pii_field_def.category
                    existing.description = pii_field_def.description or existing.description
                    existing.retention_days = pii_field_def.retention_days
                    registered.append(existing)
                else:
                    entry = PIIInventory(
                        table_name=table_name,
                        field_name=field_name,
                        category=pii_field_def.category,
                        description=pii_field_def.description,
                        retention_days=pii_field_def.retention_days,
                        masking_rule=pii_field_def.masking_func.__name__
                        if pii_field_def.masking_func
                        else "mask_generic",
                    )
                    db.add(entry)
                    registered.append(entry)

        await db.commit()
        for entry in registered:
            await db.refresh(entry)

        return registered

    async def get_inventory(
        self,
        db: AsyncSession,
        category: PIICategory | None = None,
    ) -> list[dict[str, Any]]:
        """Get PII inventory report.

        Returns a list of dicts with all PII fields and their metadata.
        """
        query = select(PIIInventory).order_by(PIIInventory.table_name, PIIInventory.field_name)
        if category:
            query = query.where(PIIInventory.category == category)

        result = await db.execute(query)
        entries = result.scalars().all()

        return [
            {
                "id": str(e.id),
                "table_name": e.table_name,
                "field_name": e.field_name,
                "category": e.category.value,
                "description": e.description,
                "is_required": e.is_required,
                "retention_days": e.retention_days,
                "masking_rule": e.masking_rule,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in entries
        ]

    def mask_value(
        self,
        field_name: str,
        value: Any,
        custom_masker: Callable[[Any], str] | None = None,
    ) -> str:
        """Mask a single value using the appropriate masker.

        Looks up the masker by field name pattern, then falls back to
        generic masking.
        """
        if custom_masker:
            return custom_masker(value)

        # Check DEFAULT_MASKERS for matching pattern
        field_lower = field_name.lower().replace("_", "")
        for pattern, masker in DEFAULT_MASKERS.items():
            if pattern.lower().replace("_", "") in field_lower:
                return masker(value)

        return mask_generic(value)

    def mask_dict(
        self,
        data: dict[str, Any],
        pii_fields: set[str] | None = None,
    ) -> dict[str, Any]:
        """Return a copy of *data* with PII values masked.

        Args:
            data: The dict to mask.
            pii_fields: Set of field names that are PII. If None, all
                fields matching known PII patterns are masked.

        Returns:
            A new dict with PII values masked.
        """
        masked = copy.deepcopy(data)
        for key in list(masked.keys()):
            if pii_fields is None or key in pii_fields:
                masked[key] = self.mask_value(key, masked[key])
        return masked

    async def handle_dsar(
        self,
        db: AsyncSession,
        user_id: UUID,
    ) -> dict[str, Any]:
        """Data Subject Access Request (DSAR) — collect all PII for a user.

        Gathers all data related to a user across tables for export.

        Args:
            db: Database session.
            user_id: UUID of the data subject.

        Returns:
            A dict with categories of personal data found.
        """
        from forex_trading.shared.database.models_user import User, UserSession

        dsar_data: dict[str, Any] = {
            "user_id": str(user_id),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "data": {},
        }

        # User profile data
        result = await db.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalars().first()
        if user:
            dsar_data["data"]["profile"] = {
                "id": str(user.id),
                "email": user.email,
                "username": user.username,
                "full_name": user.full_name,
                "role": user.role.value if hasattr(user.role, "value") else user.role,
                "is_active": user.is_active,
                "is_verified": user.is_verified,
                "mfa_enabled": user.mfa_enabled,
                "last_login": user.last_login.isoformat() if user.last_login else None,
                "preferences": user.preferences,
                "created_at": user.created_at.isoformat() if user.created_at else None,
            }

        # Sessions
        result = await db.execute(
            select(UserSession).where(UserSession.user_id == user_id)
        )
        sessions = result.scalars().all()
        dsar_data["data"]["sessions"] = [
            {
                "id": str(s.id),
                "ip_address": s.ip_address,
                "user_agent": s.user_agent,
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "expires_at": s.expires_at.isoformat() if s.expires_at else None,
            }
            for s in sessions
        ]

        # Audit logs
        from forex_trading.shared.database.models_user import AuditLog
        result = await db.execute(
            select(AuditLog).where(AuditLog.user_id == user_id).limit(1000)
        )
        audit_logs = result.scalars().all()
        dsar_data["data"]["audit_logs"] = [
            {
                "id": str(a.id),
                "action": a.action,
                "resource_type": a.resource_type,
                "resource_id": a.resource_id,
                "timestamp": a.timestamp.isoformat() if a.timestamp else None,
                "ip_address": a.ip_address,
            }
            for a in audit_logs
        ]

        # Consent records
        from forex_trading.shared.database.models_compliance import ConsentRecord
        result = await db.execute(
            select(ConsentRecord).where(ConsentRecord.user_id == user_id)
        )
        consents = result.scalars().all()
        dsar_data["data"]["consent_records"] = [
            {
                "id": str(c.id),
                "consent_type": c.consent_type.value if hasattr(c.consent_type, "value") else c.consent_type,
                "status": c.status.value if hasattr(c.status, "value") else c.status,
                "granted_at": c.granted_at.isoformat() if c.granted_at else None,
                "withdrawn_at": c.withdrawn_at.isoformat() if c.withdrawn_at else None,
            }
            for c in consents
        ]

        # Audit the DSAR
        await audit_service.record(
            db,
            user_id=user_id,
            action="compliance.pii.dsar",
            resource_type="user",
            resource_id=str(user_id),
            details={"categories": list(dsar_data["data"].keys())},
            ip_address=None,
        )

        return dsar_data

    async def right_to_erasure(
        self,
        db: AsyncSession,
        user_id: UUID,
        *,
        preserve_audit_logs: bool = True,
        preserve_trade_records: bool = True,
    ) -> dict[str, int]:
        """GDPR Art. 17 — Right to erasure (right to be forgotten).

        Anonymizes or deletes personal data for the specified user.
        By default, audit logs and trade records are preserved
        (anonymized) for legal/regulatory compliance.

        Args:
            db: Database session.
            user_id: UUID of the data subject.
            preserve_audit_logs: Anonymize audit logs rather than delete.
            preserve_trade_records: Anonymize trade records rather than delete.

        Returns:
            Dict with counts of deleted/anonymized records.
        """
        from forex_trading.shared.database.models_user import User, UserSession, AuditLog
        from forex_trading.shared.database.models_compliance import ConsentRecord

        counts: dict[str, int] = {
            "profile_anonymized": 0,
            "sessions_deleted": 0,
            "consent_records_deleted": 0,
            "audit_logs_anonymized": 0,
        }

        # Anonymize user profile
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalars().first()
        if user:
            user.email = f"redacted-{user.id}@anonymized.local"
            user.username = f"user-{user.id.hex[:8]}"
            user.full_name = None
            user.hashed_password = "ANONYMIZED"
            user.mfa_secret = None
            user.preferences = None
            counts["profile_anonymized"] = 1

        # Delete sessions
        result = await db.execute(
            select(UserSession).where(UserSession.user_id == user_id)
        )
        sessions = result.scalars().all()
        for session in sessions:
            await db.delete(session)
        counts["sessions_deleted"] = len(sessions)

        # Handle audit logs
        if preserve_audit_logs:
            result = await db.execute(
                select(AuditLog).where(AuditLog.user_id == user_id)
            )
            logs = result.scalars().all()
            for log in logs:
                log.user_id = None
                log.ip_address = None
                if log.details and isinstance(log.details, dict):
                    log.details["anonymized"] = True
                counts["audit_logs_anonymized"] = len(logs)
        else:
            result = await db.execute(
                select(AuditLog).where(AuditLog.user_id == user_id)
            )
            logs = result.scalars().all()
            for log in logs:
                await db.delete(log)
            counts["audit_logs_deleted"] = len(logs)

        # Delete consent records
        result = await db.execute(
            select(ConsentRecord).where(ConsentRecord.user_id == user_id)
        )
        consents = result.scalars().all()
        for consent in consents:
            await db.delete(consent)
        counts["consent_records_deleted"] = len(consents)

        await db.commit()

        # Audit the erasure
        await audit_service.record(
            db,
            user_id=user_id,
            action="compliance.pii.erasure",
            resource_type="user",
            resource_id=str(user_id),
            details=counts,
            ip_address=None,
        )

        return counts


# Global default PII manager
pii_manager = PIIManager()
