"""
Insider Trade Collector: Gather training data for insider trading detection model.

Collects trades in a time window (10min - 1day) BEFORE a market resolves.
If the trader correctly predicted the winner, label as potential insider.
"""

import os
import sys
import json
import time
import argparse
import logging
from datetime import datetime
from typing import List, Dict, Optional
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from src.poly.api.polymarket import PolymarketClient

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(DATA_DIR, exist_ok=True)


class InsiderTradeCollector:
    """Collect trades before market resolution for insider trading detection."""

    def __init__(
        self,
        time_windows_minutes: List[int] = None,
        min_volume: float = 100000,
        output_file: str = None,
    ):
        if time_windows_minutes is None:
            time_windows_minutes = [10, 30, 60, 1440]
        if output_file is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = os.path.join(DATA_DIR, f"insider_trades_{timestamp}.json")

        self.client = PolymarketClient()
        self.time_windows_minutes = time_windows_minutes
        self.min_volume = min_volume
        self.output_file = output_file
        self.collected_trades: List[Dict] = []
        self.resolved_markets: List[Dict] = []

    def get_resolved_markets(self, limit: int = 50) -> List[Dict]:
        """Get recently resolved markets with high volume."""
        markets = self.client.get_markets(closed=True, limit=limit * 2)

        resolved = []
        for m in markets:
            volume = m.get("volumeNum", m.get("volume", 0))
            if volume >= self.min_volume:
                clob_ids = m.get("clobTokenIds", "")
                if isinstance(clob_ids, str):
                    try:
                        clob_ids = json.loads(clob_ids)
                    except:
                        continue

                if clob_ids and len(clob_ids) >= 2:
                    resolved.append(
                        {
                            **m,
                            "token_ids": clob_ids,
                            "volume": volume,
                        }
                    )

        return resolved[:limit]

    def get_market_resolution(self, condition_id: str) -> Optional[Dict]:
        """Get how a market resolved (which outcome won)."""
        result = self.client.get_market_resolution_state(condition_id)
        if not result:
            return None

        question = result.get("question", "")
        winner_idx = result.get("winner_idx", 0)

        return {
            "condition_id": condition_id,
            "winner_idx": winner_idx,
            "question": question,
            "resolved_at": result.get("closed_at", 0),
        }

    def collect_trades_before_resolution(
        self, market: Dict, resolution: Dict, trader: str
    ) -> List[Dict]:
        """Collect trades by a trader before market resolution."""
        resolved_ts = resolution.get("resolved_at", 0)
        if not resolved_ts:
            return []

        collected = []

        for window_min in self.time_windows_minutes:
            window_start = resolved_ts - (window_min * 60)
            window_end = resolved_ts - 60

            if window_start < 0:
                continue

            trades = self.client.get_trader_history(
                address=trader,
                start=int(window_start),
                end=int(window_end),
                limit=1000,
            )

            for trade in trades:
                outcome_idx = trade.get("outcomeIndex", 0)
                if isinstance(outcome_idx, str):
                    try:
                        outcome_idx = int(outcome_idx)
                    except:
                        outcome_idx = 0

                won = 1 if outcome_idx == resolution.get("winner_idx", -1) else 0

                collected.append(
                    {
                        **trade,
                        "market_condition_id": market.get("conditionId", ""),
                        "market_question": resolution.get("question", ""),
                        "resolution_timestamp": resolved_ts,
                        "winner_idx": resolution.get("winner_idx", -1),
                        "trader_outcome_idx": outcome_idx,
                        "won_trade": won,
                        "time_before_resolution_min": window_min,
                        "volume": market.get("volume", 0),
                    }
                )

        return collected

    def get_traders_for_market(self, condition_id: str) -> List[str]:
        """Get traders who traded in a specific market."""
        fills = self.client.graphql.get_recent_fills(limit=1000)

        traders = set()
        for fill in fills:
            maker = fill.get("maker", "").lower()
            taker = fill.get("taker", "").lower()
            if maker:
                traders.add(maker)
            if taker:
                traders.add(taker)

        return list(traders)[:100]

    def collect_for_market(
        self, market: Dict, resolution: Dict, max_traders: int = 50
    ) -> int:
        """Collect trade data for a single resolved market."""
        condition_id = market.get("conditionId")
        traders = self.get_traders_for_market(condition_id)

        total_collected = 0

        for trader in traders[:max_traders]:
            trades_before = self.collect_trades_before_resolution(
                market, resolution, trader
            )

            if trades_before:
                self.collected_trades.extend(trades_before)
                total_collected += len(trades_before)

            time.sleep(0.05)

        return total_collected

    def run(self, max_markets: int = 20, max_trades: int = 1000000) -> Dict:
        """Main collection loop."""
        logger.info(f"Starting collection (target: {max_trades} trades)")
        logger.info(f"Time windows: {self.time_windows_minutes} minutes")
        logger.info(f"Min volume: ${self.min_volume:,}")

        markets = self.get_resolved_markets(limit=max_markets)
        logger.info(f"Found {len(markets)} resolved markets with sufficient volume")

        start_time = time.time()

        for i, market in enumerate(markets):
            if len(self.collected_trades) >= max_trades:
                break

            condition_id = market.get("conditionId", "")
            question = market.get("question", "")[:50]

            logger.info(f"Processing market {i + 1}/{len(markets)}: {question}...")

            resolution = self.get_market_resolution(condition_id)
            if not resolution:
                logger.warning(f"Could not get resolution for {condition_id}")
                continue

            logger.info(
                f"  Winner: outcome {resolution.get('winner_idx')}, resolved at {resolution.get('resolved_at')}"
            )
            self.resolved_markets.append(
                {**resolution, "volume": market.get("volume", 0)}
            )

            collected = self.collect_for_market(market, resolution, max_traders=30)
            logger.info(f"  Collected {collected} trades")

            time.sleep(0.2)

        elapsed = time.time() - start_time

        summary = {
            "config": {
                "time_windows_minutes": self.time_windows_minutes,
                "min_volume": self.min_volume,
                "max_markets": max_markets,
                "max_trades": max_trades,
            },
            "stats": {
                "total_trades_collected": len(self.collected_trades),
                "resolved_markets": len(self.resolved_markets),
                "elapsed_seconds": elapsed,
                "winning_trades": sum(
                    1 for t in self.collected_trades if t.get("won_trade", 0) == 1
                ),
            },
            "output_file": self.output_file,
        }

        self._save_data(summary)

        logger.info(f"Collection complete!")
        logger.info(f"Total trades: {len(self.collected_trades)}")
        logger.info(f"Resolved markets: {len(self.resolved_markets)}")
        logger.info(f"Winning trades: {summary['stats']['winning_trades']}")
        logger.info(f"Elapsed: {elapsed:.1f}s")
        logger.info(f"Saved to: {self.output_file}")

        return summary

    def _save_data(self, summary: Dict):
        """Save collected data to JSON file."""
        output = {
            "summary": summary,
            "trades": self.collected_trades,
            "markets": self.resolved_markets,
        }

        with open(self.output_file, "w") as f:
            json.dump(output, f, indent=2, default=str)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Collect insider trading training data"
    )

    parser.add_argument(
        "--windows",
        type=str,
        default="10,30,60,1440",
        help="Comma-separated time windows in minutes",
    )
    parser.add_argument(
        "--min-volume",
        type=float,
        default=100000,
        help="Minimum market volume",
    )
    parser.add_argument(
        "--max-markets",
        type=int,
        default=20,
        help="Maximum markets to process",
    )
    parser.add_argument(
        "--max-trades",
        type=int,
        default=1000000,
        help="Target number of trades",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output file path",
    )

    return parser.parse_args()


def main():
    args = parse_args()

    windows = [int(x.strip()) for x in args.windows.split(",")]

    collector = InsiderTradeCollector(
        time_windows_minutes=windows,
        min_volume=args.min_volume,
        output_file=args.output,
    )

    summary = collector.run(
        max_markets=args.max_markets,
        max_trades=args.max_trades,
    )

    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
