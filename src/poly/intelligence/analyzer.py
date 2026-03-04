"""
Comprehensive Trader Analysis: Timing, Whales, Multi-Market, Cross-Market.
Uses Polars for high-performance vectorized data processing.
"""

import polars as pl
import numpy as np
from typing import List, Dict, Any, Optional

from poly.intelligence.utils import categorize_market


class BaseAnalyzer:
    """Base class providing shared utilities for trader analysis."""

    @staticmethod
    def _to_df(data: List[Dict]) -> Optional[pl.DataFrame]:
        """Convert a list of dictionaries to a Polars DataFrame, returning None if empty."""
        if not data:
            return None
        df = pl.DataFrame(data)
        return df if not df.is_empty() else None

    @staticmethod
    def _get_resolution_df(
        market_resolutions: Dict[str, Dict],
    ) -> Optional[pl.DataFrame]:
        """Convert market resolutions map to a Polars DataFrame with all metadata."""
        if not market_resolutions:
            return None

        data = []
        for k, v in market_resolutions.items():
            if v.get("closed_at") is not None:
                data.append(
                    {
                        "conditionId": k,
                        "closed_at": v.get("closed_at"),
                        "winner_idx": v.get("winner_idx"),
                    }
                )

        if not data:
            return None
        return pl.DataFrame(data)


class TimingAnalyzer(BaseAnalyzer):
    """Analyze trading timing patterns relative to market resolution."""

    PRE_RESOLUTION_THRESHOLD_HOURS = 1.0
    LAST_MINUTE_THRESHOLD_SECONDS = 600

    @staticmethod
    def analyze_trader_timing(
        trades: List[Dict], market_resolutions: Dict[str, Dict]
    ) -> Dict[str, Any]:
        """Analyze timing patterns using Polars for vectorized speed."""
        default_stats = {
            "avg_hours_before_resolution": 0,
            "min_hours_before_resolution": 0,
            "max_hours_before_resolution": 0,
            "last_minute_ratio": 0,
            "pre_resolution_trades": 0,
            "pre_resolution_ratio": 0,
            "total_trades": len(trades),
            "trades_with_resolution": 0,
        }

        df = BaseAnalyzer._to_df(trades)
        res_df = BaseAnalyzer._get_resolution_df(market_resolutions)

        if df is None or res_df is None:
            return default_stats

        merged = df.select(["conditionId", "timestamp"]).join(
            res_df, on="conditionId", how="inner"
        )
        if merged.is_empty():
            return default_stats

        # Filter out invalid resolutions (closed_at = 0 or timestamp > closed_at)
        merged = merged.filter(pl.col("closed_at") > 0)
        if merged.is_empty():
            return default_stats

        # Detect if timestamps are in milliseconds (if > 1e12) and convert to seconds
        sample_ts = merged["timestamp"].head(1).item()
        if sample_ts > 1e12:
            merged = merged.with_columns(pl.col("timestamp") / 1000)

        # Also check closed_at - if it's also in milliseconds, convert it
        sample_closed = merged["closed_at"].head(1).item()
        if sample_closed > 1e12:
            merged = merged.with_columns(pl.col("closed_at") / 1000)

        hours_before = ((merged["closed_at"] - merged["timestamp"]) / 3600).clip(
            lower_bound=0
        )

        is_pre_res = hours_before < TimingAnalyzer.PRE_RESOLUTION_THRESHOLD_HOURS
        is_last_minute = (
            hours_before * 3600
        ) < TimingAnalyzer.LAST_MINUTE_THRESHOLD_SECONDS

        total_res = len(merged)
        pre_res_count = is_pre_res.sum()
        # Last minute is a subset of pre-resolution for consistency
        last_min_count = (is_pre_res & is_last_minute).sum()

        return {
            "avg_hours_before_resolution": float(hours_before.mean()),
            "min_hours_before_resolution": float(hours_before.min()),
            "max_hours_before_resolution": float(hours_before.max()),
            "timing_std_hours": float(hours_before.std()) if total_res > 1 else 0.0,
            "last_minute_ratio": last_min_count / total_res,
            "pre_resolution_trades": int(pre_res_count),
            "pre_resolution_ratio": pre_res_count / total_res,
            "total_trades": len(trades),
            "trades_with_resolution": total_res,
        }


class WhaleAnalyzer(BaseAnalyzer):
    """Analyze whale (large position) trading patterns."""

    WHALE_THRESHOLD = 5000
    MEGA_WHALE_THRESHOLD = 25000

    @staticmethod
    def analyze_trader_whales(
        trades: List[Dict], market_resolutions: Optional[Dict[str, Dict]] = None
    ) -> Dict[str, Any]:
        """Analyze whale patterns using vectorized Polars logic."""
        default_stats = {
            "max_bet": 0,
            "avg_bet": 0,
            "whale_trades": 0,
            "mega_whale_trades": 0,
            "whale_ratio": 0,
            "total_value": 0,
            "pre_resolution_whale_trades": 0,
            "pre_resolution_whale_ratio": 0,
            "winning_pre_resolution_whale_trades": 0,
            "winning_pre_resolution_whale_ratio": 0,
        }

        df = BaseAnalyzer._to_df(trades)
        if df is None:
            return default_stats

        df = df.with_columns(
            (pl.col("size").cast(pl.Float64) * pl.col("price").cast(pl.Float64)).alias(
                "value"
            )
        )

        values = df["value"]
        whales_mask = values >= WhaleAnalyzer.WHALE_THRESHOLD
        whale_count = whales_mask.sum()
        mega_whale_count = (values >= WhaleAnalyzer.MEGA_WHALE_THRESHOLD).sum()

        pre_res_whales = 0
        win_pre_res_whales = 0
        if market_resolutions:
            res_df = BaseAnalyzer._get_resolution_df(market_resolutions)
            if res_df is not None:
                merged = df.join(res_df, on="conditionId", how="inner")
                if not merged.is_empty():
                    hours_before = (merged["closed_at"] - merged["timestamp"]) / 3600
                    pre_res = (hours_before > 0) & (
                        hours_before < TimingAnalyzer.PRE_RESOLUTION_THRESHOLD_HOURS
                    )
                    is_whale = merged["value"] >= WhaleAnalyzer.WHALE_THRESHOLD
                    pre_res_whales = (is_whale & pre_res).sum()

                    # NEW: Winning Pre-Resolution Whale activity
                    is_win = merged["outcomeIndex"].cast(pl.Int64) == merged[
                        "winner_idx"
                    ].cast(pl.Int64)
                    win_pre_res_whales = (is_whale & pre_res & is_win).sum()

        total = len(df)
        return {
            "max_bet": float(values.max()),
            "avg_bet": float(values.mean()),
            "total_value": float(values.sum()),
            "whale_trades": int(whale_count),
            "mega_whale_trades": int(mega_whale_count),
            "whale_ratio": whale_count / total if total > 0 else 0,
            "pre_resolution_whale_trades": int(pre_res_whales),
            "pre_resolution_whale_ratio": pre_res_whales / whale_count
            if whale_count > 0
            else 0,
            "winning_pre_resolution_whale_trades": int(win_pre_res_whales),
            "winning_pre_resolution_whale_ratio": win_pre_res_whales / whale_count
            if whale_count > 0
            else 0,
        }


class MultiMarketAnalyzer(BaseAnalyzer):
    """Analyze success patterns across multiple distinct markets."""

    @staticmethod
    def analyze_multi_market_success(
        trades: List[Dict], market_resolutions: Dict[str, Dict]
    ) -> Dict[str, Any]:
        """Analyze multi-market success with fully vectorized Polars join."""
        default_stats = {
            "unique_markets": 0,
            "resolved_markets": 0,
            "winning_markets": 0,
            "multi_market_success_rate": 0,
            "cross_market_winrate": 0,
        }

        df = BaseAnalyzer._to_df(trades)
        res_df = BaseAnalyzer._get_resolution_df(market_resolutions)

        if df is None:
            return default_stats

        unique_cids = df["conditionId"].n_unique()
        if res_df is None:
            return {**default_stats, "unique_markets": unique_cids}

        # Vectorized success detection
        merged = df.join(res_df, on="conditionId", how="inner")
        if merged.is_empty():
            return {**default_stats, "unique_markets": unique_cids}

        # Group by market to see if ANY trade in that market was a winner
        market_stats = merged.group_by("conditionId").agg(
            (
                pl.col("outcomeIndex").cast(pl.Int64)
                == pl.col("winner_idx").cast(pl.Int64)
            )
            .any()
            .alias("is_win")
        )

        resolved_count = len(market_stats)
        winning_count = market_stats["is_win"].sum()

        success_rate = winning_count / resolved_count if resolved_count > 0 else 0

        return {
            "unique_markets": unique_cids,
            "resolved_markets": resolved_count,
            "winning_markets": int(winning_count),
            "multi_market_success_rate": success_rate,
            "cross_market_winrate": success_rate,
        }


class CrossMarketAnalyzer(BaseAnalyzer):
    """Analyze cross-market patterns and category-based diversification."""

    CATEGORIES = {
        "crypto": ["crypto", "bitcoin", "btc", "ethereum", "eth", "solana", "sol"],
        "politics": ["election", "president", "trump", "biden", "congress", "senate"],
        "sports": ["nfl", "nba", "football", "basketball", "soccer", "mlb"],
        "business": ["stock", "market", "fed", "inflation", "gdp"],
        "science": ["science", "climate", "weather", "space", "nasa"],
    }

    @staticmethod
    def _categorize(market_id: str, meta: Dict[str, Dict]) -> str:
        text = f"{meta.get(market_id, {}).get('slug', '')} {meta.get(market_id, {}).get('question', '')}".lower()
        for cat, keywords in CrossMarketAnalyzer.CATEGORIES.items():
            if any(k in text for k in keywords):
                return cat
        return "other"

    @staticmethod
    def analyze_cross_market(
        trades: List[Dict],
        market_resolutions: Dict[str, Dict],
        market_metadata: Optional[Dict[str, Dict]] = None,
    ) -> Dict[str, Any]:
        """Analyze cross-category diversification and success."""
        df = BaseAnalyzer._to_df(trades)
        if df is None:
            return {
                "categories_traded": 0,
                "category_performance": {},
                "cross_category_success": 0,
                "diversification_score": 0,
            }

        unique_cids = df["conditionId"].n_unique()

        # Simple diversification heuristic based on unique markets
        return {
            "categories_traded": unique_cids,
            "category_performance": {},
            "cross_category_success": 0,  # Note: Actual win detection moved to MultiMarketAnalyzer for clarity
            "diversification_score": unique_cids / 5.0,
        }


class ComprehensiveAnalyzer:
    """Combines all analysis sub-modules into a unified trader profile."""

    def analyze_trader(
        self,
        address: str,
        trades: List[Dict],
        market_resolutions: Dict[str, Dict],
        market_metadata: Optional[Dict[str, Dict]] = None,
    ) -> Dict[str, Any]:
        """Generate a complete behavioral profile for a single address."""

        if not trades:
            return {"address": address}

        timestamps = [int(t.get("timestamp", 0)) for t in trades if t.get("timestamp")]
        first_ts = min(timestamps) if timestamps else 0
        last_ts = max(timestamps) if timestamps else 0

        sorted_trades = sorted(
            trades, key=lambda x: x.get("timestamp", 0), reverse=True
        )
        recent_trades = sorted_trades[:50]

        recent_wins = 0
        recent_resolved = 0
        for tr in recent_trades:
            cid = tr.get("conditionId")
            if cid in market_resolutions:
                outcome_idx = tr.get("outcomeIndex")
                winner_idx = market_resolutions[cid].get("winner_idx")
                if outcome_idx is not None and winner_idx is not None:
                    recent_resolved += 1
                    if int(outcome_idx) == int(winner_idx):
                        recent_wins += 1

        recent_winrate = recent_wins / recent_resolved if recent_resolved > 0 else 0

        category_scores = []
        market_info_list = {}
        if market_metadata:
            for tr in trades:
                cid = tr.get("conditionId")
                if cid in market_metadata:
                    m = market_metadata[cid]
                    score = categorize_market(
                        m.get("question", ""),
                        m.get("group_item_title", ""),
                        m.get("category", ""),
                    )
                    category_scores.append(score)
                    market_info_list[cid] = m

        avg_category_score = (
            sum(category_scores) / len(category_scores) if category_scores else 1.0
        )

        market_value = {}
        for tr in trades:
            cid = tr.get("conditionId")
            if cid:
                size = float(tr.get("size", 0))
                price = float(tr.get("price", 0))
                value = size * price
                market_value[cid] = market_value.get(cid, 0) + value

        max_market_value = max(market_value.values()) if market_value else 0
        total_value = sum(market_value.values()) if market_value else 0
        max_market_share = max_market_value / total_value if total_value > 0 else 0

        return {
            "address": address,
            "first_trade_timestamp": first_ts,
            "last_trade_timestamp": last_ts,
            "recent_winrate": recent_winrate,
            "market_category_score": avg_category_score,
            "market_info": market_info_list,
            "max_market_share": max_market_share,
            "timing": TimingAnalyzer.analyze_trader_timing(trades, market_resolutions),
            "whales": WhaleAnalyzer.analyze_trader_whales(trades, market_resolutions),
            "multi_market": MultiMarketAnalyzer.analyze_multi_market_success(
                trades, market_resolutions
            ),
            "cross_market": CrossMarketAnalyzer.analyze_cross_market(
                trades, market_resolutions, market_metadata
            ),
        }
