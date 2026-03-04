"""
Scalable trade collector for 1M+ trades
Collects trades in batches and saves to parquet
"""

import logging
import pandas as pd
import pickle
from pathlib import Path
from typing import Dict, List, Set, Optional
from datetime import datetime

from poly.api.polymarket import PolymarketClient
from poly.collection.analyzer import get_qualified_traders, get_top_roi_traders

logger = logging.getLogger(__name__)


class TradeCollector:
    """
    Scalable trade collector.
    Collects trades in batches, saves to parquet incrementally.
    """

    def __init__(
        self,
        client: Optional[PolymarketClient] = None,
        data_dir: str = "data/raw",
        batch_size: int = 100000,
    ):
        self.client = client or PolymarketClient()
        self.data_dir = Path(data_dir)
        self.batch_size = batch_size
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # State
        self.collected_traders: Set[str] = set()
        self.trader_cache: Dict[str, Dict] = {}
        self.all_trader_addresses: Set[str] = set()
        self._load_cache()

    def _load_cache(self):
        """Load trader qualification cache"""
        cache_path = self.data_dir / "trader_cache.pkl"
        if cache_path.exists():
            with open(cache_path, "rb") as f:
                self.trader_cache = pickle.load(f)
            self.collected_traders = set(self.trader_cache.keys())
            logger.info(f"Loaded {len(self.trader_cache)} cached traders")

    def _save_cache(self):
        """Save trader cache"""
        cache_path = self.data_dir / "trader_cache.pkl"
        with open(cache_path, "wb") as f:
            pickle.dump(self.trader_cache, f)
        logger.info(f"Saved cache: {len(self.trader_cache)} traders")

    def collect_markets(self, tags: List[str], markets_per_tag: int = 200) -> pd.DataFrame:
        """Collect markets from multiple tags"""
        logger.info(f"Collecting markets from {len(tags)} tags...")
        all_markets = []

        for tag in tags:
            events = self.client.get_events_by_tag(tag, limit=markets_per_tag)
            markets = self.client.get_markets_from_events(events)
            for m in markets:
                m["_tag"] = tag
            all_markets.extend(markets)
            logger.info(f"  Tag {tag}: {len(markets)} markets")

        # Filter valid markets
        valid = [m for m in all_markets if m.get("conditionId") and m.get("active")]
        df = pd.DataFrame(valid)

        # Save
        output_path = self.data_dir / "markets.parquet"
        df.to_parquet(output_path, index=False)
        logger.info(f"Saved {len(df)} markets to {output_path}")

        return df

    def collect_trades_batch(
        self,
        market_ids: List[str],
        batch_num: int = 0,
    ) -> pd.DataFrame:
        """Collect trades for a batch of markets"""
        logger.info(f"Collecting trades for {len(market_ids)} markets (batch {batch_num})...")

        all_trades = []
        batch_size = 20

        for i in range(0, len(market_ids), batch_size):
            batch_ids = market_ids[i : i + batch_size]
            try:
                trades = self.client.get_trades_for_markets(batch_ids, limit=50000)
                all_trades.extend(trades)
            except Exception as e:
                logger.warning(f"Failed to get trades for batch: {e}")

        df = pd.DataFrame(all_trades)
        logger.info(f"Collected {len(df)} trades")

        # Save incrementally
        if len(df) > 0:
            output_path = self.data_dir / f"trades_batch_{batch_num:04d}.parquet"
            df.to_parquet(output_path, index=False)
            logger.info(f"Saved to {output_path}")

        return df

    def collect_top_traders(
        self,
        market_ids: List[str],
        top_n: int = 100,
    ) -> pd.DataFrame:
        """Collect top ROI traders from markets"""
        logger.info(f"Collecting top {top_n} traders from markets...")

        all_market_trades = {}

        # Fetch trades in batches
        batch_size = 20
        for i in range(0, min(len(market_ids), 500), batch_size):
            batch_ids = market_ids[i : i + batch_size]
            try:
                trades = self.client.get_trades_for_markets(batch_ids, limit=50000)
                for t in trades:
                    cid = t.get("conditionId", "")
                    if cid not in all_market_trades:
                        all_market_trades[cid] = []
                    all_market_trades[cid].append(t)
            except Exception as e:
                logger.warning(f"Failed batch: {e}")

        # Get top ROI traders
        top_traders = get_top_roi_traders(all_market_trades, top_n=top_n)
        df = pd.DataFrame(top_traders)

        # Save
        output_path = self.data_dir / "top_traders.parquet"
        df.to_parquet(output_path, index=False)
        logger.info(f"Saved {len(df)} top traders")

        return df

    def collect_trades_from_markets(
        self,
        market_ids: List[str],
        target_trades: int = 100000,
    ) -> int:
        """
        Collect trades directly from markets (diversified across all markets).
        Returns total trades collected.
        """
        logger.info(f"Collecting {target_trades:,} trades from {len(market_ids)} markets...")

        total_trades = 0
        batch_num = 0

        # Fetch trades in batches until we reach target
        batch_size = 20
        market_idx = 0

        while total_trades < target_trades and market_idx < len(market_ids):
            batch_ids = market_ids[market_idx : market_idx + batch_size]
            market_idx += batch_size

            try:
                trades = self.client.get_trades_for_markets(batch_ids, limit=50000)

                if trades:
                    df = pd.DataFrame(trades)

                    # Collect trader addresses
                    for t in trades:
                        addr = t.get("proxyWallet", "")
                        if addr:
                            self.all_trader_addresses.add(addr)

                    # Save batch
                    output_path = self.data_dir / f"trades_batch_{batch_num:04d}.parquet"
                    df.to_parquet(output_path, index=False)

                    total_trades += len(df)
                    logger.info(
                        f"Batch {batch_num + 1}: {len(df):,} trades ({total_trades:,} total)"
                    )
                    batch_num += 1

            except Exception as e:
                logger.warning(f"Failed batch: {e}")

        logger.info(f"Collection complete: {total_trades:,} trades in {batch_num} batches")
        return total_trades

    def get_trader_addresses(self) -> Set[str]:
        """Get all unique trader addresses from collected trades"""
        # Also scan existing trade files
        for path in self.data_dir.glob("trades_batch_*.parquet"):
            df = pd.read_parquet(path)
            if "proxyWallet" in df.columns:
                self.all_trader_addresses.update(df["proxyWallet"].dropna().unique())

        return self.all_trader_addresses

    def count_existing_trades(self) -> int:
        """Count existing trades in batch files"""
        total = 0
        for path in self.data_dir.glob("trades_batch_*.parquet"):
            df = pd.read_parquet(path)
            total += len(df)
        return total

    def collect_trader_histories(
        self,
        trader_addresses: List[str],
    ) -> int:
        """
        Collect full histories for top traders.
        Returns total trades collected.
        """
        logger.info(f"Collecting histories for {len(trader_addresses)} traders...")

        total_trades = 0
        batch_num = 0

        # Count existing trades
        existing = self.data_dir.glob("trader_trades_*.parquet")
        for path in existing:
            df = pd.read_parquet(path)
            total_trades += len(df)
            batch_num += 1

        logger.info(f"Existing: {total_trades:,} trades in {batch_num} batches")

        # Filter already collected
        to_collect = [a for a in trader_addresses if a not in self.collected_traders]
        logger.info(f"New traders to collect: {len(to_collect)}")

        while to_collect:
            # Collect in batches of 50 traders
            batch_traders = to_collect[:50]
            to_collect = to_collect[50:]

            logger.info(
                f"Collecting batch {batch_num + 1}: {len(batch_traders)} traders..."
            )

            histories = self.client.get_traders_histories_parallel(batch_traders)

            # Save each trader
            all_dfs = []
            for addr, trades in histories.items():
                if trades:
                    self.trader_cache[addr] = {
                        "total_trades": len(trades),
                        "collected_at": datetime.now().isoformat(),
                    }
                    self.collected_traders.add(addr)

                    df = pd.DataFrame(trades)
                    df["trader_address"] = addr
                    all_dfs.append(df)

            if all_dfs:
                combined = pd.concat(all_dfs, ignore_index=True)
                output_path = self.data_dir / f"trader_trades_{batch_num:04d}.parquet"
                combined.to_parquet(output_path, index=False)

                total_trades += len(combined)
                logger.info(
                    f"Saved {len(combined):,} trades ({total_trades:,} total)"
                )
                batch_num += 1

            self._save_cache()

        logger.info(f"Collection complete: {total_trades:,} trades in {batch_num} batches")
        return total_trades

    def combine_all_trades(self) -> pd.DataFrame:
        """Combine all trade batches into single file"""
        logger.info("Combining all trades...")

        all_dfs = []
        
        # Try trader_trades_*.parquet first (top traders collection)
        for path in sorted(self.data_dir.glob("trader_trades_*.parquet")):
            df = pd.read_parquet(path)
            all_dfs.append(df)
            logger.info(f"  {path.name}: {len(df)} trades")
        
        # Fallback to trades_batch_*.parquet (diversified collection)
        if not all_dfs:
            for path in sorted(self.data_dir.glob("trades_batch_*.parquet")):
                df = pd.read_parquet(path)
                all_dfs.append(df)
                logger.info(f"  {path.name}: {len(df)} trades")

        if all_dfs:
            combined = pd.concat(all_dfs, ignore_index=True)
            output_path = self.data_dir / "all_trades.parquet"
            combined.to_parquet(output_path, index=False)
            logger.info(f"Combined {len(combined):,} trades to {output_path}")
            return combined

        return pd.DataFrame()
