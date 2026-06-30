"""Database seed script for development data."""

import asyncio
from datetime import datetime, timedelta
from uuid import uuid4

from forex_trading.core.security import security_manager
from forex_trading.shared.database.base import Base
from forex_trading.shared.database.models import (
    User,
    UserRole,
    BrokerAccount,
    BrokerType,
    Strategy,
    StrategyType,
    StrategyStatus,
    RiskConfiguration,
    RiskState,
    SymbolInfo,
    AgentType,
    AgentPerformance,
)


# Sample symbol data
SYMBOLS = [
    {
        "symbol": "EURUSD",
        "description": "Euro / US Dollar",
        "base_currency": "EUR",
        "quote_currency": "USD",
        "pip_value": 10.0,
        "pip_size": 0.0001,
        "min_lot_size": 0.01,
        "max_lot_size": 100.0,
        "lot_step": 0.01,
        "typical_spread": 1.2,
    },
    {
        "symbol": "GBPUSD",
        "description": "British Pound / US Dollar",
        "base_currency": "GBP",
        "quote_currency": "USD",
        "pip_value": 10.0,
        "pip_size": 0.0001,
        "min_lot_size": 0.01,
        "max_lot_size": 100.0,
        "lot_step": 0.01,
        "typical_spread": 1.5,
    },
    {
        "symbol": "USDJPY",
        "description": "US Dollar / Japanese Yen",
        "base_currency": "USD",
        "quote_currency": "JPY",
        "pip_value": 6.67,
        "pip_size": 0.01,
        "min_lot_size": 0.01,
        "max_lot_size": 100.0,
        "lot_step": 0.01,
        "typical_spread": 1.3,
    },
    {
        "symbol": "USDCHF",
        "description": "US Dollar / Swiss Franc",
        "base_currency": "USD",
        "quote_currency": "CHF",
        "pip_value": 10.0,
        "pip_size": 0.0001,
        "min_lot_size": 0.01,
        "max_lot_size": 100.0,
        "lot_step": 0.01,
        "typical_spread": 1.4,
    },
    {
        "symbol": "AUDUSD",
        "description": "Australian Dollar / US Dollar",
        "base_currency": "AUD",
        "quote_currency": "USD",
        "pip_value": 10.0,
        "pip_size": 0.0001,
        "min_lot_size": 0.01,
        "max_lot_size": 100.0,
        "lot_step": 0.01,
        "typical_spread": 1.4,
    },
    {
        "symbol": "USDCAD",
        "description": "US Dollar / Canadian Dollar",
        "base_currency": "USD",
        "quote_currency": "CAD",
        "pip_value": 7.5,
        "pip_size": 0.0001,
        "min_lot_size": 0.01,
        "max_lot_size": 100.0,
        "lot_step": 0.01,
        "typical_spread": 1.6,
    },
    {
        "symbol": "NZDUSD",
        "description": "New Zealand Dollar / US Dollar",
        "base_currency": "NZD",
        "quote_currency": "USD",
        "pip_value": 10.0,
        "pip_size": 0.0001,
        "min_lot_size": 0.01,
        "max_lot_size": 100.0,
        "lot_step": 0.01,
        "typical_spread": 1.8,
    },
    {
        "symbol": "EURJPY",
        "description": "Euro / Japanese Yen",
        "base_currency": "EUR",
        "quote_currency": "JPY",
        "pip_value": 6.67,
        "pip_size": 0.01,
        "min_lot_size": 0.01,
        "max_lot_size": 100.0,
        "lot_step": 0.01,
        "typical_spread": 1.7,
    },
    {
        "symbol": "GBPJPY",
        "description": "British Pound / Japanese Yen",
        "base_currency": "GBP",
        "quote_currency": "JPY",
        "pip_value": 6.67,
        "pip_size": 0.01,
        "min_lot_size": 0.01,
        "max_lot_size": 100.0,
        "lot_step": 0.01,
        "typical_spread": 2.5,
    },
    {
        "symbol": "EURGBP",
        "description": "Euro / British Pound",
        "base_currency": "EUR",
        "quote_currency": "GBP",
        "pip_value": 12.5,
        "pip_size": 0.0001,
        "min_lot_size": 0.01,
        "max_lot_size": 100.0,
        "lot_step": 0.01,
        "typical_spread": 1.5,
    },
]

# Sample strategies
STRATEGIES = [
    {
        "name": "Trend Following Pro",
        "strategy_type": StrategyType.TREND_FOLLOWING,
        "description": "Follows strong trends with trailing stops",
        "parameters": {
            "ema_fast": 20,
            "ema_slow": 50,
            "atr_multiplier": 2.0,
            "trailing_stop_pips": 30,
        },
        "symbols": ["EURUSD", "GBPUSD", "USDJPY"],
        "timeframes": ["H1", "H4"],
        "max_position_size_pct": 2.0,
        "risk_per_trade_pct": 1.0,
    },
    {
        "name": "Mean Reversion Master",
        "strategy_type": StrategyType.MEAN_REVERSION,
        "description": "Fades extremes at support/resistance levels",
        "parameters": {
            "rsi_period": 14,
            "rsi_overbought": 70,
            "rsi_oversold": 30,
            "bb_period": 20,
            "bb_std": 2.0,
        },
        "symbols": ["EURUSD", "GBPUSD", "AUDUSD"],
        "timeframes": ["M15", "H1"],
        "max_position_size_pct": 1.5,
        "risk_per_trade_pct": 0.5,
    },
    {
        "name": "London Breakout",
        "strategy_type": StrategyType.BREAKOUT,
        "description": "Breakout strategy for London session open",
        "parameters": {
            "lookback_hours": 4,
            "breakout_pips": 20,
            "confirmation_candles": 2,
        },
        "symbols": ["EURUSD", "GBPUSD", "EURGBP"],
        "timeframes": ["M15", "H1"],
        "max_position_size_pct": 2.0,
        "risk_per_trade_pct": 1.0,
    },
    {
        "name": "Scalping Machine",
        "strategy_type": StrategyType.SCALPING,
        "description": "Quick scalps during high liquidity sessions",
        "parameters": {
            "ema_period": 8,
            "volume_threshold": 1.5,
            "max_spread_pips": 2.0,
            "take_profit_pips": 10,
        },
        "symbols": ["EURUSD", "GBPUSD"],
        "timeframes": ["M1", "M5"],
        "max_position_size_pct": 1.0,
        "risk_per_trade_pct": 0.25,
    },
]


async def seed_database():
    """Seed database with development data."""
    from forex_trading.shared.database import db_manager

    await db_manager.initialize()

    async with db_manager.session() as session:
        # Check if data already exists
        from sqlalchemy import select, func

        result = await session.execute(select(func.count()).select_from(User))
        user_count = result.scalar()

        if user_count > 0:
            print("Database already seeded. Skipping.")
            return

        print("Seeding database...")

        # Create admin user
        admin_user = User(
            email="admin@forex-trading.com",
            username="admin",
            hashed_password=security_manager.hash_password("admin123"),
            full_name="System Admin",
            role=UserRole.SUPERADMIN,
            is_active=True,
            is_verified=True,
        )
        session.add(admin_user)

        # Create trader user
        trader_user = User(
            email="trader@forex-trading.com",
            username="trader",
            hashed_password=security_manager.hash_password("trader123"),
            full_name="Demo Trader",
            role=UserRole.TRADER,
            is_active=True,
            is_verified=True,
        )
        session.add(trader_user)

        # Create viewer user
        viewer_user = User(
            email="viewer@forex-trading.com",
            username="viewer",
            hashed_password=security_manager.hash_password("viewer123"),
            full_name="Demo Viewer",
            role=UserRole.VIEWER,
            is_active=True,
            is_verified=True,
        )
        session.add(viewer_user)

        await session.flush()

        # Create broker account for trader
        broker_account = BrokerAccount(
            user_id=trader_user.id,
            broker_type=BrokerType.OANDA,
            account_name="OANDA Practice",
            account_number="101-001-12345678-001",
            environment="practice",
            currency="USD",
            leverage=100,
            balance=10000.0,
            equity=10000.0,
            margin=0.0,
            free_margin=10000.0,
        )
        session.add(broker_account)
        await session.flush()

        # Create risk configuration
        risk_config = RiskConfiguration(
            broker_account_id=broker_account.id,
            max_position_size_pct=2.0,
            max_total_exposure_pct=20.0,
            max_positions=10,
            daily_drawdown_limit_pct=3.0,
            weekly_drawdown_limit_pct=5.0,
            monthly_drawdown_limit_pct=10.0,
            max_drawdown_limit_pct=15.0,
            risk_per_trade_pct=1.0,
        )
        session.add(risk_config)

        # Create risk state
        risk_state = RiskState(
            broker_account_id=broker_account.id,
            current_equity=10000.0,
            peak_equity=10000.0,
            current_drawdown_pct=0.0,
            max_drawdown_pct=0.0,
        )
        session.add(risk_state)

        # Create strategies
        for strategy_data in STRATEGIES:
            strategy = Strategy(**strategy_data)
            session.add(strategy)

        # Create symbol info
        for symbol_data in SYMBOLS:
            symbol_info = SymbolInfo(**symbol_data)
            session.add(symbol_info)

        await session.commit()

        print("Database seeded successfully!")
        print(f"  - Users: 3 (admin, trader, viewer)")
        print(f"  - Broker Accounts: 1")
        print(f"  - Strategies: {len(STRATEGIES)}")
        print(f"  - Symbols: {len(SYMBOLS)}")

    await db_manager.close()


if __name__ == "__main__":
    asyncio.run(seed_database())
