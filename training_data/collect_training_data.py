"""
Training Data Collector: Gather insider/non-insider trader profiles for ML training.

Collects:
- 300 CRITICAL traders (insiders) - high-signal targets
- 300 LOW traders (normal) - baseline non-insiders

Outputs:
- training_data/insider_profiles.json (CRITICAL)
- training_data/normal_profiles.json (LOW)
- training_data/combined_for_training.json (mixed)
"""

import os
import sys
import json
import time
import argparse
import logging
from datetime import datetime
from typing import List, Dict, Set, Optional
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.poly.api.polymarket import PolymarketClient
from src.poly.intelligence.scorer import InsiderScorerV4
from src.poly.intelligence.clustering import WalletClusterDetector

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

OUTPUT_DIR = "training_data"
os.makedirs(OUTPUT_DIR, exist_ok=True)


class TrainingDataCollector:
    """Collect labeled trader profiles for ML training."""

    def __init__(
        self,
        target_insiders: int = 300,
        target_normal: int = 300,
        max_iterations: int = 50,
        workers: int = 10,
    ):
        self.target_insiders = target_insiders
        self.target_normal = target_normal
        self.max_iterations = max_iterations
        self.workers = workers

        self.client = PolymarketClient(timeout=120.0)
        self.scorer = InsiderScorerV4(use_ml=False)  # Rule-based for labeling
        self.cluster_detector = WalletClusterDetector()

        self.insider_profiles: List[Dict] = []
        self.normal_profiles: List[Dict] = []
        self.all_profiles: List[Dict] = []

    def run(self) -> Dict:
        """Main collection loop."""
        logger.info(
            f"Starting collection: target {self.target_insiders} insiders, {self.target_normal} normal"
        )
        logger.info(f"Max iterations: {self.max_iterations}")

        iteration = 0
        start_time = time.time()

        while iteration < self.max_iterations:
            iteration += 1

            if (
                len(self.insider_profiles) >= self.target_insiders
                and len(self.normal_profiles) >= self.target_normal
            ):
                logger.info("Collection complete! Reached targets.")
                break

            logger.info(f"\n=== Iteration {iteration}/{self.max_iterations} ===")
            logger.info(
                f"Current: {len(self.insider_profiles)} insiders, {len(self.normal_profiles)} normal"
            )

            try:
                # Collect new traders
                new_profiles = self._collect_traders_batch(iteration)

                if not new_profiles:
                    logger.warning("No new profiles collected, continuing...")
                    continue

                # Score all profiles
                scored_profiles = self.scorer.fit_and_score(new_profiles)

                # Cluster detection
                trades_by_wallet = self._get_trades_by_wallet(scored_profiles)
                scored_profiles = self.cluster_detector.detect_clusters(
                    scored_profiles, trades_by_wallet
                )

                # Separate by level
                for p in scored_profiles:
                    level = p.get("level", "LOW")
                    if (
                        level == "CRITICAL"
                        and len(self.insider_profiles) < self.target_insiders
                    ):
                        self.insider_profiles.append(p)
                        self.all_profiles.append({**p, "label": 1})
                    elif (
                        level == "LOW"
                        and len(self.normal_profiles) < self.target_normal
                    ):
                        self.normal_profiles.append(p)
                        self.all_profiles.append({**p, "label": 0})

                logger.info(f"  Collected: {len(scored_profiles)} profiles")
                logger.info(
                    f"  Insiders: {len(self.insider_profiles)}/{self.target_insiders}"
                )
                logger.info(
                    f"  Normal: {len(self.normal_profiles)}/{self.target_normal}"
                )

            except Exception as e:
                logger.error(f"Iteration {iteration} failed: {e}")
                continue

        elapsed = time.time() - start_time

        # Save results
        summary = self._save_data(elapsed)

        return summary

    def _collect_traders_batch(self, iteration: int) -> List[Dict]:
        """Collect a batch of trader profiles."""
        profiles = []

        try:
            # Get recent traders from leaderboard
            leaderboard_traders = self._get_leaderboard_traders()

            # Get traders from active markets
            active_traders = self._get_active_market_traders()

            # Combine and dedupe
            all_traders = list(set(leaderboard_traders + active_traders))

            logger.info(f"  Found {len(all_traders)} unique traders")

            # Get full history for each trader
            for i, trader in enumerate(all_traders):
                if i >= self.workers:
                    break

                try:
                    profile = self._build_trader_profile(trader)
                    if profile:
                        profiles.append(profile)
                except Exception as e:
                    logger.debug(f"Failed to get profile for {trader[:10]}...: {e}")
                    continue

        except Exception as e:
            logger.error(f"Batch collection failed: {e}")

        return profiles

    def _get_leaderboard_traders(self) -> List[str]:
        """Get top traders from leaderboard."""
        traders = []

        for category in ["OVERALL", "POLITICS", "SCIENCE", "ECONOMICS"]:
            try:
                leaderboard = self.client.get_leaderboard(
                    category=category, period="MONTH", limit=100
                )

                for entry in leaderboard:
                    addr = entry.get("proxyWallet") or entry.get("address")
                    if addr:
                        traders.append(addr.lower())

            except Exception as e:
                logger.debug(f"Failed to get leaderboard for {category}: {e}")
                continue

        return list(set(traders))

    def _get_active_market_traders(self) -> List[str]:
        """Get traders from active markets."""
        traders = set()

        try:
            # Get recent trades via GraphQL
            fills = self.client.graphql.get_recent_fills(limit=500)

            for fill in fills:
                maker = fill.get("maker", "").lower()
                taker = fill.get("taker", "").lower()

                if maker:
                    traders.add(maker)
                if taker:
                    traders.add(taker)

        except Exception as e:
            logger.debug(f"Failed to get active traders: {e}")

        return list(traders)

    def _build_trader_profile(self, address: str) -> Optional[Dict]:
        """Build a complete profile for a trader."""
        address = address.lower()

        try:
            # Get trade history
            trades = self.client.get_full_trader_history(address, max_trades=5000)

            if not trades:
                return None

            # Get positions
            positions = self.client.get_positions(address)

            # Get trader PnL from leaderboard
            pnl_data = self.client.get_trader_pnl_from_leaderboard(address)
            pnl = pnl_data.get("pnl", 0) if pnl_data else 0

            # Calculate metrics
            winrate = self._calculate_winrate(trades)
            total_trades = len(trades)

            # Timing analysis
            timing = self._analyze_timing(trades)

            # Whale analysis
            whales = self._analyze_whales(trades)

            # Multi-market analysis
            multi_market = self._analyze_markets(trades)

            # Calculate freshness
            timestamps = [t.get("timestamp", 0) for t in trades]
            first_ts = min(timestamps) if timestamps else 0
            last_ts = max(timestamps) if timestamps else 0

            # Trade sizes
            sizes = [float(t.get("size", 0)) for t in trades]
            avg_size = sum(sizes) / len(sizes) if sizes else 0
            max_size = max(sizes) if sizes else 0

            profile = {
                "address": address,
                "total_trades": total_trades,
                "total_trades_actual": total_trades,
                "winrate": winrate,
                "pnl": pnl,
                "positions": positions,
                "timing": timing,
                "whales": whales,
                "multi_market": multi_market,
                "first_trade_timestamp": first_ts,
                "last_trade_timestamp": last_ts,
                "avg_trade_size": avg_size,
                "max_trade_size": max_size,
                "total_volume": sum(sizes),
                "trades": trades[:100],  # Save first 100 for reference
            }

            return profile

        except Exception as e:
            logger.debug(f"Failed to build profile for {address[:10]}...: {e}")
            return None

    def _calculate_winrate(self, trades: List[Dict]) -> float:
        """Calculate trader winrate."""
        if not trades:
            return 0.5

        wins = 0
        for t in trades:
            if t.get("outcome") == "Yes" and t.get("outcomeIndex") == 1:
                wins += 1
            elif t.get("outcome") == "No" and t.get("outcomeIndex") == 0:
                wins += 1

        return wins / len(trades) if trades else 0.5

    def _analyze_timing(self, trades: List[Dict]) -> Dict:
        """Analyze trade timing patterns."""
        if not trades:
            return {"last_minute_ratio": 0, "pre_resolution_ratio": 0}

        last_minute = 0
        pre_resolution = 0
        timestamps = []

        for t in trades:
            ts = t.get("timestamp", 0)
            if ts:
                timestamps.append(ts)
                # Simplified timing (in real implementation, check against market resolution)
                if ts > time.time() - 86400:  # Last 24h
                    last_minute += 1
                pre_resolution += 1

        return {
            "last_minute_ratio": last_minute / len(trades) if trades else 0,
            "pre_resolution_ratio": pre_resolution / len(trades) if trades else 0,
            "avg_hours_before_resolution": 48,  # Placeholder
        }

    def _analyze_whales(self, trades: List[Dict]) -> Dict:
        """Analyze whale trading patterns."""
        if not trades:
            return {"max_market_share": 0}

        sizes = [float(t.get("size", 0)) for t in trades]
        total_size = sum(sizes)

        if total_size == 0:
            return {"max_market_share": 0}

        # Group by market
        market_sizes = defaultdict(float)
        for t in trades:
            cid = t.get("conditionId", "unknown")
            market_sizes[cid] += float(t.get("size", 0))

        max_share = max(market_sizes.values()) / total_size if market_sizes else 0

        return {
            "max_market_share": max_share,
            "avg_trade_size": sum(sizes) / len(sizes),
            "big_trades": len([s for s in sizes if s > 1000]),
        }

    def _analyze_markets(self, trades: List[Dict]) -> Dict:
        """Analyze market diversity."""
        if not trades:
            return {"unique_markets": 0}

        markets = set()
        for t in trades:
            cid = t.get("conditionId")
            if cid:
                markets.add(cid)

        return {
            "unique_markets": len(markets),
            "categories": {},  # Would need market info
        }

    def _get_trades_by_wallet(self, profiles: List[Dict]) -> Dict[str, List[Dict]]:
        """Extract trades by wallet for clustering."""
        trades_by_wallet = {}

        for p in profiles:
            addr = p.get("address", "").lower()
            trades = p.get("trades", [])
            if addr and trades:
                trades_by_wallet[addr] = trades

        return trades_by_wallet

    def _save_data(self, elapsed: float) -> Dict:
        """Save collected data."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Save insiders
        insider_file = os.path.join(OUTPUT_DIR, f"insider_profiles_{timestamp}.json")
        with open(insider_file, "w") as f:
            json.dump(self.insider_profiles, f, indent=2, default=str)
        logger.info(f"Saved {len(self.insider_profiles)} insiders to {insider_file}")

        # Save normal
        normal_file = os.path.join(OUTPUT_DIR, f"normal_profiles_{timestamp}.json")
        with open(normal_file, "w") as f:
            json.dump(self.normal_profiles, f, indent=2, default=str)
        logger.info(f"Saved {len(self.normal_profiles)} normal to {normal_file}")

        # Save combined
        combined_file = os.path.join(OUTPUT_DIR, "combined_for_training.json")
        with open(combined_file, "w") as f:
            json.dump(self.all_profiles, f, indent=2, default=str)
        logger.info(f"Saved {len(self.all_profiles)} total profiles to {combined_file}")

        summary = {
            "timestamp": timestamp,
            "config": {
                "target_insiders": self.target_insiders,
                "target_normal": self.target_normal,
                "max_iterations": self.max_iterations,
            },
            "stats": {
                "insiders_collected": len(self.insider_profiles),
                "normal_collected": len(self.normal_profiles),
                "total": len(self.all_profiles),
                "elapsed_seconds": elapsed,
            },
            "files": {
                "insider": insider_file,
                "normal": normal_file,
                "combined": combined_file,
            },
        }

        summary_file = os.path.join(OUTPUT_DIR, "collection_summary.json")
        with open(summary_file, "w") as f:
            json.dump(summary, f, indent=2)
        logger.info(f"Saved summary to {summary_file}")

        return summary


def parse_args():
    parser = argparse.ArgumentParser(
        description="Collect training data for insider detection"
    )

    parser.add_argument(
        "--insiders",
        type=int,
        default=300,
        help="Target number of insider (CRITICAL) profiles",
    )
    parser.add_argument(
        "--normal",
        type=int,
        default=300,
        help="Target number of normal (LOW) profiles",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=50,
        help="Maximum collection iterations",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=10,
        help="Traders to process per iteration",
    )

    return parser.parse_args()


def main():
    args = parse_args()

    collector = TrainingDataCollector(
        target_insiders=args.insiders,
        target_normal=args.normal,
        max_iterations=args.iterations,
        workers=args.workers,
    )

    summary = collector.run()

    print("\n" + "=" * 50)
    print("COLLECTION COMPLETE")
    print("=" * 50)
    print(
        f"Insiders: {summary['stats']['insiders_collected']}/{summary['config']['target_insiders']}"
    )
    print(
        f"Normal: {summary['stats']['normal_collected']}/{summary['config']['target_normal']}"
    )
    print(f"Total: {summary['stats']['total']}")
    print(f"Time: {summary['stats']['elapsed_seconds']:.1f}s")
    print(f"\nOutput: {summary['files']['combined']}")


if __name__ == "__main__":
    main()
