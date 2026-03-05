"""
Async Polymarket API Client: High-performance parallel fetching.
Provides 10-30x speedup using async/await with connection pooling.
"""

import asyncio
import logging
import time
from typing import Optional, List, Dict, Any
import httpx

logger = logging.getLogger(__name__)


class AsyncPolymarketClient:
    """High-performance async client with connection pooling and rate limiting."""

    def __init__(
        self,
        max_connections: int = 100,
        trades_concurrency: int = 20,
        markets_concurrency: int = 30,
        timeout: float = 60.0,
        redis_cache=None,
    ):
        self.gamma_base = "https://gamma-api.polymarket.com"
        self.data_base = "https://data-api.polymarket.com"
        self.clob_base = "https://clob.polymarket.com"

        # Redis cache (optional)
        self.redis_cache = redis_cache

        # Connection pooling for speed
        self.client = httpx.AsyncClient(
            limits=httpx.Limits(max_connections=max_connections),
            timeout=httpx.Timeout(timeout, connect=10.0, read=30.0),
        )

        # Semaphores for rate limiting
        self.trades_semaphore = asyncio.Semaphore(trades_concurrency)
        self.markets_semaphore = asyncio.Semaphore(markets_concurrency)

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def _safe_get(
        self, url: str, params: Optional[Dict] = None, max_retries: int = 3
    ) -> Optional[Any]:
        """Execute GET request with exponential backoff retry."""
        backoff = 1.0
        for attempt in range(max_retries):
            try:
                resp = await self.client.get(url, params=params)
                if resp.status_code == 200:
                    return resp.json()
                if resp.status_code == 429:
                    await asyncio.sleep(backoff)
                    backoff *= 2.0
                    continue
                return None
            except Exception:
                await asyncio.sleep(backoff)
                backoff *= 2.0
        return None

    async def fetch_trader_history_single(
        self,
        address: str,
        limit: int = 1000,
        offset: int = 0,
        min_size: Optional[float] = None,
    ) -> List[Dict]:
        """Fetch a single batch of trades for a trader."""
        async with self.trades_semaphore:
            params = {"user": address, "limit": limit, "offset": offset}
            if min_size is not None:
                params["min_size"] = min_size
            data = await self._safe_get(f"{self.data_base}/trades", params=params)
            return data if isinstance(data, list) else []

    async def fetch_full_trader_history(
        self,
        address: str,
        max_trades: int = 10000,
        batch_size: int = 1000,
        min_size: Optional[float] = None,
    ) -> List[Dict]:
        """Fetch complete trading history for a single user with async pagination."""
        all_trades = []
        tasks = []

        # Create tasks for all pages concurrently
        offset = 0
        while offset < max_trades:
            task = self.fetch_trader_history_single(
                address, limit=batch_size, offset=offset, min_size=min_size
            )
            tasks.append(task)
            offset += batch_size

        # Execute all requests concurrently
        results = await asyncio.gather(*tasks)

        # Combine results
        for batch in results:
            if not batch:
                break
            all_trades.extend(batch)
            if len(batch) < batch_size:
                break

        return all_trades[:max_trades]

    async def fetch_trader_histories_batch(
        self,
        addresses: List[str],
        max_trades: int = 1000,
        min_size: Optional[float] = None,
    ) -> Dict[str, List[Dict]]:
        """
        Fetch histories for multiple traders concurrently.
        This is the main optimization - fetch N wallets in parallel.
        """
        tasks = {
            addr: self.fetch_full_trader_history(addr, max_trades, min_size=min_size)
            for addr in addresses
        }
        results = await asyncio.gather(*tasks.values())
        return dict(zip(tasks.keys(), results))

    async def get_market_info_single(self, condition_id: str) -> Dict[str, Any]:
        """Fetch metadata for a single market with Redis caching."""
        # Check Redis cache first
        if self.redis_cache:
            cached = self.redis_cache.get_market_metadata(condition_id)
            if cached:
                return cached

        async with self.markets_semaphore:
            data = await self._safe_get(
                f"{self.gamma_base}/markets",
                params={"condition_id": condition_id},
            )

            if not data or not isinstance(data, list) or len(data) == 0:
                return {}

            market = data[0]
            result = {
                "condition_id": condition_id,
                "question": market.get("question", ""),
                "group_item_title": market.get("groupItemTitle", ""),
                "category": market.get("category", ""),
                "slug": market.get("slug", ""),
                "volume": market.get("volume", 0),
                "liquidity": market.get("liquidity", 0),
                "active": market.get("active", False),
                "closed": market.get("closed", False),
                "clobTokenIds": market.get("clobTokenIds", []),
            }

            # Cache in Redis (24h TTL)
            if self.redis_cache:
                self.redis_cache.set_market_metadata(condition_id, result)

            return result

    async def get_market_info_batch(
        self, condition_ids: List[str]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Fetch metadata for multiple markets concurrently.
        Note: API doesn't support batch endpoint, but we fetch in parallel.
        """
        tasks = {cid: self.get_market_info_single(cid) for cid in condition_ids}
        results = await asyncio.gather(*tasks.values())
        return dict(zip(tasks.keys(), results))

    async def get_market_resolution_state(
        self, condition_id: str, cache: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Fetch market resolution state (winner, closed timestamp) with Redis caching."""
        # Check memory cache first
        if cache and condition_id in cache:
            return cache[condition_id]

        # Check Redis cache
        if self.redis_cache:
            cached = self.redis_cache.get_resolution(condition_id)
            if cached:
                if cache is not None:
                    cache[condition_id] = cached
                return cached

        async with self.markets_semaphore:
            data = await self._safe_get(
                f"{self.gamma_base}/markets",
                params={"condition_id": condition_id},
            )

            if not data or not isinstance(data, list):
                return {}

            market = data[0]
            if not market or not market.get("closed"):
                return {}

            try:
                import json

                prices_raw = market.get("outcomePrices")
                prices = (
                    json.loads(prices_raw)
                    if isinstance(prices_raw, str)
                    else prices_raw
                )

                if not prices:
                    return {}

                closed_time = market.get("closedTime")
                import pandas as pd
                import numpy as np

                closed_at_ts = (
                    int(pd.to_datetime(closed_time).timestamp()) if closed_time else 0
                )

                result = {
                    "winner_idx": int(np.argmax([float(p) for p in prices])),
                    "closed_at": closed_at_ts,
                    "question": market.get("question", ""),
                    "slug": market.get("slug", ""),
                    "clobTokenIds": market.get("clobTokenIds", []),
                }

                # Cache in memory
                if cache is not None:
                    cache[condition_id] = result

                # Cache in Redis (7d TTL - resolutions are immutable)
                if self.redis_cache:
                    self.redis_cache.set_resolution(condition_id, result)

                return result
            except Exception:
                return {}

    async def get_market_resolutions_batch(
        self, condition_ids: List[str], cache: Optional[Dict] = None
    ) -> Dict[str, Dict[str, Any]]:
        """Fetch resolutions for multiple markets concurrently."""
        # Filter out cached ones
        to_fetch = (
            [cid for cid in condition_ids if cid not in cache]
            if cache
            else condition_ids
        )

        if not to_fetch:
            return cache or {}

        tasks = {cid: self.get_market_resolution_state(cid, cache) for cid in to_fetch}
        results = await asyncio.gather(*tasks.values())

        if cache is None:
            cache = {}

        for cid, result in zip(to_fetch, results):
            if result:
                cache[cid] = result

        return cache

    async def get_leaderboard(
        self,
        category: str = "OVERALL",
        period: str = "ALL",
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict]:
        """Fetch leaderboard with pre-computed PnL."""
        params = {
            "category": category,
            "timePeriod": period,
            "orderBy": "PNL",
            "limit": limit,
            "offset": offset,
        }
        data = await self._safe_get(f"{self.data_base}/v1/leaderboard", params=params)
        return data if isinstance(data, list) else []

    async def get_user_traded_count(self, address: str) -> int:
        """Get total markets traded by user."""
        data = await self._safe_get(
            f"{self.data_base}/traded", params={"user": address}
        )
        return int(data.get("traded", 0)) if isinstance(data, dict) else 0


# Sync wrapper for compatibility
class SyncWrapper:
    """Synchronous wrapper for AsyncPolymarketClient."""

    def __init__(self, **kwargs):
        self.async_client = AsyncPolymarketClient(**kwargs)
        self._loop = None

    def _get_loop(self):
        if self._loop is None:
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)
        return self._loop

    def run(self, coro):
        loop = self._get_loop()
        if loop.is_running():
            # Already in async context
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, coro)
                return future.result()
        else:
            return loop.run_until_complete(coro)

    def fetch_trader_histories_batch(
        self, addresses: List[str], max_trades: int = 1000
    ) -> Dict[str, List[Dict]]:
        """Sync wrapper for batch fetching."""
        return self.run(
            self.async_client.fetch_trader_histories_batch(addresses, max_trades)
        )

    def get_market_info_batch(self, condition_ids: List[str]) -> Dict[str, Dict]:
        """Sync wrapper for batch market info."""
        return self.run(self.async_client.get_market_info_batch(condition_ids))

    def get_market_resolutions_batch(
        self, condition_ids: List[str], cache: Optional[Dict] = None
    ) -> Dict[str, Dict]:
        """Sync wrapper for batch resolutions."""
        return self.run(
            self.async_client.get_market_resolutions_batch(condition_ids, cache)
        )

    def close(self):
        """Close the client."""
        self.run(self.async_client.close())
