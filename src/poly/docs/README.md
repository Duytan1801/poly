# Polymarket ML Pipeline

Detect insider trading behavior on Polymarket using **IAX (Information Asymmetry Index)** and **Perpetual ML**.

## Quick Start

```bash
# Install
uv sync

# Run full pipeline
uv run python cli.py run

# Or step by step
uv run python cli.py collect    # Collect 1M trades
uv run python cli.py process    # Generate features
uv run python cli.py train      # Train model
```

## Project Structure

```
poly/
├── poly/                    # Source package
│   ├── api/                 # Polymarket API client
│   ├── collection/          # Trade collection & IAX analysis
│   ├── features/            # Feature engineering
│   ├── models/              # Perpetual ML trainer
│   └── utils/               # Utilities
├── pipelines/               # Pipeline scripts
│   ├── collect.py           # Collect 1M trades
│   ├── process.py           # Generate features
│   └── train.py             # Train classifier
├── cli.py                   # Command-line interface
├── config.py                # Configuration
└── data/                    # Data storage
    ├── raw/                 # Raw trades (parquet)
    ├── processed/           # Features
    └── models/              # Trained models
```

## Pipeline

### 1. Data Collection (`poly collect`)

Collects **top 100 traders from each market**:
- Fetches 1,000 markets from each of 10 tags (10,000 total markets)
- Gets top 100 ROI traders per market
- Collects full trading histories for all top traders
- Saves incrementally to parquet

```bash
uv run python cli.py collect
```

Output:
- `data/raw/markets.parquet` - Market data
- `data/raw/top_traders.parquet` - Top traders by ROI
- `data/raw/trader_trades_*.parquet` - Trader history batches
- `data/raw/all_trades.parquet` - Combined trades

### 2. Feature Engineering (`poly process`)

Generates features for each trader:

| Feature | Description |
|---------|-------------|
| `total_trades` | Trade count |
| `overall_winrate` | Win rate |
| `overall_roi` | ROI |
| `avg_bet_size` | Average bet |
| `max_bet_size` | Max bet |
| `days_active` | Activity duration |
| **`iax_score`** | Insider detection score |
| **`iax_total_edge`** | Total edge |

```bash
uv run python cli.py process
```

Output:
- `data/processed/features.parquet` - Trader features

### 3. Model Training (`poly train`)

Trains win/loss classifier using **Perpetual ML**:
- Objective: `LogLoss` (binary classification)
- Budget: `1.15` (auto-determines trees)
- Features: 8 core features including IAX

```bash
uv run python cli.py train
```

Output:
- `data/models/classifier.json` - Trained model
- `data/models/metrics.json` - Performance metrics

## IAX (Information Asymmetry Index)

Detects insider trading behavior:

$$IAX = \frac{\sum (\Delta P \times C \times O \times U)}{\sqrt{N}}$$

| Component | Formula | Insider Signal |
|-----------|---------|----------------|
| **ΔP** (Edge) | `close - exec` | Must win bets |
| **C** (Conviction) | `bet / bankroll` | 100% = insider |
| **O** (Obscurity) | `-ln(price)` | Longshots = 3-4× |
| **U** (Urgency) | `1 + slippage` | Market orders = 1.2× |

**Insiders score 200× higher** than normal traders.

## Configuration

Edit `config.py`:

```python
TAGS = ["21", "107", "1401", ...]  # 10 market tags
MARKETS_PER_TAG = 1000              # Markets per tag
TOP_TRADERS_PER_MARKET = 100        # Top traders per market
MODEL_BUDGET = 1.15                 # Model complexity
```

**Note:** No manual qualification thresholds - the model learns patterns from all traders automatically.

## API Usage

```python
from poly import PolymarketClient, TradeCollector
from poly.features import calculate_iax_for_wallet
from poly.models import ModelTrainer

# Collect
client = PolymarketClient()
collector = TradeCollector(client)
collector.collect_markets(["21"])
collector.collect_trader_histories(traders, target=1_000_000)

# IAX
trades = [...]
iax = calculate_iax_for_wallet(trades, bankroll=5000)
print(f"IAX Score: {iax['iax_score']}")

# Train
trainer = ModelTrainer()
results = trainer.train(features_df)
```

## Requirements

- Python 3.10+
- See `pyproject.toml` for dependencies

## License

MIT
