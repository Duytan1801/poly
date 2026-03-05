# Polymarket API Reference

## Official Documentation

**URL:** https://docs.polymarket.com

Polymarket provides multiple API tiers for accessing market data and trading:

## API Endpoints

### 1. Gamma API
**Base URL:** `https://gamma-api.polymarket.com`

Market metadata and information:
- `/markets` - Get market data with filtering
- `/events` - Get event groups
- Market resolution states
- Category information

### 2. Data API
**Base URL:** `https://data-api.polymarket.com`

Trading and user data:
- `/v1/leaderboard` - Top traders by PnL
- `/trades` - Historical trades with pagination
- `/positions` - Current positions
- `/holders` - Top holders per market
- `/traded` - Markets traded count

### 3. CLOB API
**Base URL:** `https://clob.polymarket.com`

Order book and pricing:
- `/prices-history` - Historical price data
- Order book snapshots
- Trade execution

### 4. GraphQL API

On-chain event queries:
- Recent fills/trades
- Maker/taker data
- Transaction hashes

## Key Features in Our Implementation

### Optimizations

1. **Server-Side Filtering**
   ```python
   # Only fetch large trades
   trades = client.get_trader_history(
       address, 
       min_size=1000  # Server filters trades < $1000
   )
   ```

2. **Efficient Pagination**
   ```python
   # Offset-based (4 requests for 4K trades)
   trades = client.get_full_trader_history(
       address,
       max_trades=4000,
       batch_size=1000
   )
   ```

3. **Parallel Fetching**
   ```python
   # Fetch multiple traders concurrently
   with ThreadPoolExecutor(max_workers=64) as executor:
       results = executor.map(fetch_trader, addresses)
   ```

4. **Caching**
   ```python
   # Market resolution cache (MessagePack)
   resolution = client.get_market_resolution_state(condition_id)
   # Automatically cached to disk
   ```

### Rate Limiting

All API calls include:
- Exponential backoff on 429 errors
- Automatic retry logic
- Connection pooling
- Timeout handling

### Error Handling

```python
def _safe_get(url, params=None):
    max_retries = 5
    backoff = 1.0
    
    for attempt in range(max_retries):
        try:
            resp = self.http.get(url, params=params)
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 429:
                time.sleep(backoff)
                backoff *= 2.0
                continue
            return None
        except Exception:
            time.sleep(backoff)
            backoff *= 2.0
    return None
```

## Usage Examples

### Get Top Traders
```python
from poly.api.polymarket import PolymarketClient

client = PolymarketClient()

# Get monthly leaderboard
leaderboard = client.get_leaderboard(
    category="OVERALL",
    period="MONTH",
    limit=50
)

for trader in leaderboard:
    print(f"{trader['userName']}: ${trader['pnl']:,.0f}")
```

### Fetch Trade History
```python
# Get full history with pagination
trades = client.get_full_trader_history(
    address="0x...",
    max_trades=10000,
    batch_size=1000
)

print(f"Fetched {len(trades)} trades")
```

### Get Market Data
```python
# Get active markets with minimum liquidity
markets = client.get_active_markets(
    min_liquidity=50000,
    limit=100
)

for market in markets:
    print(f"{market['question']}: ${market['liquidity']:,.0f}")
```

### Real-Time Events
```python
# Get latest on-chain events
events = client.graphql.get_latest_events(limit=100)

for event in events:
    print(f"Trade: {event['maker']} -> {event['taker']}")
```

### Market Resolution
```python
# Check if market is resolved
resolution = client.get_market_resolution_state(condition_id)

if resolution:
    winner = resolution['winner_idx']
    closed_at = resolution['closed_at']
    print(f"Winner: Outcome {winner}, Closed: {closed_at}")
```

## API Limits

- **Rate Limit**: ~100 requests/minute per IP
- **Pagination**: Max 1000 items per request
- **History**: Full trade history available
- **Real-time**: WebSocket feeds for live data

## Authentication

Most endpoints are public and don't require authentication. For trading operations, you'll need:
- Private key for signing transactions
- API key for CLOB operations (optional)

## Best Practices

1. **Use Caching**: Cache market resolutions and metadata
2. **Batch Requests**: Fetch multiple items in parallel
3. **Handle Errors**: Implement retry logic with backoff
4. **Rate Limiting**: Respect API limits, use delays
5. **Pagination**: Use offset-based pagination for efficiency

## Additional Resources

- **Official Docs**: https://docs.polymarket.com
- **Discord**: https://discord.gg/polymarket
- **GitHub**: https://github.com/Polymarket
- **Subgraph**: For advanced blockchain queries

## Our Implementation

See `src/poly/api/polymarket.py` for the complete implementation with all optimizations and error handling built-in.