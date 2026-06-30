"""Shared cache module - stub for cache manager."""


class CacheManager:
    """Stub cache manager."""

    async def initialize(self) -> None:
        pass

    async def close(self) -> None:
        pass


cache_manager = CacheManager()

__all__ = ["CacheManager", "cache_manager"]
