"""Add performance-optimized indexes.

Adds missing indexes identified during Phase 8 performance audit:
- ai_decisions: (symbol, decision_time) for common query pattern
- ai_decisions: (strategy_id) for strategy lookups
- positions: (broker_position_id) for reconciliation lookups
- orders: (broker_order_id) for broker reconciliation
- deals: (symbol, executed_at) for trade history queries
- risk_alerts: (category, created_at) for alert filtering
- risk_states: (broker_account_id) unique already exists, adding (is_circuit_breaker_active)
- event_outbox: (status, created_at) is covered, adding (event_type, status)
- Partial indexes for active/open status filters

Revision ID: 003_performance
Revises: 002_event_outbox
Create Date: 2024-07-14 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "003_performance"
down_revision: Union[str, None] = "002_event_outbox"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add performance indexes."""

    # AI Decisions indexes
    op.create_index(
        "idx_ai_decisions_symbol_time",
        "ai_decisions",
        ["symbol", "decision_time"],
        postgresql_using="btree",
    )
    op.create_index(
        "idx_ai_decisions_strategy_time",
        "ai_decisions",
        ["strategy_id", "decision_time"],
        postgresql_using="btree",
    )
    # Partial index: only non-executed decisions for pending analysis
    op.create_index(
        "idx_ai_decisions_pending",
        "ai_decisions",
        ["symbol", "decision_time"],
        postgresql_where=sa.text("was_executed = false"),
    )

    # Orders indexes
    op.create_index(
        "idx_orders_broker_order_id",
        "orders",
        ["broker_order_id"],
        postgresql_using="btree",
    )
    op.create_index(
        "idx_orders_status_created",
        "orders",
        ["status", "created_at"],
        postgresql_using="btree",
    )
    # Partial index: only active orders
    op.create_index(
        "idx_orders_active",
        "orders",
        ["broker_account_id", "created_at"],
        postgresql_where=sa.text("status IN ('pending', 'new', 'partially_filled')"),
    )

    # Positions indexes
    op.create_index(
        "idx_positions_broker_position_id",
        "positions",
        ["broker_position_id"],
        postgresql_using="btree",
    )
    op.create_index(
        "idx_positions_opened_at",
        "positions",
        ["broker_account_id", "opened_at"],
        postgresql_using="btree",
    )
    op.create_index(
        "idx_positions_updated_at",
        "positions",
        ["updated_at"],
        postgresql_using="btree",
    )

    # Deals indexes
    op.create_index(
        "idx_deals_symbol_executed",
        "deals",
        ["symbol", "executed_at"],
        postgresql_using="btree",
    )
    op.create_index(
        "idx_deals_position_executed",
        "deals",
        ["position_id", "executed_at"],
        postgresql_using="btree",
    )

    # Risk alerts indexes
    op.create_index(
        "idx_risk_alerts_category_time",
        "risk_alerts",
        ["category", "created_at"],
        postgresql_using="btree",
    )
    op.create_index(
        "idx_risk_alerts_acknowledged",
        "risk_alerts",
        ["acknowledged", "created_at"],
        postgresql_using="btree",
    )

    # Risk states index for circuit breaker scanning
    op.create_index(
        "idx_risk_states_circuit_breaker",
        "risk_states",
        ["is_circuit_breaker_active"],
        postgresql_where=sa.text("is_circuit_breaker_active = true"),
    )

    # Event outbox index for faster polling
    op.create_index(
        "idx_outbox_event_type_status",
        "event_outbox",
        ["event_type", "status"],
        postgresql_using="btree",
    )

    # Composite index for aggregate lookups
    op.create_index(
        "idx_outbox_aggregate",
        "event_outbox",
        ["aggregate_type", "aggregate_id", "status"],
        postgresql_using="btree",
    )

    # Agent performance indexes
    op.create_index(
        "idx_agent_performance_lookup",
        "agent_performance",
        ["agent_type", "symbol", "timeframe"],
        postgresql_using="btree",
    )

    # Audit logs index for common search patterns
    op.create_index(
        "idx_audit_logs_action_time",
        "audit_logs",
        ["action", "timestamp"],
        postgresql_using="btree",
    )

    # Notifications index for pending delivery
    op.create_index(
        "idx_notifications_pending",
        "notifications",
        ["channel", "sent", "priority"],
        postgresql_using="btree",
    )


def downgrade() -> None:
    """Remove performance indexes."""
    op.drop_index("idx_notifications_pending", table_name="notifications")
    op.drop_index("idx_audit_logs_action_time", table_name="audit_logs")
    op.drop_index("idx_agent_performance_lookup", table_name="agent_performance")
    op.drop_index("idx_outbox_aggregate", table_name="event_outbox")
    op.drop_index("idx_outbox_event_type_status", table_name="event_outbox")
    op.drop_index("idx_risk_states_circuit_breaker", table_name="risk_states")
    op.drop_index("idx_risk_alerts_acknowledged", table_name="risk_alerts")
    op.drop_index("idx_risk_alerts_category_time", table_name="risk_alerts")
    op.drop_index("idx_deals_position_executed", table_name="deals")
    op.drop_index("idx_deals_symbol_executed", table_name="deals")
    op.drop_index("idx_positions_updated_at", table_name="positions")
    op.drop_index("idx_positions_opened_at", table_name="positions")
    op.drop_index("idx_positions_broker_position_id", table_name="positions")
    op.drop_index("idx_orders_active", table_name="orders")
    op.drop_index("idx_orders_status_created", table_name="orders")
    op.drop_index("idx_orders_broker_order_id", table_name="orders")
    op.drop_index("idx_ai_decisions_pending", table_name="ai_decisions")
    op.drop_index("idx_ai_decisions_strategy_time", table_name="ai_decisions")
    op.drop_index("idx_ai_decisions_symbol_time", table_name="ai_decisions")
