"""Execution - order lifecycle, position management, and automated trading."""

__all__ = ["ExecutionEngine", "PositionManager", "AutoTrader", "PositionSizer"]


def __getattr__(name: str):
    if name == "ExecutionEngine":
        from forex_trading.execution.engine import ExecutionEngine
        return ExecutionEngine
    if name == "PositionManager":
        from forex_trading.execution.position_manager import PositionManager
        return PositionManager
    if name == "AutoTrader":
        from forex_trading.execution.services.auto_trader import AutoTrader
        return AutoTrader
    if name == "PositionSizer":
        from forex_trading.execution.services.position_sizer import PositionSizer
        return PositionSizer
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
