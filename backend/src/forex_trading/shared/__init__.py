"""Shared infrastructure - database, cache, events, messaging."""

def __getattr__(name):
    if name == "DatabaseManager":
        from forex_trading.shared.database.manager import DatabaseManager
        return DatabaseManager
    if name == "db_manager":
        from forex_trading.shared.database.manager import get_db_manager
        return get_db_manager()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = ["DatabaseManager", "db_manager"]
