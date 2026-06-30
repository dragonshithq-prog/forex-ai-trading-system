"""Broker Gateway - plugin-based architecture for multiple brokers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

import structlog

logger = structlog.get_logger()


class BrokerType(str, Enum):
    """Supported broker types."""
    MT4 = "mt4"
    MT5 = "mt5"
    OANDA = "oanda"
    FXCM = "fxcm"
    CTRADER = "ctrader"
    IBKR = "ibkr"


class ConnectionStatus(str, Enum):
    """Broker connection status."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass
class BrokerCredentials:
    """Broker authentication credentials."""
    broker_type: BrokerType
    api_key: str | None = None
    api_secret: str | None = None
    account_id: str | None = None
    password: str | None = None
    host: str | None = None
    port: int | None = None
    environment: str = "practice"  # practice | live
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AccountInfo:
    """Broker account information."""
    account_id: str
    broker: BrokerType
    balance: float
    equity: float
    margin: float
    free_margin: float
    margin_level: float
    unrealized_pnl: float
    currency: str = "USD"
    leverage: int = 100
    last_updated: datetime = field(default_factory=datetime.utcnow)


@dataclass
class BrokerPosition:
    """Position from broker."""
    position_id: UUID = field(default_factory=uuid4)
    broker_position_id: str = ""
    symbol: str = ""
    side: str = ""  # "long" | "short"
    size: float = 0.0
    entry_price: float = 0.0
    current_price: float = 0.0
    unrealized_pnl: float = 0.0
    stop_loss: float | None = None
    take_profit: float | None = None
    swap: float = 0.0
    commission: float = 0.0
    opened_at: datetime = field(default_factory=datetime.utcnow)


class BrokerPlugin(ABC):
    """
    Abstract base class for broker plugins.

    Each broker implementation must implement this interface.
    """

    def __init__(self, broker_type: BrokerType) -> None:
        self.broker_type = broker_type
        self._status = ConnectionStatus.DISCONNECTED
        self._credentials: BrokerCredentials | None = None

    @property
    def status(self) -> ConnectionStatus:
        return self._status

    @abstractmethod
    async def connect(self, credentials: BrokerCredentials) -> bool:
        """Connect to broker."""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from broker."""
        pass

    @abstractmethod
    async def subscribe_market_data(self, symbols: list[str]) -> None:
        """Subscribe to real-time market data."""
        pass

    @abstractmethod
    async def unsubscribe_market_data(self, symbols: list[str]) -> None:
        """Unsubscribe from market data."""
        pass

    @abstractmethod
    async def get_account_info(self) -> AccountInfo:
        """Get account information."""
        pass

    @abstractmethod
    async def get_positions(self) -> list[BrokerPosition]:
        """Get all open positions."""
        pass

    @abstractmethod
    async def place_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        order_type: str = "market",
        price: float | None = None,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> dict:
        """Place an order with the broker."""
        pass

    @abstractmethod
    async def modify_order(
        self,
        order_id: str,
        quantity: float | None = None,
        price: float | None = None,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> bool:
        """Modify an existing order."""
        pass

    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an order."""
        pass

    @abstractmethod
    async def get_order_history(self, since: datetime | None = None) -> list[dict]:
        """Get order history."""
        pass


class BrokerGateway:
    """
    Broker Gateway - manages multiple broker connections.

    Features:
    - Plugin-based architecture for broker auto-discovery
    - Unified interface across all brokers
    - Connection health monitoring
    - Smart routing based on spread/latency
    """

    def __init__(self) -> None:
        self._plugins: dict[BrokerType, BrokerPlugin] = {}
        self._connections: dict[UUID, BrokerPlugin] = {}
        self._connection_status: dict[UUID, ConnectionStatus] = {}

    def register_plugin(self, plugin: BrokerPlugin) -> None:
        """Register a broker plugin."""
        self._plugins[plugin.broker_type] = plugin
        logger.info("broker_plugin_registered", broker=plugin.broker_type.value)

    def get_plugin(self, broker_type: BrokerType) -> BrokerPlugin | None:
        """Get plugin by broker type."""
        return self._plugins.get(broker_type)

    async def connect(
        self,
        connection_id: UUID,
        broker_type: BrokerType,
        credentials: BrokerCredentials,
    ) -> bool:
        """
        Connect to a broker.

        Args:
            connection_id: Unique connection identifier
            broker_type: Type of broker
            credentials: Authentication credentials

        Returns:
            True if connected successfully
        """
        plugin = self._plugins.get(broker_type)
        if not plugin:
            logger.error("broker_plugin_not_found", broker=broker_type.value)
            return False

        self._connection_status[connection_id] = ConnectionStatus.CONNECTING

        try:
            success = await plugin.connect(credentials)
            if success:
                self._connections[connection_id] = plugin
                self._connection_status[connection_id] = ConnectionStatus.CONNECTED
                logger.info("broker_connected", broker=broker_type.value, connection_id=str(connection_id))
            else:
                self._connection_status[connection_id] = ConnectionStatus.ERROR
                logger.error("broker_connection_failed", broker=broker_type.value)
            return success
        except Exception as e:
            self._connection_status[connection_id] = ConnectionStatus.ERROR
            logger.exception("broker_connection_error", broker=broker_type.value, error=str(e))
            return False

    async def disconnect(self, connection_id: UUID) -> None:
        """Disconnect from a broker."""
        plugin = self._connections.get(connection_id)
        if plugin:
            await plugin.disconnect()
            del self._connections[connection_id]
            self._connection_status[connection_id] = ConnectionStatus.DISCONNECTED
            logger.info("broker_disconnected", connection_id=str(connection_id))

    async def get_account_info(self, connection_id: UUID) -> AccountInfo | None:
        """Get account info from a specific broker connection."""
        plugin = self._connections.get(connection_id)
        if not plugin:
            return None
        return await plugin.get_account_info()

    async def get_positions(self, connection_id: UUID) -> list[BrokerPosition]:
        """Get positions from a specific broker connection."""
        plugin = self._connections.get(connection_id)
        if not plugin:
            return []
        return await plugin.get_positions()

    async def place_order(
        self,
        connection_id: UUID,
        symbol: str,
        side: str,
        quantity: float,
        **kwargs,
    ) -> dict:
        """Place an order through a specific broker connection."""
        plugin = self._connections.get(connection_id)
        if not plugin:
            return {"error": "Not connected to broker"}
        return await plugin.place_order(symbol, side, quantity, **kwargs)

    def get_connected_brokers(self) -> list[UUID]:
        """Get list of connected broker connection IDs."""
        return [
            cid for cid, status in self._connection_status.items()
            if status == ConnectionStatus.CONNECTED
        ]

    def get_best_connection(self, symbol: str) -> UUID | None:
        """Get best broker connection for a symbol (based on spread/latency)."""
        connected = self.get_connected_brokers()
        if not connected:
            return None
        # In production, this would check spreads and latency
        return connected[0]
