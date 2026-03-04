"""
Rigorous Insider Scoring System v3.0
Based on iykykmarkets research + PolyTrack detection methodology.

Key principles:
1. Winrate MUST be >50% - otherwise score is penalized, not neutral
2. Value-weighted accuracy over simple winrate
3. Camouflage detection - high profit hidden in mediocre stats
4. Cross-market consistency - trade across unrelated markets
5. Late trading - enter in final 48h (informed timing)
"""

import math
import logging
from typing import List, Dict, Any, Optional

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
        return -2.0  # PENALTY for below breakeven
    elif winrate < 0.55:
        return 0.0  # Neutral - barely breakeven
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
        return -1.5  # Significant penalty for losing

    log_pnl = math.log1p(abs(pnl))
    max_log = math.log1p(1_000_000)

    score = (log_pnl / max_log) * 4.0
    return min(4.0, score)


def calculate_timing_score(
    late_ratio: float, pre_res_ratio: float, avg_hours_before: float
) -> float:
    """
    Timing edge based on:
    - Late trading (% in final 48h)
    - Pre-resolution trading
    - Average hours before resolution
    """
    score = 0.0

    # Late trading is a STRONG signal of insider knowledge
    if late_ratio >= 0.5:
        score += 2.0
    elif late_ratio >= 0.3:
        score += 1.5
    elif late_ratio >= 0.15:
        score += 1.0

    # Pre-resolution trading also signals timing edge
    if pre_res_ratio >= 0.3:
        score += 1.0
    elif pre_res_ratio >= 0.15:
        score += 0.5

    return min(2.5, score)


def calculate_concentration_score(
    unique_markets: int, total_trades: int, max_market_share: float = 0.0
) -> float:
    """
    Cross-market consistency score.
    Insiders trade across UNRELATED markets (not just many trades in one).
    """
    score = 0.0

    # Cross-market repeat: >=4 markets is the iykykmarkets threshold
    if unique_markets >= 8:
        score += 2.5
    elif unique_markets >= 6:
        score += 2.0
    elif unique_markets >= 4:
        score += 1.5
    elif unique_markets >= 2:
        score += 1.0

    # Dominance in single market (concentration)
    if max_market_share >= 0.30:
        score += 1.0
    elif max_market_share >= 0.15:
        score += 0.5

    return min(3.0, score)


def calculate_camouflage_score(pnl: float, winrate: float, total_trades: int) -> float:
    """
    CAMOUFLAGE DETECTION - Key insight from iykykmarkets!

    Insiders often have:
    - High total profit
    - Mediocre overall winrate (52-55%)
    - But concentrated wins in few high-conviction bets

    This is the "noise trading" pattern.
    """
    score = 0.0

    # High profit but mediocre winrate = potential camouflage
    if pnl > 50000 and winrate < 0.55:
        score += 2.0
    elif pnl > 25000 and winrate < 0.50:
        score += 1.5
    elif pnl > 10000 and winrate < 0.48:
        score += 1.0

    # Fewer trades with high profit = more suspicious
    if total_trades < 50 and pnl > 10000:
        score += 1.0

    return min(3.0, score)


def calculate_market_category_bonus(
    question: str, group_title: str = "", category: str = ""
) -> float:
    """Event category insider probability."""
    score = categorize_market(question, group_title, category)
    return score * 0.3  # Scale to 0-1.5 range


def calculate_activity_penalty(trades: int) -> float:
    """
    Too much activity dilutes insider signal.
    Insiders are selective, not grinders.
    """
    if trades > 1000:
        return -2.0
    elif trades > 500:
        return -1.5
    elif trades > 200:
        return -1.0
    return 0.0


def calculate_freshness_score(first_trade_ts: int, last_trade_ts: int) -> float:
    """Account freshness - new accounts with high activity = suspicious."""
    import time

    if not first_trade_ts or not last_trade_ts:
        return 0.0

    current_ts = int(time.time())
    account_age_days = (current_ts - first_trade_ts) / 86400
    days_since_last = (current_ts - last_trade_ts) / 86400

    # New account with high activity = suspicious
    if account_age_days < 30:
        return 1.5
    elif account_age_days < 90:
        return 1.0
    elif account_age_days < 180:
        return 0.5

    return 0.0


class InsiderScorer:
    """
    Rigorous Insider Scoring System v3.0

    Scoring components (max ~20 points):
    - Winrate: -2 to +4 (MUST be >50%)
    - PnL: -1.5 to +4
    - Timing: 0 to +2.5
    - Cross-market: 0 to +3
    - Camouflage: 0 to +3
    - Category: 0 to +1.5
    - Freshness: 0 to +1.5
    - Activity penalty: -2 to 0

    Level thresholds:
    - CRITICAL: >= 12
    - HIGH: >= 9
    - MEDIUM: >= 6
    - LOW: < 6
    """

    def __init__(self):
        pass

    def calculate_level(self, score: float) -> str:
        """Categorize risk based on rigorous scoring."""
        if score >= 8.0:
            return "CRITICAL"
        if score >= 5.0:
            return "HIGH"
        if score >= 2.0:
            return "MEDIUM"
        return "LOW"

    def fit_and_score(self, profiles: List[Dict]) -> List[Dict]:
        """Run the rigorous scoring pipeline."""
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

            # Get market metadata for category
            market_info = p.get("market_info", {})

            # ==================== CALCULATE COMPONENTS ====================

            # 1. WINRATE SCORE (CRITICAL - must be >50%)
            winrate_score = calculate_winrate_score(winrate, trades)

            # 2. PNL SCORE
            pnl_score = calculate_pnl_score(pnl)

            # 3. TIMING SCORE
            late_ratio = t.get("last_minute_ratio", 0)
            pre_res_ratio = t.get("pre_resolution_ratio", 0)
            avg_hours = t.get("avg_hours_before_resolution", 0)
            timing_score = calculate_timing_score(late_ratio, pre_res_ratio, avg_hours)

            # 4. CROSS-MARKET SCORE
            unique_markets = mm.get("unique_markets", 0)
            max_share = w.get("max_market_share", 0.0)
            cross_market_score = calculate_concentration_score(
                unique_markets, trades, max_share
            )

            # 5. CAMOUFLAGE SCORE
            camouflage_score = calculate_camouflage_score(pnl, winrate, trades)

            # 6. MARKET CATEGORY BONUS
            category_score = calculate_market_category_bonus(
                market_info.get("question", ""),
                market_info.get("group_item_title", ""),
                market_info.get("category", ""),
            )

            # 7. FRESHNESS SCORE
            first_ts = p.get("first_trade_timestamp", 0)
            last_ts = p.get("last_trade_timestamp", 0)
            freshness_score = calculate_freshness_score(first_ts, last_ts)

            # 8. ACTIVITY PENALTY
            activity_penalty = calculate_activity_penalty(trades)

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
                ),
                10.0,
            )

            # Determine profile type
            if winrate < 0.50:
                profile_type = "LOSER"  # Below breakeven
            elif camouflage_score >= 2.0:
                profile_type = "CAMOUFLAGED_INSIDER"
            elif cross_market_score >= 2.0 and timing_score >= 1.5:
                profile_type = "INSIDER"
            elif trades >= 200 and winrate >= 0.55:
                profile_type = "PRO"
            else:
                profile_type = "CASUAL"

            # Update profile
            p.update(
                {
                    "risk_score": round(total_score, 2),
                    "profile_type": profile_type,
                    "level": self.calculate_level(total_score),
                    # Component breakdown for debugging
                    "score_breakdown": {
                        "winrate": round(winrate_score, 2),
                        "pnl": round(pnl_score, 2),
                        "timing": round(timing_score, 2),
                        "cross_market": round(cross_market_score, 2),
                        "camouflage": round(camouflage_score, 2),
                        "category": round(category_score, 2),
                        "freshness": round(freshness_score, 2),
                        "activity_penalty": round(activity_penalty, 2),
                    },
                    # Key metrics
                    "value_weighted_accuracy": p.get(
                        "value_weighted_accuracy", winrate
                    ),
                    "late_trading_ratio": late_ratio,
                    "unique_markets": unique_markets,
                }
            )

            results.append(p)

        # Sort by score descending
        return sorted(
            results,
            key=lambda x: x.get("risk_score", 0),
            reverse=True,
        )
