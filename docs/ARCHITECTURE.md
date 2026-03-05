# Polymarket Intelligence System - Architecture

## Overview

An AI-powered insider trading detection system for Polymarket that discovers elite traders in real-time, scores them using the proprietary IAX (Information Asymmetry Index) formula, and monitors their activity.

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Event-Driven Engine                      │
│  (Continuous discovery & monitoring of elite traders)        │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      API Layer (Unified)                     │
│  • Polymarket (Gamma, Data, CLOB, GraphQL)                  │
│  • Polygon RPC & PolygonScan                                │
│  • WebSocket (Real-time feeds)                              │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   Intelligence Pipeline                      │
│  1. Scout → Discover elite traders from leaderboards        │
│  2. Analyzer → Deep behavior analysis                        │
│  3. Scorer → IAX-based insider scoring                       │
│  4. Clusterer → Sybil attack detection                       │
│  5. Prioritizer → Risk classification                        │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Monitoring System                         │
│  • Trade Monitor → Real-time trade tracking                  │
│  • Position Monitor → Portfolio tracking                     │
│  • Market Monitor → Volume anomaly detection                 │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   Discord Notifications                      │
│  • #big-whales → New elite trader discoveries               │
│  • #trades-holding → Live trades + holdings                 │
│  • #live-scanning → Market anomalies                        │
└─────────────────────────────────────────────────────────────┘
```

## Core Components

### 1. API Layer (`src/poly/api/`)
- **polymarket.py** - Unified Polymarket API client
  - Gamma API: Markets, events, metadata
  - Data API: Leaderboards, trades, positions
  - CLOB API: Orderbook, price history
  - GraphQL: On-chain events
- **async_client.py** - Async operations for parallel processing
- **websocket_client.py** - Real-time market data
- **polygon_rpc.py** - Blockchain RPC calls
- **polygonscan.py** - Transaction history

### 2. Intelligence Engine (`src/poly/intelligence/`)
- **scout.py** - Elite trader discovery from leaderboards
- **analyzer.py** - Comprehensive trader behavior analysis
- **scorer.py** - IAX-based insider scoring
- **clustering.py** - Sybil attack detection
- **prioritization.py** - Risk level classification

### 3. Monitoring (`src/poly/monitoring/`)
- **trade_monitor.py** - Real-time trade tracking
- **position_monitor.py** - Portfolio monitoring
- **market_volume_monitor.py** - Anomaly detection

### 4. Discord Integration (`src/poly/discord/`)
- **bot.py** - Automated Discord alerts
- **webhook.py** - Webhook notifications

### 5. Caching (`src/poly/cache/`)
- **redis_cache.py** - Redis-based caching
- Market resolution caching (MessagePack)

## Data Flow

1. **Discovery Phase**
   - GraphQL events → New trader addresses
   - Leaderboard API → Elite traders
   - Market scanning → Active participants

2. **Analysis Phase**
   - Fetch full trade history (parallel)
   - Calculate IAX score
   - Detect Sybil clusters
   - Classify risk level

3. **Monitoring Phase**
   - Track HIGH/CRITICAL traders
   - Real-time trade notifications
   - Position updates
   - Market anomaly alerts

4. **Notification Phase**
   - Discord embeds with trader stats
   - Batched updates (every 10 discoveries)
   - Live trade alerts with holdings

## Key Optimizations

1. **Parallel Processing**
   - ThreadPoolExecutor for batch operations
   - Async HTTP clients
   - Concurrent trade fetching

2. **Efficient Pagination**
   - Offset-based (4 requests for 4K trades)
   - Server-side filtering (min_size parameter)

3. **Caching Strategy**
   - Market resolution cache (MessagePack)
   - Redis for high-frequency queries
   - In-memory state management

4. **Rate Limiting**
   - Exponential backoff
   - Request batching
   - Connection pooling

## Configuration

Environment variables (`.env`):
```bash
DISCORD_BOT_TOKEN=your_token_here
ALCHEMY_API_KEY=your_key_here
REDIS_URL=redis://localhost:6379
```

## Execution Modes

### Event-Driven Engine (Production)
```bash
python src/poly/cli.py --workers 8 --max-trades 100000
```

### Optimized CLI (Batch Processing)
```bash
python src/poly/cli_optimized.py
```

## Performance Metrics

- **Discovery Rate**: ~10-20 new traders per iteration
- **Analysis Speed**: ~100 trades/second per worker
- **Monitoring Capacity**: Unlimited HIGH/CRITICAL traders
- **Notification Latency**: <5 seconds from trade execution

## Security

- Environment-based secrets
- Rate limiting protection
- Sybil attack detection
- Deduplication windows
- Error handling & logging

## Scalability

- Horizontal: Add more workers
- Vertical: Increase max_trades limit
- Caching: Redis cluster support
- Database: Optional PostgreSQL for persistence