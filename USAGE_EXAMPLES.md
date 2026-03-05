# CLI Usage Examples with API Key Flags

## New in this version

Both `cli.py` and `cli_optimized.py` now support passing API keys via command-line flags instead of only environment variables.

## Flag Options

### Discord Bot Token
```bash
--discord-bot-token YOUR_TOKEN_HERE
```
- **Priority**: CLI flag > Environment variable > .env file
- **Environment variable**: `DISCORD_BOT_TOKEN`

### Alchemy API Key
```bash
--alchemy-api-key YOUR_KEY_HERE
```
- **Priority**: CLI flag > Environment variable > .env file
- **Environment variable**: `ALCHEMY_API_KEY`

## Usage Examples

### 1. Using CLI Flags (Recommended for remote servers)

```bash
# Run cli_optimized.py with both tokens via flags
uv run python src/poly/cli_optimized.py \
  --discord-bot-token "YOUR_DISCORD_BOT_TOKEN_HERE" \
  --alchemy-api-key "YOUR_ALCHEMY_API_KEY_HERE"

# Run cli.py with flags
uv run python src/poly/cli.py \
  --discord-bot-token "YOUR_DISCORD_BOT_TOKEN_HERE" \
  --alchemy-api-key "YOUR_ALCHEMY_API_KEY_HERE" \
  --workers 8
```

### 2. Using Environment Variables (Traditional method)

```bash
# Set environment variables (note: use underscores, not hyphens!)
export DISCORD_BOT_TOKEN="YOUR_DISCORD_BOT_TOKEN_HERE"
export ALCHEMY_API_KEY="YOUR_ALCHEMY_API_KEY_HERE"

# Run without flags
uv run python src/poly/cli_optimized.py
```

### 3. Using .env File (Local development)

Create `.env` file:
```bash
DISCORD_BOT_TOKEN=YOUR_DISCORD_BOT_TOKEN_HERE
ALCHEMY_API_KEY=YOUR_ALCHEMY_API_KEY_HERE
```

Then run:
```bash
uv run python src/poly/cli_optimized.py \
  --discord-bot-token "YOUR_DISCORD_TOKEN" \
  --alchemy-api-key "YOUR_ALCHEMY_KEY" \
  --wallets-per-iteration 20 \
  --max-trades 100000 \
  --trade-poll-interval 10 \
  --use-redis
```

### 4. Mixed Approach (Some flags, some env vars)

```bash
# Set Discord token via env var
export DISCORD_BOT_TOKEN="YOUR_DISCORD_BOT_TOKEN_HERE"

# Pass Alchemy key via flag
uv run python src/poly/cli_optimized.py \
  --alchemy-api-key "YOUR_ALCHEMY_API_KEY_HERE"
```

## Common Pitfall: Hyphens vs Underscores

❌ **WRONG** - Environment variables cannot have hyphens:
```bash
export DISCORD-BOT-TOKEN="..."  # This will fail!
```

✅ **CORRECT** - Use underscores in environment variables:
```bash
export DISCORD_BOT_TOKEN="..."  # This works!
```

✅ **CORRECT** - Use hyphens in CLI flags:
```bash
--discord-bot-token "..."  # This works!
```

## Full Example with All Options

```bash
uv run python src/poly/cli_optimized.py \
  --discord-bot-token "YOUR_DISCORD_TOKEN" \
  --alchemy-api-key "YOUR_ALCHEMY_KEY" \
  --wallets-per-iteration 20 \
  --max-trades 100000 \
  --trade-poll-interval 10 \
  --position-poll-interval 120 \
  --market-monitor-interval 15 \
  --use-redis \
  --redis-host localhost \
  --redis-port 6379
```

## Checking Available Flags

```bash
# See all available options
uv run python src/poly/cli_optimized.py --help
uv run python src/poly/cli.py --help
```

## Security Note

⚠️ **Warning**: When passing tokens via command-line flags, they may be visible in:
- Process lists (`ps aux`)
- Shell history
- System logs

For production deployments, consider:
1. Using environment variables set in systemd service files
2. Using `.env` files with restricted permissions (chmod 600)
3. Using secrets management tools (AWS Secrets Manager, HashiCorp Vault, etc.)
