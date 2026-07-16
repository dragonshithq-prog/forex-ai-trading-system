"""Data Classification — Classification levels, automatic classification,
handling procedures per level, and data flow mapping for regulated data.

Classification Levels:
  - PUBLIC: Non-sensitive, freely distributable
  - INTERNAL: Internal use only, not for public distribution
  - CONFIDENTIAL: Sensitive business data, restricted access
  - RESTRICTED: Highly sensitive, regulated data (PII, credentials, trade secrets)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from forex_trading.shared.database.models_compliance import (
    ClassificationLevel,
    DataClassificationRule,
)
from forex_trading.shared.security.audit import audit_service

logger = logging.getLogger(__name__)


# Re-export for convenience
ClassificationLevel = ClassificationLevel


@dataclass
class DataClassification:
    """Classification metadata for a data element."""

    level: ClassificationLevel
    label: str
    description: str = ""
    handling_procedure: str = ""
    retention_days: int | None = None
    requires_encryption: bool = False
    requires_access_logging: bool = False
    requires_anonymization: bool = False
    data_flow: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Default classification rules for known tables/fields
# ---------------------------------------------------------------------------

DEFAULT_CLASSIFICATION_RULES: dict[str, dict[str, Any]] = {
    "users.email": {
        "level": ClassificationLevel.RESTRICTED,
        "label": "Personal Email",
        "description": "User email address — PII",
        "handling_procedure": "Must be encrypted at rest. Only accessible to user and admins.",
        "requires_encryption": True,
        "requires_access_logging": True,
    },
    "users.username": {
        "level": ClassificationLevel.INTERNAL,
        "label": "Username",
        "description": "User display name",
        "handling_procedure": "Internal use only.",
    },
    "users.hashed_password": {
        "level": ClassificationLevel.RESTRICTED,
        "label": "Password Hash",
        "description": "Bcrypt password hash",
        "handling_procedure": "Never logged, never exposed. Use bcrypt comparison only.",
        "requires_encryption": True,
        "requires_access_logging": True,
    },
    "users.full_name": {
        "level": ClassificationLevel.CONFIDENTIAL,
        "label": "Full Name",
        "description": "User legal name — PII",
        "handling_procedure": "Masked in logs and exports. Access limited to authorized personnel.",
        "requires_anonymization": True,
    },
    "users.mfa_secret": {
        "level": ClassificationLevel.RESTRICTED,
        "label": "MFA Secret",
        "description": "Multi-factor authentication secret key",
        "handling_procedure": "Must be encrypted at rest. Never logged.",
        "requires_encryption": True,
        "requires_access_logging": True,
    },
    "users.preferences": {
        "level": ClassificationLevel.INTERNAL,
        "label": "User Preferences",
        "description": "User settings and preferences",
    },
    "broker_accounts.credentials_encrypted": {
        "level": ClassificationLevel.RESTRICTED,
        "label": "Broker Credentials",
        "description": "Encrypted broker API credentials",
        "handling_procedure": "Must be encrypted at rest. Access logged. Decrypt only in-memory.",
        "requires_encryption": True,
        "requires_access_logging": True,
    },
    "broker_accounts.account_number": {
        "level": ClassificationLevel.CONFIDENTIAL,
        "label": "Account Number",
        "description": "Broker account identifier",
        "handling_procedure": "Masked in logs and exports.",
        "requires_anonymization": True,
    },
    "broker_accounts.balance": {
        "level": ClassificationLevel.CONFIDENTIAL,
        "label": "Account Balance",
        "description": "Current account balance",
        "handling_procedure": "Internal use only. Not shared externally.",
    },
    "orders.*": {
        "level": ClassificationLevel.CONFIDENTIAL,
        "label": "Order Data",
        "description": "Trading order details",
        "handling_procedure": "Regulated trading data. Retained per MiFID II requirements.",
        "retention_days": 2555,
    },
    "positions.*": {
        "level": ClassificationLevel.CONFIDENTIAL,
        "label": "Position Data",
        "description": "Trading position details",
        "handling_procedure": "Regulated trading data. Retained per MiFID II requirements.",
        "retention_days": 2555,
    },
    "deals.*": {
        "level": ClassificationLevel.CONFIDENTIAL,
        "label": "Deal Data",
        "description": "Execution deal details",
        "handling_procedure": "Regulated trading data. Retained per regulatory requirements.",
        "retention_days": 2555,
    },
    "ai_decisions.*": {
        "level": ClassificationLevel.INTERNAL,
        "label": "AI Decision Data",
        "description": "AI agent decision records",
        "handling_procedure": "Internal audit and improvement data.",
    },
    "risk_configurations.*": {
        "level": ClassificationLevel.CONFIDENTIAL,
        "label": "Risk Configuration",
        "description": "Risk management settings",
        "handling_procedure": "Access limited to admins and risk managers.",
    },
    "audit_logs.*": {
        "level": ClassificationLevel.CONFIDENTIAL,
        "label": "Audit Logs",
        "description": "System audit trail",
        "handling_procedure": "Immutable. Access limited to authorized auditors.",
        "retention_days": 2555,
    },
    "consent_records.*": {
        "level": ClassificationLevel.RESTRICTED,
        "label": "Consent Records",
        "description": "User consent for data processing",
        "handling_procedure": "GDPR-regulated data. Must be retained for regulatory period.",
        "retention_days": 2555,
        "requires_access_logging": True,
    },
    "user_sessions.*": {
        "level": ClassificationLevel.CONFIDENTIAL,
        "label": "Session Data",
        "description": "User authentication sessions",
        "handling_procedure": "Retained for limited period. Revoked on logout.",
        "retention_days": 90,
    },
    "notifications.*": {
        "level": ClassificationLevel.INTERNAL,
        "label": "Notification Data",
        "description": "User notification records",
        "retention_days": 365,
    },
}

# Data flow mappings for regulated data
DATA_FLOW_MAP: dict[str, list[dict[str, str]]] = {
    "PII": [
        {"source": "User Registration", "destination": "Users Table", "purpose": "Account Creation"},
        {"source": "Users Table", "destination": "Session Store", "purpose": "Authentication"},
        {"source": "Users Table", "destination": "Audit Log", "purpose": "Activity Tracking"},
        {"source": "Users Table", "destination": "Notification Service", "purpose": "Communication"},
    ],
    "TRADING_DATA": [
        {"source": "Broker Gateway", "destination": "Orders Table", "purpose": "Order Execution"},
        {"source": "Orders Table", "destination": "Positions Table", "purpose": "Position Management"},
        {"source": "Positions Table", "destination": "Deals Table", "purpose": "Settlement"},
        {"source": "Deals Table", "destination": "Risk Engine", "purpose": "Risk Monitoring"},
        {"source": "Positions Table", "destination": "P&L Reports", "purpose": "Regulatory Reporting"},
    ],
    "CONSENT_DATA": [
        {"source": "Consent Banner", "destination": "Consent Records", "purpose": "Consent Management"},
        {"source": "Consent Records", "destination": "Audit Log", "purpose": "Compliance Audit"},
    ],
}


class DataClassifier:
    """Classify data elements and provide handling procedures.

    Maintains a rule set that can be loaded from the database or
    initialized from defaults.
    """

    def __init__(self) -> None:
        self._rules: dict[str, DataClassification] = {}
        self._initialize_defaults()

    def _initialize_defaults(self) -> None:
        """Load default classification rules."""
        for key, rule_data in DEFAULT_CLASSIFICATION_RULES.items():
            rule_data["level"] = ClassificationLevel(rule_data["level"])
            self._rules[key] = DataClassification(**rule_data)

    async def load_rules_from_db(
        self,
        db: AsyncSession,
    ) -> dict[str, DataClassification]:
        """Load classification rules from database, overriding defaults."""
        result = await db.execute(
            select(DataClassificationRule).where(DataClassificationRule.is_active.is_(True))
        )
        db_rules = result.scalars().all()

        for rule in db_rules:
            key = f"{rule.table_name}.{rule.field_name}"
            self._rules[key] = DataClassification(
                level=ClassificationLevel(rule.classification_level.value if hasattr(rule.classification_level, 'value') else rule.classification_level),
                label=f"{rule.table_name}.{rule.field_name}",
                description=rule.rationale or "",
                handling_procedure=rule.handling_procedure or "",
            )

        return self._rules

    async def sync_rules_to_db(
        self,
        db: AsyncSession,
    ) -> list[DataClassificationRule]:
        """Sync default classification rules to the database."""
        db_rules = []
        for key, classification in self._rules.items():
            table_name, field_name = key.split(".", 1)

            result = await db.execute(
                select(DataClassificationRule).where(
                    DataClassificationRule.table_name == table_name,
                    DataClassificationRule.field_name == field_name,
                )
            )
            existing = result.scalars().first()

            if existing:
                existing.classification_level = classification.level
                existing.rationale = classification.description
                existing.handling_procedure = classification.handling_procedure
                db_rules.append(existing)
            else:
                rule = DataClassificationRule(
                    table_name=table_name,
                    field_name=field_name,
                    classification_level=classification.level,
                    rationale=classification.description,
                    handling_procedure=classification.handling_procedure,
                )
                db.add(rule)
                db_rules.append(rule)

        await db.commit()
        for rule in db_rules:
            await db.refresh(rule)
        return db_rules

    def classify(
        self,
        table_name: str,
        field_name: str,
    ) -> DataClassification:
        """Classify a data element by table and field name.

        Returns the classification with handling procedures. Falls back
        to CONFIDENTIAL if no specific rule exists.
        """
        # Try exact match
        key = f"{table_name}.{field_name}"
        if key in self._rules:
            return self._rules[key]

        # Try wildcard match (table.*)
        wildcard_key = f"{table_name}.*"
        if wildcard_key in self._rules:
            return self._rules[wildcard_key]

        # Default fallback
        return DataClassification(
            level=ClassificationLevel.CONFIDENTIAL,
            label=f"{table_name}.{field_name}",
            description="Default classification — no specific rule defined",
            handling_procedure="Handle as confidential data. Access limited to authorized personnel.",
        )

    def get_handling_procedure(self, classification: DataClassification) -> str:
        """Get the full handling procedure for a classification level."""
        level = classification.level
        if isinstance(level, str):
            level = ClassificationLevel(level)

        procedures = {
            ClassificationLevel.PUBLIC: (
                "• Freely distributable\n"
                "• No access restrictions\n"
                "• No encryption required\n"
                "• May be cached publicly"
            ),
            ClassificationLevel.INTERNAL: (
                "• Internal use only — not for public distribution\n"
                "• Access limited to authenticated users\n"
                "• Encryption at rest recommended\n"
                "• Do not share with external parties"
            ),
            ClassificationLevel.CONFIDENTIAL: (
                "• Restricted to authorized personnel only\n"
                "• Encryption at rest required\n"
                "• Encryption in transit required (TLS)\n"
                "• Access must be logged\n"
                "• Data masking in logs and exports\n"
                "• Do not store on personal devices\n"
                "• Regular access audits required"
            ),
            ClassificationLevel.RESTRICTED: (
                "• HIGHLY SENSITIVE — Strict access control required\n"
                "• Encryption at rest required (AES-256 or equivalent)\n"
                "• Encryption in transit required (TLS 1.2+)\n"
                "• All access must be logged and monitored\n"
                "• Data masking required in all non-essential contexts\n"
                "• MFA required for access\n"
                "• No export without approval\n"
                "• Regular compliance audits required\n"
                "• Breach notification within 72 hours"
            ),
        }

        base = procedures.get(level, procedures[ClassificationLevel.CONFIDENTIAL])
        if classification.handling_procedure:
            base += f"\n\nSpecific handling:\n{classification.handling_procedure}"

        return base

    def get_data_flow(
        self,
        data_category: str,
    ) -> list[dict[str, str]]:
        """Get data flow mapping for a regulated data category.

        Args:
            data_category: One of "PII", "TRADING_DATA", "CONSENT_DATA"

        Returns:
            List of flow steps with source, destination, and purpose.
        """
        return DATA_FLOW_MAP.get(data_category.upper(), [])

    def get_all_data_flows(self) -> dict[str, list[dict[str, str]]]:
        """Get all regulated data flow mappings."""
        return dict(DATA_FLOW_MAP)

    def add_classification_rule(
        self,
        table_name: str,
        field_name: str,
        classification: DataClassification,
    ) -> None:
        """Add or update a classification rule in memory."""
        key = f"{table_name}.{field_name}"
        self._rules[key] = classification

    def get_report(
        self,
        level_filter: ClassificationLevel | None = None,
    ) -> list[dict[str, Any]]:
        """Generate a data classification report.

        Args:
            level_filter: Optional filter by classification level.

        Returns:
            List of classified data elements with their handling procedures.
        """
        report = []
        for key, classification in sorted(self._rules.items()):
            if level_filter and classification.level != level_filter:
                continue
            report.append({
                "key": key,
                "level": classification.level.value if hasattr(classification.level, "value") else classification.level,
                "label": classification.label,
                "description": classification.description,
                "requires_encryption": classification.requires_encryption,
                "requires_access_logging": classification.requires_access_logging,
                "requires_anonymization": classification.requires_anonymization,
                "retention_days": classification.retention_days,
                "handling_procedure": classification.handling_procedure,
                "data_flow": classification.data_flow,
            })
        return report


# Global default data classifier
data_classifier = DataClassifier()
