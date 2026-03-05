"""
Improved market volume monitoring with statistical anomaly detection.
Uses historical baselines, concentration metrics (HHI/Gini), and composite scoring.
"""

import asyncio
import logging
import time
import numpy as np
from typing import List, Dict, Set, Optional
from collections import defaultdict, deque

logger = logging.getLogger(__name__)


class MarketHistoricalBaseline:
    """Tracks historical patterns for a market to establish normal behavior."""

    def __init__(self, lookback_hours: int = 168):  # 7 days
        self.lookback_hours = lookback_hours
        self.hourly_volumes = deque(maxlen=lookback_hours)
        self.hourly_trader_counts = deque(maxlen=lookback_hours)
        self.hourly_hhi = deque(maxlen=lookback_hours)
        self.hourly_trades_per_min = deque(maxlen=lookback_hours)

        self.last_hour_update = 0

    def update_hourly(self, hour_data: Dict):
        """Update with completed hour data."""
        self.hourly_volumes.append(hour_data.get("volume", 0))
        self.hourly_trader_counts.append(hour_data.get("trader_count", 0))
        self.hourly_hhi.append(hour_data.get("hhi", 0))
        self.hourly_trades_per_min.append(hour_data.get("trades_per_min", 0))
        self.last_hour_update = int(time.time())

    def get_volume_z_score(self, current_volume: float) -> float:
        """Calculate z-score for current volume vs historical."""
        if len(self.hourly_volumes) < 24:  # Need at least 1 day
            return 0.0

        mean = np.mean(self.hourly_volumes)
        std = np.std(self.hourly_volumes)

        if std == 0:
            return 0.0

        return (current_volume - mean) / std

    def get_trader_count_z_score(self, current_count: int) -> float:
        """Calculate z-score for trader count."""
        if len(self.hourly_trader_counts) < 24:
            return 0.0

        mean = np.mean(self.hourly_trader_counts)
        std = np.std(self.hourly_trader_counts)

        if std == 0:
            return 0.0

        return (current_count - mean) / std

    def get_velocity_z_score(self, current_tpm: float) -> float:
        """Calculate z-score for trades per minute."""
        if len(self.hourly_trades_per_min) < 24:
            return 0.0

        mean = np.mean(self.hourly_trades_per_min)
        std = np.std(self.hourly_trades_per_min)

        if std == 0:
            return 0.0

        return (current_tpm - mean) / std

    @property
    def has_sufficient_data(self) -> bool:
        """Check if we have enough data for reliable statistics."""
        return len(self.hourly_volumes) >= 24


class MarketTradingWindow:
    """Rolling 30-minute window of trades for a single market."""

    def __init__(self, condition_id: str):
        self.condition_id = condition_id
        self.trades: deque = deque()
        self.total_volume: float = 0.0
        self.buy_volume: float = 0.0
        self.sell_volume: float = 0.0
        self.traders: set = set()
        self.trader_volumes: Dict[str, float] = defaultdict(float)

        self.market_info: Dict = {}
        self.volume_24h: float = 0.0
        self.last_update: int = 0

    def add_trade(self, trade: Dict):
        """Add a trade to the window."""
        timestamp = trade["timestamp"]
        size = float(trade["size"])
        price = float(trade["price"])
        wallet = trade["proxyWallet"].lower()
        side = trade["side"].upper()

        trade_value = size * price

        self.trades.append(trade)
        self.last_update = int(time.time())

        self.total_volume += trade_value
        self.traders.add(wallet)
        self.trader_volumes[wallet] += trade_value

        if side == "BUY":
            self.buy_volume += trade_value
        else:
            self.sell_volume += trade_value

    def remove_oldest(self, cutoff_timestamp: int):
        """Remove trades older than cutoff."""
        while self.trades and self.trades[0]["timestamp"] < cutoff_timestamp:
            trade = self.trades.popleft()

            trade_value = float(trade["size"]) * float(trade["price"])
            side = trade["side"].upper()
            wallet = trade["proxyWallet"].lower()

            self.total_volume -= trade_value
            self.trader_volumes[wallet] -= trade_value

            if self.trader_volumes[wallet] <= 0:
                self.traders.discard(wallet)
                del self.trader_volumes[wallet]

            if side == "BUY":
                self.buy_volume -= trade_value
            else:
                self.sell_volume -= trade_value

    def calculate_hhi(self) -> float:
        """Calculate Herfindahl-Hirschman Index (concentration)."""
        if self.total_volume == 0:
            return 0.0

        shares = [v / self.total_volume for v in self.trader_volumes.values()]
        return sum(s**2 for s in shares)

    def calculate_gini(self) -> float:
        """Calculate Gini coefficient (inequality)."""
        volumes = list(self.trader_volumes.values())
        n = len(volumes)

        if n == 0 or self.total_volume == 0:
            return 0.0

        sorted_volumes = sorted(volumes)
        cumsum = 0
        weighted_sum = 0

        for i, v in enumerate(sorted_volumes):
            cumsum += v
            weighted_sum += (i + 1) * v

        return (2 * weighted_sum) / (n * self.total_volume) - (n + 1) / n

    def get_whale_dominance(self) -> float:
        """Get percentage of volume from top 3 traders."""
        if self.total_volume == 0:
            return 0.0

        top_3 = sorted(self.trader_volumes.values(), reverse=True)[:3]
        return sum(top_3) / self.total_volume

    def get_trades_per_minute(self) -> float:
        """Calculate trades per minute in window."""
        if not self.trades:
            return 0.0

        window_minutes = 30  # 30-minute window
        return len(self.trades) / window_minutes


class GlobalMarketState:
    """Manages all market trading windows and baselines."""

    def __init__(self):
        self.market_windows: Dict[str, MarketTradingWindow] = {}
        self.market_baselines: Dict[str, MarketHistoricalBaseline] = {}
        self.alert_history: Dict[str, List[Dict]] = defaultdict(list)
        self.alert_cooldown_minutes = 10
        self.total_alerts_sent = 0
        self.markets_monitored = 0

    def get_or_create_window(self, condition_id: str) -> MarketTradingWindow:
        """Get or create trading window for market."""
        if condition_id not in self.market_windows:
            self.market_windows[condition_id] = MarketTradingWindow(condition_id)
            self.markets_monitored += 1
        return self.market_windows[condition_id]

    def get_or_create_baseline(self, condition_id: str) -> MarketHistoricalBaseline:
        """Get or create baseline for market."""
        if condition_id not in self.market_baselines:
            self.market_baselines[condition_id] = MarketHistoricalBaseline()
        return self.market_baselines[condition_id]

    def cleanup_stale_markets(self, active_condition_ids: set):
        """Remove markets no longer in top 100."""
        to_remove = set(self.market_windows.keys()) - active_condition_ids
        for cid in to_remove:
            del self.market_windows[cid]
            # Keep baselines for historical data
            self.markets_monitored -= 1

    def can_alert(self, condition_id: str, alert_level: str) -> bool:
        """Check if we can send alert (cooldown logic)."""
        if alert_level == "CRITICAL_TRADER":
            return True  # Always alert for critical traders

        now = time.time()
        last_alerts = self.alert_history.get(condition_id, [])

        recent_alerts = [
            a
            for a in last_alerts
            if now - a["timestamp"] < (self.alert_cooldown_minutes * 60)
        ]

        return len(recent_alerts) == 0

    def record_alert(self, condition_id: str, alert_level: str):
        """Record that an alert was sent."""
        self.alert_history[condition_id].append(
            {"timestamp": time.time(), "level": alert_level}
        )


class ImprovedMarketVolumeMonitor:
    """
    Improved volume monitor using statistical anomaly detection.

    Key improvements:
    - Historical baseline comparison (Z-scores)
    - Concentration metrics (HHI, Gini)
    - Composite anomaly scoring
    - Whale dominance tracking
    - Reduced false positives
    """

    def __init__(
        self,
        discord_bot,
        state,
        poll_interval: int = 15,
        market_refresh_interval: int = 120,
    ):
        self.discord_bot = discord_bot
        self.state = state
        self.poll_interval = poll_interval
        self.market_refresh_interval = market_refresh_interval

        self.top_n_markets = 100
        self.window_size_minutes = 30

        # Anomaly thresholds
        self.min_anomaly_score = 7.0  # Only alert if score > 7
        self.min_volume_z_score = 2.5  # 95%+ confidence
        self.min_hhi = 0.20  # Concentration threshold
        self.min_whale_dominance = 0.40  # Top 3 traders threshold
        self.min_absolute_volume = 500000  # $500k minimum

        self.market_state = GlobalMarketState()
        self.last_market_refresh = 0
        self.last_baseline_update = 0

    async def monitor_continuously(self):
        """Main monitoring loop."""
        logger.info("Starting improved market volume monitor...")

        while True:
            try:
                if not self.discord_bot:
                    await asyncio.sleep(self.poll_interval)
                    continue

                current_time = time.time()

                # Refresh top markets list
                if (
                    current_time - self.last_market_refresh
                    > self.market_refresh_interval
                ):
                    await self._refresh_top_markets()
                    self.last_market_refresh = current_time

                # Update baselines hourly
                if current_time - self.last_baseline_update > 3600:
                    self._update_baselines()
                    self.last_baseline_update = current_time

                # Fetch and process trades
                await self._fetch_and_process_trades()

                # Check for anomalies and alert
                await self._check_and_alert()

                await asyncio.sleep(self.poll_interval)

            except asyncio.CancelledError:
                logger.info("Market volume monitor cancelled")
                break
            except Exception as e:
                logger.error(f"Error in market volume monitor: {e}", exc_info=True)
                await asyncio.sleep(self.poll_interval)

    async def _refresh_top_markets(self):
        """Refresh list of top 100 markets by volume."""
        from poly.api.async_client import AsyncPolymarketClient

        async with AsyncPolymarketClient() as client:
            params = {
                "active": True,
                "closed": False,
                "limit": self.top_n_markets,
                "order": "volume24hr",
                "ascending": False,
            }

            markets = await client._safe_get(
                f"{client.gamma_base}/markets", params=params
            )

            if not markets:
                return

            active_cids = set()
            for market in markets:
                cid = market["conditionId"]
                active_cids.add(cid)

                window = self.market_state.get_or_create_window(cid)
                window.market_info = {
                    "question": market.get("question", ""),
                    "slug": market.get("slug", ""),
                    "category": market.get("category", ""),
                }
                window.volume_24h = market.get("volume24hr", 0)

            self.market_state.cleanup_stale_markets(active_cids)
            logger.info(f"Refreshed {len(active_cids)} top markets")

    def _update_baselines(self):
        """Update hourly baselines for all markets."""
        for cid, window in self.market_state.market_windows.items():
            baseline = self.market_state.get_or_create_baseline(cid)

            hour_data = {
                "volume": window.total_volume,
                "trader_count": len(window.traders),
                "hhi": window.calculate_hhi(),
                "trades_per_min": window.get_trades_per_minute(),
            }

            baseline.update_hourly(hour_data)

        logger.info("Updated hourly baselines for all markets")

    async def _fetch_and_process_trades(self):
        """Fetch recent trades for all monitored markets."""
        from poly.api.async_client import AsyncPolymarketClient

        current_time = int(time.time() * 1000)
        window_start = int(current_time - (self.window_size_minutes * 60 * 1000))

        markets = list(self.market_state.market_windows.keys())
        batch_size = 20
        batch_delay = 0.2

        for i in range(0, len(markets), batch_size):
            batch = markets[i : i + batch_size]

            tasks = [self._fetch_market_trades(cid, window_start) for cid in batch]
            results = await asyncio.gather(*tasks)

            for cid, trades in zip(batch, results):
                window = self.market_state.get_or_create_window(cid)
                window.remove_oldest(int(window_start / 1000))

                for trade in trades:
                    window.add_trade(trade)

            if i + batch_size < len(markets):
                await asyncio.sleep(batch_delay)

    async def _fetch_market_trades(
        self, condition_id: str, start_ts: int
    ) -> List[Dict]:
        """Fetch trades for a specific market."""
        from poly.api.async_client import AsyncPolymarketClient

        async with AsyncPolymarketClient() as client:
            params = {
                "market": condition_id,
                "limit": 1000,
                "start": int(start_ts / 1000),
            }

            trades = await client._safe_get(f"{client.data_base}/trades", params=params)
            return trades if isinstance(trades, list) else []

    def _calculate_anomaly_score(
        self, window: MarketTradingWindow, baseline: MarketHistoricalBaseline
    ) -> Dict:
        """Calculate composite anomaly score."""

        # 1. Volume Z-Score (30% weight)
        volume_z = baseline.get_volume_z_score(window.total_volume)
        volume_component = min(abs(volume_z) / 3.0, 1.0) * 3.0

        # 2. Concentration Score (25% weight)
        hhi = window.calculate_hhi()
        concentration_component = (hhi / 0.25) * 2.5

        # 3. Velocity Score (20% weight)
        tpm = window.get_trades_per_minute()
        velocity_z = baseline.get_velocity_z_score(tpm)
        velocity_component = min(abs(velocity_z) / 3.0, 1.0) * 2.0

        # 4. Whale Score (15% weight)
        whale_dominance = window.get_whale_dominance()
        whale_component = (whale_dominance / 0.5) * 1.5

        # 5. Directional Score (10% weight)
        if window.total_volume > 0:
            same_side = max(window.buy_volume, window.sell_volume) / window.total_volume
            directional_component = ((same_side - 0.5) / 0.5) * 1.0
        else:
            directional_component = 0.0

        total_score = (
            volume_component
            + concentration_component
            + velocity_component
            + whale_component
            + directional_component
        )

        return {
            "total_score": total_score,
            "volume_z": volume_z,
            "hhi": hhi,
            "gini": window.calculate_gini(),
            "whale_dominance": whale_dominance,
            "trades_per_min": tpm,
            "velocity_z": velocity_z,
            "same_side_pct": same_side if window.total_volume > 0 else 0.5,
            "components": {
                "volume": volume_component,
                "concentration": concentration_component,
                "velocity": velocity_component,
                "whale": whale_component,
                "directional": directional_component,
            },
        }

    async def _check_and_alert(self):
        """Check for anomalies and send alerts."""
        critical_wallets = {
            addr
            for addr, profile in self.state.master_profiles.items()
            if profile.get("level") == "CRITICAL"
        }

        alerts = []

        for cid, window in self.market_state.market_windows.items():
            # Skip if insufficient volume
            if window.total_volume < self.min_absolute_volume:
                continue

            baseline = self.market_state.get_or_create_baseline(cid)

            # Check for CRITICAL trader activity first
            critical_trades = [
                t for t in window.trades if t["proxyWallet"].lower() in critical_wallets
            ]

            if critical_trades:
                # Check if any single trade > $50k or wallet dominance > 30%
                for trade in critical_trades:
                    trade_value = float(trade["size"]) * float(trade["price"])
                    wallet = trade["proxyWallet"].lower()
                    wallet_volume = window.trader_volumes.get(wallet, 0)
                    wallet_pct = (
                        wallet_volume / window.total_volume
                        if window.total_volume > 0
                        else 0
                    )

                    if trade_value > 50000 or wallet_pct > 0.30:
                        alert = {
                            "condition_id": cid,
                            "alert_level": "CRITICAL_TRADER",
                            "window": window,
                            "critical_trades": critical_trades,
                            "anomaly_score": None,
                        }
                        alerts.append(alert)
                        self.market_state.record_alert(cid, "CRITICAL_TRADER")
                        break

            # Skip statistical analysis if no baseline data yet
            if not baseline.has_sufficient_data:
                continue

            # Calculate anomaly score
            score_data = self._calculate_anomaly_score(window, baseline)

            # Check if meets alert criteria
            meets_criteria = (
                score_data["total_score"] >= self.min_anomaly_score
                and score_data["volume_z"] >= self.min_volume_z_score
                and (
                    score_data["hhi"] >= self.min_hhi
                    or score_data["whale_dominance"] >= self.min_whale_dominance
                )
            )

            if meets_criteria:
                if not self.market_state.can_alert(cid, "STATISTICAL_ANOMALY"):
                    continue

                alert_level = self._determine_alert_level(score_data, window)

                alert = {
                    "condition_id": cid,
                    "alert_level": alert_level,
                    "window": window,
                    "anomaly_score": score_data,
                    "critical_trades": [],
                }

                alerts.append(alert)
                self.market_state.record_alert(cid, alert_level)

        # Send all alerts
        for alert in alerts:
            await self._send_alert(alert)

    def _determine_alert_level(
        self, score_data: Dict, window: MarketTradingWindow
    ) -> str:
        """Determine alert severity level."""
        score = score_data["total_score"]
        hhi = score_data["hhi"]
        whale = score_data["whale_dominance"]

        if score >= 9.0:
            return "CRITICAL_ANOMALY"
        elif score >= 8.0 and (hhi >= 0.30 or whale >= 0.60):
            return "HIGH_CONCENTRATION"
        elif score >= 7.5:
            return "MODERATE_ANOMALY"
        else:
            return "STATISTICAL_ANOMALY"

    async def _send_alert(self, alert: Dict):
        """Send Discord alert."""
        if not self.discord_bot:
            return

        window = alert["window"]
        alert_level = alert["alert_level"]
        score_data = alert.get("anomaly_score")

        color = self._get_alert_color(alert_level)
        emoji = self._get_alert_emoji(alert_level)

        embed = {
            "title": f"{emoji} MARKET ANOMALY: {alert_level}",
            "description": f"**{window.market_info['question']}**",
            "url": f"https://polymarket.com/event/{window.market_info['slug']}",
            "color": color,
            "fields": [
                {
                    "name": "Volume (30m)",
                    "value": f"**${window.total_volume:,.0f}**",
                    "inline": True,
                },
                {
                    "name": "24h Volume",
                    "value": f"${window.volume_24h:,.0f}",
                    "inline": True,
                },
                {
                    "name": "Traders",
                    "value": f"{len(window.traders)}",
                    "inline": True,
                },
            ],
            "footer": {
                "text": "🛰️ Poly Intelligence Hub | Statistical Anomaly Detection"
            },
        }

        if score_data:
            embed["fields"].extend(
                [
                    {
                        "name": "Anomaly Score",
                        "value": f"**{score_data['total_score']:.1f}**/10",
                        "inline": True,
                    },
                    {
                        "name": "Volume Z-Score",
                        "value": f"{score_data['volume_z']:.1f}σ",
                        "inline": True,
                    },
                    {
                        "name": "HHI (Concentration)",
                        "value": f"{score_data['hhi']:.3f}",
                        "inline": True,
                    },
                    {
                        "name": "Whale Dominance",
                        "value": f"{score_data['whale_dominance']:.1%}",
                        "inline": True,
                    },
                    {
                        "name": "Gini Coefficient",
                        "value": f"{score_data['gini']:.3f}",
                        "inline": True,
                    },
                    {
                        "name": "Directional",
                        "value": f"{score_data['same_side_pct']:.1%}",
                        "inline": True,
                    },
                ]
            )

        if alert["critical_trades"]:
            critical_text = "\n".join(
                [
                    f"- {t.get('pseudonym', t['proxyWallet'][:10])} (${float(t['size']) * float(t['price']):,.0f})"
                    for t in alert["critical_trades"][:3]
                ]
            )
            embed["fields"].append(
                {
                    "name": "⚠️ CRITICAL Traders Active",
                    "value": critical_text,
                    "inline": False,
                }
            )

        url = f"{self.discord_bot.base_url}/channels/{self.discord_bot.channels['market_anomalies']}/messages"

        resp = self.discord_bot.client.post(
            url, headers=self.discord_bot.headers, json={"embeds": [embed]}
        )

        if resp.status_code in [200, 201, 204]:
            logger.info(f"Sent {alert_level} alert for {alert['condition_id'][:20]}")
            self.market_state.total_alerts_sent += 1
        else:
            logger.warning(f"Failed to send alert: {resp.status_code}")

    def _get_alert_color(self, alert_level: str) -> int:
        """Get Discord embed color for alert level."""
        colors = {
            "CRITICAL_TRADER": 0xFF0000,
            "CRITICAL_ANOMALY": 0xFF4500,
            "HIGH_CONCENTRATION": 0xFF6600,
            "MODERATE_ANOMALY": 0xFFA500,
            "STATISTICAL_ANOMALY": 0xFFD700,
        }
        return colors.get(alert_level, 0x7289DA)

    def _get_alert_emoji(self, alert_level: str) -> str:
        """Get emoji for alert level."""
        emojis = {
            "CRITICAL_TRADER": "🔴",
            "CRITICAL_ANOMALY": "🟠",
            "HIGH_CONCENTRATION": "🟠",
            "MODERATE_ANOMALY": "🟡",
            "STATISTICAL_ANOMALY": "🟢",
        }
        return emojis.get(alert_level, "📊")
