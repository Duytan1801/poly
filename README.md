# Polymarket Intelligence System

AI-powered insider trading detection and elite trader monitoring for Polymarket.

## Features

- 🔍 **Real-time Discovery** - Event-driven architecture discovers elite traders instantly
- 🧮 **IAX Scoring** - Proprietary formula detects insider trading patterns (200× more sensitive)
- 🤖 **Machine Learning** - Perpetual ML predicts winning traders
- 📊 **Live Monitoring** - Track HIGH/CRITICAL traders in real-time
- 🔔 **Discord Alerts** - Automated notifications for significant activity
- ⚡ **High Performance** - Parallel processing, caching, optimized pagination

## Quick Start

### Installation

```bash
# Clone repository
git clone <repo-url>
cd poly

# Install dependencies (using uv)
uv sync

# Or with pip
pip install -e .
```

### Configuration

Create `.env` file:
```bash
DISCORD_BOT_TOKEN=your_discord_bot_token
ALCHEMY_API_KEY=your_alchemy_key  # Optional
REDIS_URL=redis://localhost:6379  # Optional
```

### Run

```bash
# Start event-driven intelligence engine
python src/poly/cli.py --workers 8 --max-trades 100000

# Or use optimized CLI for batch processing
python src/poly/cli_optimized.py
```

## Architecture

```
Event Discovery → Analysis → Scoring → Monitoring → Discord Alerts
     ↓              ↓          ↓          ↓            ↓
  GraphQL      Trade History  IAX     Real-time    #big-whales
  Events       + Metadata    Formula   Tracking    #trades-holding
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for detailed system design.

## IAX Formula

The **Information Asymmetry Index** detects insider trading by analyzing:

```
IAX = Σ(ΔP × C × O × U) / √N
```

- **ΔP** (Edge): Actual profit from bet
- **C** (Conviction): Bet size / bankroll
- **O** (Obscurity): -ln(price) - rewards longshots
- **U** (Urgency): Slippage tolerance

**Result**: Insiders score 200× higher than normal traders.

See [docs/IAX_FORMULA.md](docs/IAX_FORMULA.md) for complete details.

## Project Structure

```
poly/
├── src/poly/              # Source code
│   ├── api/              # Polymarket API clients
│   ├── intelligence/     # IAX scoring & analysis
│   ├── monitoring/       # Real-time tracking
│   ├── discord/          # Alert system
│   ├── cache/            # Redis caching
│   └── utils/            # Utilities
├── docs/                 # Documentation
│   ├── ARCHITECTURE.md   # System design
│   ├── IAX_FORMULA.md    # Scoring algorithm
│   ├── API_REFERENCE.md  # Polymarket APIs
│   └── *.md             # Additional docs
├── data/                 # Data storage
│   ├── raw/             # Trade data
│   ├── processed/       # Features
│   └── models/          # ML models
└── README.md            # This file
```

## Key Components

### API Layer
- **Polymarket Client** - Unified API access (Gamma, Data, CLOB, GraphQL)
- **Async Client** - Parallel operations
- **WebSocket** - Real-time feeds
- **Blockchain** - Polygon RPC & PolygonScan

### Intelligence Engine
- **Scout** - Discovers elite traders from leaderboards
- **Analyzer** - Deep behavior analysis
- **Scorer** - IAX-based insider detection
- **Clusterer** - Sybil attack detection
- **Prioritizer** - Risk classification (CRITICAL/HIGH/MEDIUM/LOW)

### Monitoring System
- **Trade Monitor** - Real-time trade tracking
- **Position Monitor** - Portfolio monitoring
- **Market Monitor** - Volume anomaly detection

### Discord Integration
- **#big-whales** - New elite trader discoveries
- **#trades-holding** - Live trades + top 3 holdings
- **#live-scanning** - Market volume anomalies

## Usage Examples

### Discover Elite Traders
```python
from poly.intelligence.scout import InsiderScout

scout = InsiderScout()
profiles = await scout.discover_elite_wallets()

for profile in profiles:
    if profile['winrate'] > 0.7:
        print(f"{profile['address']}: {profile['winrate']:.1%} WR")
```

### Analyze Trader
```python
from poly.api.polymarket import PolymarketClient
from poly.intelligence.analyzer import ComprehensiveAnalyzer

client = PolymarketClient()
analyzer = ComprehensiveAnalyzer()

trades = client.get_full_trader_history(address)
profile = analyzer.analyze_trader(address, trades, {}, {})

print(f"IAX Score: {profile['iax_score']:.1f}")
print(f"Win Rate: {profile['winrate']:.1%}")
```

### Monitor Real-Time
```python
from poly.monitoring.trade_monitor import RealTimeTradeMonitor

monitor = RealTimeTradeMonitor(discord_bot, state)
await monitor.monitor_continuously()
```

## Performance

- **Discovery Rate**: 10-20 new traders per iteration
- **Analysis Speed**: ~100 trades/second per worker
- **Monitoring**: Unlimited HIGH/CRITICAL traders
- **Latency**: <5 seconds from trade to alert

## Optimizations

1. **Parallel Processing** - ThreadPoolExecutor for batch operations
2. **Efficient Pagination** - Offset-based (4 requests for 4K trades)
3. **Server-Side Filtering** - `min_size` parameter reduces data transfer
4. **Caching** - MessagePack resolution cache + Redis
5. **Rate Limiting** - Exponential backoff with retry logic

## Documentation

- [ARCHITECTURE.md](docs/ARCHITECTURE.md) - System design and data flow
- [IAX_FORMULA.md](docs/IAX_FORMULA.md) - Insider detection algorithm
- [API_REFERENCE.md](docs/API_REFERENCE.md) - Polymarket API guide
- [PERPETUAL_API_DOCS.md](docs/PERPETUAL_API_DOCS.md) - ML library reference
- [CATEGORICAL_FEATURES.md](docs/CATEGORICAL_FEATURES.md) - Feature engineering
- [SECURITY.md](SECURITY.md) - Security best practices

## Requirements

- Python 3.10+
- Dependencies in `pyproject.toml`
- Optional: Redis for caching
- Optional: Alchemy API for blockchain data

## Development

```bash
# Install dev dependencies
uv sync --dev

# Run tests
pytest

# Format code
ruff format src/

# Lint
ruff check src/
```

## License

MIT

## Support

- Discord: https://discord.gg/polymarket
- Issues: GitHub Issues
- Docs: https://docs.polymarket.com

## Acknowledgments

Built on top of:
- Polymarket APIs
- Perpetual ML
- GraphQL
- Redis
- Discord