"""
Discord Webhook Client: Sends real-time alerts for high-signal traders.
"""

import logging
import httpx
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class DiscordWebhookClient:
    """Sends formatted alerts to a Discord channel via Webhook."""

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url
        self.client = httpx.Client(timeout=10.0)

    def send_trader_alert(self, profile: Dict[str, Any]):
        """Format and send an alert for a high-signal trader."""
        if not self.webhook_url:
            return

        addr = profile.get("address", "Unknown")
        level = profile.get("level", "LOW")
        score = profile.get("risk_score", 0)
        winrate = profile.get("winrate", 0)
        pnl = profile.get("pnl", 0)
        
        # Color based on level
        color = 0xff0000 if level == "CRITICAL" else (0xffa500 if level == "HIGH" else 0xffff00)

        embed = {
            "title": f"🚨 SMART MONEY ALERT: {level} Risk Detected",
            "description": f"A high-signal trader has been identified by the scanner.",
            "color": color,
            "fields": [
                {"name": "Address", "value": f"[`{addr}`](https://polymarket.com/profile/{addr})", "inline": False},
                {"name": "Insider Score", "value": f"**{score:.1f}/10.0**", "inline": True},
                {"name": "Win Rate", "value": f"{winrate:.1%}", "inline": True},
                {"name": "Total PnL", "value": f"${pnl:,.2f}", "inline": True},
                {"name": "Trades", "value": f"{profile.get('total_trades_actual', 0)}", "inline": True},
                {"name": "Max Bet", "value": f"${profile.get('whales', {}).get('max_bet', 0):,.0f}", "inline": True},
            ],
            "footer": {"text": "Polymarket Intelligence Hub | Real-time Scanner"}
        }

        payload = {"embeds": [embed]}

        try:
            resp = self.client.post(self.webhook_url, json=payload)
            if resp.status_code != 204:
                logger.warning(f"Discord Webhook failed with status {resp.status_code}: {resp.text}")
        except Exception as e:
            logger.error(f"Failed to send Discord alert: {e}")

    def close(self):
        self.client.close()
