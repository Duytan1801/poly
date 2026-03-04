"""
Insider Scout (Elite-Direct): Directly tracing the Monthly/Overall PnL Leaders.
"""

import asyncio
import logging
import pandas as pd
import numpy as np
from typing import List, Dict, Any
from poly.api.polymarket import PolymarketClient

logger = logging.getLogger(__name__)

class InsiderScout:
    def __init__(self):
        self.client = PolymarketClient()
        self.market_cache = {}

    def get_wallet_performance(self, address: str) -> Dict[str, Any]:
        """Profile verified leaderboard whales."""
        trades = self.client.get_trader_history(address, limit=200)
        if not trades: return {"address": address, "total_resolved": 0}

        wins = 0
        total_resolved = 0
        timing_offsets = []

        for t in trades:
            cid = t.get("conditionId")
            if not cid: continue
            
            if cid not in self.market_cache:
                self.market_cache[cid] = self.client.get_market_resolution_state(cid)
            
            res = self.market_cache[cid]
            if res:
                bet_idx = int(t.get("outcomeIndex", 0))
                if bet_idx == res["winner_idx"]: wins += 1
                total_resolved += 1
                timing_offsets.append(res["closed_at"] - int(t.get("timestamp", 0)))

        return {
            "address": address,
            "winrate": wins / total_resolved if total_resolved > 0 else 0.0,
            "total_resolved": total_resolved,
            "avg_timing_seconds": np.mean(timing_offsets) if timing_offsets else 0,
            "last_minute_ratio": sum(1 for o in timing_offsets if 0 < o < 600) / len(timing_offsets) if timing_offsets else 0,
            "max_bet": max([float(t.get("size", 0)) for t in trades]) if trades else 0
        }

    async def discover_elite_wallets(self) -> List[Dict]:
        """Query the direct leaderboard API for elite whales."""
        categories = ["OVERALL", "POLITICS", "CRYPTO"]
        elite_wallets = set()
        
        print(f"📡 Querying Direct Leaderboard for Monthly/Overall PnL Leaders...")
        for cat in categories:
            # Query MONTH and ALL time periods
            for period in ["MONTH", "ALL"]:
                leaderboard = self.client.get_leaderboard(cat, period, limit=20)
                for entry in leaderboard:
                    addr = entry.get("proxyWallet")
                    if addr: elite_wallets.add(addr)
                    
        print(f"✅ Found {len(elite_wallets)} Verified Leaders. Running performance verification...")
        
        loop = asyncio.get_event_loop()
        wallets_list = list(elite_wallets)
        profiles = []
        
        # Batching for performance
        for i in range(0, len(wallets_list), 10):
            batch = wallets_list[i:i+10]
            batch_profiles = await asyncio.gather(*[
                loop.run_in_executor(None, self.get_wallet_performance, w) for w in batch
            ])
            profiles.extend([p for p in batch_profiles if p["total_resolved"] >= 5])
            
        return profiles
