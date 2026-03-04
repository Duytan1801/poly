"""
GraphQL Client for Polymarket Subgraphs (Goldsky).
Provides high-speed access to on-chain data via GraphQL endpoints.
"""

import logging
import time
import httpx
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

SUBGRAPH_ENDPOINTS = {
    "orders": "https://api.goldsky.com/api/public/project_cl6mb8i9h0003e201j6li0diw/subgraphs/orderbook-subgraph/0.0.1/gn",
    "pnl": "https://api.goldsky.com/api/public/project_cl6mb8i9h0003e201j6li0diw/subgraphs/pnl-subgraph/0.0.14/gn",
    "positions": "https://api.goldsky.com/api/public/project_cl6mb8i9h0003e201j6li0diw/subgraphs/positions-subgraph/0.0.7/gn",
    "activity": "https://api.goldsky.com/api/public/project_cl6mb8i9h0003e201j6li0diw/subgraphs/activity-subgraph/0.0.4/gn",
    "oi": "https://api.goldsky.com/api/public/project_cl6mb8i9h0003e201j6li0diw/subgraphs/oi-subgraph/0.0.6/gn",
}


class GraphQLClient:
    """Unified GraphQL client for all Polymarket subgraphs."""

    def __init__(self, timeout: float = 60.0):
        self.http = httpx.Client(
            timeout=httpx.Timeout(timeout, connect=30.0, read=120.0)
        )

    def _query(
        self,
        subgraph: str,
        query: str,
        variables: Optional[Dict] = None,
        max_retries: int = 3,
    ) -> Optional[Dict]:
        """Execute a GraphQL query with retry logic."""
        url = SUBGRAPH_ENDPOINTS.get(subgraph)
        if not url:
            logger.error(f"Unknown subgraph: {subgraph}")
            return None

        backoff = 1.0
        for attempt in range(max_retries):
            try:
                resp = self.http.post(
                    url,
                    json={"query": query, "variables": variables}
                    if variables
                    else {"query": query},
                    headers={"Content-Type": "application/json"},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if "errors" in data:
                        logger.warning(f"GraphQL errors: {data['errors']}")
                        return None
                    return data.get("data")
                elif resp.status_code == 429:
                    time.sleep(backoff)
                    backoff *= 2
                    continue
                else:
                    logger.warning(f"Request failed with status {resp.status_code}")
            except Exception as e:
                logger.error(f"Network error: {e}")
                time.sleep(backoff)
                backoff *= 2
        return None

    def get_trader_fills(
        self,
        address: str,
        limit: int = 500,
        offset: int = 0,
        start_timestamp: Optional[int] = None,
        end_timestamp: Optional[int] = None,
    ) -> List[Dict]:
        """Fetch order fill events for a trader (as maker or taker)."""
        address = address.lower()

        where_parts = []
        if start_timestamp:
            where_parts.append(f"timestamp_gte: {start_timestamp}")
        if end_timestamp:
            where_parts.append(f"timestamp_lte: {end_timestamp}")

        where_str = ", ".join(where_parts) if where_parts else ""

        query = f"""
        {{
            orderFilledEvents(
                where: {{ maker: "{address}" {", " + where_str if where_str else ""} }},
                first: {limit},
                skip: {offset},
                orderBy: timestamp,
                orderDirection: desc
            ) {{
                id
                transactionHash
                timestamp
                maker
                taker
                makerAssetId
                takerAssetId
                makerAmountFilled
                takerAmountFilled
                fee
            }}
        }}
        """

        data = self._query("orders", query)
        maker_events = data.get("orderFilledEvents", []) if data else []

        query = f"""
        {{
            orderFilledEvents(
                where: {{ taker: "{address}" {", " + where_str if where_str else ""} }},
                first: {limit},
                skip: {offset},
                orderBy: timestamp,
                orderDirection: desc
            ) {{
                id
                transactionHash
                timestamp
                maker
                taker
                makerAssetId
                takerAssetId
                makerAmountFilled
                takerAmountFilled
                fee
            }}
        }}
        """

        data = self._query("orders", query)
        taker_events = data.get("orderFilledEvents", []) if data else []

        all_events = maker_events + taker_events
        all_events.sort(key=lambda x: int(x.get("timestamp", 0)), reverse=True)

        return all_events[:limit]

    def get_trader_trade_count(self, address: str) -> int:
        """Get total trade count for a trader using GraphQL."""
        address = address.lower()

        query = f"""
        {{
            orderFilledEvents(
                where: {{ maker: "{address}" }},
                first: 1,
                orderBy: timestamp,
                orderDirection: desc
            ) {{
                timestamp
            }}
        }}
        """

        data = self._query("orders", query)
        if not data:
            return 0

        events = data.get("orderFilledEvents", [])
        if not events:
            return 0

        oldest_ts = events[0].get("timestamp")
        if not oldest_ts:
            return 0

        query_count = f"""
        {{
            orderFilledEvents(
                where: {{ maker: "{address}", timestamp_lte: "{oldest_ts}" }},
                first: 1000,
                skip: 0,
                orderBy: timestamp,
                orderDirection: asc
            ) {{
                id
            }}
        }}
        """

        total = 0
        current_offset = 0
        batch_size = 1000

        while True:
            query_batch = f"""
            {{
                orderFilledEvents(
                    where: {{ maker: "{address}" }},
                    first: {batch_size},
                    skip: {current_offset},
                    orderBy: timestamp,
                    orderDirection: asc
                ) {{
                    id
                }}
            }}
            """
            data = self._query("orders", query_batch)
            if not data:
                break
            events = data.get("orderFilledEvents", [])
            if not events:
                break
            total += len(events)
            current_offset += batch_size
            if len(events) < batch_size:
                break

        return total

    def get_user_positions(self, address: str) -> List[Dict]:
        """Get user positions with PnL data from PNL subgraph."""
        address = address.lower()

        query = f"""
        {{
            userPositions(
                where: {{ user: "{address}" }},
                first: 1000
            ) {{
                id
                user
                tokenId
                amount
                avgPrice
                realizedPnl
                totalBought
            }}
        }}
        """

        data = self._query("pnl", query)
        if not data:
            return []
        return data.get("userPositions", [])

    def get_recent_fills(self, limit: int = 100) -> List[Dict]:
        """Get recent order fills globally."""
        query = f"""
        {{
            orderFilledEvents(
                first: {limit},
                orderBy: timestamp,
                orderDirection: desc
            ) {{
                id
                transactionHash
                timestamp
                maker
                taker
                makerAssetId
                takerAssetId
                makerAmountFilled
                takerAmountFilled
                fee
            }}
        }}
        """

        data = self._query("orders", query)
        if not data:
            return []
        return data.get("orderFilledEvents", [])

    def get_user_redemptions(
        self,
        address: str,
        limit: int = 100,
    ) -> List[Dict]:
        """Get user redemption history."""
        address = address.lower()

        query = f"""
        {{
            redemptions(
                where: {{ redeemer: "{address}" }},
                first: {limit},
                orderBy: timestamp,
                orderDirection: desc
            ) {{
                id
                timestamp
                redeemer
                condition
                indexSets
                payout
            }}
        }}
        """

        data = self._query("activity", query)
        if not data:
            return []
        return data.get("redemptions", [])

    def get_condition_payouts(self, condition_id: str) -> Optional[str]:
        """Get payout vector for a condition (for determining winner)."""
        query = f"""
        {{
            conditions(
                where: {{ id: "{condition_id}" }},
                first: 1
            ) {{
                id
                payouts
            }}
        }}
        """

        data = self._query("positions", query)
        if not data:
            return None
        conditions = data.get("conditions", [])
        if not conditions:
            return None
        return conditions[0].get("payouts")

    def get_latest_events(self, limit: int = 100) -> List[Dict]:
        """Get latest order filled events for discovery."""
        query = f"""
        {{
            orderFilledEvents(
                first: {limit},
                orderBy: timestamp,
                orderDirection: desc
            ) {{
                id
                maker
                taker
                timestamp
            }}
        }}
        """

        data = self._query("orders", query)
        if not data:
            return []
        return data.get("orderFilledEvents", [])

    def close(self):
        """Close the HTTP client."""
        self.http.close()
