"""
Persistent cache for trader profiles with incremental updates.

Features:
- Disk-based storage using msgpack format
- Timestamp tracking for incremental updates
- Automatic TTL-based invalidation
- LRU eviction for memory management
"""

import os
import time
import logging
import msgpack
from pathlib import Path
from typing import Optional, Dict, Any
from collections import OrderedDict

logger = logging.getLogger(__name__)


class ProfileCache:
    """
    Persistent cache for trader profiles with incremental updates.
    
    Storage format:
    {
        "address": {
            "profile": {...},  # Trader profile data
            "timestamp": 1234567890,  # Last update timestamp
            "last_trade_ts": 1234567890  # Timestamp of last trade processed
        }
    }
    """
    
    def __init__(
        self, 
        cache_dir: str = "data/cache",
        ttl_seconds: int = 3600,
        max_memory_items: int = 1000
    ):
        """
        Initialize profile cache.
        
        Args:
            cache_dir: Directory for cache storage
            ttl_seconds: Time-to-live for cached profiles (default 1 hour)
            max_memory_items: Maximum items to keep in memory (LRU eviction)
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_file = self.cache_dir / "profiles.msgpack"
        self.ttl = ttl_seconds
        self.max_memory_items = max_memory_items
        
        # In-memory cache with LRU eviction
        self._memory_cache: OrderedDict[str, Dict] = OrderedDict()
        
        # Load existing cache from disk
        self._load_from_disk()
    
    def _load_from_disk(self):
        """Load cache from disk into memory."""
        if not self.cache_file.exists():
            logger.info("No existing cache file found, starting fresh")
            return
        
        try:
            with open(self.cache_file, "rb") as f:
                data = f.read()
                if data:
                    disk_cache = msgpack.unpackb(data, raw=False)
                    
                    # Load into memory cache (most recent first)
                    sorted_items = sorted(
                        disk_cache.items(),
                        key=lambda x: x[1].get('timestamp', 0),
                        reverse=True
                    )
                    
                    for addr, entry in sorted_items[:self.max_memory_items]:
                        self._memory_cache[addr] = entry
                    
                    logger.info(f"Loaded {len(self._memory_cache)} profiles from cache")
        except Exception as e:
            logger.warning(f"Failed to load cache from disk: {e}")
            self._memory_cache = OrderedDict()
    
    def _save_to_disk(self):
        """Save memory cache to disk."""
        try:
            # Convert OrderedDict to regular dict for msgpack
            cache_dict = dict(self._memory_cache)
            
            with open(self.cache_file, "wb") as f:
                f.write(msgpack.packb(cache_dict))
            
            logger.debug(f"Saved {len(cache_dict)} profiles to disk")
        except Exception as e:
            logger.warning(f"Failed to save cache to disk: {e}")
    
    def get(self, address: str) -> Optional[Dict[str, Any]]:
        """
        Get cached profile if fresh.
        
        Args:
            address: Trader wallet address
            
        Returns:
            Cached profile dict or None if not found/stale
        """
        if address not in self._memory_cache:
            return None
        
        entry = self._memory_cache[address]
        
        # Check if stale
        if self.is_stale(address):
            return None
        
        # Move to end (LRU)
        self._memory_cache.move_to_end(address)
        
        return entry.get('profile')
    
    def set(self, address: str, profile: Dict[str, Any], last_trade_ts: Optional[int] = None):
        """
        Save profile to cache.
        
        Args:
            address: Trader wallet address
            profile: Profile data to cache
            last_trade_ts: Timestamp of last trade processed (for incremental updates)
        """
        current_ts = int(time.time())
        
        entry = {
            'profile': profile,
            'timestamp': current_ts,
            'last_trade_ts': last_trade_ts or current_ts
        }
        
        # Add to memory cache
        self._memory_cache[address] = entry
        self._memory_cache.move_to_end(address)
        
        # Evict oldest if over limit
        if len(self._memory_cache) > self.max_memory_items:
            self._memory_cache.popitem(last=False)
        
        # Periodically save to disk (every 10 updates)
        if len(self._memory_cache) % 10 == 0:
            self._save_to_disk()
    
    def is_stale(self, address: str) -> bool:
        """
        Check if cached profile needs refresh.
        
        Args:
            address: Trader wallet address
            
        Returns:
            True if cache is stale or missing
        """
        if address not in self._memory_cache:
            return True
        
        entry = self._memory_cache[address]
        cache_age = int(time.time()) - entry.get('timestamp', 0)
        
        return cache_age > self.ttl
    
    def get_last_update_ts(self, address: str) -> int:
        """
        Get timestamp of last update for incremental fetching.
        
        Args:
            address: Trader wallet address
            
        Returns:
            Unix timestamp of last trade processed, or 0 if not cached
        """
        if address not in self._memory_cache:
            return 0
        
        entry = self._memory_cache[address]
        return entry.get('last_trade_ts', 0)
    
    def invalidate(self, address: str):
        """
        Invalidate cached profile for an address.
        
        Args:
            address: Trader wallet address
        """
        if address in self._memory_cache:
            del self._memory_cache[address]
            logger.debug(f"Invalidated cache for {address}")
    
    def clear(self):
        """Clear all cached profiles."""
        self._memory_cache.clear()
        logger.info("Cleared all cached profiles")
    
    def flush(self):
        """Force save memory cache to disk."""
        self._save_to_disk()
        logger.info("Flushed cache to disk")
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.
        
        Returns:
            Dict with cache stats
        """
        current_ts = int(time.time())
        
        fresh_count = sum(
            1 for entry in self._memory_cache.values()
            if (current_ts - entry.get('timestamp', 0)) <= self.ttl
        )
        
        stale_count = len(self._memory_cache) - fresh_count
        
        return {
            'total_cached': len(self._memory_cache),
            'fresh_profiles': fresh_count,
            'stale_profiles': stale_count,
            'cache_file_exists': self.cache_file.exists(),
            'cache_file_size_mb': self.cache_file.stat().st_size / (1024 * 1024) 
                if self.cache_file.exists() else 0,
            'ttl_seconds': self.ttl,
            'max_memory_items': self.max_memory_items
        }
    
    def __del__(self):
        """Save cache on destruction."""
        try:
            self._save_to_disk()
        except:
            pass