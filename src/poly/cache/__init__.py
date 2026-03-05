"""
Caching layer for Polymarket data.
Supports Redis and MessagePack fallback.
"""

from .redis_cache import RedisCache

__all__ = ["RedisCache"]
