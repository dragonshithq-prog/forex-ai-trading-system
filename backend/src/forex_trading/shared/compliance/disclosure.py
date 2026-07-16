"""Risk Disclosure — Dynamic risk disclaimer generation, per-trade risk
acknowledgment, strategy-specific risk warnings, and jurisdiction-specific
disclaimers.

All generated disclosures are recorded and can be tied to user acknowledgment
for compliance auditing.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from forex_trading.shared.database.models_compliance import RiskDisclosure
from forex_trading.shared.security.audit import audit_service
import structlog

logger = structlog.get_logger()


class Jurisdiction(str, Enum):
    """Supported regulatory jurisdictions."""
    GLOBAL = "global"
    EU = "eu"
    UK = "uk"
    US = "us"
    AU = "au"
    JP = "jp"
    SG = "sg"
    CH = "ch"
    CA = "ca"
    BR = "br"


# ---------------------------------------------------------------------------
# Jurisdiction-specific disclaimer templates
# ---------------------------------------------------------------------------

# Base disclaimer components
BASE_RISK_WARNING = (
    "Trading foreign exchange (Forex) on margin carries a high level of risk "
    "and may not be suitable for all investors. The high degree of leverage "
    "can work against you as well as for you. Before deciding to trade Forex, "
    "you should carefully consider your investment objectives, level of "
    "experience, and risk appetite."
)

LEVERAGE_WARNING = (
    "The possibility exists that you could sustain a loss of some or all of "
    "your initial deposit and therefore you should not speculate with capital "
    "that you cannot afford to lose."
)

PAST_PERFORMANCE_WARNING = (
    "Past performance is not indicative of future results. The historical "
    "performance of any trading strategy or system is not a guarantee of "
    "future results."
)

AUTOMATED_TRADING_WARNING = (
    "Automated trading systems, including AI-driven strategies, may experience "
    "technical failures, data inaccuracies, or unexpected market conditions "
    "that could result in losses. You should monitor your automated trading "
    "strategies regularly."
)

JURISDICTION_DISCLAIMERS: dict[Jurisdiction, str] = {
    Jurisdiction.GLOBAL: (
        "This service is provided for informational purposes only and does "
        "not constitute investment advice, solicitation, or recommendation."
    ),
    Jurisdiction.EU: (
        "CFDs are complex instruments and come with a high risk of losing "
        "money rapidly due to leverage. Between 74-89% of retail investor "
        "accounts lose money when trading CFDs. You should consider whether "
        "you understand how CFDs work and whether you can afford to take the "
        "high risk of losing your money. This information is provided in "
        "compliance with ESMA guidelines."
    ),
    Jurisdiction.UK: (
        "Forex and CFD trading carries significant risk. Past performance is "
        "not a reliable indicator of future results. This communication is "
        "issued by [Company Name] which is authorised and regulated by the "
        "Financial Conduct Authority (FCA)."
    ),
    Jurisdiction.US: (
        "Trading foreign exchange on margin carries a high level of risk and "
        "may not be suitable for all investors. The Commodity Futures Trading "
        "Commission (CFTC) has not reviewed or approved this trading system. "
        "Hypothetical or simulated performance results have certain inherent "
        "limitations. Unlike an actual performance record, simulated results "
        "do not represent actual trading."
    ),
    Jurisdiction.AU: (
        "This service is provided by [Company Name] (ABN [number]), which is "
        "regulated by the Australian Securities and Investments Commission "
        "(ASIC). Forex and CFD trading carries significant risk. You should "
        "consider seeking independent financial advice."
    ),
    Jurisdiction.JP: (
        "外国為替証拠金取引は、元本および利益を保証するものではなく、"
        "為替レートの変動により損失が生じることがあります。取引を開始する"
        "前に、取引の仕組みやリスクについて十分に理解し、ご自身の判断で"
        "取引を行ってください。"
    ),
    Jurisdiction.SG: (
        "Trading in Forex and CFDs involves significant risk and may result "
        "in the loss of your invested capital. This product may not be "
        "suitable for all investors. Please ensure you understand the risks "
        "and seek independent advice if necessary."
    ),
    Jurisdiction.CH: (
        "Der Devisen- und CFD-Handel birgt ein erhebliches Verlustrisiko. "
        "Sie können mehr als Ihre Einlage verlieren. Diese Informationen "
        "stellen keine Anlageberatung dar."
    ),
    Jurisdiction.CA: (
        "Trading in Forex and CFDs is risky and may not be suitable for all "
        "investors. You could lose more than your initial deposit. This "
        "service is provided in compliance with Canadian securities regulations."
    ),
    Jurisdiction.BR: (
        "A negociação de Forex e CFDs envolve riscos significativos e pode "
        "resultar na perda de seu capital investido. Este produto pode não "
        "ser adequado para todos os investidores. Consulte a regulamentação "
        "da CVM para mais informações."
    ),
}

STRATEGY_RISK_WARNINGS: dict[str, str] = {
    "trend_following": (
        "Trend-following strategies perform best in trending markets and may "
        "experience significant drawdowns during ranging or choppy market "
        "conditions. Whipsaws in sideways markets can generate multiple "
        "consecutive losing trades."
    ),
    "mean_reversion": (
        "Mean reversion strategies assume prices will return to their average. "
        "During strong trends, these strategies can experience extended losses "
        "as prices continue away from the mean. Use appropriate stop-losses."
    ),
    "scalping": (
        "Scalping strategies involve a high volume of trades with small profit "
        "targets. They are highly sensitive to spreads, slippage, and "
        "commission costs. Latency and execution quality significantly impact "
        "profitability."
    ),
    "breakout": (
        "Breakout strategies attempt to capture moves following key levels. "
        "False breakouts are common and can lead to losses. Consider volume "
        "confirmation and use proper risk management."
    ),
    "grid_trading": (
        "Grid trading involves placing multiple orders at predetermined levels. "
        "In strongly trending markets, grid strategies can accumulate large "
        "unrealized losses and may require significant margin. Grid trading "
        "carries a risk of total account loss in extreme moves."
    ),
    "sentiment_fade": (
        "Sentiment-fading strategies trade against prevailing market sentiment. "
        "These strategies require precise timing and can experience significant "
        "losses if sentiment does not reverse as expected."
    ),
}


class RiskDisclosureGenerator:
    """Generate risk disclosures for various contexts.

    Disclosures are versioned, jurisdiction-specific, and recorded in the
    database for compliance auditing.
    """

    def __init__(self) -> None:
        self._current_version = "1.0.0"

    async def generate_general_disclaimer(
        self,
        db: AsyncSession,
        jurisdiction: Jurisdiction | str = Jurisdiction.GLOBAL,
        language: str = "en",
        user_id: UUID | None = None,
    ) -> RiskDisclosure:
        """Generate a general risk disclaimer for the specified jurisdiction."""
        if isinstance(jurisdiction, str):
            jurisdiction = Jurisdiction(jurisdiction)

        jur_text = JURISDICTION_DISCLAIMERS.get(
            jurisdiction, JURISDICTION_DISCLAIMERS[Jurisdiction.GLOBAL]
        )

        content = (
            f"RISK DISCLAIMER\n"
            f"{'=' * 60}\n\n"
            f"Jurisdiction: {jurisdiction.value.upper()}\n"
            f"Version: {self._current_version}\n"
            f"Language: {language}\n"
            f"Generated: {datetime.now(timezone.utc).isoformat()}\n\n"
            f"{BASE_RISK_WARNING}\n\n"
            f"{LEVERAGE_WARNING}\n\n"
            f"{PAST_PERFORMANCE_WARNING}\n\n"
            f"{AUTOMATED_TRADING_WARNING}\n\n"
            f"{jur_text}\n\n"
            f"{'=' * 60}\n"
            f"By using this platform, you acknowledge that you have read, "
            f"understood, and accepted these risks."
        )

        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

        disclosure = RiskDisclosure(
            user_id=user_id,
            disclosure_type="general",
            jurisdiction=jurisdiction.value,
            content=content,
            content_hash=content_hash,
            version=self._current_version,
            language=language,
        )
        db.add(disclosure)
        await db.commit()
        await db.refresh(disclosure)

        # Audit
        await audit_service.record(
            db,
            user_id=user_id,
            action="compliance.disclosure.generated",
            resource_type="risk_disclosure",
            resource_id=str(disclosure.id),
            details={
                "disclosure_type": "general",
                "jurisdiction": jurisdiction.value,
                "version": self._current_version,
            },
            ip_address=None,
        )

        return disclosure

    async def generate_strategy_warning(
        self,
        db: AsyncSession,
        strategy_type: str,
        user_id: UUID | None = None,
        jurisdiction: Jurisdiction | str = Jurisdiction.GLOBAL,
    ) -> RiskDisclosure:
        """Generate a strategy-specific risk warning."""
        if isinstance(jurisdiction, str):
            jurisdiction = Jurisdiction(jurisdiction)

        strategy_warning = STRATEGY_RISK_WARNINGS.get(
            strategy_type,
            "This trading strategy carries financial risk. Ensure you "
            "understand the strategy mechanics before trading."
        )

        jur_text = JURISDICTION_DISCLAIMERS.get(
            jurisdiction, JURISDICTION_DISCLAIMERS[Jurisdiction.GLOBAL]
        )

        content = (
            f"STRATEGY-SPECIFIC RISK WARNING\n"
            f"{'=' * 60}\n\n"
            f"Strategy: {strategy_type}\n"
            f"Jurisdiction: {jurisdiction.value.upper()}\n"
            f"Version: {self._current_version}\n\n"
            f"{BASE_RISK_WARNING}\n\n"
            f"{strategy_warning}\n\n"
            f"{LEVERAGE_WARNING}\n\n"
            f"{PAST_PERFORMANCE_WARNING}\n\n"
            f"{jur_text}\n\n"
            f"{'=' * 60}\n"
            f"By activating this strategy, you acknowledge the specific "
            f"risks described above."
        )

        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

        disclosure = RiskDisclosure(
            user_id=user_id,
            disclosure_type=f"strategy_{strategy_type}",
            jurisdiction=jurisdiction.value,
            content=content,
            content_hash=content_hash,
            version=self._current_version,
            language="en",
        )
        db.add(disclosure)
        await db.commit()
        await db.refresh(disclosure)

        # Audit
        await audit_service.record(
            db,
            user_id=user_id,
            action="compliance.disclosure.strategy_warning",
            resource_type="risk_disclosure",
            resource_id=str(disclosure.id),
            details={
                "strategy_type": strategy_type,
                "jurisdiction": jurisdiction.value,
            },
            ip_address=None,
        )

        return disclosure

    async def generate_per_trade_acknowledgment(
        self,
        db: AsyncSession,
        user_id: UUID,
        order_id: UUID,
        symbol: str,
        side: str,
        quantity: float,
        leverage: float,
        jurisdiction: Jurisdiction | str = Jurisdiction.GLOBAL,
    ) -> RiskDisclosure:
        """Generate a per-trade risk acknowledgment.

        This is a specific acknowledgment the user must accept before
        a trade is executed in high-risk scenarios.
        """
        if isinstance(jurisdiction, str):
            jurisdiction = Jurisdiction(jurisdiction)

        jur_text = JURISDICTION_DISCLAIMERS.get(
            jurisdiction, JURISDICTION_DISCLAIMERS[Jurisdiction.GLOBAL]
        )

        notional_value = quantity * leverage
        content = (
            f"PER-TRADE RISK ACKNOWLEDGMENT\n"
            f"{'=' * 60}\n\n"
            f"Order ID: {order_id}\n"
            f"Symbol: {symbol}\n"
            f"Side: {side.upper()}\n"
            f"Quantity: {quantity}\n"
            f"Leverage: {leverage}:1\n"
            f"Notional Value: ${notional_value:,.2f}\n"
            f"Date: {datetime.now(timezone.utc).isoformat()}\n\n"
            f"{BASE_RISK_WARNING}\n\n"
            f"I acknowledge that this trade:\n"
            f"  1. Involves a notional exposure of ${notional_value:,.2f}\n"
            f"  2. May result in the loss of my entire investment\n"
            f"  3. Uses leverage of {leverage}:1, which amplifies both gains and losses\n"
            f"  4. Is executed through an automated trading system\n\n"
            f"{LEVERAGE_WARNING}\n\n"
            f"{jur_text}\n\n"
            f"{'=' * 60}\n"
            f"I ACKNOWLEDGE AND ACCEPT THESE RISKS."
        )

        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

        disclosure = RiskDisclosure(
            user_id=user_id,
            disclosure_type=f"per_trade_{order_id}",
            jurisdiction=jurisdiction.value,
            content=content,
            content_hash=content_hash,
            version=self._current_version,
            language="en",
        )
        db.add(disclosure)
        await db.commit()
        await db.refresh(disclosure)

        # Audit
        await audit_service.record(
            db,
            user_id=user_id,
            action="compliance.disclosure.per_trade",
            resource_type="risk_disclosure",
            resource_id=str(disclosure.id),
            details={
                "order_id": str(order_id),
                "symbol": symbol,
                "side": side,
                "quantity": quantity,
                "leverage": leverage,
            },
            ip_address=None,
        )

        return disclosure

    async def acknowledge_disclosure(
        self,
        db: AsyncSession,
        disclosure_id: UUID,
        user_id: UUID,
    ) -> RiskDisclosure | None:
        """Record user acknowledgment of a risk disclosure."""
        result = await db.execute(
            select(RiskDisclosure).where(
                RiskDisclosure.id == disclosure_id,
                RiskDisclosure.user_id == user_id,
            )
        )
        disclosure = result.scalars().first()
        if not disclosure:
            logger.warning(
                "Disclosure not found for acknowledgment",
                disclosure_id=str(disclosure_id),
                user_id=str(user_id),
            )
            return None

        disclosure.acknowledged = True
        disclosure.acknowledged_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(disclosure)

        # Audit
        await audit_service.record(
            db,
            user_id=user_id,
            action="compliance.disclosure.acknowledged",
            resource_type="risk_disclosure",
            resource_id=str(disclosure_id),
            details={
                "disclosure_type": disclosure.disclosure_type,
                "version": disclosure.version,
            },
            ip_address=None,
        )

        return disclosure

    async def get_user_disclosures(
        self,
        db: AsyncSession,
        user_id: UUID,
        acknowledged_only: bool = False,
    ) -> list[dict[str, Any]]:
        """Get all risk disclosures for a user."""
        query = select(RiskDisclosure).where(
            RiskDisclosure.user_id == user_id,
        ).order_by(RiskDisclosure.generated_at.desc())

        if acknowledged_only:
            query = query.where(RiskDisclosure.acknowledged.is_(True))

        result = await db.execute(query)
        disclosures = result.scalars().all()

        return [
            {
                "id": str(d.id),
                "disclosure_type": d.disclosure_type,
                "jurisdiction": d.jurisdiction,
                "version": d.version,
                "acknowledged": d.acknowledged,
                "acknowledged_at": d.acknowledged_at.isoformat() if d.acknowledged_at else None,
                "generated_at": d.generated_at.isoformat() if d.generated_at else None,
            }
            for d in disclosures
        ]

    def get_strategy_warning(self, strategy_type: str) -> str:
        """Get the warning text for a specific strategy type."""
        return STRATEGY_RISK_WARNINGS.get(
            strategy_type,
            "This trading strategy carries financial risk."
        )

    def get_jurisdiction_disclaimer(self, jurisdiction: Jurisdiction | str) -> str:
        """Get the jurisdiction-specific disclaimer text."""
        if isinstance(jurisdiction, str):
            try:
                jurisdiction = Jurisdiction(jurisdiction)
            except ValueError:
                jurisdiction = Jurisdiction.GLOBAL
        return JURISDICTION_DISCLAIMERS.get(
            jurisdiction, JURISDICTION_DISCLAIMERS[Jurisdiction.GLOBAL]
        )


# Global default risk disclosure generator
risk_disclosure_generator = RiskDisclosureGenerator()
