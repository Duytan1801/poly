"""
Insider Scoring System v4.0 - Perpetual ML Integration
Based on iykykmarkets research + PolyTrack + polymarket-insider-tracker methodologies.

Key improvements from v3.0:
1. Fresh Wallet Detection - Flag new wallets making large trades
2. Position Sizing Analysis - % of capital in single bet
3. Early Entry Scoring - Reward first-movers (within 6hrs of market creation)
4. Off-Hours Activity - Night/weekend trading detection
5. Volume Impact Analysis - Trade size vs daily market volume
6. Cluster Detection - Coordinated wallet groups
7. Perpetual ML - Replace weighted sum with ML model
"""

import math
import logging
import time
from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict

import numpy as np

try:
    import perpetual
    from perpetual import PerpetualClassifier

    PERPETUAL_AVAILABLE = True
except ImportError:
    PERPETUAL_AVAILABLE = False

from poly.intelligence.utils import categorize_market

logger = logging.getLogger(__name__)

MIN_LIQUIDITY_VOLUME = 50000
MIN_LIQUIDITY_PARTICIPANTS = 20

# Feature extraction for ML model
FEATURE_NAMES = [
    "winrate",
    "total_trades",
    "pnl",
    "unique_markets",
    "value_weighted_accuracy",
    "fresh_wallet_score",
    "position_sizing_score",
    "early_entry_score",
    "off_hours_score",
    "volume_impact_score",
    "cluster_score",
    "late_trading_ratio",
    "pre_resolution_ratio",
    "avg_hours_before_resolution",
    "account_age_days",
    "days_since_last_trade",
    "avg_trade_size",
    "max_trade_size",
    "pnl_per_trade",
    "winrate_vs_category_avg",
]


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
    days_since_last = (current_ts - last_trade_ts) / 86400

    if account_age_days < 30:
        return 1.5
    elif account_age_days < 90:
        return 1.0
    elif account_age_days < 180:
        return 0.5
    return 0.0


# ============================================================================
# NEW FEATURES FROM RESEARCH
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
        # Off-hours: 10PM - 6AM (weekday) or any time weekend
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
# ML FEATURE EXTRACTION
# ============================================================================


def extract_ml_features(profile: Dict) -> np.ndarray:
    """Extract features for ML model from trader profile."""
    features = []

    # Basic metrics
    winrate = profile.get("winrate", 0)
    features.append(winrate)

    trades = profile.get("total_trades_actual", profile.get("total_trades", 0))
    features.append(trades)

    pnl = profile.get("pnl", 0)
    features.append(pnl)

    # Multi-market
    mm = profile.get("multi_market", {})
    unique_markets = mm.get("unique_markets", 0)
    features.append(unique_markets)

    # Value-weighted accuracy
    vwa = profile.get("value_weighted_accuracy", winrate)
    features.append(vwa)

    # New features
    avg_trade_size = profile.get("avg_trade_size", 0)
    max_trade_size = profile.get("max_trade_size", 0)
    total_volume = profile.get("total_volume", 0)

    first_ts = profile.get("first_trade_timestamp", 0)
    last_ts = profile.get("last_trade_timestamp", 0)

    features.append(calculate_fresh_wallet_score(trades, avg_trade_size, first_ts))
    features.append(
        calculate_position_sizing_score(max_trade_size, avg_trade_size, total_volume)
    )
    features.append(0.0)  # Early entry - needs market creation time
    features.append(0.0)  # Off-hours - needs raw timestamps
    features.append(0.0)  # Volume impact - needs market data
    features.append(0.0)  # Cluster score - needs cluster analysis

    # Timing features
    t = profile.get("timing", {})
    features.append(t.get("last_minute_ratio", 0))
    features.append(t.get("pre_resolution_ratio", 0))
    features.append(t.get("avg_hours_before_resolution", 0))

    # Account age
    current_ts = int(time.time())
    account_age_days = (current_ts - first_ts) / 86400 if first_ts else 0
    days_since = (current_ts - last_ts) / 86400 if last_ts else 0
    features.append(account_age_days)
    features.append(days_since)

    # Size features
    features.append(avg_trade_size)
    features.append(max_trade_size)

    # Efficiency
    pnl_per_trade = pnl / trades if trades > 0 else 0
    features.append(pnl_per_trade)

    # Winrate vs category (placeholder)
    features.append(0.0)

    return np.array(features, dtype=np.float64)


# ============================================================================
# PERPETUAL ML SCORER
# ============================================================================


class PerpetualInsiderScorer:
    """
    ML-based insider detection using Perpetual gradient boosting.

    Automatically generalizes - no manual hyperparameter tuning needed.
    """

    def __init__(self, budget: float = 0.5):
        self.budget = budget
        self.model: Optional[PerpetualClassifier] = None
        self.is_fitted = False
        self.feature_names = FEATURE_NAMES

    def _create_model(self) -> PerpetualClassifier:
        """Create a new Perpetual classifier."""
        if not PERPETUAL_AVAILABLE:
            raise RuntimeError(
                "Perpetual library not installed. Run: uv pip install perpetual"
            )

        return PerpetualClassifier(
            objective="LogLoss",
            budget=self.budget,
            num_threads=4,
            feature_importance_method="Gain",
        )

    def fit(self, profiles: List[Dict], labels: np.ndarray) -> "PerpetualInsiderScorer":
        """
        Train the model on trader profiles.

        Args:
            profiles: List of trader profile dictionaries
            labels: Binary labels (1 = insider, 0 = not insider)
        """
        logger.info(f"Training Perpetual model on {len(profiles)} samples...")

        # Extract features
        X = np.array([extract_ml_features(p) for p in profiles])

        # Handle NaN/Inf
        X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

        # Create and train model
        self.model = self._create_model()
        self.model.fit(X, labels)

        self.is_fitted = True
        logger.info("Training complete!")

        # Log feature importance
        importance = self.model.feature_importances_
        logger.info("Feature importances:")
        for i, (name, imp) in enumerate(
            sorted(zip(self.feature_names, importance), key=lambda x: -x[1])
        ):
            logger.info(f"  {name}: {imp:.4f}")

        return self

    def predict_proba(self, profiles: List[Dict]) -> np.ndarray:
        """
        Predict insider probability for traders.

        Returns:
            Array of probabilities [0, 1] for each trader
        """
        if not self.is_fitted:
            raise RuntimeError("Model not trained. Call fit() first.")

        X = np.array([extract_ml_features(p) for p in profiles])
        X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

        # Get probability of class 1 (insider)
        proba = self.model.predict_proba(X)
        return proba[:, 1] if proba.ndim > 1 else proba

    def predict(self, profiles: List[Dict], threshold: float = 0.5) -> np.ndarray:
        """Predict insider labels (binary)."""
        proba = self.predict_proba(profiles)
        return (proba >= threshold).astype(int)

    def calibrate(self, X_cal: np.ndarray, y_cal: np.ndarray, alpha: float = 0.1):
        """Calibrate model for better probability estimates."""
        if not self.is_fitted:
            raise RuntimeError("Model not trained.")

        self.model.calibrate(X_cal, y_cal, alpha)
        logger.info("Model calibrated!")

    def calculate_drift(self, X_new: np.ndarray) -> float:
        """Calculate concept drift for new data."""
        if not self.is_fitted:
            raise RuntimeError("Model not trained.")

        return self.model.calculate_drift(X_new, drift_type="concept")

    def save(self, path: str):
        """Save model to file."""
        if not self.is_fitted:
            raise RuntimeError("Model not trained.")

        self.model.save_model(path)
        logger.info(f"Model saved to {path}")

    def load(self, path: str):
        """Load model from file."""
        self.model = self._create_model()
        self.model.load_model(path)
        self.is_fitted = True
        logger.info(f"Model loaded from {path}")


# ============================================================================
# RULE-BASED FALLBACK (when ML not available)
# ============================================================================


class InsiderScorerV4:
    """
    Hybrid scorer - uses ML when available, falls back to rule-based.

    Level thresholds (ML-based 0-1 score scaled to 0-10):
    - CRITICAL: >= 8.0
    - HIGH: >= 5.0
    - MEDIUM: >= 2.0
    - LOW: < 2.0
    """

    def __init__(
        self,
        use_ml: bool = True,
        ml_model_path: Optional[str] = None,
        budget: float = 0.5,
    ):
        self.use_ml = use_ml and PERPETUAL_AVAILABLE
        self.budget = budget
        self.ml_scorer: Optional[PerpetualInsiderScorer] = None
        self.ml_model_path = ml_model_path

        if self.use_ml:
            try:
                self.ml_scorer = PerpetualInsiderScorer(budget=budget)
                if ml_model_path:
                    self.ml_scorer.load(ml_model_path)
                    logger.info(f"Loaded ML model from {ml_model_path}")
            except Exception as e:
                logger.warning(f"Failed to initialize ML model: {e}. Using rule-based.")
                self.use_ml = False

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

        # Use ML if available and trained
        if self.use_ml and self.ml_scorer and self.ml_scorer.is_fitted:
            return self._score_with_ml(profiles)
        else:
            return self._score_with_rules(profiles)

    def _score_with_ml(self, profiles: List[Dict]) -> List[Dict]:
        """Score using ML model."""
        proba = self.ml_scorer.predict_proba(profiles)

        results = []
        for i, p in enumerate(profiles):
            ml_score = proba[i]
            # Scale 0-1 to 0-10
            total_score = ml_score * 10.0

            results.append(
                {
                    **p,
                    "risk_score": round(total_score, 2),
                    "ml_probability": round(ml_score, 4),
                    "level": self.calculate_level(total_score),
                    "scoring_method": "ml",
                }
            )

        return results

    def _score_with_rules(self, profiles: List[Dict]) -> List[Dict]:
        """Score using rule-based system (fallback)."""
        results = []
        for p in profiles:
            winrate = p.get("winrate", 0)
            trades = p.get("total_trades_actual", p.get("total_trades", 0))
            pnl = p.get("pnl", 0)
            t = p.get("timing", {})
            w = p.get("whales", {})
            mm = p.get("multi_market", {})
            market_info = p.get("market_info", {})

            # Original components
            winrate_score = calculate_winrate_score(winrate, trades)
            pnl_score = calculate_pnl_score(pnl)

            late_ratio = t.get("last_minute_ratio", 0)
            pre_res_ratio = t.get("pre_resolution_ratio", 0)
            avg_hours = t.get("avg_hours_before_resolution", 0)
            timing_score = calculate_timing_score(late_ratio, pre_res_ratio, avg_hours)

            unique_markets = mm.get("unique_markets", 0)
            max_share = w.get("max_market_share", 0.0)
            cross_market_score = calculate_concentration_score(
                unique_markets, trades, max_share
            )

            camouflage_score = calculate_camouflage_score(pnl, winrate, trades)

            category_score = calculate_market_category_bonus(
                market_info.get("question", ""),
                market_info.get("group_item_title", ""),
                market_info.get("category", ""),
            )

            first_ts = p.get("first_trade_timestamp", 0)
            last_ts = p.get("last_trade_timestamp", 0)
            freshness_score = calculate_freshness_score(first_ts, last_ts)

            activity_penalty = calculate_activity_penalty(trades)

            # New features
            avg_trade_size = p.get("avg_trade_size", 0)
            max_trade_size = p.get("max_trade_size", 0)
            total_volume = p.get("total_volume", 0)

            fresh_wallet_score = calculate_fresh_wallet_score(
                trades, avg_trade_size, first_ts
            )
            position_sizing_score = calculate_position_sizing_score(
                max_trade_size, avg_trade_size, total_volume
            )

            # New features (placeholders - would need more data)
            early_entry_score = 0.0
            off_hours_score = 0.0
            volume_impact_score = 0.0
            cluster_score = 0.0

            # Total score
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

            # Profile type
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
                    "scoring_method": "rules",
                }
            )

        return results


# ============================================================================
# BACKWARDS COMPATIBILITY
# ============================================================================


class InsiderScorer(InsiderScorerV4):
    """Backwards compatible alias."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
