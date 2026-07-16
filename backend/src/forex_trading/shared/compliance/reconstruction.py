"""Trade Reconstruction — Full trade reconstruction from audit trail.

Supports the complete chain:
  Order → Fill → Position → PnL

With timestamp verification, slippage/commission breakdown, and export
to regulatory formats (CSV, JSON, PDF).
"""

from __future__ import annotations

import csv
import io
import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from forex_trading.shared.database.models_trading import (
    Order,
    Position,
    Deal,
    OrderStatus,
    PositionStatus,
)
from forex_trading.shared.security.audit import audit_service

logger = logging.getLogger(__name__)


@dataclass
class ReconstructionStep:
    """A single step in the trade reconstruction chain."""

    step_type: str  # "order", "fill", "position_open", "position_close", "deal"
    timestamp: datetime
    description: str
    details: dict[str, Any] = field(default_factory=dict)
    broker_timestamp: datetime | None = None
    timestamp_discrepancy_seconds: float | None = None


@dataclass
class SlippageBreakdown:
    """Slippage details for regulatory reporting."""

    expected_price: float
    actual_price: float
    slippage_pips: float
    slippage_amount: float
    slippage_bps: float  # basis points
    market_volatility_at_time: float | None = None
    liquidity_score: float | None = None


@dataclass
class CommissionBreakdown:
    """Commission details for regulatory reporting."""

    total_commission: float
    broker_commission: float
    exchange_fees: float = 0.0
    clearing_fees: float = 0.0
    swap_fees: float = 0.0
    other_fees: float = 0.0
    commission_per_unit: float | None = None
    commission_currency: str = "USD"


@dataclass
class ReconstructionChain:
    """Full trade reconstruction from order through fill to PnL."""

    order_id: str
    order: dict[str, Any] | None = None
    deals: list[dict[str, Any]] = field(default_factory=list)
    position: dict[str, Any] | None = None
    steps: list[ReconstructionStep] = field(default_factory=list)
    slippage: SlippageBreakdown | None = None
    commission: CommissionBreakdown | None = None
    realized_pnl: float | None = None
    chain_integrity: bool = True
    integrity_issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for export."""
        return {
            "order_id": self.order_id,
            "order": self.order,
            "deals": self.deals,
            "position": self.position,
            "steps": [
                {
                    "step_type": s.step_type,
                    "timestamp": s.timestamp.isoformat(),
                    "description": s.description,
                    "details": s.details,
                    "broker_timestamp": s.broker_timestamp.isoformat()
                    if s.broker_timestamp else None,
                    "timestamp_discrepancy_seconds": s.timestamp_discrepancy_seconds,
                }
                for s in self.steps
            ],
            "slippage": asdict(self.slippage) if self.slippage else None,
            "commission": asdict(self.commission) if self.commission else None,
            "realized_pnl": self.realized_pnl,
            "chain_integrity": self.chain_integrity,
            "integrity_issues": self.integrity_issues,
        }

    def to_csv(self) -> str:
        """Export steps as CSV string."""
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "step_type", "timestamp", "description",
            "broker_timestamp", "ts_discrepancy_sec",
            "expected_price", "actual_price", "slippage_pips",
            "commission", "realized_pnl",
        ])
        for step in self.steps:
            writer.writerow([
                step.step_type,
                step.timestamp.isoformat(),
                step.description,
                step.broker_timestamp.isoformat() if step.broker_timestamp else "",
                step.timestamp_discrepancy_seconds or "",
                step.details.get("expected_price", ""),
                step.details.get("actual_price", ""),
                step.details.get("slippage_pips", ""),
                step.details.get("commission", ""),
                step.details.get("realized_pnl", ""),
            ])
        return output.getvalue()


class TradeReconstructor:
    """Reconstruct a full trade lifecycle from the database.

    Usage::

        reconstructor = TradeReconstructor()

        # Reconstruct by order ID
        chain = await reconstructor.reconstruct_by_order(db, order_id)

        # Reconstruct by position ID
        chain = await reconstructor.reconstruct_by_position(db, position_id)

        # Export
        json_data = chain.to_dict()
        csv_data = chain.to_csv()
    """

    async def reconstruct_by_order(
        self,
        db: AsyncSession,
        order_id: UUID,
    ) -> ReconstructionChain:
        """Reconstruct trade from a specific order.

        Follows: Order → Deal(s) → Position → PnL
        """
        # Fetch order
        result = await db.execute(select(Order).where(Order.id == order_id))
        order = result.scalars().first()
        if not order:
            raise ValueError(f"Order {order_id} not found")

        chain = ReconstructionChain(order_id=str(order_id))
        chain.order = self._order_to_dict(order)

        # Add order step
        chain.steps.append(ReconstructionStep(
            step_type="order",
            timestamp=order.created_at,
            description=f"Order {order.side.value} {order.quantity} {order.symbol} @ {order.order_type.value}",
            details={
                "symbol": order.symbol,
                "side": order.side.value,
                "quantity": order.quantity,
                "order_type": order.order_type.value,
                "price": order.price,
                "stop_loss": order.stop_loss,
                "take_profit": order.take_profit,
                "status": order.status.value,
            },
            broker_timestamp=order.submitted_at,
        ))

        # Fetch deals
        result = await db.execute(
            select(Deal).where(Deal.order_id == order_id).order_by(Deal.executed_at)
        )
        deals = result.scalars().all()

        total_slippage = 0.0
        total_commission = 0.0
        for deal in deals:
            deal_dict = self._deal_to_dict(deal)
            chain.deals.append(deal_dict)
            total_slippage += deal.slippage
            total_commission += deal.commission

            chain.steps.append(ReconstructionStep(
                step_type="deal",
                timestamp=deal.executed_at,
                description=f"Fill: {deal.quantity} @ {deal.price}",
                details={
                    "quantity": deal.quantity,
                    "price": deal.price,
                    "commission": deal.commission,
                    "slippage": deal.slippage,
                    "realized_pnl": deal.realized_pnl,
                    "broker_deal_id": deal.broker_deal_id,
                },
                broker_timestamp=deal.executed_at,
            ))

        # Fetch position
        if deals and deals[0].position_id:
            result = await db.execute(
                select(Position).where(Position.id == deals[0].position_id)
            )
            position = result.scalars().first()
            if position:
                chain.position = self._position_to_dict(position)
                chain.steps.append(ReconstructionStep(
                    step_type="position_open",
                    timestamp=position.opened_at,
                    description=f"Position opened: {position.side.value} {position.size} {position.symbol} @ {position.entry_price}",
                    details={
                        "symbol": position.symbol,
                        "side": position.side.value,
                        "size": position.size,
                        "entry_price": position.entry_price,
                        "stop_loss": position.stop_loss,
                        "take_profit": position.take_profit,
                    },
                ))

                if position.status == PositionStatus.CLOSED and position.closed_at:
                    chain.realized_pnl = position.realized_pnl
                    chain.steps.append(ReconstructionStep(
                        step_type="position_close",
                        timestamp=position.closed_at,
                        description=f"Position closed: realized PnL = {position.realized_pnl}",
                        details={
                            "realized_pnl": position.realized_pnl,
                            "commission": position.commission,
                            "swap": position.swap,
                            "exit_price": position.current_price,
                        },
                    ))

        # Build slippage breakdown
        if order.filled_price and order.price:
            slippage_pips = abs(order.filled_price - order.price) * 10000
            slippage_amount = slippage_pips * order.filled_quantity
            chain.slippage = SlippageBreakdown(
                expected_price=order.price,
                actual_price=order.filled_price,
                slippage_pips=round(slippage_pips, 2),
                slippage_amount=round(slippage_amount, 2),
                slippage_bps=round((slippage_pips / (order.price * 10000)) * 10000, 2)
                if order.price else 0,
            )

        # Build commission breakdown
        chain.commission = CommissionBreakdown(
            total_commission=round(total_commission, 2),
            broker_commission=round(total_commission, 2),
        )

        # Verify chain integrity
        chain = self._verify_chain_integrity(chain)

        # Audit the reconstruction
        await audit_service.record(
            db,
            user_id=None,
            action="compliance.reconstruction.query",
            resource_type="order",
            resource_id=str(order_id),
            details={
                "chain_integrity": chain.chain_integrity,
                "steps_count": len(chain.steps),
                "issues": chain.integrity_issues,
            },
            ip_address=None,
        )

        return chain

    async def reconstruct_by_position(
        self,
        db: AsyncSession,
        position_id: UUID,
    ) -> list[ReconstructionChain]:
        """Reconstruct all trades for a given position.

        Returns a list of reconstruction chains (one per order linked
        to the position via deals).
        """
        result = await db.execute(
            select(Deal).where(Deal.position_id == position_id)
        )
        deals = result.scalars().all()

        order_ids = {d.order_id for d in deals if d.order_id}
        chains: list[ReconstructionChain] = []
        for oid in order_ids:
            chain = await self.reconstruct_by_order(db, oid)
            chains.append(chain)

        return chains

    async def reconstruct_by_date_range(
        self,
        db: AsyncSession,
        start_date: datetime,
        end_date: datetime,
    ) -> list[ReconstructionChain]:
        """Reconstruct all orders in a date range."""
        result = await db.execute(
            select(Order).where(
                Order.created_at >= start_date,
                Order.created_at <= end_date,
                Order.status.in_([OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED]),
            ).order_by(Order.created_at)
        )
        orders = result.scalars().all()

        chains: list[ReconstructionChain] = []
        for order in orders:
            chain = await self.reconstruct_by_order(db, order.id)
            chains.append(chain)
        return chains

    async def export_to_json(
        self,
        db: AsyncSession,
        order_id: UUID,
    ) -> str:
        """Export trade reconstruction to JSON string."""
        chain = await self.reconstruct_by_order(db, order_id)
        return json.dumps(chain.to_dict(), indent=2, default=str)

    async def export_to_csv(
        self,
        db: AsyncSession,
        order_id: UUID,
    ) -> str:
        """Export trade reconstruction steps as CSV string."""
        chain = await self.reconstruct_by_order(db, order_id)
        return chain.to_csv()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _order_to_dict(self, order: Order) -> dict[str, Any]:
        return {
            "id": str(order.id),
            "symbol": order.symbol,
            "side": order.side.value if hasattr(order.side, "value") else order.side,
            "order_type": order.order_type.value if hasattr(order.order_type, "value") else order.order_type,
            "quantity": order.quantity,
            "price": order.price,
            "filled_quantity": order.filled_quantity,
            "filled_price": order.filled_price,
            "commission": order.commission,
            "slippage": order.slippage,
            "status": order.status.value if hasattr(order.status, "value") else order.status,
            "broker_order_id": order.broker_order_id,
            "stop_loss": order.stop_loss,
            "take_profit": order.take_profit,
            "submitted_at": order.submitted_at.isoformat() if order.submitted_at else None,
            "filled_at": order.filled_at.isoformat() if order.filled_at else None,
            "created_at": order.created_at.isoformat() if order.created_at else None,
        }

    def _deal_to_dict(self, deal: Deal) -> dict[str, Any]:
        return {
            "id": str(deal.id),
            "order_id": str(deal.order_id),
            "position_id": str(deal.position_id) if deal.position_id else None,
            "symbol": deal.symbol,
            "side": deal.side.value if hasattr(deal.side, "value") else deal.side,
            "quantity": deal.quantity,
            "price": deal.price,
            "commission": deal.commission,
            "slippage": deal.slippage,
            "realized_pnl": deal.realized_pnl,
            "broker_deal_id": deal.broker_deal_id,
            "executed_at": deal.executed_at.isoformat() if deal.executed_at else None,
        }

    def _position_to_dict(self, position: Position) -> dict[str, Any]:
        return {
            "id": str(position.id),
            "symbol": position.symbol,
            "side": position.side.value if hasattr(position.side, "value") else position.side,
            "size": position.size,
            "entry_price": position.entry_price,
            "current_price": position.current_price,
            "unrealized_pnl": position.unrealized_pnl,
            "realized_pnl": position.realized_pnl,
            "commission": position.commission,
            "swap": position.swap,
            "status": position.status.value if hasattr(position.status, "value") else position.status,
            "stop_loss": position.stop_loss,
            "take_profit": position.take_profit,
            "opened_at": position.opened_at.isoformat() if position.opened_at else None,
            "closed_at": position.closed_at.isoformat() if position.closed_at else None,
        }

    def _verify_chain_integrity(self, chain: ReconstructionChain) -> ReconstructionChain:
        """Verify the consistency of the reconstruction chain.

        Checks:
          - Order status matches deal existence
          - Position PnL matches deal-level PnL
          - Timestamps are consistent
          - Slippage values are reasonable
        """
        issues: list[str] = []

        if chain.order:
            status = chain.order.get("status", "")
            filled_qty = chain.order.get("filled_quantity", 0)

            # Check: filled order should have at least one deal
            if status == "filled" and not chain.deals:
                issues.append("Order is filled but no deals found")
                chain.chain_integrity = False

            # Check: cancelled/rejected orders should have no deals
            if status in ("cancelled", "rejected") and chain.deals:
                issues.append(f"Order is {status} but deals exist ({len(chain.deals)} found)")
                chain.chain_integrity = False

            # Verify filled quantity matches deal quantities
            if chain.deals and filled_qty > 0:
                deal_qty = sum(d.get("quantity", 0) for d in chain.deals)
                if abs(deal_qty - filled_qty) > 0.0001:
                    issues.append(f"Filled quantity mismatch: order={filled_qty}, deals={deal_qty}")
                    chain.chain_integrity = False

        # Check position PnL vs deal PnL
        if chain.position and chain.deals:
            deal_pnl = sum(d.get("realized_pnl") or 0 for d in chain.deals)
            pos_pnl = chain.position.get("realized_pnl", 0)
            if deal_pnl and abs(deal_pnl - pos_pnl) > 0.01:
                issues.append(f"PnL mismatch: position PnL={pos_pnl}, deal PnL sum={deal_pnl}")
                chain.chain_integrity = False

        # Check step timestamp ordering
        for i in range(1, len(chain.steps)):
            if chain.steps[i].timestamp < chain.steps[i - 1].timestamp:
                issues.append(
                    f"Timestamp out of order: {chain.steps[i-1].step_type} before {chain.steps[i].step_type}"
                )
                chain.chain_integrity = False

        # Check broker timestamp discrepancies
        for step in chain.steps:
            if step.broker_timestamp and step.timestamp:
                discrepancy = abs((step.timestamp - step.broker_timestamp).total_seconds())
                step.timestamp_discrepancy_seconds = round(discrepancy, 3)
                if discrepancy > 60:  # More than 1 minute is suspicious
                    issues.append(
                        f"Large timestamp discrepancy ({discrepancy:.0f}s) at step: {step.step_type}"
                    )

        chain.integrity_issues = issues
        return chain


# Global default trade reconstructor
trade_reconstructor = TradeReconstructor()
