"""
Sybil Clusterer: Detects shared funding sources on Polygon.
Groups wallets controlled by the same entity using USDC traces.
"""

import logging
from typing import List, Dict, Set, Optional
from collections import defaultdict
from poly.api.polygon_rpc import PolygonRPCClient

logger = logging.getLogger(__name__)

USDC_POLYGON = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"


class SybilClusterer:
    """Detects clusters of coordinated wallets by tracing their on-chain funding origins."""

    def __init__(
        self,
        alchemy_api_key: Optional[str] = None,
        polygonscan_api_key: Optional[str] = None,
    ):
        self.alchemy_api_key = alchemy_api_key
        self.polygonscan_api_key = polygonscan_api_key
        self.funding_cache = {}
        self._rpc_client = None

    def _get_rpc_client(self) -> Optional[PolygonRPCClient]:
        """Lazy-load the Polygon RPC client."""
        if self._rpc_client is None and self.alchemy_api_key:
            self._rpc_client = PolygonRPCClient(self.alchemy_api_key)
        return self._rpc_client

    def get_first_funding_source(self, address: str) -> Optional[Dict]:
        """Find the initial USDC funding transaction for a wallet."""
        addr_lower = address.lower()
        if addr_lower in self.funding_cache:
            return self.funding_cache[addr_lower]

        client = self._get_rpc_client()
        if client:
            try:
                funding = client.get_first_usdc_funding(address)
                if funding:
                    self.funding_cache[addr_lower] = funding
                    return funding
            except Exception as e:
                logger.error(f"Funding trace failed for {address}: {e}")

        return None

    def detect_clusters(self, profiles: List[Dict]) -> List[Dict]:
        """Identifies wallet clusters sharing identical funding sources."""
        if not self.alchemy_api_key:
            logger.warning("No Alchemy API key; clustering will be limited.")
            return self._placeholder_clustering(profiles)

        source_groups = defaultdict(list)
        
        # Phase 1: Group addresses by source
        for p in profiles:
            addr = p.get("address")
            if not addr: continue
            
            funding = self.get_first_funding_source(addr)
            source = funding.get("from", "unknown").lower() if funding else "unknown"
            source_groups[source].append(addr.lower())

        # Phase 2: Assign cluster metadata to profiles
        for p in profiles:
            addr = p.get("address", "").lower()
            funding = self.funding_cache.get(addr)
            source = funding.get("from", "unknown") if funding else "unknown"
            
            cluster_id = source[:10] if source != "unknown" else "unknown"
            cluster_size = len(source_groups.get(source.lower(), []))
            
            p.update({
                "cluster_id": cluster_id,
                "cluster_source": source if source != "unknown" else None,
                "cluster_size": cluster_size,
                "cluster_bonus": 0.5 if (cluster_size > 2 and source != "unknown") else 0.0
            })

            if cluster_size > 5 and source != "unknown":
                p["cluster_warning"] = f"Suspected Sybil Cluster ({cluster_size} wallets)"

        return profiles

    def _placeholder_clustering(self, profiles: List[Dict]) -> List[Dict]:
        """Simple prefix-based clustering for environments without RPC access."""
        for p in profiles:
            addr = p.get("address", "unknown")
            p.update({
                "cluster_id": addr[:10],
                "cluster_size": 1,
                "cluster_source": None
            })
        return profiles

    def close(self):
        """Clean up RPC resources."""
        if self._rpc_client:
            self._rpc_client.close()
            self._rpc_client = None
