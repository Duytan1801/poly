"""
Insider Scoring System v4.0 - Pure Rule-Based
Based on iykykmarkets research + PolyTrack + polymarket-insider-tracker methodologies.

Features (14 components):
1. Winrate Score - Strict >50% requirement
2. PnL Score - Log-scaled profit
3. Timing Score - Late trading detection
4. Cross-Market Score - Multi-market consistency
5. Camouflage Score - High profit + mediocre winrate
6. Category Score - Market type insider probability
7. Freshness Score - Account age analysis
8. Activity Penalty - Too many trades = noise
9. Fresh Wallet Score - New wallets making large trades
10. Position Sizing - % capital in single bet
11. Early Entry - First-mover advantage
12. Off-Hours Activity - Night/weekend trading
13. Volume Impact - Trade size vs market
14. Cluster Score - Coordinated wallets
"""

import math
import logging
import time
from typing import List, Dict, Any
from collections import defaultdict

from poly.intelligence.utils import categorize_market

logger = logging.getLogger(__name__)

MIN_LIQUIDITY_VOLUME = 50000
MIN_LIQUIDITY_PARTICIPANTS = 20


def calculate_value_weighted_accuracy(
    trades: List[Dict], market_resolutions: Dict[str, Dict]
) -> float:
    """Calculate accuracy weighted by trade value, not count."""
    if not trades or not market_resolutions:
        return 0.0

    winning_value = 0.0
    total_value = 0.0

    for tr in trades:
        cid = tr.get("conditionId")
        if cid not in market_resolutions:
            continue

        size = float(tr.get("size", 0))
        price = float(tr.get("price", 0))
        value = size * price

        if value <= 0:
            continue

        outcome_idx = tr.get("outcomeIndex")
        winner_idx = market_resolutions[cid].get("winner_idx")

        if outcome_idx is None or winner_idx is None:
            continue

        total_value += value
        if int(outcome_idx) == int(winner_idx):
            winning_value += value

    return winning_value / total_value if total_value > 0 else 0.0


def calculate_winrate_score(winrate: float, trades: int) -> float:
    """
    Strict winrate scoring:
    - <50%: PENALTY (not neutral!)
    - 50-55%: 0 points
    - 55-65%: 1 point
    - 65-75%: 2 points
    - 75-85%: 3 points
    - 85%+: 4 points
    """
    if trades < 5:
        return 0.0

    if winrate < 0.50:
        return -2.0
    elif winrate < 0.55:
        return 0.0
    elif winrate < 0.65:
        return 1.0
    elif winrate < 0.75:
        return 2.0
    elif winrate < 0.85:
        return 3.0
    else:
        return 4.0


def calculate_pnl_score(pnl: float) -> float:
    """Log-scaled PnL scoring with negative penalty."""
    if pnl <= 0:
        return -1.5

    log_pnl = math.log1p(abs(pnl))
    max_log = math.log1p(1_000_000)

    score = (log_pnl / max_log) * 4.0
    return min(4.0, score)


def calculate_timing_score(
    late_ratio: float, pre_res_ratio: float, avg_hours_before: float
) -> float:
    """Timing edge based on late trading and pre-resolution activity."""
    score = 0.0

    if late_ratio >= 0.5:
        score += 2.0
    elif late_ratio >= 0.3:
        score += 1.5
    elif late_ratio >= 0.15:
        score += 1.0

    if pre_res_ratio >= 0.3:
        score += 1.0
    elif pre_res_ratio >= 0.15:
        score += 0.5

    return min(2.5, score)


def calculate_concentration_score(
    unique_markets: int, total_trades: int, max_market_share: float = 0.0
) -> float:
    """Cross-market consistency score."""
    score = 0.0

    if unique_markets >= 8:
        score += 2.5
    elif unique_markets >= 6:
        score += 2.0
    elif unique_markets >= 4:
        score += 1.5
    elif unique_markets >= 2:
        score += 1.0

    if max_market_share >= 0.30:
        score += 1.0
    elif max_market_share >= 0.15:
        score += 0.5

    return min(3.0, score)


def calculate_camouflage_score(pnl: float, winrate: float, total_trades: int) -> float:
    """CAMOUFLAGE DETECTION - High profit hidden in mediocre stats."""
    score = 0.0

    if pnl > 50000 and winrate < 0.55:
        score += 2.0
    elif pnl > 25000 and winrate < 0.50:
        score += 1.5
    elif pnl > 10000 and winrate < 0.48:
        score += 1.0

    if total_trades < 50 and pnl > 10000:
        score += 1.0

    return min(3.0, score)


def calculate_market_category_bonus(
    question: str, group_title: str = "", category: str = ""
) -> float:
    """Event category insider probability."""
    score = categorize_market(question, group_title, category)
    return score * 0.3


def calculate_activity_penalty(trades: int) -> float:
    """Too much activity dilutes insider signal."""
    if trades > 1000:
        return -2.0
    elif trades > 500:
        return -1.5
    elif trades > 200:
        return -1.0
    return 0.0


def calculate_freshness_score(first_trade_ts: int, last_trade_ts: int) -> float:
    """Account freshness - new accounts with high activity = suspicious."""
    if not first_trade_ts or not last_trade_ts:
        return 0.0

    current_ts = int(time.time())
    account_age_days = (current_ts - first_trade_ts) / 86400

    if account_age_days < 30:
        return 1.5
    elif account_age_days < 90:
        return 1.0
    elif account_age_days < 180:
        return 0.5
    return 0.0


# ============================================================================
# NEW FEATURES FROM RESEARCH (v4.0)
# ============================================================================


def calculate_fresh_wallet_score(
    trade_count: int, avg_trade_size: float, first_trade_ts: int
) -> float:
    """
    Fresh Wallet Detection (from polymarket-insider-tracker):
    Wallets with <5 lifetime transactions making $1,000+ trades are suspicious.

    Score:
    - <5 trades + avg >$1000: +2.5
    - <10 trades + avg >$500: +2.0
    - <20 trades + avg >$250: +1.5
    """
    if trade_count == 0:
        return 0.0

    if trade_count < 5 and avg_trade_size >= 1000:
        return 2.5
    elif trade_count < 10 and avg_trade_size >= 500:
        return 2.0
    elif trade_count < 20 and avg_trade_size >= 250:
        return 1.5
    elif trade_count < 50 and avg_trade_size >= 100:
        return 1.0
    return 0.0


def calculate_position_sizing_score(
    max_trade_size: float, avg_trade_size: float, total_volume: float
) -> float:
    """
    Position Sizing Analysis:
    % of total capital in single bet. High conviction = suspicious.

    Score:
    - Single bet >60% of total: +2.0
    - Single bet >40% of total: +1.5
    - Single bet >25% of total: +1.0
    """
    if total_volume <= 0 or max_trade_size <= 0:
        return 0.0

    concentration = max_trade_size / total_volume

    if concentration >= 0.60:
        return 2.0
    elif concentration >= 0.40:
        return 1.5
    elif concentration >= 0.25:
        return 1.0
    elif concentration >= 0.15:
        return 0.5
    return 0.0


def calculate_early_entry_score(
    market_created_ts: int, trade_ts: int, market_duration_hours: float = 168
) -> float:
    """
    Early Entry Scoring:
    Insiders often enter within first few hours of market creation.

    Score:
    - First 1% of market lifetime: +2.0
    - First 6 hours: +1.5
    - First 12 hours: +1.0
    - First 24 hours: +0.5
    """
    if not market_created_ts or not trade_ts:
        return 0.0

    hours_since_creation = (trade_ts - market_created_ts) / 3600

    if hours_since_creation <= 1:
        return 2.0
    elif hours_since_creation <= 6:
        return 1.5
    elif hours_since_creation <= 12:
        return 1.0
    elif hours_since_creation <= 24:
        return 0.5
    return 0.0


def calculate_off_hours_score(trade_timestamps: List[int]) -> float:
    """
    Off-Hours Activity Detection:
    Trading during nights/weekends (fewer observers) = suspicious.

    Score:
    - >50% off-hours: +1.5
    - >30% off-hours: +1.0
    - >15% off-hours: +0.5
    """
    if not trade_timestamps:
        return 0.0

    off_hours_count = 0
    for ts in trade_timestamps:
        from datetime import datetime

        dt = datetime.fromtimestamp(ts)
        hour = dt.hour
        is_weekend = dt.weekday() >= 5

        if is_weekend or hour >= 22 or hour < 6:
            off_hours_count += 1

    off_hours_ratio = off_hours_count / len(trade_timestamps)

    if off_hours_ratio >= 0.50:
        return 1.5
    elif off_hours_ratio >= 0.30:
        return 1.0
    elif off_hours_ratio >= 0.15:
        return 0.5
    return 0.0


def calculate_volume_impact_score(
    trade_size: float, market_daily_volume: float
) -> float:
    """
    Volume Impact Analysis:
    Trade size relative to daily market volume.
    >2% of daily volume = significant impact.

    Score:
    - >5% of daily volume: +2.0
    - >2% of daily volume: +1.5
    - >1% of daily volume: +1.0
    """
    if market_daily_volume <= 0 or trade_size <= 0:
        return 0.0

    impact_ratio = trade_size / market_daily_volume

    if impact_ratio >= 0.05:
        return 2.0
    elif impact_ratio >= 0.02:
        return 1.5
    elif impact_ratio >= 0.01:
        return 1.0
    return 0.0


def calculate_cluster_score(related_wallets: int, coordinated_trades: int) -> float:
    """
    Cluster Detection Score:
    Coordinated trading from related wallets = potential insider ring.

    Score:
    - 5+ related wallets + coordinated: +2.5
    - 3+ related wallets: +2.0
    - 2 related wallets: +1.5
    - 1 related wallet: +1.0
    """
    if related_wallets >= 5 and coordinated_trades > 0:
        return 2.5
    elif related_wallets >= 3:
        return 2.0
    elif related_wallets >= 2:
        return 1.5
    elif related_wallets >= 1:
        return 1.0
    return 0.0


# ============================================================================
# MAIN SCORER CLASS
# ============================================================================


class InsiderScorer:
    """
    Rule-based Insider Scoring System v4.0.

    Level thresholds (score 0-10):
    - CRITICAL: >= 8.0
    - HIGH: >= 5.0
    - MEDIUM: >= 2.0
    - LOW: < 2.0

    Components (14 total):
    1. winrate_score (max 4.0)
    2. pnl_score (max 4.0)
    3. timing_score (max 2.5)
    4. cross_market_score (max 3.0)
    5. camouflage_score (max 3.0)
    6. category_score (max 1.5)
    7. freshness_score (max 1.5)
    8. activity_penalty (min -2.0)
    9. fresh_wallet_score (max 2.5)
    10. position_sizing_score (max 2.0)
    11. early_entry_score (max 2.0)
    12. off_hours_score (max 1.5)
    13. volume_impact_score (max 2.0)
    14. cluster_score (max 2.5)
    """

    def __init__(self):
        pass

    def calculate_level(self, score: float) -> str:
        """Categorize risk based on score."""
        if score >= 8.0:
            return "CRITICAL"
        if score >= 5.0:
            return "HIGH"
        if score >= 2.0:
            return "MEDIUM"
        return "LOW"

    def fit_and_score(self, profiles: List[Dict]) -> List[Dict]:
        """Run the scoring pipeline."""
        if not profiles:
            return []

        results = []
        for p in profiles:
            winrate = p.get("winrate", 0)
            trades = p.get("total_trades_actual", p.get("total_trades", 0))
            pnl = p.get("pnl", 0)
            t = p.get("timing", {})
            w = p.get("whales", {})
            mm = p.get("multi_market", {})
            market_info = p.get("market_info", {})

            # ==================== CORE COMPONENTS ====================

            # 1. Winrate Score (CRITICAL - must be >50%)
            winrate_score = calculate_winrate_score(winrate, trades)

            # 2. PnL Score
            pnl_score = calculate_pnl_score(pnl)

            # 3. Timing Score
            late_ratio = t.get("last_minute_ratio", 0)
            pre_res_ratio = t.get("pre_resolution_ratio", 0)
            avg_hours = t.get("avg_hours_before_resolution", 0)
            timing_score = calculate_timing_score(late_ratio, pre_res_ratio, avg_hours)

            # 4. Cross-Market Score
            unique_markets = mm.get("unique_markets", 0)
            max_share = w.get("max_market_share", 0.0)
            cross_market_score = calculate_concentration_score(
                unique_markets, trades, max_share
            )

            # 5. Camouflage Score
            camouflage_score = calculate_camouflage_score(pnl, winrate, trades)

            # 6. Category Score
            category_score = calculate_market_category_bonus(
                market_info.get("question", ""),
                market_info.get("group_item_title", ""),
                market_info.get("category", ""),
            )

            # 7. Freshness Score
            first_ts = p.get("first_trade_timestamp", 0)
            last_ts = p.get("last_trade_timestamp", 0)
            freshness_score = calculate_freshness_score(first_ts, last_ts)

            # 8. Activity Penalty
            activity_penalty = calculate_activity_penalty(trades)

            # ==================== NEW FEATURES (v4.0) ====================

            # 9. Fresh Wallet Score
            avg_trade_size = p.get("avg_trade_size", 0)
            fresh_wallet_score = calculate_fresh_wallet_score(
                trades, avg_trade_size, first_ts
            )

            # 10. Position Sizing Score
            max_trade_size = p.get("max_trade_size", 0)
            total_volume = p.get(
                "total_volume", max_trade_size * trades if trades > 0 else 0
            )
            position_sizing_score = calculate_position_sizing_score(
                max_trade_size, avg_trade_size, total_volume
            )

            # 11. Early Entry Score (placeholder - needs market creation time)
            early_entry_score = 0.0

            # 12. Off-Hours Score (placeholder - needs raw timestamps)
            off_hours_score = 0.0

            # 13. Volume Impact Score (placeholder - needs market daily volume)
            volume_impact_score = 0.0

            # 14. Cluster Score
            related_wallets = len(p.get("related_wallets", []))
            coordinated_trades = p.get("coordinated_trades", 0)
            cluster_score = calculate_cluster_score(related_wallets, coordinated_trades)

            # ==================== FINAL SCORE ====================
            total_score = min(
                (
                    winrate_score
                    + pnl_score
                    + timing_score
                    + cross_market_score
                    + camouflage_score
                    + category_score
                    + freshness_score
                    + activity_penalty
                    + fresh_wallet_score
                    + position_sizing_score
                    + early_entry_score
                    + off_hours_score
                    + volume_impact_score
                    + cluster_score
                ),
                10.0,
            )

            # Determine profile type
            if winrate < 0.50:
                profile_type = "LOSER"
            elif camouflage_score >= 2.0:
                profile_type = "CAMOUFLAGED_INSIDER"
            elif cross_market_score >= 2.0 and timing_score >= 1.5:
                profile_type = "INSIDER"
            elif trades >= 200 and winrate >= 0.55:
                profile_type = "PRO"
            else:
                profile_type = "CASUAL"

            results.append(
                {
                    **p,
                    "risk_score": round(total_score, 2),
                    "level": self.calculate_level(total_score),
                    "profile_type": profile_type,
                    "score_breakdown": {
                        "winrate": round(winrate_score, 2),
                        "pnl": round(pnl_score, 2),
                        "timing": round(timing_score, 2),
                        "cross_market": round(cross_market_score, 2),
                        "camouflage": round(camouflage_score, 2),
                        "category": round(category_score, 2),
                        "freshness": round(freshness_score, 2),
                        "activity_penalty": round(activity_penalty, 2),
                        "fresh_wallet": round(fresh_wallet_score, 2),
                        "position_sizing": round(position_sizing_score, 2),
                        "early_entry": round(early_entry_score, 2),
                        "off_hours": round(off_hours_score, 2),
                        "volume_impact": round(volume_impact_score, 2),
                        "cluster": round(cluster_score, 2),
                    },
                    "value_weighted_accuracy": p.get(
                        "value_weighted_accuracy", winrate
                    ),
                }
            )

        return results
