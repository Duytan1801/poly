"""
Redis caching layer for Polymarket data.
Provides distributed caching with TTL support.
"""

import json
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

try:
    import redis

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.warning("Redis not installed. Install with: pip install redis")


class RedisCache:
    """Redis-based cache with fallback to no-op if Redis unavailable."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        decode_responses: bool = True,
        enabled: bool = True,
    ):
        self.enabled = enabled and REDIS_AVAILABLE
        self.client = None

        if self.enabled:
            try:
                self.client = redis.Redis(
                    host=host,
                    port=port,
                    db=db,
                    decode_responses=decode_responses,
                    socket_connect_timeout=2,
                    socket_timeout=2,
                )
                # Test connection
                self.client.ping()
                logger.info(f"Redis cache connected: {host}:{port}")
            except Exception as e:
                logger.warning(f"Redis connection failed: {e}. Running without cache.")
                self.enabled = False
                self.client = None

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        if not self.enabled or not self.client:
            return None

        try:
            data = self.client.get(key)
            if data:
                return json.loads(data)
            return None
        except Exception as e:
            logger.debug(f"Redis get error for {key}: {e}")
            return None

    def set(self, key: str, value: Any, ttl: int = 3600) -> bool:
        """Set value in cache with TTL (seconds)."""
        if not self.enabled or not self.client:
            return False

        try:
            serialized = json.dumps(value)
            self.client.setex(key, ttl, serialized)
            return True
        except Exception as e:
            logger.debug(f"Redis set error for {key}: {e}")
            return False

    def delete(self, key: str) -> bool:
        """Delete key from cache."""
        if not self.enabled or not self.client:
            return False

        try:
            self.client.delete(key)
            return True
        except Exception as e:
            logger.debug(f"Redis delete error for {key}: {e}")
            return False

    def get_market_metadata(self, condition_id: str) -> Optional[Dict]:
        """Get market metadata from cache (24h TTL)."""
        return self.get(f"market:{condition_id}")

    def set_market_metadata(self, condition_id: str, metadata: Dict) -> bool:
        """Set market metadata in cache (24h TTL)."""
        return self.set(f"market:{condition_id}", metadata, ttl=86400)

    def get_resolution(self, condition_id: str) -> Optional[Dict]:
        """Get market resolution from cache (7d TTL - immutable once resolved)."""
        return self.get(f"resolution:{condition_id}")

    def set_resolution(self, condition_id: str, resolution: Dict) -> bool:
        """Set market resolution in cache (7d TTL)."""
        return self.set(f"resolution:{condition_id}", resolution, ttl=604800)

    def get_pnl(self, address: str) -> Optional[float]:
        """Get trader PnL from cache (1h TTL)."""
        data = self.get(f"pnl:{address.lower()}")
        return data.get("pnl") if data else None

    def set_pnl(self, address: str, pnl: float) -> bool:
        """Set trader PnL in cache (1h TTL)."""
        return self.set(f"pnl:{address.lower()}", {"pnl": pnl}, ttl=3600)

    def get_leaderboard(self) -> Optional[Dict]:
        """Get cached leaderboard data (1h TTL)."""
        return self.get("leaderboard:all")

    def set_leaderboard(self, data: Dict) -> bool:
        """Set leaderboard data in cache (1h TTL)."""
        return self.set("leaderboard:all", data, ttl=3600)

    def close(self):
        """Close Redis connection."""
        if self.client:
            try:
                self.client.close()
            except Exception:
                pass
