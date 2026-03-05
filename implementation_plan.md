# Implementation Plan: Server-Side Optimization for Polymarket Insider Detection

## [Overview]

Optimize the insider detection system by shifting heavy calculations from client-side to server-side using Polymarket's public APIs. This will reduce data transfer by 80-90%, speed up analysis by 5-10x, and eliminate the need to download and process millions of trades locally.

The current system downloads 100K+ trades per trader and processes them with Numba/Polars locally. The optimized system will leverage Polymarket's pre-computed metrics (leaderboard PnL, positions, market data) and use server-side filtering to minimize data transfer. Only metrics that require raw trade data (timing analysis, whale detection, multi-market patterns) will continue to use client-side processing, but with optimized data fetching.

## [Types]

Define new data structures for server-side optimized analysis.

```python
from typing import TypedDict, Optional, List, Dict
from dataclasses import dataclass

class LeaderboardEntry(TypedDict):
    """Pre-computed trader metrics from Polymarket leaderboard API"""
    rank: int
    pnl: float
    vol: float
    userName: Optional[str]

class OptimizedTraderProfile(TypedDict):
    """Trader profile using server-side data"""
    address: str
    # Server-side metrics (fast)
    leaderboard_pnl: float
    leaderboard_volume: float
    leaderboard_rank: Optional[int]
    total_markets_traded: int
    current_positions_count: int
    current_positions_value: float
    # Client-side metrics (still needed)
    timing_score: float
    whale_score: float
    multi_market_score: float
    # Computed
    risk_score: float
    level: str

@dataclass
class APIBatchRequest:
    """Batch request configuration"""
    token_ids: List[str]
    max_batch_size: int = 500
    
@dataclass
class CacheConfig:
    """Cache configuration for incremental updates"""
    last_update_ts: int
    cache_ttl_seconds: int = 3600
```

## [Files]

Modify existing files and create new optimized modules.

### New Files to Create:

1. **src/poly/api/optimized_client.py**
   - Purpose: Wrapper around PolymarketClient with server-side optimization methods
   - Contains: Batch request handlers, caching layer, incremental update logic

2. **src/poly/intelligence/optimized_scorer.py**
   - Purpose: Optimized scoring system using server-side data
   - Contains: Fast PnL scoring, position-based metrics, minimal trade processing

3. **src/poly/cache/profile_cache.py**
   - Purpose: Persistent cache for trader profiles with incremental updates
   - Contains: Redis/disk cache, timestamp tracking, invalidation logic

### Existing Files to Modify:

1. **src/poly/api/polymarket.py**
   - Add batch endpoint methods: `get_prices_batch()`, `get_spreads_batch()`, `get_midpoints_batch()`
   - Add incremental fetch: `get_trader_history_since(address, start_ts)`
   - Add server-side filtering: Enhance `get_trader_history()` with `min_size`, `start`, `end` params
   - Add position value calculation: `get_positions_total_value(address)`

2. **src/poly/intelligence/scorer.py**
   - Replace `calculate_pnl_score()` to use leaderboard API
   - Add `calculate_pnl_score_fast()` using `get_trader_pnl_from_leaderboard()`
   - Keep existing timing/whale/multi-market functions but optimize data fetching

3. **src/poly/collection/collector.py**
   - Add `collect_trader_profiles_optimized()` method
   - Use batch requests for market metadata
   - Implement incremental collection with timestamp filtering

4. **src/poly/intelligence/analyzer.py**
   - Add `analyze_trader_fast()` method using server-side data
   - Keep existing `analyze_trader()` for detailed analysis
   - Add hybrid mode that uses server data + minimal client processing

## [Functions]

Define new functions and modifications to existing ones.

### New Functions in `src/poly/api/optimized_client.py`:

```python
def get_trader_profile_fast(address: str) -> OptimizedTraderProfile:
    """
    Get trader profile using only server-side APIs.
    
    Uses:
    - GET /leaderboard for PnL/volume
    - GET /positions for current holdings
    - GET /traded for market count
    
    Returns complete profile in <1 second vs 10-30 seconds for full analysis.
    """

def get_prices_batch(token_ids: List[str], side: str = "BUY") -> Dict[str, float]:
    """
    Batch fetch prices for multiple tokens.
    
    API: POST /prices with body: [{"token_id": "...", "side": "BUY"}, ...]
    Max 500 tokens per request.
    
    Returns: {"token_id": price, ...}
    """

def get_orderbooks_batch(token_ids: List[str]) -> Dict[str, Dict]:
    """
    Batch fetch orderbooks for multiple tokens.
    
    API: POST /books with body: [{"token_id": "..."}, ...]
    Max 500 tokens per request.
    
    Returns: {"token_id": {"bids": [...], "asks": [...]}, ...}
    """

def get_trader_history_incremental(
    address: str,
    last_update_ts: int,
    max_trades: int = 1000
) -> List[Dict]:
    """
    Fetch only new trades since last update.
    
    API: GET /trades?user={address}&start={last_update_ts}&limit={max_trades}
    
    Returns: List of new trades only
    """

def get_large_trades_filtered(
    address: str,
    min_size: float = 1000,
    limit: int = 500
) -> List[Dict]:
    """
    Server-side filtering for large trades only.
    
    API: GET /trades?user={address}&min_size={min_size}&limit={limit}
    
    Reduces data transfer by 80-90% for whale detection.
    """
```

### Modified Functions in `src/poly/api/polymarket.py`:

```python
def get_trader_history(
    address: str,
    limit: int = 500,
    offset: int = 0,
    start: Optional[int] = None,  # NEW: Server-side time filter
    end: Optional[int] = None,    # NEW: Server-side time filter
    min_size: Optional[float] = None,  # NEW: Server-side size filter
) -> List[Dict]:
    """
    Enhanced with server-side filtering.
    
    API: GET /trades?user={address}&limit={limit}&offset={offset}&start={start}&end={end}&min_size={min_size}
    
    Existing implementation already supports these params!
    """

def get_positions_total_value(address: str) -> float:
    """
    Calculate total position value from positions API.
    
    API: GET /positions?user={address}
    Sum all position values.
    
    Much faster than calculating from trade history.
    """
```

### New Functions in `src/poly/intelligence/optimized_scorer.py`:

```python
def calculate_pnl_score_fast(address: str, client: PolymarketClient) -> float:
    """
    Fast PnL scoring using leaderboard API.
    
    BEFORE: Download 100K trades, calculate PnL locally (10-30s)
    AFTER: Single API call to leaderboard (0.1s)
    
    Returns: PnL score (0-4.0)
    """

def calculate_position_score_fast(address: str, client: PolymarketClient) -> Dict:
    """
    Fast position analysis using positions API.
    
    API: GET /positions?user={address}
    
    Returns: {
        "num_positions": int,
        "total_value": float,
        "largest_position": float,
        "concentration": float
    }
    """

def score_trader_fast(address: str, client: PolymarketClient) -> Dict:
    """
    Fast scoring using only server-side data.
    
    Calculates:
    - PnL score (from leaderboard)
    - Position score (from positions API)
    - Activity score (from traded count)
    - Freshness score (from first/last trade in positions)
    
    Skips:
    - Timing analysis (needs full trade history)
    - Whale detection (needs trade sizes)
    - Multi-market patterns (needs cross-market data)
    
    Use for initial screening, then detailed analysis on high-risk traders.
    """
```

### Modified Functions in `src/poly/intelligence/scorer.py`:

```python
def calculate_pnl_score(pnl: float) -> float:
    """
    DEPRECATED: Use calculate_pnl_score_fast() instead.
    
    This function calculates PnL from trade history.
    New version uses leaderboard API for 100x speedup.
    """

def fit_and_score(profiles: List[Dict], use_fast_mode: bool = True) -> List[Dict]:
    """
    Enhanced with fast mode option.
    
    If use_fast_mode=True:
    - Use leaderboard API for PnL
    - Use positions API for holdings
    - Skip expensive calculations
    
    If use_fast_mode=False:
    - Use existing full analysis
    - Process all trades locally
    """
```

## [Classes]

Define new classes and modifications to existing ones.

### New Class: `OptimizedPolymarketClient`

```python
class OptimizedPolymarketClient:
    """
    Optimized wrapper around PolymarketClient with:
    - Batch request handling
    - Automatic caching
    - Incremental updates
    - Server-side filtering
    
    File: src/poly/api/optimized_client.py
    """
    
    def __init__(self, client: PolymarketClient, cache_dir: str = "data/cache"):
        self.client = client
        self.cache = ProfileCache(cache_dir)
        self.batch_size = 500
    
    def get_trader_profile_optimized(
        self, 
        address: str,
        use_cache: bool = True,
        force_refresh: bool = False
    ) -> OptimizedTraderProfile:
        """
        Get trader profile with automatic caching and incremental updates.
        
        Flow:
        1. Check cache, return if fresh
        2. If stale, fetch only new data since last update
        3. Merge with cached data
        4. Save updated cache
        """
    
    def batch_get_profiles(
        self,
        addresses: List[str],
        max_workers: int = 10
    ) -> Dict[str, OptimizedTraderProfile]:
        """
        Parallel batch processing of multiple traders.
        
        Uses asyncio for concurrent API calls.
        Processes 10-50 traders simultaneously.
        """
    
    def get_market_data_batch(
        self,
        condition_ids: List[str]
    ) -> Dict[str, Dict]:
        """
        Batch fetch market metadata.
        
        API: GET /markets with multiple condition_ids
        Returns: {"condition_id": {metadata}, ...}
        """
```

### New Class: `ProfileCache`

```python
class ProfileCache:
    """
    Persistent cache for trader profiles with incremental updates.
    
    File: src/poly/cache/profile_cache.py
    
    Features:
    - Disk-based storage (msgpack format)
    - Timestamp tracking for incremental updates
    - Automatic invalidation
    - LRU eviction for memory management
    """
    
    def __init__(self, cache_dir: str, ttl_seconds: int = 3600):
        self.cache_dir = Path(cache_dir)
        self.ttl = ttl_seconds
        self.cache_file = self.cache_dir / "profiles.msgpack"
    
    def get(self, address: str) -> Optional[OptimizedTraderProfile]:
        """Get cached profile if fresh"""
    
    def set(self, address: str, profile: OptimizedTraderProfile):
        """Save profile to cache"""
    
    def is_stale(self, address: str) -> bool:
        """Check if cached profile needs refresh"""
    
    def get_last_update_ts(self, address: str) -> int:
        """Get timestamp of last update for incremental fetching"""
```

### Modified Class: `InsiderScorer`

```python
class InsiderScorer:
    """
    Enhanced with fast mode support.
    
    File: src/poly/intelligence/scorer.py
    """
    
    def __init__(self, use_fast_mode: bool = True):
        self.use_fast_mode = use_fast_mode
        self.optimized_client = None
    
    def fit_and_score_fast(
        self,
        addresses: List[str],
        client: PolymarketClient
    ) -> List[Dict]:
        """
        Fast scoring mode using server-side data.
        
        Flow:
        1. Batch fetch leaderboard data
        2. Batch fetch positions
        3. Calculate scores from server data
        4. Return results in <5 seconds for 100 traders
        
        vs. Original: 30-60 seconds for 100 traders
        """
    
    def fit_and_score_hybrid(
        self,
        addresses: List[str],
        client: PolymarketClient,
        detailed_threshold: float = 5.0
    ) -> List[Dict]:
        """
        Hybrid mode: Fast screening + detailed analysis.
        
        Flow:
        1. Fast score all traders (server-side)
        2. Filter high-risk traders (score >= threshold)
        3. Detailed analysis on high-risk only (client-side)
        
        Best of both worlds: Fast + accurate
        """
```

## [Dependencies]

No new external dependencies required.

All optimizations use existing libraries:
- `httpx` - Already used for HTTP requests
- `msgpack` - Already used for caching
- `asyncio` - Python standard library for async operations
- `concurrent.futures` - Python standard library for parallel processing

Optional performance enhancements:
- `aiohttp` - For async HTTP requests (if httpx async is not sufficient)
- `redis` - For distributed caching (if scaling beyond single machine)

## [Testing]

Create comprehensive tests for optimized functionality.

### New Test Files:

1. **tests/test_optimized_client.py**
   - Test batch requests
   - Test caching behavior
   - Test incremental updates
   - Test server-side filtering

2. **tests/test_optimized_scorer.py**
   - Test fast PnL scoring
   - Test position-based metrics
   - Test hybrid mode
   - Compare results with original scorer

3. **tests/test_profile_cache.py**
   - Test cache persistence
   - Test TTL expiration
   - Test incremental updates
   - Test cache invalidation

### Modified Test Files:

1. **tests/test_polymarket_client.py**
   - Add tests for new batch methods
   - Add tests for server-side filtering
   - Add tests for incremental fetching

2. **tests/test_scorer.py**
   - Add tests for fast mode
   - Add tests for hybrid mode
   - Add performance benchmarks

### Performance Benchmarks:

```python
def test_performance_comparison():
    """
    Compare original vs optimized performance.
    
    Metrics:
    - Time to score 100 traders
    - Data transfer volume
    - API call count
    - Memory usage
    
    Expected improvements:
    - Time: 5-10x faster
    - Data: 80-90% reduction
    - API calls: 100x fewer
    """
```

## [Implementation Order]

Implement in this sequence to minimize conflicts and ensure successful integration.

### Phase 1: Foundation (Week 1)

1. **Create `OptimizedPolymarketClient` class**
   - File: `src/poly/api/optimized_client.py`
   - Implement basic wrapper around existing client
   - Add batch request methods for prices, spreads, orderbooks
   - Test batch functionality

2. **Create `ProfileCache` class**
   - File: `src/poly/cache/profile_cache.py`
   - Implement disk-based caching with msgpack
   - Add timestamp tracking
   - Test cache persistence and retrieval

3. **Enhance `PolymarketClient` with server-side filtering**
   - File: `src/poly/api/polymarket.py`
   - Verify `get_trader_history()` supports `start`, `end`, `min_size` params
   - Add `get_positions_total_value()` method
   - Add `get_trader_history_incremental()` wrapper
   - Test filtering functionality

### Phase 2: Fast Scoring (Week 2)

4. **Create `optimized_scorer.py` module**
   - File: `src/poly/intelligence/optimized_scorer.py`
   - Implement `calculate_pnl_score_fast()` using leaderboard API
   - Implement `calculate_position_score_fast()` using positions API
   - Implement `score_trader_fast()` for quick screening
   - Test against original scorer for accuracy

5. **Add fast mode to `InsiderScorer`**
   - File: `src/poly/intelligence/scorer.py`
   - Add `use_fast_mode` parameter to `__init__()`
   - Implement `fit_and_score_fast()` method
   - Implement `fit_and_score_hybrid()` method
   - Test performance improvements

### Phase 3: Integration (Week 3)

6. **Update `TradeCollector` for optimized collection**
   - File: `src/poly/collection/collector.py`
   - Add `collect_trader_profiles_optimized()` method
   - Use batch requests for market metadata
   - Implement incremental collection
   - Test collection performance

7. **Add incremental update support**
   - Integrate `ProfileCache` with `OptimizedPolymarketClient`
   - Implement automatic cache refresh logic
   - Add cache invalidation on demand
   - Test incremental updates

### Phase 4: Testing & Optimization (Week 4)

8. **Create comprehensive test suite**
   - Write tests for all new functionality
   - Add performance benchmarks
   - Compare results with original implementation
   - Verify accuracy is maintained

9. **Performance tuning**
   - Optimize batch sizes
   - Tune cache TTL
   - Add connection pooling
   - Implement retry logic with exponential backoff

10. **Documentation and migration guide**
    - Document new API methods
    - Create migration guide from old to new system
    - Add usage examples
    - Update README with performance improvements

### Phase 5: Deployment (Week 5)

11. **Gradual rollout**
    - Deploy fast mode as opt-in feature
    - Monitor performance and accuracy
    - Collect user feedback
    - Fix any issues

12. **Make fast mode default**
    - Switch default to `use_fast_mode=True`
    - Keep original mode available as fallback
    - Update all scripts to use optimized version
    - Deprecate old methods

### Success Criteria:

- ✅ 5-10x faster trader analysis
- ✅ 80-90% reduction in data transfer
- ✅ 100x fewer API calls
- ✅ Accuracy within 5% of original system
- ✅ All tests passing
- ✅ No breaking changes to existing API