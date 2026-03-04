"""
Polymarket API Client: Full API coverage for Gamma, Data, and CLOB APIs.
Provides high-fidelity trader history and market resolution data.
"""

import logging
import json
import time
import os
import httpx
import pandas as pd
import numpy as np
import msgpack
from typing import Optional, List, Dict, Any
from poly.api.graphql import GraphQLClient

logger = logging.getLogger(__name__)

CACHE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "data"
)
RESOLUTION_CACHE_FILE = os.path.join(CACHE_DIR, "resolution_cache.msgpack")


class PolymarketClient:
    """Unified client for interacting with all Polymarket API tiers."""

    def __init__(self, timeout: float = 60.0):
        self.http = httpx.Client(
            timeout=httpx.Timeout(timeout, connect=30.0, read=120.0)
        )
        self.gamma_base = "https://gamma-api.polymarket.com"
        self.data_base = "https://data-api.polymarket.com"
        self.clob_base = "https://clob.polymarket.com"
        self.graphql = GraphQLClient(timeout=timeout)

    def _load_resolution_from_disk(self, condition_id: str) -> Optional[Dict]:
        """Load a single resolution from MessagePack cache file."""
        if not os.path.exists(RESOLUTION_CACHE_FILE):
            return None
        try:
            with open(RESOLUTION_CACHE_FILE, "rb") as f:
                data = f.read()
                if not data:
                    return None
                cache = msgpack.unpackb(data)
                return cache.get(condition_id)
        except Exception:
            return None

    def _save_resolution_to_disk(self, condition_id: str, data: Dict):
        """Save a single resolution to MessagePack cache file."""
        try:
            os.makedirs(CACHE_DIR, exist_ok=True)

            # Load existing cache
            cache = {}
            if os.path.exists(RESOLUTION_CACHE_FILE):
                try:
                    with open(RESOLUTION_CACHE_FILE, "rb") as f:
                        file_data = f.read()
                        if file_data:
                            cache = msgpack.unpackb(file_data)
                except Exception:
                    cache = {}

            # Add new data
            cache[condition_id] = data

            # Write back
            with open(RESOLUTION_CACHE_FILE, "wb") as f:
                f.write(msgpack.packb(cache))
        except Exception:
            pass

    def _safe_get(self, url: str, params: Optional[Dict] = None) -> Optional[Any]:
        """Safely execute a GET request with exponential backoff retry for rate limits."""
        max_retries = 5
        backoff = 1.0

        for attempt in range(max_retries):
            try:
                resp = self.http.get(url, params=params)
                if resp.status_code == 200:
                    return resp.json()

                if resp.status_code == 429:
                    time.sleep(backoff)
                    backoff *= 2.0
                    continue

                return None
            except Exception as e:
                time.sleep(backoff)
                backoff *= 2.0

        return None

    def get_leaderboard(
        self,
        category: str = "OVERALL",
        period: str = "MONTH",
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict]:
        """Directly fetch the Top Traders by PnL with pagination."""
        url = f"{self.data_base}/v1/leaderboard"
        params = {
            "category": category,
            "timePeriod": period,
            "orderBy": "PNL",
            "limit": limit,
            "offset": offset,
        }
        data = self._safe_get(url, params=params)
        return data if isinstance(data, list) else []

    def get_trader_pnl_from_leaderboard(
        self,
        address: str,
        category: str = "OVERALL",
        period: str = "ALL",
    ) -> Optional[Dict]:
        """OPTIMIZATION: Get pre-computed PnL from leaderboard API.

        This is MUCH faster than calculating PnL from trade history.
        Polymarket already calculates this on their server.

        Returns: {rank, pnl, vol} or None if not found
        """
        url = f"{self.data_base}/v1/leaderboard"
        params = {
            "category": category,
            "timePeriod": period,
            "orderBy": "PNL",
            "limit": 2000,  # Get top 2000 to search
        }
        data = self._safe_get(url, params=params)
        if not isinstance(data, list):
            return None

        address_lower = address.lower()
        for entry in data:
            if entry.get("proxyWallet", "").lower() == address_lower:
                return {
                    "rank": entry.get("rank"),
                    "pnl": entry.get("pnl", 0),
                    "vol": entry.get("vol", 0),
                    "userName": entry.get("userName"),
                }
        return None
        data = self._safe_get(url, params=params)
        return data if isinstance(data, list) else []

    def get_trader_history(
        self,
        address: str,
        limit: int = 500,
        offset: int = 0,
        start: Optional[int] = None,
        end: Optional[int] = None,
        min_size: Optional[float] = None,
    ) -> List[Dict]:
        """Fetch historical trades for a user with temporal pagination support.

        Args:
            address: Trader wallet address
            limit: Max trades to return
            offset: Pagination offset
            start: Filter trades after this timestamp
            end: Filter trades before this timestamp
            min_size: OPTIMIZATION - Only fetch trades >= this size (server-side filter!)
        """
        url = f"{self.data_base}/trades"
        params = {"user": address, "limit": limit, "offset": offset}
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        if min_size:
            params["min_size"] = min_size
        data = self._safe_get(url, params=params)
        return data if isinstance(data, list) else []

    def get_large_trades_only(
        self,
        address: str,
        min_size: float = 1000,
        limit: int = 500,
    ) -> List[Dict]:
        """OPTIMIZATION: Fetch only large trades (>min_size) from server.

        This dramatically reduces data transfer and client-side processing.
        Server does the filtering, we only get relevant trades.
        """
        return self.get_trader_history(address, limit=limit, min_size=min_size)

    def get_full_trader_history(
        self,
        address: str,
        max_trades: int = 100000,
        batch_size: int = 1000,
    ) -> List[Dict]:
        """Fetch complete trading history for a user via offset-based pagination.

        OPTIMIZATION: Using offset pagination instead of timestamp-based.
        This is MUCH faster - 4 requests for 4000 trades vs dozens with old method.

        API limit: Max 1000 trades per request
        """
        import time

        all_trades = []
        offset = 0

        while len(all_trades) < max_trades:
            # Fetch trades using offset pagination
            batch = self.get_trader_history(
                address,
                limit=batch_size,
                offset=offset,
            )

            if not batch:
                break

            all_trades.extend(batch)

            # If we got fewer than batch_size, we're done
            if len(batch) < batch_size:
                break

            offset += batch_size

            # Small delay to be nice to the API
            time.sleep(0.02)

        return all_trades[:max_trades]

    def get_user_traded_count(self, address: str) -> int:
        """Get the total number of unique markets a user has traded in."""
        url = f"{self.data_base}/traded"
        data = self._safe_get(url, params={"user": address})
        if isinstance(data, dict):
            return int(data.get("traded", 0))
        return 0

    def get_positions(
        self, address: str, market: Optional[str] = None, status: str = "ALL"
    ) -> List[Dict]:
        """Get current positions for a user."""
        url = f"{self.data_base}/positions"
        params = {"user": address, "status": status}
        if market:
            params["market"] = market
        data = self._safe_get(url, params=params)
        return data if isinstance(data, list) else []

    def get_market_holders(self, condition_id: str, limit: int = 100) -> List[Dict]:
        """Get top holders for a specific market condition."""
        url = f"{self.data_base}/holders"
        params = {"market": condition_id, "limit": limit}
        data = self._safe_get(url, params=params)
        return data if isinstance(data, list) else []

    def get_market_resolution_state(self, condition_id: str) -> Dict[str, Any]:
        """Fetch high-fidelity resolution state including winning index and closed timestamp."""
        # Check disk cache first
        cached = self._load_resolution_from_disk(condition_id)
        if cached:
            return cached

        # Fetch from API
        url = f"{self.gamma_base}/markets"
        data = self._safe_get(url, params={"condition_id": condition_id})

        market = data[0] if data and isinstance(data, list) else None
        if not market or not market.get("closed"):
            return {}

        try:
            prices_raw = market.get("outcomePrices")
            prices = (
                json.loads(prices_raw) if isinstance(prices_raw, str) else prices_raw
            )

            if not prices:
                return {}

            closed_time = market.get("closedTime")
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

            # Save to disk cache
            self._save_resolution_to_disk(condition_id, result)

            return result
        except Exception:
            return {}

    def get_clob_token_ids(self, condition_id: str) -> List[str]:
        """Fetch the CLOB token IDs (Yes/No) for a specific market condition."""
        url = f"{self.gamma_base}/markets"
        data = self._safe_get(url, params={"condition_id": condition_id})
        if data and isinstance(data, list):
            return data[0].get("clobTokenIds", [])
        return []

    def get_price_history(
        self,
        token_id: str,
        start_ts: Optional[int] = None,
        end_ts: Optional[int] = None,
        interval: str = "1h",
        fidelity: int = 1,
    ) -> List[Dict]:
        """Fetch historical prices for a specific token from the CLOB API."""
        url = f"{self.clob_base}/prices-history"
        params = {
            "market": token_id,
            "interval": interval,
            "fidelity": fidelity,
        }
        if start_ts:
            params["start_ts"] = start_ts
        if end_ts:
            params["end_ts"] = end_ts

        data = self._safe_get(url, params=params)
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "history" in data:
            return data.get("history", [])
        return []

    def save_resolution_cache(self):
        """Manually save the resolution cache to disk."""
        pass  # No-op since we write directly to disk

    def get_markets(
        self,
        active: Optional[bool] = None,
        closed: Optional[bool] = None,
        limit: int = 1000,
        condition_id: Optional[str] = None,
    ) -> List[Dict]:
        """Fetch markets with advanced filtering options."""
        url = f"{self.gamma_base}/markets"
        params = {"limit": limit}
        if active is not None:
            params["active"] = active
        if closed is not None:
            params["closed"] = closed
        if condition_id:
            params["condition_id"] = condition_id

        data = self._safe_get(url, params=params)
        return data if isinstance(data, list) else []

    def get_market_info(self, condition_id: str) -> Dict[str, Any]:
        """Fetch market metadata including groupItemTitle for category detection."""
        url = f"{self.gamma_base}/markets"
        data = self._safe_get(url, params={"condition_id": condition_id})

        market = data[0] if data and isinstance(data, list) else None
        if not market:
            return {}

        return {
            "condition_id": condition_id,
            "question": market.get("question", ""),
            "group_item_title": market.get("groupItemTitle", ""),
            "category": market.get("category", ""),
            "description": market.get("description", ""),
            "slug": market.get("slug", ""),
            "volume": market.get("volume", 0),
            "liquidity": market.get("liquidity", 0),
            "active": market.get("active", False),
            "closed": market.get("closed", False),
        }

    def get_events(
        self,
        limit: int = 100,
        cursor: Optional[str] = None,
        active: Optional[bool] = None,
        closed: Optional[bool] = None,
    ) -> List[Dict]:
        """Fetch event groups with proper status filtering."""
        url = f"{self.gamma_base}/events"
        params = {"limit": limit}
        if cursor:
            params["cursor"] = cursor
        if active is not None:
            params["active"] = active
        if closed is not None:
            params["closed"] = closed

        data = self._safe_get(url, params=params)
        if isinstance(data, dict) and "events" in data:
            return data["events"]
        return data if isinstance(data, list) else []

    def get_liquid_events(
        self,
        min_volume: float = 100000,
        limit: int = 50,
    ) -> List[Dict]:
        """OPTIMIZATION: Get only high-volume (liquid) events.

        This filters server-side to only return markets with meaningful volume,
        reducing data transfer and eliminating noise from micro-markets.

        Args:
            min_volume: Minimum 24hr volume (default $100K)
            limit: Max events to return
        """
        url = f"{self.gamma_base}/events"
        params = {
            "limit": limit,
            "active": True,
            "closed": False,
            "volume_min": min_volume,
            "order": "volume_24hr",
            "ascending": False,
        }
        data = self._safe_get(url, params=params)
        # Events endpoint returns list directly
        return data if isinstance(data, list) else []

    def get_active_markets(
        self,
        min_liquidity: float = 50000,
        limit: int = 100,
    ) -> List[Dict]:
        """OPTIMIZATION: Get active markets with minimum liquidity.

        Better than fetching all markets - focuses on tradeable ones.
        """
        url = f"{self.gamma_base}/markets"
        params = {
            "limit": limit,
            "active": True,
            "closed": False,
            "liquidity_num_min": min_liquidity,
            "order": "liquidity",
            "ascending": False,
        }
        data = self._safe_get(url, params=params)
        return data if isinstance(data, list) else []

    def get_recent_trades(self, limit: int = 100) -> List[Dict]:
        """Fetch the absolute latest global trades from Polymarket using GraphQL (faster)."""
        fills = self.graphql.get_recent_fills(limit=limit)

        trades = []
        for fill in fills:
            maker = fill.get("maker", "").lower()

            trades.append(
                {
                    "id": fill.get("id"),
                    "transactionHash": fill.get("transactionHash"),
                    "timestamp": int(fill.get("timestamp", 0)),
                    "address": maker,
                    "side": "buy",
                    "outcomeIndex": fill.get("makerAssetId", "0"),
                    "size": fill.get("makerAmountFilled", "0"),
                    "price": "0.5",
                    "conditionId": fill.get("id", "").split("_")[0]
                    if fill.get("id")
                    else "",
                    "fee": fill.get("fee", "0"),
                }
            )

        return trades

    def close(self):
        """Close the underlying HTTP client session."""
        self.http.close()
        self.graphql.close()
