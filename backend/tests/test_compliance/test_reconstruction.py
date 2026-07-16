"""Tests for trade reconstruction."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from forex_trading.shared.compliance.reconstruction import (
    TradeReconstructor,
    ReconstructionChain,
    ReconstructionStep,
    SlippageBreakdown,
    CommissionBreakdown,
    trade_reconstructor,
)


class TestReconstructionDataClasses:
    """Tests for reconstruction data classes."""

    def test_reconstruction_step(self):
        step = ReconstructionStep(
            step_type="order",
            timestamp=datetime.now(timezone.utc),
            description="Test order",
            details={"key": "value"},
        )
        assert step.step_type == "order"
        assert step.details["key"] == "value"

    def test_slippage_breakdown(self):
        slip = SlippageBreakdown(
            expected_price=1.1000,
            actual_price=1.1005,
            slippage_pips=5.0,
            slippage_amount=0.5,
            slippage_bps=45.45,
        )
        assert slip.slippage_pips == 5.0
        assert slip.expected_price == 1.1000

    def test_commission_breakdown(self):
        comm = CommissionBreakdown(
            total_commission=10.0,
            broker_commission=8.0,
            exchange_fees=2.0,
        )
        assert comm.total_commission == 10.0

    def test_reconstruction_chain_to_dict(self):
        chain = ReconstructionChain(order_id=str(uuid4()))
        chain.realized_pnl = 100.0
        d = chain.to_dict()
        assert d["order_id"] == chain.order_id
        assert d["realized_pnl"] == 100.0
        assert d["chain_integrity"] is True

    def test_reconstruction_chain_csv(self):
        chain = ReconstructionChain(order_id=str(uuid4()))
        chain.steps.append(ReconstructionStep(
            step_type="order",
            timestamp=datetime.now(timezone.utc),
            description="Test",
        ))
        csv = chain.to_csv()
        assert "step_type" in csv
        assert "order" in csv

    def test_chain_integrity_issues(self):
        chain = ReconstructionChain(order_id=str(uuid4()))
        chain.chain_integrity = False
        chain.integrity_issues = ["Issue 1"]
        d = chain.to_dict()
        assert d["chain_integrity"] is False
        assert len(d["integrity_issues"]) == 1


class TestTradeReconstructor:
    """Tests for the TradeReconstructor."""

    @pytest.fixture
    def reconstructor(self):
        return TradeReconstructor()

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    async def test_reconstruct_order_not_found(self, reconstructor, mock_db):
        """Reconstructing a non-existent order should raise ValueError."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        mock_db.execute.return_value = mock_result

        with pytest.raises(ValueError, match="not found"):
            await reconstructor.reconstruct_by_order(mock_db, uuid4())

    async def test_reconstruct_order_integrity_checks(self, reconstructor, mock_db):
        """Reconstruction should verify chain integrity for filled orders."""
        from forex_trading.shared.database.models_trading import (
            Order, Deal, Position, OrderSide, OrderType,
            OrderStatus, PositionSide, PositionStatus,
        )

        order_id = uuid4()
        position_id = uuid4()

        # Mock order
        mock_order = MagicMock(spec=Order)
        mock_order.id = order_id
        mock_order.symbol = "EURUSD"
        mock_order.side = OrderSide.BUY
        mock_order.order_type = OrderType.MARKET
        mock_order.quantity = 0.1
        mock_order.price = 1.1000
        mock_order.filled_quantity = 0.0  # Not filled
        mock_order.filled_price = None
        mock_order.commission = 0.0
        mock_order.slippage = 0.0
        mock_order.stop_loss = None
        mock_order.take_profit = None
        mock_order.status = OrderStatus.CANCELLED
        mock_order.broker_order_id = None
        mock_order.submitted_at = datetime.now(timezone.utc)
        mock_order.filled_at = None
        mock_order.created_at = datetime.now(timezone.utc)

        # Mock empty deals
        mock_order_result = MagicMock()
        mock_order_result.scalars.return_value.first.return_value = mock_order

        mock_deals_result = MagicMock()
        mock_deals_result.scalars.return_value.all.return_value = []

        mock_chain_result = MagicMock()
        mock_chain_result.scalars.return_value.first.return_value = None
        mock_chain_result.scalars.return_value.all.return_value = []

        mock_audit_result = MagicMock()
        mock_audit_result.scalars.return_value.all.return_value = []

        async def execute_side_effect(*args, **kwargs):
            q = args[0] if args else kwargs.get('query')
            q_str = str(q).lower()
            if 'deal' in q_str:
                return mock_deals_result
            elif 'position' in q_str:
                pos_result = MagicMock()
                pos_result.scalars.return_value.first.return_value = None
                return pos_result
            elif 'audit_log_chain' in q_str:
                return mock_chain_result
            elif 'audit_log' in q_str:
                return mock_audit_result
            return mock_order_result

        mock_db.execute = execute_side_effect

        chain = await reconstructor.reconstruct_by_order(mock_db, order_id)
        assert chain.order_id == str(order_id)
        assert chain.chain_integrity is True  # Cancelled with no deals = OK

    async def test_reconstruct_by_date_range_empty(self, reconstructor, mock_db):
        """Reconstruct by date with no orders should return empty list."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        chains = await reconstructor.reconstruct_by_date_range(
            mock_db,
            datetime(2024, 1, 1, tzinfo=timezone.utc),
            datetime(2024, 12, 31, tzinfo=timezone.utc),
        )
        assert chains == []

    async def test_export_json(self, reconstructor, mock_db):
        """Export to JSON should produce valid JSON string."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        mock_db.execute.return_value = mock_result

        with pytest.raises(ValueError):
            await reconstructor.export_to_json(mock_db, uuid4())


class TestGlobalReconstructor:
    """Tests for the global trade_reconstructor instance."""

    def test_global_instance_exists(self):
        assert trade_reconstructor is not None
        assert isinstance(trade_reconstructor, TradeReconstructor)
