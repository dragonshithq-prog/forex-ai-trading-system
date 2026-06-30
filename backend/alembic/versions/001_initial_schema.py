"""Initial database schema.

Revision ID: 001_initial
Revises:
Create Date: 2024-01-01 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create initial schema."""

    # Enum types
    user_role = postgresql.ENUM('viewer', 'trader', 'admin', 'superadmin', name='userrole', create_type=False)
    broker_type = postgresql.ENUM('mt4', 'mt5', 'oanda', 'fxcm', 'ctrader', 'ibkr', name='brokertype', create_type=False)
    connection_status = postgresql.ENUM('disconnected', 'connecting', 'connected', 'error', name='connectionstatus', create_type=False)
    order_side = postgresql.ENUM('buy', 'sell', name='orderside', create_type=False)
    order_type = postgresql.ENUM('market', 'limit', 'stop', 'stop_limit', 'trailing_stop', name='ordertype', create_type=False)
    order_status = postgresql.ENUM('pending', 'new', 'filled', 'partially_filled', 'cancelled', 'rejected', 'expired', name='orderstatus', create_type=False)
    time_in_force = postgresql.ENUM('gtc', 'ioc', 'fok', 'day', name='timeinforce', create_type=False)
    position_side = postgresql.ENUM('long', 'short', name='positionside', create_type=False)
    position_status = postgresql.ENUM('open', 'closed', 'partially_closed', name='positionstatus', create_type=False)
    strategy_type = postgresql.ENUM('trend_following', 'mean_reversion', 'scalping', 'breakout', 'grid_trading', 'sentiment_fade', name='strategytype', create_type=False)
    strategy_status = postgresql.ENUM('active', 'paused', 'disabled', name='strategystatus', create_type=False)
    agent_type = postgresql.ENUM('structure', 'trend', 'momentum', 'liquidity', 'sentiment', 'volatility', 'correlation', name='agenttype', create_type=False)
    signal_direction = postgresql.ENUM('long', 'short', 'neutral', name='signaldirection', create_type=False)
    risk_level = postgresql.ENUM('info', 'warning', 'critical', name='risklevel', create_type=False)
    override_action = postgresql.ENUM('reject_order', 'close_position', 'reduce_size', 'halt_trading', 'emergency_liquidate', name='overrideaction', create_type=False)
    notification_channel = postgresql.ENUM('email', 'slack', 'telegram', 'webhook', name='notificationchannel', create_type=False)
    notification_priority = postgresql.ENUM('low', 'medium', 'high', 'critical', name='notificationpriority', create_type=False)

    # Create enums
    for enum in [user_role, broker_type, connection_status, order_side, order_type,
                 order_status, time_in_force, position_side, position_status,
                 strategy_type, strategy_status, agent_type, signal_direction,
                 risk_level, override_action, notification_channel, notification_priority]:
        enum.create(op.get_bind(), checkfirst=True)

    # Users table
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('email', sa.String(255), unique=True, nullable=False, index=True),
        sa.Column('username', sa.String(100), unique=True, nullable=False, index=True),
        sa.Column('hashed_password', sa.String(255), nullable=False),
        sa.Column('full_name', sa.String(255), nullable=True),
        sa.Column('role', user_role, nullable=False, server_default='viewer'),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('is_verified', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('mfa_enabled', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('mfa_secret', sa.String(255), nullable=True),
        sa.Column('last_login', sa.DateTime(timezone=True), nullable=True),
        sa.Column('preferences', postgresql.JSONB, nullable=True),
        sa.Column('is_deleted', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # User Sessions table
    op.create_table(
        'user_sessions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('refresh_token', sa.String(500), nullable=False, unique=True),
        sa.Column('user_agent', sa.String(500), nullable=True),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('is_revoked', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Audit Logs table
    op.create_table(
        'audit_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True),
        sa.Column('action', sa.String(100), nullable=False, index=True),
        sa.Column('resource_type', sa.String(100), nullable=False),
        sa.Column('resource_id', sa.String(100), nullable=True),
        sa.Column('details', postgresql.JSONB, nullable=True),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Broker Accounts table
    op.create_table(
        'broker_accounts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('broker_type', broker_type, nullable=False),
        sa.Column('account_name', sa.String(255), nullable=False),
        sa.Column('account_number', sa.String(100), nullable=False),
        sa.Column('environment', sa.String(50), nullable=False, server_default='practice'),
        sa.Column('currency', sa.String(3), nullable=False, server_default='USD'),
        sa.Column('leverage', sa.Integer, nullable=False, server_default='100'),
        sa.Column('credentials_encrypted', sa.Text, nullable=True),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('last_sync', sa.DateTime(timezone=True), nullable=True),
        sa.Column('balance', sa.Float, nullable=False, server_default='0'),
        sa.Column('equity', sa.Float, nullable=False, server_default='0'),
        sa.Column('margin', sa.Float, nullable=False, server_default='0'),
        sa.Column('free_margin', sa.Float, nullable=False, server_default='0'),
        sa.Column('unrealized_pnl', sa.Float, nullable=False, server_default='0'),
        sa.Column('metadata', postgresql.JSONB, nullable=True),
        sa.Column('is_deleted', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Broker Connections table
    op.create_table(
        'broker_connections',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('account_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('broker_accounts.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('status', connection_status, nullable=False, server_default='disconnected'),
        sa.Column('connected_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('disconnected_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_heartbeat', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error_message', sa.Text, nullable=True),
        sa.Column('connection_info', postgresql.JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Strategies table
    op.create_table(
        'strategies',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(100), unique=True, nullable=False),
        sa.Column('strategy_type', strategy_type, nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('status', strategy_status, nullable=False, server_default='active'),
        sa.Column('parameters', postgresql.JSONB, nullable=False, server_default='{}'),
        sa.Column('symbols', postgresql.JSONB, nullable=False, server_default='[]'),
        sa.Column('timeframes', postgresql.JSONB, nullable=False, server_default='[]'),
        sa.Column('max_position_size_pct', sa.Float, nullable=False, server_default='2'),
        sa.Column('risk_per_trade_pct', sa.Float, nullable=False, server_default='1'),
        sa.Column('total_trades', sa.Integer, nullable=False, server_default='0'),
        sa.Column('winning_trades', sa.Integer, nullable=False, server_default='0'),
        sa.Column('total_pnl', sa.Float, nullable=False, server_default='0'),
        sa.Column('is_deleted', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # AI Decisions table
    op.create_table(
        'ai_decisions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('strategy_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('strategies.id', ondelete='SET NULL'), nullable=True),
        sa.Column('symbol', sa.String(20), nullable=False, index=True),
        sa.Column('timeframe', sa.String(10), nullable=False),
        sa.Column('direction', signal_direction, nullable=False),
        sa.Column('confidence', sa.Float, nullable=False),
        sa.Column('agreement_ratio', sa.Float, nullable=False),
        sa.Column('conflict_ratio', sa.Float, nullable=False),
        sa.Column('agents_responding', sa.Integer, nullable=False),
        sa.Column('total_agents', sa.Integer, nullable=False),
        sa.Column('was_rejected', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('rejection_reason', sa.Text, nullable=True),
        sa.Column('market_regime', sa.String(50), nullable=True),
        sa.Column('session', sa.String(50), nullable=True),
        sa.Column('price_at_decision', sa.Float, nullable=True),
        sa.Column('agent_signals', postgresql.JSONB, nullable=False, server_default='{}'),
        sa.Column('rationale', sa.Text, nullable=True),
        sa.Column('was_executed', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('outcome_pnl', sa.Float, nullable=True),
        sa.Column('decision_time', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Agent Performance table
    op.create_table(
        'agent_performance',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('agent_type', agent_type, nullable=False, index=True),
        sa.Column('symbol', sa.String(20), nullable=False),
        sa.Column('timeframe', sa.String(10), nullable=False),
        sa.Column('total_signals', sa.Integer, nullable=False, server_default='0'),
        sa.Column('correct_signals', sa.Integer, nullable=False, server_default='0'),
        sa.Column('avg_confidence', sa.Float, nullable=False, server_default='0'),
        sa.Column('period_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('period_end', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Orders table
    op.create_table(
        'orders',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('broker_account_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('broker_accounts.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('signal_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('ai_decisions.id', ondelete='SET NULL'), nullable=True),
        sa.Column('strategy_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('strategies.id', ondelete='SET NULL'), nullable=True),
        sa.Column('symbol', sa.String(20), nullable=False),
        sa.Column('side', order_side, nullable=False),
        sa.Column('order_type', order_type, nullable=False),
        sa.Column('quantity', sa.Float, nullable=False),
        sa.Column('price', sa.Float, nullable=True),
        sa.Column('stop_price', sa.Float, nullable=True),
        sa.Column('take_profit', sa.Float, nullable=True),
        sa.Column('stop_loss', sa.Float, nullable=True),
        sa.Column('time_in_force', time_in_force, nullable=False, server_default='gtc'),
        sa.Column('status', order_status, nullable=False, server_default='pending'),
        sa.Column('filled_quantity', sa.Float, nullable=False, server_default='0'),
        sa.Column('filled_price', sa.Float, nullable=True),
        sa.Column('commission', sa.Float, nullable=False, server_default='0'),
        sa.Column('slippage', sa.Float, nullable=False, server_default='0'),
        sa.Column('broker_order_id', sa.String(100), nullable=True),
        sa.Column('broker_status', sa.String(50), nullable=True),
        sa.Column('rejection_reason', sa.Text, nullable=True),
        sa.Column('metadata', postgresql.JSONB, nullable=True),
        sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('filled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('idx_orders_symbol_status', 'orders', ['symbol', 'status'])
    op.create_index('idx_orders_broker_account_created', 'orders', ['broker_account_id', 'created_at'])

    # Positions table
    op.create_table(
        'positions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('broker_account_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('broker_accounts.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('strategy_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('strategies.id', ondelete='SET NULL'), nullable=True),
        sa.Column('symbol', sa.String(20), nullable=False),
        sa.Column('side', position_side, nullable=False),
        sa.Column('size', sa.Float, nullable=False),
        sa.Column('entry_price', sa.Float, nullable=False),
        sa.Column('current_price', sa.Float, nullable=False),
        sa.Column('unrealized_pnl', sa.Float, nullable=False, server_default='0'),
        sa.Column('realized_pnl', sa.Float, nullable=False, server_default='0'),
        sa.Column('stop_loss', sa.Float, nullable=True),
        sa.Column('take_profit', sa.Float, nullable=True),
        sa.Column('trailing_stop', sa.Float, nullable=True),
        sa.Column('status', position_status, nullable=False, server_default='open'),
        sa.Column('broker_position_id', sa.String(100), nullable=True),
        sa.Column('commission', sa.Float, nullable=False, server_default='0'),
        sa.Column('swap', sa.Float, nullable=False, server_default='0'),
        sa.Column('opened_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('metadata', postgresql.JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('idx_positions_symbol_status', 'positions', ['symbol', 'status'])
    op.create_index('idx_positions_broker_account_status', 'positions', ['broker_account_id', 'status'])

    # Deals table
    op.create_table(
        'deals',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('order_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('orders.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('position_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('positions.id', ondelete='SET NULL'), nullable=True),
        sa.Column('symbol', sa.String(20), nullable=False),
        sa.Column('side', order_side, nullable=False),
        sa.Column('quantity', sa.Float, nullable=False),
        sa.Column('price', sa.Float, nullable=False),
        sa.Column('commission', sa.Float, nullable=False, server_default='0'),
        sa.Column('slippage', sa.Float, nullable=False, server_default='0'),
        sa.Column('realized_pnl', sa.Float, nullable=True),
        sa.Column('broker_deal_id', sa.String(100), nullable=True),
        sa.Column('executed_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Risk Configurations table
    op.create_table(
        'risk_configurations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('broker_account_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('broker_accounts.id', ondelete='CASCADE'), nullable=True, index=True),
        sa.Column('max_position_size_pct', sa.Float, nullable=False, server_default='2'),
        sa.Column('max_total_exposure_pct', sa.Float, nullable=False, server_default='20'),
        sa.Column('max_positions', sa.Integer, nullable=False, server_default='10'),
        sa.Column('daily_drawdown_limit_pct', sa.Float, nullable=False, server_default='3'),
        sa.Column('weekly_drawdown_limit_pct', sa.Float, nullable=False, server_default='5'),
        sa.Column('monthly_drawdown_limit_pct', sa.Float, nullable=False, server_default='10'),
        sa.Column('max_drawdown_limit_pct', sa.Float, nullable=False, server_default='15'),
        sa.Column('max_exposure_per_pair_pct', sa.Float, nullable=False, server_default='5'),
        sa.Column('max_correlated_exposure_pct', sa.Float, nullable=False, server_default='10'),
        sa.Column('max_slippage_pips', sa.Float, nullable=False, server_default='3'),
        sa.Column('max_spread_pips', sa.Float, nullable=False, server_default='5'),
        sa.Column('max_consecutive_losses', sa.Integer, nullable=False, server_default='5'),
        sa.Column('cooldown_minutes', sa.Integer, nullable=False, server_default='60'),
        sa.Column('risk_per_trade_pct', sa.Float, nullable=False, server_default='1'),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Risk States table
    op.create_table(
        'risk_states',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('broker_account_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('broker_accounts.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('current_equity', sa.Float, nullable=False, server_default='0'),
        sa.Column('peak_equity', sa.Float, nullable=False, server_default='0'),
        sa.Column('current_drawdown_pct', sa.Float, nullable=False, server_default='0'),
        sa.Column('max_drawdown_pct', sa.Float, nullable=False, server_default='0'),
        sa.Column('daily_pnl', sa.Float, nullable=False, server_default='0'),
        sa.Column('weekly_pnl', sa.Float, nullable=False, server_default='0'),
        sa.Column('monthly_pnl', sa.Float, nullable=False, server_default='0'),
        sa.Column('total_exposure_pct', sa.Float, nullable=False, server_default='0'),
        sa.Column('open_positions', sa.Integer, nullable=False, server_default='0'),
        sa.Column('consecutive_losses', sa.Integer, nullable=False, server_default='0'),
        sa.Column('daily_trades', sa.Integer, nullable=False, server_default='0'),
        sa.Column('is_circuit_breaker_active', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('circuit_breaker_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('circuit_breaker_reason', sa.Text, nullable=True),
        sa.Column('last_updated', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('last_trade_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Risk Alerts table
    op.create_table(
        'risk_alerts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('broker_account_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('broker_accounts.id', ondelete='CASCADE'), nullable=True),
        sa.Column('level', risk_level, nullable=False),
        sa.Column('category', sa.String(100), nullable=False),
        sa.Column('message', sa.Text, nullable=False),
        sa.Column('current_value', sa.Float, nullable=True),
        sa.Column('threshold_value', sa.Float, nullable=True),
        sa.Column('action_required', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('acknowledged', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('acknowledged_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('idx_risk_alerts_level_timestamp', 'risk_alerts', ['level', 'created_at'])

    # Risk Overrides table
    op.create_table(
        'risk_overrides',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('broker_account_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('broker_accounts.id', ondelete='CASCADE'), nullable=True),
        sa.Column('order_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('orders.id', ondelete='SET NULL'), nullable=True),
        sa.Column('position_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('positions.id', ondelete='SET NULL'), nullable=True),
        sa.Column('action', override_action, nullable=False),
        sa.Column('reason', sa.Text, nullable=False),
        sa.Column('risk_state_snapshot', postgresql.JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Notifications table
    op.create_table(
        'notifications',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('channel', notification_channel, nullable=False),
        sa.Column('priority', notification_priority, nullable=False, server_default='medium'),
        sa.Column('subject', sa.String(255), nullable=False),
        sa.Column('message', sa.Text, nullable=False),
        sa.Column('sent', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error', sa.Text, nullable=True),
        sa.Column('metadata', postgresql.JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Notification Preferences table
    op.create_table(
        'notification_preferences',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('email_enabled', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('slack_enabled', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('telegram_enabled', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('webhook_url', sa.String(500), nullable=True),
        sa.Column('trade_alerts', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('risk_alerts', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('system_alerts', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('daily_summary', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Symbol Info table
    op.create_table(
        'symbol_info',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('symbol', sa.String(20), unique=True, nullable=False),
        sa.Column('description', sa.String(255), nullable=True),
        sa.Column('base_currency', sa.String(3), nullable=False),
        sa.Column('quote_currency', sa.String(3), nullable=False),
        sa.Column('pip_value', sa.Float, nullable=False),
        sa.Column('pip_size', sa.Float, nullable=False),
        sa.Column('min_lot_size', sa.Float, nullable=False),
        sa.Column('max_lot_size', sa.Float, nullable=False),
        sa.Column('lot_step', sa.Float, nullable=False),
        sa.Column('typical_spread', sa.Float, nullable=True),
        sa.Column('trading_sessions', postgresql.JSONB, nullable=True),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default='true'),
    )

    # Create TimescaleDB hypertables (if using TimescaleDB extension)
    # These will be run after the tables are created
    op.execute("SELECT create_hypertable('ticks', 'timestamp', if_not_exists => TRUE)")
    op.execute("SELECT create_hypertable('candles', 'timestamp', if_not_exists => TRUE)")
    op.execute("SELECT create_hypertable('market_structures', 'timestamp', if_not_exists => TRUE)")


def downgrade() -> None:
    """Drop all tables."""

    # Drop tables in reverse order of dependencies
    tables = [
        'notification_preferences',
        'notifications',
        'risk_overrides',
        'risk_alerts',
        'risk_states',
        'risk_configurations',
        'deals',
        'positions',
        'orders',
        'agent_performance',
        'ai_decisions',
        'strategies',
        'broker_connections',
        'broker_accounts',
        'symbol_info',
        'market_structures',
        'candles',
        'ticks',
        'audit_logs',
        'user_sessions',
        'users',
    ]

    for table in tables:
        op.drop_table(table)

    # Drop enums
    enums = [
        'notificationpriority', 'notificationchannel', 'overrideaction',
        'risklevel', 'signaldirection', 'agenttype', 'strategystatus',
        'strategytype', 'positionstatus', 'positionside', 'timeinforce',
        'orderstatus', 'ordertype', 'orderside', 'connectionstatus',
        'brokertype', 'userrole',
    ]

    for enum in enums:
        op.execute(f"DROP TYPE IF EXISTS {enum}")
