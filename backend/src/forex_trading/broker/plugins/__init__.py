"""Broker plugins - OANDA, MT5 bridge, MT4 bridge."""

from typing import Optional

from forex_trading.broker.gateway import BrokerPlugin
from forex_trading.broker.plugins.oanda import OANDAPlugin
from forex_trading.broker.plugins.mt5_bridge import MT5BridgePlugin
from forex_trading.broker.plugins.mt4_bridge import MT4BridgePlugin

__all__ = [
    "OANDAPlugin",
    "MT5BridgePlugin",
    "MT4BridgePlugin",
]

_plugin_registry: dict[str, BrokerPlugin] = {
    "oanda": OANDAPlugin(),
    "mt5": MT5BridgePlugin(),
    "mt4": MT4BridgePlugin(),
}


def get_plugin(broker_type: str) -> Optional[BrokerPlugin]:
    """Get broker plugin by type string."""
    return _plugin_registry.get(broker_type.lower())
