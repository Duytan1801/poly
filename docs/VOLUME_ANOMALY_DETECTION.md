# Improved Volume Anomaly Detection Algorithm

## Problem Statement

Current algorithm flags normal distributed trading as anomalous:
- ✗ $1M volume spread across many traders = Normal market activity
- ✓ $1M volume concentrated in few traders = Potential manipulation

## Statistical Approach

### 1. Z-Score Based Detection (Standard Deviations)

Instead of absolute thresholds, compare to historical baseline:

```python
z_score = (current_volume - mean_volume) / std_volume
```

**Anomaly if:** `z_score > 3.0` (99.7% confidence)

### 2. Concentration Metrics

**Herfindahl-Hirschman Index (HHI)** - Measures market concentration:

```python
HHI = Σ(trader_volume_share²)
```

- **HHI < 0.15**: Highly distributed (normal)
- **HHI 0.15-0.25**: Moderate concentration
- **HHI > 0.25**: High concentration (suspicious)

**Gini Coefficient** - Measures inequality:

```python
Gini = (Σ|xi - xj|) / (2n²μ)
```

- **Gini < 0.4**: Equal distribution (normal)
- **Gini 0.4-0.6**: Moderate inequality
- **Gini > 0.6**: High inequality (suspicious)

### 3. Velocity Analysis

**Trade Velocity** - Trades per minute deviation:

```python
velocity_z = (current_tpm - baseline_tpm) / std_tpm
```

**Anomaly if:** High volume + High velocity + High concentration

### 4. Whale Dominance Score

```python
whale_score = (top_3_traders_volume / total_volume) × (1 + velocity_multiplier)
```

**Thresholds:**
- **< 0.3**: Normal distribution
- **0.3-0.5**: Moderate concentration
- **> 0.5**: Whale-dominated (alert)

## Improved Algorithm

### Phase 1: Historical Baseline (Learn Normal Behavior)

For each market, track over 7 days:
- Hourly volume distribution (mean, std)
- Trader count distribution
- HHI distribution
- Time-of-day patterns
- Day-of-week patterns

### Phase 2: Real-Time Anomaly Scoring

```python
anomaly_score = (
    0.30 × z_score_volume +      # Volume deviation
    0.25 × concentration_score +  # HHI/Gini
    0.20 × velocity_score +       # Trade frequency
    0.15 × whale_score +          # Top trader dominance
    0.10 × directional_score      # Same-side bias
)
```

**Alert Levels:**
- **Score < 5**: Normal
- **Score 5-7**: Monitor
- **Score 7-9**: Warning
- **Score > 9**: Critical

### Phase 3: Pattern Recognition

**Coordinated Attack Patterns:**

1. **Pump Pattern**
   - Rapid buy orders
   - Multiple wallets
   - Similar timing (< 60s apart)
   - Price impact > 5%

2. **Dump Pattern**
   - Rapid sell orders
   - Large positions liquidated
   - Price impact > 5%

3. **Wash Trading**
   - Same wallets buying/selling
   - Minimal price movement
   - High volume, low net position change

4. **Sybil Coordination**
   - Clustered wallets (from clustering.py)
   - Synchronized trading
   - Similar bet sizes

## Implementation Strategy

### Step 1: Add Historical Tracking

```python
class MarketHistoricalBaseline:
    def __init__(self, lookback_days=7):
        self.hourly_volumes = deque(maxlen=24*lookback_days)
        self.hourly_trader_counts = deque(maxlen=24*lookback_days)
        self.hourly_hhi = deque(maxlen=24*lookback_days)
        
    def update(self, hour_data):
        self.hourly_volumes.append(hour_data['volume'])
        self.hourly_trader_counts.append(hour_data['traders'])
        self.hourly_hhi.append(hour_data['hhi'])
    
    def get_z_score(self, current_volume):
        if len(self.hourly_volumes) < 24:
            return 0.0  # Not enough data
        
        mean = np.mean(self.hourly_volumes)
        std = np.std(self.hourly_volumes)
        
        if std == 0:
            return 0.0
        
        return (current_volume - mean) / std
```

### Step 2: Calculate Concentration Metrics

```python
def calculate_hhi(trader_volumes: List[float]) -> float:
    """Herfindahl-Hirschman Index"""
    total = sum(trader_volumes)
    if total == 0:
        return 0.0
    
    shares = [v / total for v in trader_volumes]
    return sum(s**2 for s in shares)

def calculate_gini(trader_volumes: List[float]) -> float:
    """Gini Coefficient"""
    n = len(trader_volumes)
    if n == 0:
        return 0.0
    
    sorted_volumes = sorted(trader_volumes)
    cumsum = np.cumsum(sorted_volumes)
    
    return (2 * sum((i+1) * v for i, v in enumerate(sorted_volumes))) / (n * sum(sorted_volumes)) - (n + 1) / n
```

### Step 3: Composite Anomaly Score

```python
def calculate_anomaly_score(window: MarketTradingWindow, baseline: MarketHistoricalBaseline) -> float:
    # 1. Volume Z-Score (30%)
    volume_z = baseline.get_z_score(window.total_volume)
    volume_component = min(volume_z / 3.0, 1.0) * 3.0  # Cap at 3.0
    
    # 2. Concentration Score (25%)
    trader_volumes = [t['size'] * t['price'] for t in window.trades]
    hhi = calculate_hhi(trader_volumes)
    concentration_component = (hhi / 0.25) * 2.5  # Scale to 2.5 max
    
    # 3. Velocity Score (20%)
    trades_per_minute = len(window.trades) / 30  # 30-min window
    velocity_z = (trades_per_minute - baseline.avg_tpm) / baseline.std_tpm if baseline.std_tpm > 0 else 0
    velocity_component = min(velocity_z / 3.0, 1.0) * 2.0
    
    # 4. Whale Score (15%)
    top_3 = sorted(trader_volumes, reverse=True)[:3]
    whale_dominance = sum(top_3) / sum(trader_volumes) if trader_volumes else 0
    whale_component = (whale_dominance / 0.5) * 1.5
    
    # 5. Directional Score (10%)
    same_side = max(window.buy_volume, window.sell_volume) / window.total_volume if window.total_volume > 0 else 0
    directional_component = ((same_side - 0.5) / 0.5) * 1.0  # 0 if 50/50, 1.0 if 100% one side
    
    total_score = (
        volume_component +
        concentration_component +
        velocity_component +
        whale_component +
        directional_component
    )
    
    return total_score
```

## Alert Criteria (Revised)

Only alert if **ALL** of these conditions are met:

1. **Anomaly Score > 7.0** (statistically significant)
2. **Volume Z-Score > 2.5** (95%+ confidence)
3. **HHI > 0.20 OR Whale Dominance > 0.4** (concentrated)
4. **Absolute Volume > $500k** (material impact)

**OR** if CRITICAL trader is active with:
- Single trade > $50k
- Wallet concentration > 30% of window volume

## Benefits

✅ **Reduces False Positives**: Normal distributed trading won't trigger
✅ **Statistical Rigor**: Z-scores provide confidence levels
✅ **Concentration Focus**: Detects actual manipulation patterns
✅ **Adaptive**: Learns each market's normal behavior
✅ **Multi-Factor**: Combines multiple signals for accuracy

## Migration Path

1. **Week 1**: Deploy historical tracking (silent mode)
2. **Week 2**: Collect 7 days of baseline data
3. **Week 3**: Run new algorithm in parallel (log only)
4. **Week 4**: Compare old vs new alerts, tune thresholds
5. **Week 5**: Switch to new algorithm, deprecate old

## Expected Results

- **False Positive Rate**: Reduce from ~80% to <20%
- **True Positive Rate**: Maintain >90%
- **Alert Volume**: Reduce by 60-70%
- **Signal Quality**: Increase significantly