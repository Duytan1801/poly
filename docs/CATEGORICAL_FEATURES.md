# Perpetual ML Categorical Features Guide

## Official Documentation (from PerpetualBooster)

### `categorical_features` Parameter

**Type:** `str` or `iterable`  
**Default:** `"auto"`

Feature indices or names to treat as categorical.

### Accepted Values

| Value | Type | Description | Example |
|-------|------|-------------|---------|
| `"auto"` | str | Auto-detect categorical columns | `categorical_features="auto"` |
| `[int, ...]` | list | Column indices (0-based) | `categorical_features=[0, 2, 5]` |
| `[str, ...]` | list | Column names (DataFrames only) | `categorical_features=['side', 'outcome']` |
| `None` | None | Treat all features as numeric | `categorical_features=None` |

### `max_cat` Parameter

**Type:** `int`  
**Default:** `1000`

Maximum unique categories before a feature is treated as numerical.

Features with more than `max_cat` unique values will be treated as continuous/numerical instead of categorical.

---

## How Perpetual Handles Categorical Features

Perpetual **natively handles categorical variables** using advanced tree splitting:

1. **No encoding needed** - Pass categorical features directly (integers or strings)
2. **Optimal split finding** - Finds best categorical splits automatically
3. **Handles high cardinality** - Uses `max_cat` to control complexity

### Internal Behavior

When you specify `categorical_features`:

```python
# With "auto" - detects categorical columns automatically
model = PerpetualBooster(categorical_features="auto")

# Perpetual checks each column:
# - If dtype is object/string → categorical
# - If dtype is int with few unique values → may be categorical
# - If unique values > max_cat (1000) → treated as numeric
```

---

## Usage Examples

### Example 1: Auto-detection (Recommended)

```python
import pandas as pd
from perpetual import PerpetualBooster

df = pd.DataFrame({
    'age': [25, 30, 35, 40],
    'side': ['YES', 'NO', 'YES', 'NO'],      # Categorical
    'outcome': ['win', 'loss', 'win', 'loss'], # Categorical
    'bet_size': [100, 200, 150, 300],
})
y = [1, 0, 1, 0]

# Auto-detect categorical columns
model = PerpetualBooster(
    objective="LogLoss",
    budget=1.15,
    categorical_features="auto",  # Automatically detects 'side' and 'outcome'
)

model.fit(df, y)
```

### Example 2: Specify by Column Index

```python
# Categorical features at indices 1 and 2
model = PerpetualBooster(
    objective="LogLoss",
    budget=1.15,
    categorical_features=[1, 2],  # Column indices
)

model.fit(df, y)
```

### Example 3: Specify by Column Name

```python
# Categorical features by name
model = PerpetualBooster(
    objective="LogLoss",
    budget=1.15,
    categorical_features=['side', 'outcome'],  # Column names
)

model.fit(df, y)
```

### Example 4: All Numeric (No Categorical)

```python
# Treat all features as numeric
model = PerpetualBooster(
    objective="LogLoss",
    budget=1.15,
    categorical_features=None,
)

model.fit(df, y)
```

### Example 5: High Cardinality Control

```python
# Features with > 500 categories treated as numeric
model = PerpetualBooster(
    objective="LogLoss",
    budget=1.15,
    categorical_features="auto",
    max_cat=500,  # Lower than default 1000
)
```

---

## Best Practices

### 1. Use `"auto"` for DataFrames

```python
# Recommended for pandas/polars DataFrames
model = PerpetualBooster(categorical_features="auto")
```

Perpetual will automatically detect:
- String/object columns → categorical
- Integer columns with few unique values → may be categorical

### 2. Use Names for Clarity

```python
# More readable than indices
categorical_features=['side', 'market_type', 'outcome']
```

### 3. Adjust `max_cat` for High Cardinality

```python
# For features with many categories
model = PerpetualBooster(
    categorical_features="auto",
    max_cat=500,  # Lower = faster, higher = more expressive
)
```

| `max_cat` | Use Case |
|-----------|----------|
| 100-500 | High cardinality, faster training |
| 1000 (default) | Balanced |
| 5000+ | Low cardinality, maximum expressiveness |

### 4. Don't One-Hot Encode

```python
# ❌ Don't do this - Perpetual handles it natively
X_encoded = pd.get_dummies(X)  # Wrong!

# ✅ Do this - pass raw categorical columns
model = PerpetualBooster(categorical_features="auto")
model.fit(X_raw, y)  # Correct!
```

### 5. For NumPy Arrays, Use Indices

```python
import numpy as np

X = np.array([
    [25, 0, 100],  # 0 = BUY, 1 = SELL (categorical)
    [30, 1, 200],
    [35, 0, 150],
])

# Specify column index 1 as categorical
model = PerpetualBooster(categorical_features=[1])
model.fit(X, y)
```

---

## For Polymarket ML Pipeline

### Recommended Configuration

```python
# In poly/models/trainer.py

model = PerpetualBooster(
    objective="LogLoss",
    budget=1.15,
    categorical_features="auto",  # Auto-detect 'side' and other categoricals
    max_cat=1000,                  # Default is fine
    save_node_stats=True,
)
```

### Features That Should Be Categorical

| Feature | Type | Should Be Categorical? |
|---------|------|------------------------|
| `side` | YES/NO | ✅ Yes |
| `market_type` | string | ✅ Yes |
| `outcome` | win/loss | ✅ Yes |
| `total_trades` | int | ❌ No (numeric) |
| `winrate` | float | ❌ No (numeric) |
| `iax_score` | float | ❌ No (numeric) |

---

## References

- **PerpetualBooster Docstring**: `help(PerpetualBooster.__init__)`
- **GitHub**: https://github.com/perpetual-ml/perpetual
- **Documentation**: https://perpetual-ml.github.io/perpetual/
