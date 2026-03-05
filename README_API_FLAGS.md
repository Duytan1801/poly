# API Key Flags - Quick Reference

## Summary of Changes

Both CLI scripts now support passing API keys via command-line flags:

### New Flags Added

| Flag | Environment Variable | Description |
|------|---------------------|-------------|
| `--discord-bot-token` | `DISCORD_BOT_TOKEN` | Discord bot token for notifications |
| `--alchemy-api-key` | `ALCHEMY_API_KEY` | Alchemy API key for blockchain data |

### Priority Order

1. **CLI flag** (highest priority)
2. **Environment variable**
3. **.env file** (lowest priority)

## Quick Start

### Option 1: Using Flags (Recommended for remote servers)

```bash
uv run python src/poly/cli_optimized.py \
  --discord-bot-token "YOUR_DISCORD_TOKEN" \
  --alchemy-api-key "YOUR_ALCHEMY_KEY"
```

### Option 2: Using Environment Variables

```bash
export DISCORD_BOT_TOKEN="YOUR_DISCORD_TOKEN"
export ALCHEMY_API_KEY="YOUR_ALCHEMY_KEY"
uv run python src/poly/cli_optimized.py
```

### Option 3: Using .env File

Create `.env`:
```
DISCORD_BOT_TOKEN=YOUR_DISCORD_TOKEN
ALCHEMY_API_KEY=YOUR_ALCHEMY_KEY
```

Then run:
```bash
uv run python src/poly/cli_optimized.py
```

## Important Notes

### Environment Variable Naming

⚠️ **Use underscores in environment variables, NOT hyphens:**

```bash
# ✅ CORRECT
export DISCORD_BOT_TOKEN="..."

# ❌ WRONG (bash doesn't allow hyphens in variable names)
export DISCORD-BOT-TOKEN="..."
```

### CLI Flag Naming

✅ **Use hyphens in CLI flags:**

```bash
# ✅ CORRECT
--discord-bot-token "..."

# Also works but not standard
--discord_bot_token "..."
```

## Full Example

```bash
# Run with all common options
uv run python src/poly/cli_optimized.py \
  --discord-bot-token "YOUR_DISCORD_BOT_TOKEN_HERE" \
  --alchemy-api-key "YOUR_ALCHEMY_API_KEY_HERE" \
  --wallets-per-iteration 20 \
  --max-trades 100000 \
  --trade-poll-interval 10 \
  --use-redis
```

## Testing

View all available options:
```bash
uv run python src/poly/cli_optimized.py --help
uv run python src/poly/cli.py --help
```

## Security Considerations

When using CLI flags, tokens may be visible in:
- Process lists (`ps aux`)
- Shell history
- System logs

For production, prefer:
1. Environment variables in systemd service files
2. `.env` files with restricted permissions (`chmod 600 .env`)
3. Secrets management systems (AWS Secrets Manager, Vault, etc.)

## Files Modified

- `src/poly/cli.py` - Added `--discord-bot-token` and `--alchemy-api-key` flags
- `src/poly/cli_optimized.py` - Added `--discord-bot-token` and `--alchemy-api-key` flags
- `src/poly/discord/bot.py` - Updated to accept `token` parameter with priority handling
