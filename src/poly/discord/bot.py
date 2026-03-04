"""
Discord Bot Client: Manages intelligence delivery via the Poly Bot.
"""

import logging
import httpx
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


class DiscordBotClient:
    """Uses the Poly Bot token to send formatted embeds to specific channels."""

    def __init__(self):
        import os

        self.token = os.environ.get("DISCORD_BOT_TOKEN")
        if not self.token:
            raise ValueError("DISCORD_BOT_TOKEN environment variable not set")
        self.base_url = "https://discord.com/api/v10"
        self.headers = {
            "Authorization": f"Bot {self.token}",
            "Content-Type": "application/json",
        }
        self.client = httpx.Client(timeout=10.0)
        self.whale_channel = "1478038183873740972"

    def send_trader_embed(self, profile: Dict[str, Any]):
        """Post a high-signal trader alert to the #big-whales channel."""
        addr = profile.get("address", "Unknown")
        level = profile.get("level", "LOW")
        score = profile.get("risk_score", 0)
        winrate = profile.get("winrate", 0)
        pnl = profile.get("pnl", 0)
        profile_type = profile.get("profile_type", "UNKNOWN")

        breakdown = profile.get("score_breakdown", {})

        unique_markets = profile.get("unique_markets", 0)
        late_ratio = profile.get("late_trading_ratio", 0)

        # Color: Critical=Red, High=Orange, Medium=Yellow
        color = (
            0xFF0000
            if level == "CRITICAL"
            else (0xFFA500 if level == "HIGH" else 0xFFFF00)
        )

        breakdown_text = ""
        if breakdown:
            breakdown_text = (
                f"Win: {breakdown.get('winrate', 0):+.1f} | "
                f"PnL: {breakdown.get('pnl', 0):+.1f} | "
                f"Time: {breakdown.get('timing', 0):+.1f}\n"
                f"Cross: {breakdown.get('cross_market', 0):+.1f} | "
                f"Camo: {breakdown.get('camouflage', 0):+.1f}"
            )

        embed = {
            "title": f"🐳 WHALE MOVEMENT: {level} Risk ({profile_type})",
            "description": f"The Intelligence Hub has flagged a new professional wallet.",
            "url": f"https://polymarket.com/profile/{addr}",
            "color": color,
            "fields": [
                {"name": "Wallet Address", "value": f"`{addr}`", "inline": False},
                {
                    "name": "Insider Score",
                    "value": f"🔥 **{score:.1f}/20** ({profile_type})",
                    "inline": True,
                },
                {"name": "Win Rate", "value": f"📈 **{winrate:.1%}**", "inline": True},
                {
                    "name": "Realized PnL",
                    "value": f"💰 **${pnl:,.0f}**",
                    "inline": True,
                },
                {
                    "name": "Markets Traded",
                    "value": f"🏛️ **{unique_markets}** markets",
                    "inline": True,
                },
                {
                    "name": "Late Trading",
                    "value": f"🕐 **{late_ratio:.1%}** in final 48h",
                    "inline": True,
                },
            ],
        }

        if breakdown_text:
            embed["fields"].append(
                {"name": "Score Breakdown", "value": breakdown_text, "inline": False}
            )

        embed["footer"] = {"text": "🛰️ Poly Intelligence Hub | Smart Money Scanner"}

        payload = {"embeds": [embed]}
        url = f"{self.base_url}/channels/{self.whale_channel}/messages"

        try:
            resp = self.client.post(url, headers=self.headers, json=payload)
            if resp.status_code not in [200, 201, 204]:
                logger.warning(f"Discord Bot failed ({resp.status_code}): {resp.text}")
        except Exception as e:
            logger.error(f"Failed to post to Discord: {e}")

    def send_trade_activity_embed(self, trader_profile: Dict, trade: Dict):
        """Post a live trade notification for a watched trader."""
        addr = trader_profile.get("address", "Unknown")
        level = trader_profile.get("level", "LOW")

        # Color: Critical=Red, High=Orange
        color = 0x00FF00  # Green for live activity

        # Trade details
        size = float(trade.get("size", 0))
        price = float(trade.get("price", 0))
        side = trade.get("side", "BUY").upper()
        outcome = trade.get("outcome", "Unknown")
        title = trade.get("title", "Unknown Market")

        embed = {
            "title": f"🎯 LIVE TRADE: {level} Risk Trader",
            "description": f"**{trader_profile.get('username') or 'Elite Trader'}** just executed a new position.",
            "url": f"https://polymarket.com/profile/{addr}",
            "color": color,
            "fields": [
                {"name": "Market", "value": f"{title}", "inline": False},
                {"name": "Action", "value": f"**{side}** {outcome}", "inline": True},
                {"name": "Size", "value": f"**${size:,.2f}**", "inline": True},
                {"name": "Price", "value": f"**{price:.2f}**", "inline": True},
                {
                    "name": "Trader Stats",
                    "value": f"WR: {trader_profile.get('winrate', 0):.1%} | Score: {trader_profile.get('risk_score', 0)}",
                    "inline": False,
                },
            ],
            "footer": {"text": "🛰️ Poly Intelligence Hub | Live Monitor"},
        }

        payload = {"embeds": [embed]}
        url = f"{self.base_url}/channels/1478038222855733292/messages"  # trades-holding channel

        try:
            self.client.post(url, headers=self.headers, json=payload)
        except:
            pass

    def send_summary_table(self, profiles: List[Dict]):
        """Post a formatted summary table of high-signal traders using embed fields."""
        if not profiles:
            print(f"Discord: No profiles to send")
            return

        high_signal = [p for p in profiles if p.get("level") in ["CRITICAL", "HIGH"]]
        if not high_signal:
            print(f"Discord: No high-signal profiles (CRITICAL/HIGH)")
            return

        level_order = {"CRITICAL": 2, "HIGH": 1}
        sorted_p = sorted(
            high_signal,
            key=lambda x: (level_order.get(x["level"], 0), x.get("pnl", 0)),
            reverse=True,
        )

        max_per_embed = 25
        total_traders = len(sorted_p)
        num_embeds = (total_traders + max_per_embed - 1) // max_per_embed

        for embed_idx in range(num_embeds):
            start_idx = embed_idx * max_per_embed
            end_idx = min(start_idx + max_per_embed, total_traders)
            page_traders = sorted_p[start_idx:end_idx]

            fields = []
            for p in page_traders:
                addr = p.get("address", "")
                addr_short = f"`{addr[:6]}...{addr[-4:]}`"
                winrate = p.get("winrate", 0)
                pnl = p.get("pnl", 0)
                score = p.get("risk_score", 0)
                level = p.get("level", "LOW")
                trades = p.get("total_trades_actual", 0)

                level_emoji = (
                    "🔴" if level == "CRITICAL" else ("🟠" if level == "HIGH" else "🟡")
                )

                value = (
                    f"**Win Rate:** {winrate:.1%}\n"
                    f"**PnL:** ${pnl:,.0f}\n"
                    f"**Score:** {score:.1f}/10\n"
                    f"**Trades:** {trades}"
                )

                fields.append(
                    {
                        "name": f"{level_emoji} {level} | {addr_short}",
                        "value": value,
                        "inline": True,
                    }
                )

            page_title = "📊 DISCOVERY CYCLE: HIGH-SIGNAL TARGETS"
            if num_embeds > 1:
                page_title += f" (Page {embed_idx + 1}/{num_embeds})"

            color = 0x3498DB

            embed = {
                "title": page_title,
                "description": f"Found **{total_traders}** high-signal traders. Showing {start_idx + 1}-{end_idx}.",
                "color": color,
                "fields": fields,
                "footer": {"text": "🛰️ Poly Intelligence Hub | Smart Money Scanner"},
            }

            url = f"{self.base_url}/channels/{self.whale_channel}/messages"
            try:
                resp = self.client.post(
                    url, headers=self.headers, json={"embeds": [embed]}
                )
                if resp.status_code not in [200, 201, 204]:
                    print(
                        f"Discord error ({embed_idx + 1}): {resp.status_code} - {resp.text[:200]}"
                    )
            except Exception as e:
                print(f"Discord error: {e}")

    def close(self):
        self.client.close()
