"""Execution Engine - order lifecycle management."""

__all__ = ["ExecutionEngine"]


def __getattr__(name: str):
    if name == "ExecutionEngine":
        from forex_trading.execution.engine import ExecutionEngine
        return ExecutionEngine
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
