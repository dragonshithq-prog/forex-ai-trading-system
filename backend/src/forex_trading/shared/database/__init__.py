"""Database package."""

from forex_trading.shared.database.base import Base, BaseModel
from forex_trading.shared.database.manager import DatabaseManager

def __getattr__(name):
    if name == "db_manager":
        from forex_trading.shared.database.manager import get_db_manager
        return get_db_manager()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = ["Base", "BaseModel", "DatabaseManager", "db_manager"]
