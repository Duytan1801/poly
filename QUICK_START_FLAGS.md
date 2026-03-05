# Quick Start: Using API Key Flags

## TL;DR

```bash
# Run with flags (easiest for remote servers)
uv run python src/poly/cli_optimized.py \
  --discord-bot-token "YOUR_DISCORD_TOKEN" \
  --alchemy-api-key "YOUR_ALCHEMY_KEY"
```

## Your Tokens

Based on your earlier command, here's the format:

```bash
uv run python src/poly/cli_optimized.py \
  --discord-bot-token "YOUR_DISCORD_BOT_TOKEN_HERE" \
  --alchemy-api-key "YOUR_ALCHEMY_KEY_HERE"
```

## Common Mistake to Avoid

❌ **WRONG** (hyphens in environment variables):
```bash
export DISCORD-BOT-TOKEN="..."  # This fails!
```

✅ **CORRECT** (underscores in environment variables):
```bash
export DISCORD_BOT_TOKEN="..."  # This works!
```

✅ **CORRECT** (hyphens in CLI flags):
```bash
--discord-bot-token "..."  # This works!
```

## All Available Flags

```bash
uv run python src/poly/cli_optimized.py \
  --discord-bot-token "YOUR_DISCORD_TOKEN" \
  --alchemy-api-key "YOUR_ALCHEMY_KEY" \
  --wallets-per-iteration 20 \
  --max-trades 100000 \
  --trade-poll-interval 10 \
  --position-poll-interval 120 \
  --market-monitor-interval 15 \
  --use-redis
```

## See All Options

```bash
uv run python src/poly/cli_optimized.py --help
```
