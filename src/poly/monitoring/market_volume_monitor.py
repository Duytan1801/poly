"""
Market volume monitoring for detecting insider trading patterns.
Tracks top 100 markets by 24h volume and detects anomalous trading activity.
"""

import asyncio
import logging
import time
from typing import List, Dict, Set
from collections import defaultdict, deque

logger = logging.getLogger(__name__)


class MarketTradingWindow:
    """Rolling 1-hour window of trades for a single market."""

    def __init__(self, condition_id: str):
        self.condition_id = condition_id

        self.trades: deque = deque()
        self.total_volume: float = 0.0
        self.buy_volume: float = 0.0
        self.sell_volume: float = 0.0
        self.traders: set = set()
        self.time_clusters: Dict[int, Set[str]] = defaultdict(set)

        self.market_info: Dict = {}
        self.volume_24h: float = 0.0
        self.volume_threshold: float = 0.0
        self.last_update: int = 0

    def add_trade(self, trade: Dict):
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

        if side == "BUY":
            self.buy_volume += trade_value
        else:
            self.sell_volume += trade_value

        bucket = int(timestamp / 300)
        self.time_clusters[bucket].add(wallet)

    def remove_oldest(self, cutoff_timestamp: int):
        while self.trades and self.trades[0]["timestamp"] < cutoff_timestamp:
            trade = self.trades.popleft()

            trade_value = float(trade["size"]) * float(trade["price"])
            side = trade["side"].upper()
            wallet = trade["proxyWallet"].lower()

            self.total_volume -= trade_value
            self.traders.discard(wallet)

            if side == "BUY":
                self.buy_volume -= trade_value
            else:
                self.sell_volume -= trade_value

            bucket = int(trade["timestamp"] / 300)
            if bucket in self.time_clusters and wallet in self.time_clusters[bucket]:
                self.time_clusters[bucket].discard(wallet)
                if not self.time_clusters[bucket]:
                    del self.time_clusters[bucket]

    def get_metrics(self) -> Dict:
        same_side_concentration = 0.0
        if self.total_volume > 0:
            same_side_concentration = (
                max(self.buy_volume, self.sell_volume) / self.total_volume
            )

        max_concurrent_traders = 0
        if self.time_clusters:
            max_concurrent_traders = max(
                len(wallets) for wallets in self.time_clusters.values()
            )

        return {
            "condition_id": self.condition_id,
            "total_volume": self.total_volume,
            "buy_volume": self.buy_volume,
            "sell_volume": self.sell_volume,
            "same_side_concentration": same_side_concentration,
            "trader_count": len(self.traders),
            "max_concurrent_traders": max_concurrent_traders,
            "volume_24h": self.volume_24h,
            "volume_threshold": self.volume_threshold,
            "above_threshold": self.total_volume >= self.volume_threshold,
        }


class GlobalMarketState:
    """Manages all market trading windows and global coordination."""

    def __init__(self):
        self.market_windows: Dict[str, MarketTradingWindow] = {}
        self.alert_history: Dict[str, List[Dict]] = defaultdict(list)
        self.alert_cooldown_minutes = 5  # Reduced from 15 to 5 for faster re-alerts
        self.total_alerts_sent = 0
        self.markets_monitored = 0

    def get_or_create_window(self, condition_id: str) -> MarketTradingWindow:
        if condition_id not in self.market_windows:
            self.market_windows[condition_id] = MarketTradingWindow(condition_id)
            self.markets_monitored += 1
        return self.market_windows[condition_id]

    def cleanup_stale_markets(self, active_condition_ids: set):
        to_remove = set(self.market_windows.keys()) - active_condition_ids
        for cid in to_remove:
            del self.market_windows[cid]
            self.markets_monitored -= 1

    def can_alert(self, condition_id: str, alert_level: str) -> bool:
        if alert_level == "CRITICAL_TRADER":
            return True

        now = time.time()
        last_alerts = self.alert_history.get(condition_id, [])

        recent_alerts = [
            a
            for a in last_alerts
            if now - a["timestamp"] < (self.alert_cooldown_minutes * 60)
        ]

        if recent_alerts:
            return False

        return True

    def record_alert(self, condition_id: str, alert_level: str):
        self.alert_history[condition_id].append(
            {"timestamp": time.time(), "level": alert_level}
        )


class MarketVolumeMonitor:
    """Monitor trading volume across top 100 markets by 24h volume."""

    def __init__(
        self,
        discord_bot,
        state,
        poll_interval: int = 15,  # Reduced from 60s to 15s for 4x faster detection
        market_refresh_interval: int = 120,  # Reduced from 300s to 120s
    ):
        self.discord_bot = discord_bot
        self.state = state
        self.poll_interval = poll_interval
        self.market_refresh_interval = market_refresh_interval

        self.top_n_markets = 100
        self.min_volume_threshold = 900000  # Only monitor markets with >$900k volume
        self.volume_threshold_tiers = {
            "TIER_1": 900000,  # $900k minimum threshold
            "TIER_2": 1500000,  # $1.5M threshold
            "TIER_3": 2500000,  # $2.5M threshold (critical)
        }
        self.volume_threshold_pct = (
            0.02  # Lower percentage for higher absolute threshold
        )
        self.threshold_max = 5000000  # Increase max to $5M for very high volume markets

        self.market_state = GlobalMarketState()
        self.last_market_refresh = 0
        self.window_size_hours = (
            0.5  # Reduced from 1h to 30min for faster spike detection
        )

    async def monitor_continuously(self):
        logger.info("Starting market volume monitor...")

        while True:
            try:
                if not self.discord_bot:
                    await asyncio.sleep(self.poll_interval)
                    continue

                current_time = time.time()

                if (
                    current_time - self.last_market_refresh
                    > self.market_refresh_interval
                ):
                    await self._refresh_top_markets()
                    self.last_market_refresh = current_time

                await self._fetch_and_process_trades()
                await self._check_and_alert()

                await asyncio.sleep(self.poll_interval)

            except asyncio.CancelledError:
                logger.info("Market volume monitor cancelled")
                break
            except Exception as e:
                logger.error(f"Error in market volume monitor: {e}")
                await asyncio.sleep(self.poll_interval)

    async def _refresh_top_markets(self):
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

                daily_volume = market.get("volume24hr", 0)
                threshold = daily_volume * self.volume_threshold_pct
                threshold = max(threshold, self.volume_threshold_tiers["TIER_1"])
                threshold = min(threshold, self.threshold_max)

                window.volume_24h = daily_volume
                window.volume_threshold = threshold

            self.market_state.cleanup_stale_markets(active_cids)
            logger.info(f"Refreshed {len(active_cids)} top markets")

    async def _fetch_and_process_trades(self):
        from poly.api.async_client import AsyncPolymarketClient

        current_time = int(time.time() * 1000)
        window_start = int(current_time - (self.window_size_hours * 3600 * 1000))

        markets = list(self.market_state.market_windows.keys())
        batch_size = 20  # Increased from 10 to 20 for faster processing
        batch_delay = 0.2  # Reduced from 0.5s to 0.2s for faster batching

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
        from poly.api.async_client import AsyncPolymarketClient

        async with AsyncPolymarketClient() as client:
            params = {
                "market": condition_id,
                "limit": 1000,
                "start": int(start_ts / 1000),
            }

            trades = await client._safe_get(f"{client.data_base}/trades", params=params)

            return trades if isinstance(trades, list) else []

    async def _check_and_alert(self):
        critical_wallets = {
            addr
            for addr, profile in self.state.master_profiles.items()
            if profile.get("level") == "CRITICAL"
        }

        alerts = []

        for cid, window in self.market_state.market_windows.items():
            metrics = window.get_metrics()

            # Only alert if 1-hour volume exceeds $900k minimum
            if metrics["total_volume"] < self.min_volume_threshold:
                continue

            if not metrics["above_threshold"]:
                continue

            alert_level = self._determine_alert_level(metrics, window, critical_wallets)

            if not self.market_state.can_alert(cid, alert_level):
                continue

            alert = {
                "condition_id": cid,
                "alert_level": alert_level,
                "metrics": metrics,
                "window": window,
                "critical_traders": [
                    t
                    for t in window.trades
                    if t["proxyWallet"].lower() in critical_wallets
                ],
            }

            alerts.append(alert)
            self.market_state.record_alert(cid, alert_level)

        for alert in alerts:
            await self._send_alert(alert)

    def _determine_alert_level(
        self, metrics: Dict, window: MarketTradingWindow, critical_wallets: Set[str]
    ) -> str:
        critical_trading = any(
            t["proxyWallet"].lower() in critical_wallets for t in window.trades
        )

        if critical_trading:
            return "CRITICAL_TRADER"

        same_directional = metrics["same_side_concentration"] > 0.7
        clustered = metrics["max_concurrent_traders"] >= 5

        if same_directional and clustered:
            return "COORDINATED_DIRECTIONAL"

        if same_directional:
            return "DIRECTIONAL_SPIKE"

        if clustered:
            return "COORDINATED_ACTIVITY"

        tier_3_threshold = self.volume_threshold_tiers["TIER_3"]
        if metrics["total_volume"] >= tier_3_threshold:
            return "CRITICAL_VOLUME"

        tier_2_threshold = self.volume_threshold_tiers["TIER_2"]
        if metrics["total_volume"] >= tier_2_threshold:
            return "HIGH_VOLUME"

        return "VOLUME_SPIKE"

    async def _send_alert(self, alert: Dict):
        if not self.discord_bot:
            return

        metrics = alert["metrics"]
        alert_level = alert["alert_level"]
        window = alert["window"]

        color = self._get_alert_color(alert_level)
        emoji = self._get_alert_emoji(alert_level)

        embed = {
            "title": f"{emoji} MARKET ANOMALY: {alert_level}",
            "description": f"**{window.market_info['question']}**",
            "url": f"https://polymarket.com/event/{window.market_info['slug']}",
            "color": color,
            "fields": [
                {
                    "name": "Volume (1h)",
                    "value": f"**${metrics['total_volume']:,.0f}**",
                    "inline": True,
                },
                {
                    "name": "Threshold",
                    "value": f"${metrics['volume_threshold']:,.0f}",
                    "inline": True,
                },
                {
                    "name": "24h Volume",
                    "value": f"${metrics['volume_24h']:,.0f}",
                    "inline": True,
                },
                {
                    "name": "Directional",
                    "value": f"{metrics['same_side_concentration']:.1%}",
                    "inline": True,
                },
                {
                    "name": "Unique Traders",
                    "value": f"{metrics['trader_count']}",
                    "inline": True,
                },
                {
                    "name": "Max Concurrent",
                    "value": f"{metrics['max_concurrent_traders']} (5m)",
                    "inline": True,
                },
                {
                    "name": "Buy vs Sell",
                    "value": f"🟢 ${metrics['buy_volume']:,.0f}\n🔴 ${metrics['sell_volume']:,.0f}",
                    "inline": True,
                },
            ],
            "footer": {"text": "🛰️ Poly Intelligence Hub | Market Volume Monitor"},
        }

        if alert["critical_traders"]:
            critical_text = "\n".join(
                [
                    f"- {t.get('pseudonym', t['proxyWallet'][:10])} (${float(t['size']) * float(t['price']):,.0f})"
                    for t in alert["critical_traders"][:3]
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
        colors = {
            "CRITICAL_TRADER": 0xFF0000,
            "COORDINATED_DIRECTIONAL": 0xFF4500,
            "CRITICAL_VOLUME": 0xFF6600,
            "DIRECTIONAL_SPIKE": 0xFF8C00,
            "COORDINATED_ACTIVITY": 0xFFA500,
            "HIGH_VOLUME": 0xFFD700,
            "VOLUME_SPIKE": 0xFFE4B5,
        }
        return colors.get(alert_level, 0x7289DA)

    def _get_alert_emoji(self, alert_level: str) -> str:
        emojis = {
            "CRITICAL_TRADER": "🔴",
            "COORDINATED_DIRECTIONAL": "🟠",
            "CRITICAL_VOLUME": "🟠",
            "DIRECTIONAL_SPIKE": "🟡",
            "COORDINATED_ACTIVITY": "🟡",
            "HIGH_VOLUME": "🟡",
            "VOLUME_SPIKE": "🟢",
        }
        return emojis.get(alert_level, "📊")
