"""
Targeted Insider Trading Data Collection.
Detects significant price jumps and collects pre-jump trading activity.
"""

import logging
import pandas as pd
import numpy as np
import time
import json
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from datetime import datetime

from poly.api.polymarket import PolymarketClient

logger = logging.getLogger(__name__)

class JumpCollector:
    """
    Collects trades occurring before significant market price movements.
    Target: 1,000,000 trades.
    """

    def __init__(
        self,
        client: Optional[PolymarketClient] = None,
        data_dir: str = "data/experiments",
    ):
        self.client = client or PolymarketClient()
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.total_collected = 0

    def detect_jumps(self, price_history: List[Dict], threshold: float = 0.1) -> List[Dict]:
        """
        Scan price history for jumps >= threshold within 24 hours.
        Returns list of detected jumps with metadata.
        """
        if len(price_history) < 2:
            return []

        df = pd.DataFrame(price_history)
        # Ensure timestamp is int
        df['t'] = df['t'].astype(int)
        df['p'] = df['p'].astype(float)
        df = df.sort_values('t')

        jumps = []
        for i in range(len(df)):
            start_price = df.iloc[i]['p']
            start_time = df.iloc[i]['t']
            
            # Look ahead up to 24 hours (86400 seconds)
            future = df[(df['t'] > start_time) & (df['t'] <= start_time + 86400)]
            
            if future.empty:
                continue
                
            max_p = future['p'].max()
            min_p = future['p'].min()
            
            # Check for upward jump
            if (max_p - start_price) / start_price >= threshold:
                peak_row = future[future['p'] == max_p].iloc[0]
                jumps.append({
                    "start_ts": int(start_time),
                    "end_ts": int(peak_row['t']),
                    "start_price": start_price,
                    "end_price": max_p,
                    "magnitude": (max_p - start_price) / start_price,
                    "direction": "up"
                })
                # Skip ahead to avoid multiple detections for same jump
                # (Simple heuristic: skip to peak)
                # Note: We continue to find all unique jumps
                
            # Check for downward jump
            elif (start_price - min_p) / start_price >= threshold:
                bottom_row = future[future['p'] == min_p].iloc[0]
                jumps.append({
                    "start_ts": int(start_time),
                    "end_ts": int(bottom_row['t']),
                    "start_price": start_price,
                    "end_price": min_p,
                    "magnitude": (start_price - min_p) / start_price,
                    "direction": "down"
                })

        # Deduplicate overlapping jumps (keep largest magnitude per window)
        if not jumps:
            return []
            
        final_jumps = []
        jumps.sort(key=lambda x: x['magnitude'], reverse=True)
        
        for j in jumps:
            is_overlap = False
            for fj in final_jumps:
                if abs(j['start_ts'] - fj['start_ts']) < 86400: # Within 24h
                    is_overlap = True
                    break
            if not is_overlap:
                final_jumps.append(j)
                
        return final_jumps

    def collect_insider_data(self, target_trades: int = 1000000):
        """Main loop to discover jumps and collect trades."""
        logger.info(f"Targeting {target_trades:,} trades for insider detection...")
        
        # 1. Get Active High Volume Markets (more likely to have reachable trade data)
        markets = self.client.get_markets(active=True, limit=500)
        
        # Filter for those with clobTokenIds
        valid_markets = [m for m in markets if m.get("clobTokenIds")]
        logger.info(f"Found {len(valid_markets)} active markets with CLOB support.")
        
        batch_num = 0
        all_collected_trades = []
        
        for m in valid_markets:
            if self.total_collected >= target_trades:
                break
                
            cid = m.get("conditionId")
            q = m.get("question")
            
            # Safely parse clobTokenIds
            token_ids = m.get("clobTokenIds")
            if isinstance(token_ids, str):
                try:
                    token_ids = json.loads(token_ids)
                except:
                    continue
            
            if not token_ids or not isinstance(token_ids, list) or len(token_ids) < 2:
                continue
                
            logger.info(f"Analyzing market: {q[:50]}...")
            
            # Just look at "Yes" token for jumps
            yes_token = str(token_ids[0])
            
            # Fetch last 30 days of price history for active markets
            now = int(time.time())
            start_history = now - (30 * 86400)
            history = self.client.get_price_history(yes_token, start_ts=start_history, interval="1h")
            
            if not history:
                logger.info(f"  No price history found for {yes_token}")
                continue
                
            jumps = self.detect_jumps(history, threshold=0.05) # Lowered to 5% for better sample discovery
            
            if not jumps:
                logger.info(f"  No jumps detected in {len(history)} price points")
                continue
                
            logger.info(f"  Detected {len(jumps)} jumps in {q[:30]}")
            
            for j in jumps:
                if self.total_collected >= target_trades:
                    break
                    
                # Collection window: [jump_start - 2 days, jump_start]
                start_window = j['start_ts'] - (2 * 86400)
                end_window = j['start_ts']
                
                # Fetch trades in this window
                # Note: We use get_trader_history but for a market we need a different approach
                # Gamma API /trades endpoint supports market filter
                trades = self._fetch_market_trades_window(cid, start_window, end_window)
                
                if not trades:
                    continue
                
                # Label trades
                df = pd.DataFrame(trades)
                df['market_question'] = q
                df['jump_direction'] = j['direction']
                df['jump_magnitude'] = j['magnitude']
                df['jump_start_ts'] = j['start_ts']
                
                # Label: 1 if buy before UP jump or sell before DOWN jump
                # Simplified: insider is buying before jump
                # (Actual insiders might use complex strategies, but this is a starting point)
                df['is_pre_jump'] = 0
                if j['direction'] == 'up':
                    # Yes token price increase
                    df.loc[(df['side'].str.lower() == 'buy') & (df['outcomeIndex'].astype(str) == '0'), 'is_pre_jump'] = 1
                else:
                    # Yes token price decrease (No token increase)
                    df.loc[(df['side'].str.lower() == 'buy') & (df['outcomeIndex'].astype(str) == '1'), 'is_pre_jump'] = 1

                self.total_collected += len(df)
                all_collected_trades.append(df)
                
                logger.info(f"    Collected {len(df):,} trades for jump at {datetime.fromtimestamp(j['start_ts'])}")
                
            # Periodically save
            if self.total_collected > (batch_num + 1) * 100000:
                self._save_batch(all_collected_trades, batch_num)
                all_collected_trades = []
                batch_num += 1

        # Final save
        if all_collected_trades:
            self._save_batch(all_collected_trades, batch_num)

        logger.info(f"Finished! Collected {self.total_collected:,} total trades.")

    def _fetch_market_trades_window(self, condition_id: str, start: int, end: int) -> List[Dict]:
        """Fetch all trades for a market in a specific time window."""
        all_trades = []
        offset = 0
        limit = 1000
        
        while True:
            url = f"{self.client.data_base}/trades"
            params = {
                "market": condition_id,
                "limit": limit,
                "offset": offset,
                "start": start,
                "end": end
            }
            resp = self.client._safe_get(url, params=params)
            if not resp or not isinstance(resp, list):
                break
                
            all_trades.extend(resp)
            if len(resp) < limit:
                break
            offset += limit
            if len(all_trades) > 50000: # Safety break
                break
            time.sleep(0.05)
            
        return all_trades

    def _save_batch(self, dfs: List[pd.DataFrame], batch_num: int):
        if not dfs:
            return
        combined = pd.concat(dfs, ignore_index=True)
        output_path = self.data_dir / f"insider_training_data_{batch_num:02d}.parquet"
        combined.to_parquet(output_path, index=False)
        logger.info(f"Saved batch {batch_num} to {output_path} ({len(combined):,} trades)")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    collector = JumpCollector()
    collector.collect_insider_data(target_trades=1000000)
