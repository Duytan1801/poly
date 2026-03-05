"""
Discover Discord channels available to the bot.
"""

import os
import httpx
from dotenv import load_dotenv

load_dotenv()

token = os.environ.get("DISCORD_BOT_TOKEN")
if not token:
    print("❌ DISCORD_BOT_TOKEN not found in .env")
    exit(1)

base_url = "https://discord.com/api/v10"
headers = {
    "Authorization": f"Bot {token}",
    "Content-Type": "application/json",
}

client = httpx.Client(timeout=10.0)

print("🔍 Discovering Discord channels...\n")

# Get guilds (servers) the bot is in
try:
    resp = client.get(f"{base_url}/users/@me/guilds", headers=headers)
    if resp.status_code != 200:
        print(f"❌ Failed to get guilds: {resp.status_code}")
        print(f"Response: {resp.text}")
        exit(1)

    guilds = resp.json()
    print(f"✅ Bot is in {len(guilds)} server(s)\n")

    for guild in guilds:
        guild_id = guild["id"]
        guild_name = guild["name"]
        print(f"📡 Server: {guild_name} (ID: {guild_id})")
        print("=" * 80)

        # Get channels in this guild
        resp = client.get(f"{base_url}/guilds/{guild_id}/channels", headers=headers)
        if resp.status_code != 200:
            print(f"❌ Failed to get channels: {resp.status_code}")
            continue

        channels = resp.json()

        # Filter text channels only (type 0)
        text_channels = [ch for ch in channels if ch.get("type") == 0]

        print(f"\n📝 Text Channels ({len(text_channels)}):\n")

        for ch in text_channels:
            ch_id = ch["id"]
            ch_name = ch["name"]
            ch_topic = ch.get("topic", "No topic")
            print(f"  #{ch_name}")
            print(f"    ID: {ch_id}")
            print(f"    Topic: {ch_topic}")
            print()

        print("\n" + "=" * 80 + "\n")

except Exception as e:
    print(f"❌ Error: {e}")
finally:
    client.close()

print("\n✅ Discovery complete!")
print("\nCurrent channel mappings in bot.py:")
print("  whales: 1478038183873740972  # #big-whales")
print("  trades: 1478038222855733292  # #trades-holding")
print("  positions: 1478038222855733292  # #trades-holding")
print("  market_anomalies: 1478038222855733292  # #trades-holding")
