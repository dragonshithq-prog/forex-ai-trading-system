"""Compliance & Auditing package.

Provides regulatory compliance, data retention, PII management,
trade reconstruction, immutable audit logging, consent management,
risk disclosure, and data classification for the Forex Trading Bot.

Every compliance operation is itself audited via the existing
:class:`forex_trading.shared.security.audit.AuditService`.
"""

from forex_trading.shared.compliance.retention import (
    RetentionPolicy,
    RetentionManager,
    DataRetentionCategory,
)
from forex_trading.shared.compliance.pii import (
    pii_field,
    PIIField,
    PIIManager,
    PIICategory,
)
from forex_trading.shared.compliance.reconstruction import (
    TradeReconstructor,
    ReconstructionChain,
)
from forex_trading.shared.compliance.reporting import (
    ReportGenerator,
    ReportType,
    ReportFormat,
)
from forex_trading.shared.compliance.consent import (
    ConsentManager,
    ConsentType,
    ConsentRecord,
)
from forex_trading.shared.compliance.disclosure import (
    RiskDisclosureGenerator,
    Jurisdiction,
)
from forex_trading.shared.compliance.classification import (
    DataClassification,
    DataClassifier,
    ClassificationLevel,
)

__all__ = [
    "RetentionPolicy",
    "RetentionManager",
    "DataRetentionCategory",
    "pii_field",
    "PIIField",
    "PIIManager",
    "PIICategory",
    "TradeReconstructor",
    "ReconstructionChain",
    "ReportGenerator",
    "ReportType",
    "ReportFormat",
    "ConsentManager",
    "ConsentType",
    "ConsentRecord",
    "RiskDisclosureGenerator",
    "Jurisdiction",
    "DataClassification",
    "DataClassifier",
    "ClassificationLevel",
]
