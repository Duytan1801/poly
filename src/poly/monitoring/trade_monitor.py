"""
Real-time trade monitoring for HIGH/CRITICAL traders.
Monitors new trades and sends Discord notifications for significant activity.
"""

import asyncio
import logging
import time
from typing import List, Dict, Optional, Set
from collections import defaultdict

logger = logging.getLogger(__name__)


class RealTimeTradeMonitor:
    """Monitor real-time trades for HIGH/CRITICAL traders."""

    def __init__(self, discord_bot, state, poll_interval: int = 20):
        """
        Args:
            discord_bot: DiscordBotClient instance
            state: OptimizedEngineState instance
            poll_interval: Seconds between trade polls (default: 20)
        """
        self.discord_bot = discord_bot
        self.state = state
        self.poll_interval = poll_interval

        # Configuration
        self.min_trade_size = 5000  # $5,000 minimum for notifications
        self.deduplication_window = 60  # 60 seconds wait for same market

        # Trade deduplication tracking
        # Map: wallet -> market -> last_notification_time
        self.last_notification: Dict[str, Dict[str, float]] = defaultdict(dict)

        # Trade batch window
        # Map: wallet -> list of trades batched for notification
        self.trade_batch: Dict[str, List[Dict]] = defaultdict(list)
        self.batch_start_time: Optional[float] = None

        # Position tracking per wallet
        self.last_positions: Dict[str, Dict] = {}  # wallet -> last PnL data

    async def monitor_continuously(self):
        """Run continuous trade monitoring loop."""
        logger.info("Starting real-time trade monitor...")

        while True:
            try:
                if not self.discord_bot:
                    await asyncio.sleep(self.poll_interval)
                    continue

                monitored_wallets = [
                    addr
                    for addr, profile in self.state.master_profiles.items()
                    if profile.get("level") in ["HIGH", "CRITICAL"]
                ]

                if not monitored_wallets:
                    await asyncio.sleep(self.poll_interval)
                    continue

                # Process batched trades from previous window
                await self._process_batched_trades()

                # Fetch new trades for all monitored wallets
                await self._check_new_trades(monitored_wallets)

                await asyncio.sleep(self.poll_interval)

            except asyncio.CancelledError:
                logger.info("Trade monitor cancelled")
                break
            except Exception as e:
                logger.error(f"Error in trade monitor: {e}")
                await asyncio.sleep(self.poll_interval)

    async def _check_new_trades(self, wallets: List[str]):
        """Check for new trades on monitored wallets."""
        from poly.api.async_client import AsyncPolymarketClient

        async with AsyncPolymarketClient() as client:
            # Get current time
            current_time = time.time() * 1000  # Convert to milliseconds

            for wallet in wallets:
                try:
                    # Get last checked timestamp (or 24 hours ago if first time)
                    last_check = self.state.master_profiles[wallet].get(
                        "last_trade_check", 0
                    )
                    if last_check == 0:
                        # First time check - look back 24 hours
                        last_check = current_time - (24 * 60 * 60 * 1000)

                    # Fetch trades since last check
                    params = {
                        "user": wallet,
                        "takerOnly": "true",
                        "limit": 100,  # Last 100 trades should be enough
                    }

                    # Note: Polymarket API doesn't support timestamp filtering,
                    # so we'll fetch recent trades and filter manually
                    trades_data = await client._safe_get(
                        f"{client.data_base}/trades", params=params
                    )

                    if not trades_data:
                        continue

                    trades = trades_data if isinstance(trades_data, list) else []

                    # Filter trades since last check
                    new_trades = [
                        t for t in trades if t.get("timestamp", 0) > last_check
                    ]

                    if new_trades:
                        # Sort by timestamp (newest first)
                        new_trades.sort(
                            key=lambda x: x.get("timestamp", 0), reverse=True
                        )

                        # Filter by minimum size ($5,000)
                        significant_trades = [
                            t
                            for t in new_trades
                            if float(t.get("size", 0)) * float(t.get("price", 0))
                            >= self.min_trade_size
                        ]

                        if significant_trades:
                            # Add to batch for consolidation
                            await self._add_trades_to_batch(wallet, significant_trades)

                        # Update last check time to newest trade
                        newest_timestamp = max(
                            t.get("timestamp", last_check) for t in trades
                        )
                        self.state.master_profiles[wallet]["last_trade_check"] = (
                            newest_timestamp
                        )

                except Exception as e:
                    logger.error(f"Error checking trades for {wallet[:10]}: {e}")

    async def _add_trades_to_batch(self, wallet: str, trades: List[Dict]):
        """Add trades to batch for consolidated notification."""
        current_time = time.time()

        # Start new batch if first trade in this window
        if self.batch_start_time is None:
            self.batch_start_time = current_time

        # Check if batch window expired
        if current_time - self.batch_start_time > self.deduplication_window:
            await self._process_batched_trades()
            self.batch_start_time = current_time

        # Add trades to batch
        self.trade_batch[wallet].extend(trades)

    async def _process_batched_trades(self):
        """Process and send notifications for batched trades."""
        if not self.trade_batch:
            return

        # Group trades by wallet and market
        for wallet, trades in self.trade_batch.items():
            if not trades:
                continue

            # Group by market (conditionId + title)
            market_groups = defaultdict(list)
            for trade in trades:
                market_key = f"{trade.get('conditionId', '')}-{trade.get('title', '')}"
                market_groups[market_key].append(trade)

            # Send notification for each market with significant activity
            for market_key, market_trades in market_groups.items():
                if not market_trades:
                    continue

                # Check deduplication
                first_trade = market_trades[0]
                market_id = first_trade.get("conditionId", "")
                last_notified = self.last_notification[wallet].get(market_id, 0)

                current_time = time.time() * 1000
                if current_time - last_notified < (self.deduplication_window * 1000):
                    # Within deduplication window, skip notification
                    continue

                # Calculate total size and direction
                total_size = 0
                total_side = None
                price = 0

                for trade in market_trades:
                    size = float(trade.get("size", 0))
                    trade_side = trade.get("side", "UNKNOWN")
                    trade_price = float(trade.get("price", 0))

                    total_size += size
                    total_side = trade_side
                    price = trade_price  # Use latest price

                # Send notification
                profile = self.state.master_profiles.get(wallet, {})
                await self._send_trade_notification(
                    profile,
                    first_trade,
                    total_size,
                    total_side,
                    price,
                    len(market_trades),
                )

                # Update last notification time
                self.last_notification[wallet][market_id] = current_time

        # Clear batch
        self.trade_batch.clear()
        self.batch_start_time = None

    async def _send_trade_notification(
        self,
        profile: Dict,
        trade: Dict,
        total_size: float,
        side: str,
        price: float,
        trade_count: int = 1,
    ):
        """Send Discord notification for a significant trade."""
        if not self.discord_bot:
            return

        try:
            addr = profile.get("address", trade.get("proxyWallet", "Unknown"))
            level = profile.get("level", "LOW")
            score = profile.get("risk_score", 0)
            winrate = profile.get("winrate", 0)

            # Market details
            title = trade.get("title", "Unknown Market")
            outcome = trade.get("outcome", "Unknown")
            slug = trade.get("slug", "")

            # Calculate value
            value = total_size * price

            # Create embed
            color = 0x00FF00  # Green for live trades

            # Trade count text
            trade_text = (
                f"{trade_count} trade{'s' if trade_count > 1 else ''}"
                if trade_count > 1
                else "1 trade"
            )

            embed = {
                "title": f"🎯 LIVE TRADE: {level} Risk Trader",
                "description": f"**Elite Trader** executed a new position.",
                "url": f"https://polymarket.com/event/{slug}" if slug else None,
                "color": color,
                "fields": [
                    {"name": "Market", "value": title, "inline": False},
                    {
                        "name": "Action",
                        "value": f"**{side.upper()}** {outcome}",
                        "inline": True,
                    },
                    {"name": "Size", "value": f"**${value:,.0f}**", "inline": True},
                    {"name": "Price", "value": f"**{price:.2f}**", "inline": True},
                    {
                        "name": "Trader Stats",
                        "value": f"WR: {winrate:.1%} | Score: {score:.1f}/10",
                        "inline": False,
                    },
                ],
                "footer": {"text": f"🛰️ Poly Intel | {trade_text}"},
            }

            # Send to trades-holding channel
            url = f"{self.discord_bot.base_url}/channels/1478038222855733292/messages"

            resp = self.discord_bot.client.post(
                url, headers=self.discord_bot.headers, json={"embeds": [embed]}
            )

            if resp.status_code not in [200, 201, 204]:
                logger.warning(f"Discord trade notification failed: {resp.status_code}")
            else:
                logger.info(
                    f"Sent trade notification for {addr[:10]}: ${value:,.0f} {side} {outcome}"
                )

        except Exception as e:
            logger.error(f"Failed to send trade notification: {e}")
