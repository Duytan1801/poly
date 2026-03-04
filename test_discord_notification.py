"""Test Discord notification with a single trader profile."""

import httpx
import os
from dotenv import load_dotenv

load_dotenv()

token = os.environ.get("DISCORD_BOT_TOKEN")
if not token:
    print("❌ DISCORD_BOT_TOKEN not found")
    exit(1)

bot = httpx.Client(
    base_url="https://discord.com/api/v10",
    headers={"Authorization": f"Bot {token}", "Content-Type": "application/json"},
    timeout=10.0,
)

print("Testing Discord notification...")

# Create a test trader profile
test_profile = {
    "address": "0x1234567890abcdef1234567890abcdef1234567890",
    "level": "CRITICAL",
    "risk_score": 10.0,
    "winrate": 0.85,
    "pnl": 50000,
    "total_trades_actual": 150,
    "total_trades": 150,
    "profile_type": "INSIDER",
}

# Build embed
embed = {
    "title": "📊 DISCOVERY CYCLE: HIGH-SIGNAL TARGETS",
    "description": "Found **1** high-signal traders. Showing 1-1.",
    "color": 0x3498DB,
    "fields": [
        {
            "name": "🔴 CRITICAL | `0x1234...7890`",
            "value": (
                "**Win Rate:** 85.0%\n"
                "**PnL:** $50,000\n"
                "**Score:** 10.0/10\n"
                "**Trades:** 150"
            ),
            "inline": True,
        }
    ],
    "footer": {"text": "🛰️ Poly Intelligence Hub | Smart Money Scanner"},
}

# Send to big-whales channel
url = f"{bot.base_url}/channels/1478038183873740972/messages"
print(f"\nSending test notification to channel ID: 1478038183873740972 (#big-whales)")

resp = bot.post(url, headers=bot.headers, json={"embeds": [embed]})

if resp.status_code in [200, 201, 204]:
    print("✅ Test notification sent successfully!")
else:
    print(f"❌ Failed: {resp.status_code}")
    print(f"Response: {resp.text}")

bot.close()

print("\n📝 If the notification appeared in #big-whales, Discord is working correctly!")
