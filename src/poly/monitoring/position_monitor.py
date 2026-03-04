"""
Position holdings monitoring for HIGH/CRITICAL traders.
Monitors current positions and sends notifications when PnL changes significantly.
"""

import asyncio
import logging
from typing import List, Dict
from collections import defaultdict

logger = logging.getLogger(__name__)


class PositionMonitor:
    """Monitor position holdings and PnL changes for HIGH/CRITICAL traders."""

    def __init__(self, discord_bot, state, poll_interval: int = 300):
        """
        Args:
            discord_bot: DiscordBotClient instance
            state: OptimizedEngineState instance
            poll_interval: Seconds between position polls (default: 300 = 5 minutes)
        """
        self.discord_bot = discord_bot
        self.state = state
        self.poll_interval = poll_interval

        # Configuration
        self.pnl_change_threshold = 5000  # $5,000 PnL change to notify
        self.position_size_min = 5000  # $5,000 minimum position to include

        # Track last PnL and positions per wallet
        # wallet -> {"pnl": float, "positions": list}
        self.last_pnl_data: Dict[str, Dict] = {}

    async def monitor_continuously(self):
        """Run continuous position monitoring loop."""
        logger.info("Starting position monitor...")

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

                # Check positions for all monitored wallets
                await self._check_positions_monitored_wallets(monitored_wallets)

                await asyncio.sleep(self.poll_interval)

            except asyncio.CancelledError:
                logger.info("Position monitor cancelled")
                break
            except Exception as e:
                logger.error(f"Error in position monitor: {e}")
                await asyncio.sleep(self.poll_interval)

    async def _check_positions_monitored_wallets(self, wallets: List[str]):
        """Check positions and PnL for monitored wallets."""
        from poly.api.async_client import AsyncPolymarketClient

        async with AsyncPolymarketClient() as client:
            for wallet in wallets:
                try:
                    # Fetch current positions
                    params = {
                        "user": wallet,
                        "sortBy": "TOTALPNL",
                        "sortDirection": "DESC",
                        "limit": 50,
                    }

                    positions_data = await client._safe_get(
                        f"{client.data_base}/positions", params=params
                    )

                    if not positions_data:
                        continue

                    positions = (
                        positions_data if isinstance(positions_data, list) else []
                    )

                    # Filter significant positions (size >= $5,000 current value)
                    significant_positions = [
                        p
                        for p in positions
                        if float(p.get("currentValue", 0)) >= self.position_size_min
                    ]

                    if not significant_positions:
                        continue

                    # Calculate total PnL and portfolio value
                    total_pnl = sum(
                        float(p.get("totalPnl", 0)) for p in significant_positions
                    )
                    total_value = sum(
                        float(p.get("currentValue", 0)) for p in significant_positions
                    )

                    # Check if PnL changed significantly
                    last_pnl_data = self.last_pnl_data.get(wallet, {})
                    last_pnl = last_pnl_data.get("pnl", 0)

                    pnl_change = total_pnl - last_pnl

                    # Notify if:
                    # 1. First time checking, OR
                    # 2. PnL changed > threshold, OR
                    # 3. Time since last check > 1 hour (force update)
                    force_update = (
                        last_pnl == 0 or abs(pnl_change) >= self.pnl_change_threshold
                    )

                    if force_update:
                        await self._send_positions_summary(
                            wallet,
                            significant_positions,
                            total_pnl,
                            total_value,
                            pnl_change,
                        )

                    # Store current PnL data
                    self.last_pnl_data[wallet] = {
                        "pnl": total_pnl,
                        "value": total_value,
                        "positions": significant_positions,
                        "last_update": asyncio.get_event_loop().time(),
                    }

                except Exception as e:
                    logger.error(f"Error checking positions for {wallet[:10]}: {e}")

    async def _send_positions_summary(
        self,
        wallet: str,
        positions: List[Dict],
        total_pnl: float,
        total_value: float,
        pnl_change: float,
    ):
        """Send Discord notification with position holdings summary."""
        if not self.discord_bot:
            return

        try:
            profile = self.state.master_profiles.get(wallet, {})
            level = profile.get("level", "LOW")
            score = profile.get("risk_score", 0)
            winrate = profile.get("winrate", 0)

            # Sort positions by total PnL (descending)
            sorted_positions = sorted(
                positions, key=lambda x: float(x.get("totalPnl", 0)), reverse=True
            )

            # Take top 5 positions
            top_positions = sorted_positions[:5]

            # Create embed
            color = 0x00AD7C  # Green for position updates

            # Build fields for each position
            position_fields = []
            for i, pos in enumerate(top_positions, 1):
                pos_pnl = float(pos.get("totalPnl", 0))
                pos_value = float(pos.get("currentValue", 0))
                pos_size = float(pos.get("size", 0))
                pos_price = float(pos.get("curPrice", 0))
                outcome = pos.get("outcome", "Unknown")
                title = pos.get("title", "Unknown Market")

                pnl_emoji = "🟢" if pos_pnl > 0 else ("🔴" if pos_pnl < 0 else "⚪")

                position_fields.append(
                    {
                        "name": f"{i}. {title[:50]}",
                        "value": (
                            f"{outcome} | {pnl_emoji}${pos_pnl:+,.0f}\n"
                            f"Value: ${pos_value:,.0f} | Size: ${pos_size:,.0f} | Price: {pos_price:.2f}"
                        ),
                    }
                )

            # PnL change indicator
            if pnl_change != 0:
                change_text = f"PnL Change: {pnl_change:+,.0f}"
            else:
                change_text = "First Update"

            embed = {
                "title": f"📊 POSITIONS: {level} Risk Trader",
                "description": f"Current portfolio holdings with PnL breakdown",
                "url": f"https://polymarket.com/profile/{wallet}",
                "color": color,
                "fields": [
                    {
                        "name": "Portfolio Summary",
                        "value": (
                            f"Total Value: ${total_value:,.0f}\n"
                            f"Total PnL: {pnl_change:+,.0f}\n"
                            f"Trader WR: {winrate:.1%} | Score: {score:.1f}/10"
                        ),
                        "inline": False,
                    },
                ],
                "footer": {"text": f"🛰️ Poly Intel | {change_text}"},
            }

            # Add position fields
            embed["fields"].extend(position_fields)

            # Send to trades-holding channel
            url = f"{self.discord_bot.base_url}/channels/1478038222855733292/messages"

            resp = self.discord_bot.client.post(
                url, headers=self.discord_bot.headers, json={"embeds": [embed]}
            )

            if resp.status_code not in [200, 201, 204]:
                logger.warning(
                    f"Discord position notification failed: {resp.status_code}"
                )
            else:
                logger.info(
                    f"Sent position summary for {wallet[:10]}: PnL ${pnl_change:+,.0f}"
                )

        except Exception as e:
            logger.error(f"Failed to send position summary: {e}")
