"""Explore Discord server structure to understand channel configuration."""

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

print("=" * 80)
print("DISCORD SERVER EXPLORATION")
print("=" * 80)

# Get bot's guilds (servers)
print("\n1. Fetching bot's guilds/servers...")
try:
    resp = bot.get("/users/@me/guilds")
    if resp.status_code == 200:
        guilds = resp.json()
        print(f"   Bot has access to {len(guilds)} server(s):")
        for g in guilds:
            print(f"   - {g.get('name', 'Unknown')} (ID: {g.get('id')})")
    else:
        print(f"   Failed: {resp.status_code}")
except Exception as e:
    print(f"   Error: {e}")

# Get first guild's channels
if guilds:
    guild_id = guilds[0].get("id")
    print(f"\n2. Fetching channels from server '{guilds[0].get('name')}'...")
    try:
        resp = bot.get(f"/guilds/{guild_id}/channels")
        if resp.status_code == 200:
            channels = resp.json()
            print(f"   Found {len(channels)} channel(s):")

            # Group by channel type
            by_type = {}
            for ch in channels:
                ch_type = ch.get("type", "unknown")
                if ch_type not in by_type:
                    by_type[ch_type] = []
                by_type[ch_type].append(ch)

            # Display text channels
            if 0 in by_type:  # GUILD_TEXT
                print("\n   📝 Text Channels:")
                for ch in by_type[0]:
                    name = ch.get("name", "unknown")
                    cid = ch.get("id")
                    topic = ch.get("topic", "") or "No topic"
                    nsfw = ch.get("nsfw", False)
                    print(f"      #{name} (ID: {cid})")
                    print(f"         Topic: {topic[:100]}...")
                    if nsfw:
                        print(f"         ⚠️ NSFW channel")

            # Display categories
            if 4 in by_type:  # GUILD_CATEGORY
                print("\n   📁 Categories:")
                for cat in by_type[4]:
                    name = cat.get("name", "unknown")
                    cid = cat.get("id")
                    print(f"      {name} (ID: {cid})")

        else:
            print(f"   Failed: {resp.status_code}")
    except Exception as e:
        print(f"   Error: {e}")

# Check specific channels mentioned in bot.py
print(f"\n3. Checking hardcoded channel IDs from bot.py:")

channels = {
    "Whale alerts (big-whales)": "1478038183873740972",
    "Trades & Holdings": "1478038222855733292",
}

for name, cid in channels.items():
    try:
        resp = bot.get(f"/channels/{cid}")
        if resp.status_code == 200:
            ch = resp.json()
            print(f"\n   ✅ {name}:")
            print(f"      Name: #{ch.get('name', 'unknown')}")
            print(f"      ID: {cid}")
            print(f"      Topic: {ch.get('topic', 'No topic') or 'No topic'}")
            print(f"      Type: {ch.get('type', 'unknown')}")
        else:
            print(f"\n   ❌ {name}:")
            print(f"      ID: {cid}")
            print(f"      Error: {resp.status_code}")
    except Exception as e:
        print(f"\n   ❌ {name}:")
        print(f"      ID: {cid}")
        print(f"      Error: {e}")

bot.close()

print("\n" + "=" * 80)
print("EXPLORATION COMPLETE")
print("=" * 80)
