# Information Asymmetry Index (IAX)

## Overview

The **Information Asymmetry Index (IAX)** is a composite mathematical function designed to detect insider trading behavior on Polymarket. It rewards traders who demonstrate:

1. **High conviction** - Betting large portions of their bankroll
2. **Obscurity** - Betting on longshots/underdogs
3. **Urgency** - Using market orders that accept slippage
4. **Realized edge** - Actually winning their bets

## The Formula

### Individual Trade Edge

For each trade $i$:

$$TE_i = \Delta P_i \times C_i \times O_i \times U_i$$

Where:

| Variable | Formula | Meaning | Range |
|----------|---------|---------|-------|
| **ΔP** (Realized Edge) | `close_price - exec_price` (YES) | Actual profit/loss | -1.0 to +1.0 |
| **C** (Conviction) | `bet_size / wallet_bankroll` | How much they risked | 0.0 to 1.0 |
| **O** (Obscurity) | `-ln(exec_price)` | Betting on longshots | 0.0 to ~4.0 |
| **U** (Urgency) | `1 + \|exec_price - mid_price\| / mid_price` | Slippage accepted | 1.0 to ~2.0 |

### Wallet Aggregation

$$IAX_{wallet} = \frac{\sum_{i=1}^{N} TE_i}{\sqrt{N}}$$

The square root divisor is a **statistical stabilizer** (like Sharpe Ratio):
- **Burner wallets** (N=1, one big win): Keep full score
- **Active traders** (N=1000, consistent edge): Rewarded for volume without dilution
- **Degenerate gamblers** (losing bets): Negative scores

## Example Scores

### Normal Trader (Good but not insider)
```
- Buys $500 YES at 50¢ (wallet: $10,000)
- No slippage, wins bet
- TE = 0.50 × 0.05 × 0.69 × 1.0 = 0.017
```

### The Insider (Burner wallet)
```
- Funds wallet with $5,000
- Bets $5,000 YES at 5¢ (longshot)
- Accepts 20% slippage, wins bet
- TE = 0.95 × 1.0 × 3.0 × 1.20 = 3.42
```

**Result:** Insider scores **200× higher** than normal trader.

### Degenerate Gambler (Losing)
```
- Bets $5,000 YES at 5¢ (longshot)
- Loses bet
- TE = -0.05 × 1.0 × 3.0 × 1.0 = -0.15
```

**Result:** Negative score - punished for losing.

## Implementation

### Calculate IAX for a Wallet

```python
from src.features import calculate_iax_for_wallet

trades = [
    {
        "price": 0.05,        # Execution price
        "close_price": 1.0,   # 1.0 if won, 0.0 if lost
        "size": 5000,         # Bet size in $
        "mid_price": 0.0417,  # Market price before order
        "side": "YES",        # YES or NO
    },
    # ... more trades
]

result = calculate_iax_for_wallet(trades, wallet_bankroll=5000)
print(f"IAX Score: {result['iax_score']}")
```

### Rank Top Insider Wallets

```python
from src.features import rank_wallets_by_iax

top_50 = rank_wallets_by_iax(
    wallet_trades={...},      # addr -> trades
    wallet_bankrolls={...},   # addr -> bankroll
    top_n=50
)

for wallet in top_50:
    print(f"{wallet['address']}: IAX={wallet['iax_score']}")
```

### Get Insider Signals

```python
from src.features import get_insider_signals

insider_wallets = get_insider_signals(
    wallet_trades={...},
    wallet_bankrolls={...},
    threshold_percentile=95.0,  # Top 5%
)
```

## Features Added to ML Model

The IAX system adds **5 new features** to the ML model:

| Feature | Description |
|---------|-------------|
| `iax_score` | Composite insider score |
| `iax_total_edge` | Sum of all trade edges |
| `iax_avg_conviction` | Average bet sizing behavior |
| `iax_avg_obscurity` | Average contrarian tendency |
| `iax_avg_urgency` | Average slippage tolerance |

## Statistical Foundation

### Why Square Root of N?

The $\sqrt{N}$ divisor comes from the **Central Limit Theorem**:
- Standard error of mean decreases as $1/\sqrt{N}$
- Dividing by $\sqrt{N}$ instead of $N$ maintains score magnitude for high-volume traders
- Similar to **Sharpe Ratio** annualization

### Why Natural Log for Obscurity?

The $-\ln(P)$ function creates an **exponential reward** for underdog bets:

| Probability | -ln(P) | Interpretation |
|-------------|--------|----------------|
| 0.90 (favorite) | 0.10 | Minimal knowledge needed |
| 0.50 (coin flip) | 0.69 | Moderate insight |
| 0.10 (longshot) | 2.30 | Significant knowledge |
| 0.02 (miracle) | 3.91 | Extreme insider info |

## Usage in Production

1. **Historical Calculation**: Run IAX on all Polymarket history
2. **Rank Wallets**: Sort by IAX score descending
3. **Top 50**: These are your "God-Tier" signals
4. **Real-Time**: When top-50 wallets place new bets, weight model predictions heavily

## Files

- `src/features/iax.py` - Core IAX implementation
- `tests/test_iax.py` - Test suite (14 tests)
- `src/features/engineer.py` - Integrated into feature engineering

## References

- Based on quantitative finance index construction
- Similar to **Shiller's CAPE** ratio for market valuation
- Incorporates **Kelly Criterion** sizing principles
- Uses **Sharpe Ratio** statistical stabilization
