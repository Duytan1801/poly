"""
Wallet Cluster Detection: Identifies coordinated trader groups.

Methods:
1. On-chain funding tracing (USDC deposits)
2. Trade timing correlation
3. Coordinated trade detection
4. Gas fee pattern matching
5. Position similarity analysis
"""

import logging
import numpy as np
from typing import List, Dict, Set, Optional, Tuple
from collections import defaultdict
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class WalletClusterDetector:
    """
    Detects clusters of coordinated wallets using multiple signals.

    Signals:
    1. On-chain funding (USDC traces)
    2. Trade timing correlation (trades within seconds of each other)
    3. Coordinated entries (same market, similar size, similar time)
    4. Gas fee patterns (similar pricing = same sender)
    """

    def __init__(self, timing_window_seconds: int = 60):
        self.timing_window_seconds = timing_window_seconds
        self.funding_cache = {}

    def detect_clusters(
        self,
        profiles: List[Dict],
        trades_by_wallet: Optional[Dict[str, List[Dict]]] = None,
    ) -> List[Dict]:
        """
        Identify wallet clusters.

        Args:
            profiles: List of trader profiles
            trades_by_wallet: Optional dict mapping address -> list of trades

        Returns:
            Profiles with cluster metadata added
        """
        if not profiles:
            return profiles

        # Add cluster metadata to each profile
        for p in profiles:
            p.setdefault("cluster_id", None)
            p.setdefault("cluster_size", 1)
            p.setdefault("related_wallets", [])
            p.setdefault("coordinated_trades", 0)

        # If we have trade data, do advanced clustering
        if trades_by_wallet:
            profiles = self._cluster_by_trading_patterns(profiles, trades_by_wallet)

        return profiles

    def _cluster_by_trading_patterns(
        self,
        profiles: List[Dict],
        trades_by_wallet: Dict[str, List[Dict]],
    ) -> List[Dict]:
        """Detect clusters based on trading patterns."""

        # Build address -> profile mapping
        addr_to_profile = {}
        for p in profiles:
            addr = p.get("address", "").lower()
            if addr:
                addr_to_profile[addr] = p

        # Find correlated trades
        correlation_scores = self._find_timing_correlations(trades_by_wallet)

        # Group correlated wallets
        clusters = self._build_clusters(correlation_scores)

        # Assign cluster metadata
        for cluster_id, wallet_list in clusters.items():
            if len(wallet_list) < 2:
                continue

            for addr in wallet_list:
                if addr in addr_to_profile:
                    p = addr_to_profile[addr]
                    p["cluster_id"] = f"cluster_{cluster_id}"
                    p["cluster_size"] = len(wallet_list)
                    p["related_wallets"] = [w for w in wallet_list if w != addr]
                    p["coordinated_trades"] = correlation_scores.get(addr, {}).get(
                        "coordinated_count", 0
                    )

        return profiles

    def _find_timing_correlations(
        self,
        trades_by_wallet: Dict[str, List[Dict]],
    ) -> Dict[str, Dict]:
        """
        Find wallets with correlated trading times.

        Returns dict mapping address -> {correlated_addresses, coordinated_count}
        """
        correlations = defaultdict(
            lambda: {
                "correlated_addresses": [],
                "coordinated_count": 0,
            }
        )

        wallet_times = {}
        for addr, trades in trades_by_wallet.items():
            times = []
            for t in trades:
                ts = t.get("timestamp")
                if ts:
                    times.append(int(ts))
            if times:
                wallet_times[addr] = sorted(times)

        # Compare each pair of wallets
        wallet_list = list(wallet_times.keys())
        for i, w1 in enumerate(wallet_list):
            for w2 in wallet_list[i + 1 :]:
                coordinated = self._count_coordinated_trades(
                    wallet_times[w1],
                    wallet_times[w2],
                    self.timing_window_seconds,
                )

                if coordinated >= 3:  # Minimum threshold
                    correlations[w1]["correlated_addresses"].append(w2)
                    correlations[w1]["coordinated_count"] += coordinated
                    correlations[w2]["correlated_addresses"].append(w1)
                    correlations[w2]["coordinated_count"] += coordinated

        return dict(correlations)

    def _count_coordinated_trades(
        self,
        times1: List[int],
        times2: List[int],
        window_seconds: int,
    ) -> int:
        """Count trades within timing window of each other."""
        if not times1 or not times2:
            return 0

        coordinated = 0
        for t1 in times1:
            for t2 in times2:
                if abs(t1 - t2) <= window_seconds:
                    coordinated += 1

        return coordinated

    def _build_clusters(
        self,
        correlation_scores: Dict[str, Dict],
    ) -> Dict[int, List[str]]:
        """Build clusters from correlation scores using simple grouping."""
        clusters = {}
        cluster_id = 0
        processed = set()

        for addr, data in correlation_scores.items():
            if addr in processed:
                continue

            # BFS to find all connected wallets
            cluster = {addr}
            queue = [addr]

            while queue:
                current = queue.pop(0)
                if current in processed:
                    continue
                processed.add(current)

                correlated = correlation_scores.get(current, {}).get(
                    "correlated_addresses", []
                )
                for c in correlated:
                    if c not in cluster:
                        cluster.add(c)
                        queue.append(c)

            if len(cluster) > 1:
                clusters[cluster_id] = list(cluster)
                cluster_id += 1

        return clusters

    def calculate_cluster_score(
        self,
        related_wallets: int,
        coordinated_trades: int,
        cluster_size: int,
    ) -> float:
        """
        Calculate cluster-based risk score.

        Returns:
            Score 0-2.5 based on cluster characteristics
        """
        if related_wallets == 0:
            return 0.0

        score = 0.0

        # Size bonus
        if cluster_size >= 5:
            score += 1.5
        elif cluster_size >= 3:
            score += 1.0
        elif cluster_size >= 2:
            score += 0.5

        # Coordination bonus
        if coordinated_trades >= 10:
            score += 1.0
        elif coordinated_trades >= 5:
            score += 0.5

        return min(2.5, score)


class FundingClusterDetector:
    """
    On-chain funding based cluster detection.

    Traces USDC deposits to identify wallets funded by same source.
    """

    def __init__(self):
        self.funding_cache = {}

    def detect_by_funding(
        self,
        profiles: List[Dict],
        funding_sources: Dict[str, Dict],
    ) -> List[Dict]:
        """
        Detect clusters based on funding source.

        Args:
            profiles: Trader profiles
            funding_sources: Dict mapping address -> {from_address, tx_hash, amount}
        """
        # Group by funding source
        source_groups = defaultdict(list)
        for addr, funding in funding_sources.items():
            source = funding.get("from", "unknown").lower()
            source_groups[source].append(addr.lower())

        # Assign cluster metadata
        for p in profiles:
            addr = p.get("address", "").lower()
            funding = funding_sources.get(addr, {})

            source = funding.get("from", "unknown")
            cluster_id = f"funding_{source[:12]}" if source != "unknown" else None

            p["cluster_id"] = cluster_id
            p["cluster_size"] = len(source_groups.get(source.lower(), [addr]))
            p["cluster_source"] = source if source != "unknown" else None

        return profiles


# Backwards compatibility
SybilClusterer = WalletClusterDetector
