# Perpetual ML - Complete API Documentation

Deep research based on live inspection of the installed `perpetual` package (v1.1.2).

---

## Installation

```bash
pip install perpetual
```

### Optional Dependencies

```bash
# For Pandas DataFrame support
pip install pandas

# For zero-copy Polars support (recommended for performance)
pip install polars

# For scikit-learn compatible interface
pip install scikit-learn

# For XGBoost format export
pip install xgboost

# For ONNX format export
pip install onnxruntime
```

---

## Quick Start

### Classification

```python
from perpetual import PerpetualBooster

# Create model with LogLoss for binary classification
model = PerpetualBooster(objective="LogLoss", budget=0.5)

# Train
model.fit(X_train, y_train)

# Predict probabilities
probs = model.predict_proba(X_test)

# Predict classes
predictions = (probs > 0.5).astype(int)
```

### Regression

```python
from perpetual import PerpetualBooster

# Create model with SquaredLoss for regression
model = PerpetualBooster(objective="SquaredLoss", budget=0.5)

# Train
model.fit(X_train, y_train)

# Predict
predictions = model.predict(X_test)
```

### Ranking

```python
from perpetual import PerpetualBooster
import numpy as np

# Create model for ranking
model = PerpetualBooster(objective="ListNetLoss", budget=0.5)

# Train with group labels
model.fit(X_train, y_train, group=group_labels)

# Predict
predictions = model.predict(X_test)
```

---

## Constructor Parameters

### `PerpetualBooster.__init__()`

```python
PerpetualBooster(
    # Core Parameters
    objective='LogLoss',          # Loss function (str or custom tuple)
    budget=0.5,                   # Complexity control (higher = more trees)
    
    # Parallelism
    num_threads=None,             # Number of CPU threads (None = auto)
    timeout=None,                 # Max training time in seconds
    iteration_limit=None,         # Max number of iterations
    
    # Memory & Performance
    memory_limit=None,            # Max memory usage in bytes
    max_bin=256,                  # Max histogram bins (2-512)
    max_cat=1000,                 # Max categories before treating as numerical
    
    # Categorical Features
    categorical_features='auto',  # 'auto', list of indices/names, or None
    
    # Missing Value Handling
    missing=np.nan,               # Value to treat as missing
    allow_missing_splits=True,    # Allow splits on missing values
    create_missing_branch=False,  # Create separate branch for missing
    terminate_missing_features=None,  # Features to stop splitting on if missing
    missing_node_treatment='None',    # 'None', 'AssignToParent', 'AverageLeafWeight'
    
    # Constraints
    monotone_constraints=None,    # Dict of {feature: -1/0/1}
    interaction_constraints=None, # List of lists [[0,1], [2,3,4]]
    force_children_to_bound_parent=False,  # Monotonicity enforcement
    
    # Training Control
    reset=None,                   # Reset model before fitting (for continual learning)
    stopping_rounds=None,         # Early stopping rounds
    save_node_stats=False,        # Save node statistics (required for calibration/drift)
    log_iterations=0,             # Log progress every N iterations
    feature_importance_method='Gain',  # 'Gain', 'Weight', 'Cover', etc.
    
    # Quantile Regression
    quantile=None,                # Quantile level (0-1) for QuantileLoss
)
```

### Parameter Details

#### **Core Parameters**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `objective` | str or tuple | `'LogLoss'` | Loss function. See objectives below. |
| `budget` | float | `0.5` | Controls model complexity. Higher = more trees, better fit. |

**Budget Parameter Explained:**
- Range: 0.0 to ~2.0 (typical)
- Learning rate η = 10^(-budget)
- `budget=0.5` → ~10-50 trees
- `budget=1.0` → ~50-200 trees
- `budget=1.5` → ~200-500 trees
- Start with `0.5`, increase if underfitting

#### **Objectives**

| Objective | Use Case | Notes |
|-----------|----------|-------|
| `"LogLoss"` | Binary/Multi-class classification | Default, outputs log-odds |
| `"SquaredLoss"` | Regression | Standard MSE |
| `"QuantileLoss"` | Quantile regression | Requires `quantile` parameter |
| `"HuberLoss"` | Robust regression | Less sensitive to outliers |
| `"PoissonLoss"` | Count data | For non-negative integer targets |
| `"GammaLoss"` | Positive continuous | For skewed positive data |
| `"TweedieLoss"` | Insurance/finance | For zero-inflated continuous |
| `"ListNetLoss"` | Learning to rank | Requires `group` parameter |
| `"HingeLoss"` | SVM-like classification | Max-margin |
| `"BrierLoss"` | Probability calibration | Proper scoring rule |
| `"CrossEntropyLoss"` | Multi-class | Alternative to LogLoss |
| Custom | Any | Tuple of (loss, gradient, hessian, init_value) |

#### **Categorical Features**

```python
# Auto-detect categorical columns
PerpetualBooster(categorical_features='auto')

# Specify by index
PerpetualBooster(categorical_features=[0, 2, 5])

# Specify by name (with DataFrames)
PerpetualBooster(categorical_features=['color', 'category'])

# Disable categorical handling
PerpetualBooster(categorical_features=None)
```

#### **Missing Value Handling**

```python
# Default: treat NaN as missing, allow splits
PerpetualBooster(missing=np.nan, allow_missing_splits=True)

# Create separate branch for missing values (ternary trees)
PerpetualBooster(create_missing_branch=True)

# Treat missing as going to parent node
PerpetualBooster(missing_node_treatment='AssignToParent')
```

#### **Monotonic Constraints**

```python
# Force positive relationship with 'age'
# Force negative relationship with 'debt_ratio'
PerpetualBooster(monotone_constraints={
    'age': 1,           # As age increases, prediction increases
    'debt_ratio': -1,   # As debt increases, prediction decreases
    'income': 0,        # No constraint
})
```

#### **Interaction Constraints**

```python
# Feature 0 can only interact with feature 1
# Features 2, 3, 4 can interact with each other
PerpetualBooster(interaction_constraints=[
    [0, 1],
    [2, 3, 4],
])
```

---

## Methods

### Training

#### `fit(X, y, sample_weight=None, group=None)`

Fit the model on training data.

```python
# Basic usage
model.fit(X_train, y_train)

# With sample weights
model.fit(X_train, y_train, sample_weight=weights)

# For ranking (with group labels)
model.fit(X_train, y_train, group=group_labels)

# For continual learning (don't reset)
model = PerpetualBooster(reset=False)
model.fit(X_batch1, y_batch1)
model.fit(X_cumulative, y_cumulative)  # Uses cumulative data
```

**Parameters:**
- `X`: array-like (n_samples, n_features) - Can be DataFrame, Polars, or numpy array
- `y`: array-like (n_samples,) - Target values
- `sample_weight`: array-like (n_samples,) - Optional sample weights
- `group`: array-like - Group labels for ranking

**Returns:** `self`

---

### Prediction

#### `predict(X, parallel=None)`

Make predictions.

```python
# Basic predictions
predictions = model.predict(X_test)

# Parallel prediction
predictions = model.predict(X_test, parallel=True)
```

**Returns:** ndarray (n_samples,) - Raw predictions (log-odds for classification)

---

#### `predict_proba(X, parallel=None, calibrated=False)`

Predict class probabilities (classification only).

```python
# Standard probabilities
probs = model.predict_proba(X_test)

# Calibrated probabilities (after calling calibrate())
probs = model.predict_proba(X_test, calibrated=True)
```

**Returns:** ndarray (n_samples, n_classes) - Class probabilities

---

#### `predict_log_proba(X, parallel=None)`

Predict log-probabilities.

```python
log_probs = model.predict_log_proba(X_test)
```

---

#### `predict_contributions(X, method='Average', parallel=None)`

Get SHAP-like feature contributions.

```python
# Get feature contributions (SHAP values)
contributions = model.predict_contributions(X_test, method='Average')

# Shape: (n_samples, n_features + 1)
# Last column is bias term
```

**Methods:**
- `'Average'` - Internal node averages
- `'Shapley'` - Exact Tree SHAP values
- `'Weight'` - Saabas-style leaf weights
- `'BranchDifference'` - Chosen vs other branch
- `'MidpointDifference'` - Weighted branch difference
- `'ProbabilityChange'` - LogLoss-specific probability change

**Returns:** ndarray (n_samples, n_features + 1)

---

### Calibration & Uncertainty

#### `calibrate(X_cal, y_cal, alpha, method=None)`

Calibrate for prediction intervals.

```python
# Calibrate with multiple alpha levels
model.calibrate(X_cal, y_cal, alpha=[0.01, 0.05, 0.1])

# Specify method
model.calibrate(X_cal, y_cal, alpha=0.05, method='WeightVariance')
```

**Parameters:**
- `X_cal`: Calibration data
- `y_cal`: Calibration targets
- `alpha`: Significance level(s) (1 - coverage)
- `method`: `'MinMax'`, `'GRP'`, `'WeightVariance'`, or None

**Methods:**
- `'WeightVariance'` - Confidence-weighted (default)
- `'GRP'` - Log-odds percentiles (high efficiency)
- `'MinMax'` - Leaf value ranges

**Requires:** `save_node_stats=True` in constructor

---

#### `predict_intervals(X, parallel=None)`

Get prediction intervals (regression).

```python
# After calibration
model.calibrate(X_cal, y_cal, alpha=[0.1, 0.2])

# Get intervals
intervals = model.predict_intervals(X_test)
# Returns: {'0.1': {'lower': [...], 'upper': [...]}, '0.2': {...}}
```

---

#### `predict_sets(X, parallel=None)`

Get conformal prediction sets (classification).

```python
# After calibration
model.calibrate(X_cal, y_cal, alpha=0.1)

# Get prediction sets
sets = model.predict_sets(X_test)
# Returns: dict mapping sample index to set of classes
```

---

#### `predict_distribution(X, n=100, parallel=None)`

Get raw prediction distribution (uncalibrated).

```python
# Generate simulation distribution
dist = model.predict_distribution(X_test, n=100)
# Shape: (n_samples, 100)
```

---

### Drift Detection

#### `calculate_drift(X, drift_type='data', parallel=None)`

Detect data or concept drift.

```python
# Data drift (distribution shift)
data_drift = model.calculate_drift(X_new, drift_type='data')

# Concept drift (prediction pattern shift)
concept_drift = model.calculate_drift(X_new, drift_type='concept')

# Higher score = more drift
if data_drift > 5.0:
    print("Significant drift detected!")
```

**Drift Score Interpretation:**
- ~0: No drift
- 0-1: Minor drift (monitor)
- 1-5: Moderate drift (investigate)
- >5: Significant drift (action needed)

**Requires:** `save_node_stats=True` in constructor

---

### Feature Importance

#### `calculate_feature_importance(method='Gain', normalize=False)`

Calculate feature importance.

```python
# Gain-based importance (default)
importance = model.calculate_feature_importance(method='Gain')

# Other methods
importance = model.calculate_feature_importance(method='Weight')
importance = model.calculate_feature_importance(method='Cover')
importance = model.calculate_feature_importance(method='TotalGain')

# Normalized (sums to 1)
importance = model.calculate_feature_importance(method='Gain', normalize=True)
```

**Methods:**
- `'Gain'` - Average information gain
- `'Weight'` - Number of splits
- `'Cover'` - Average coverage
- `'TotalGain'` - Total information gain
- `'TotalCover'` - Total coverage

---

#### `feature_importances_`

Property to get feature importances after fitting.

```python
importances = model.feature_importances_
```

---

### Partial Dependence

#### `partial_dependence(X, feature, samples=100, exclude_missing=True, percentile_bounds=(0.2, 0.98))`

Calculate partial dependence for a feature.

```python
# Get PDP for feature 0
pdp_values = model.partial_dependence(X, feature=0, samples=100)

# Shape: (n_points, 2)
# Column 0: feature values
# Column 1: partial dependence values

# Custom percentile bounds (exclude outliers)
pdp_values = model.partial_dependence(
    X, feature='age', 
    samples=50,
    percentile_bounds=(0.05, 0.95)
)
```

---

### Model IO

#### `save_model()` / `from_json()`

Save and load model.

```python
# Save to bytes
model_bytes = model.save_model()
with open('model.bin', 'wb') as f:
    f.write(model_bytes)

# Load from bytes
with open('model.bin', 'rb') as f:
    model = PerpetualBooster.from_json(f.read().decode())
```

---

#### `save_booster(path)` / `load_booster(path)`

Save/load in native format.

```python
# Save
model.save_booster('model.perp')

# Load
model = PerpetualBooster.load_booster('model.perp')
```

---

#### `save_as_xgboost(path)`

Export to XGBoost format.

```python
model.save_as_xgboost('model_xgb.json')
```

---

#### `save_as_onnx(path)`

Export to ONNX format.

```python
model.save_as_onnx('model.onnx')
```

---

### Model Inspection

#### `number_of_trees()`

Get the number of trees in the ensemble.

```python
n_trees = model.number_of_trees()
print(f"Model has {n_trees} trees")
```

---

#### `is_fitted()`

Check if model is fitted.

```python
if model.is_fitted():
    predictions = model.predict(X_test)
```

---

#### `get_params()` / `set_params()`

Get/set model parameters (scikit-learn compatible).

```python
# Get all parameters
params = model.get_params()

# Set parameters
model.set_params(budget=1.0, num_threads=4)
```

---

#### `trees_to_dataframe()`

Convert trees to a pandas DataFrame.

```python
# Get detailed tree structure
trees_df = model.trees_to_dataframe()
```

---

#### `get_node_lists()`

Get list of nodes per tree.

```python
nodes = model.get_node_lists()
```

---

#### `predict_nodes(X)`

Get node indices for each sample.

```python
# Which leaf node each sample ends up in
nodes = model.predict_nodes(X_test)
```

---

#### `base_score`

Get the initial base score.

```python
initial_score = model.base_score
```

---

#### `get_metadata()` / `insert_metadata()`

Get/insert model metadata.

```python
# Get metadata
metadata = model.get_metadata()

# Insert custom metadata
model.insert_metadata({'trained_by': 'pipeline_v1', 'date': '2026-02-28'})
```

---

#### `metadata_attributes`

List of metadata attribute names.

```python
attrs = model.metadata_attributes
```

---

### Model Pruning

#### `prune()`

Prune the ensemble to reduce size.

```python
# Remove unnecessary trees/nodes
model.prune()
```

---

## Advanced Usage

### Continual Learning

```python
from perpetual import PerpetualBooster

# Enable continual learning (don't reset between fits)
model = PerpetualBooster(objective="SquaredLoss", budget=1.0, reset=False)

# First batch
model.fit(X_batch1, y_batch1)

# Subsequent batches (use CUMULATIVE data)
X_cumulative = np.vstack([X_batch1, X_batch2])
y_cumulative = np.concatenate([y_batch1, y_batch2])
model.fit(X_cumulative, y_cumulative)

# Complexity: O(n) vs O(n²) for retraining
```

---

### Custom Objective Functions

```python
import numpy as np

# Define custom loss function
def custom_loss(y_true, y_pred):
    return y_true - y_pred  # Gradient

def custom_hessian(y_true, y_pred):
    return np.ones_like(y_true)  # Hessian

def custom_init_value(y_true):
    return np.mean(y_true)  # Initial prediction

# Create model with custom objective
model = PerpetualBooster(
    objective=(custom_loss, custom_hessian, custom_init_value),
    budget=0.5
)

model.fit(X_train, y_train)
```

---

### Scikit-Learn Interface

```python
from perpetual.sklearn import PerpetualClassifier, PerpetualRegressor

# Drop-in replacement for sklearn
clf = PerpetualClassifier(budget=0.5, objective="LogLoss")
clf.fit(X_train, y_train)
score = clf.score(X_test, y_test)
probs = clf.predict_proba(X_test)

# Works with sklearn pipelines, grid search, etc.
```

---

### Polars Zero-Copy Support

```python
import polars as pl
from perpetual import PerpetualBooster

# Polars DataFrames use zero-copy path
df = pl.DataFrame({'a': [1, 2, 3], 'b': [4, 5, 6]})

model = PerpetualBooster()
model.fit(df, y)  # Zero-copy, faster!
```

---

## Best Practices

### 1. Budget Selection

```python
# Start small, increase if underfitting
budgets = [0.5, 0.75, 1.0, 1.25, 1.5]

for budget in budgets:
    model = PerpetualBooster(budget=budget)
    model.fit(X_train, y_train)
    score = model.score(X_val, y_val)
    print(f"Budget {budget}: {score:.4f}, Trees: {model.number_of_trees()}")
```

### 2. Enable Node Stats for Production

```python
# Required for calibration, drift detection, uncertainty
model = PerpetualBooster(save_node_stats=True)
```

### 3. Use Sample Weights for Imbalanced Data

```python
# Weight minority class higher
weights = np.where(y_train == 1, 5.0, 1.0)
model.fit(X_train, y_train, sample_weight=weights)
```

### 4. Monotonic Constraints for Domain Knowledge

```python
# Encode business logic
model = PerpetualBooster(monotone_constraints={
    'credit_score': 1,      # Higher score = lower risk
    'debt_to_income': -1,   # Higher DTI = higher risk
    'age': 0,               # No constraint
})
```

### 5. Continual Learning for Streaming Data

```python
# O(n) updates instead of O(n²) retraining
model = PerpetualBooster(reset=False)

for batch in data_stream:
    X_cumulative = np.vstack([X_cumulative, batch.X])
    y_cumulative = np.concatenate([y_cumulative, batch.y])
    model.fit(X_cumulative, y_cumulative)
```

---

## Performance Tips

1. **Use Polars for large datasets** - Zero-copy memory efficiency
2. **Set `num_threads` explicitly** - Control CPU usage
3. **Use `memory_limit`** - Prevent OOM errors
4. **Enable `categorical_features='auto'`** - Native categorical handling
5. **Start with low budget** - Faster iteration during development

---

## Troubleshooting

### Model Underfitting

```python
# Increase budget
model = PerpetualBooster(budget=1.5)

# Check number of trees
print(model.number_of_trees())  # If < 50, increase budget
```

### Model Overfitting

```python
# Decrease budget
model = PerpetualBooster(budget=0.3)

# Add monotonic constraints
model = PerpetualBooster(monotone_constraints={...})

# Use early stopping
model = PerpetualBooster(stopping_rounds=10)
```

### Memory Issues

```python
# Limit memory usage
model = PerpetualBooster(memory_limit=1e9)  # 1GB

# Reduce max_bin
model = PerpetualBooster(max_bin=128)
```

### Slow Training

```python
# Increase threads
model = PerpetualBooster(num_threads=8)

# Reduce max_cat for high-cardinality categoricals
model = PerpetualBooster(max_cat=100)
```

---

## References

- **GitHub**: https://github.com/perpetual-ml/perpetual
- **PyPI**: https://pypi.org/project/perpetual/
- **Documentation**: https://perpetual-ml.github.io/perpetual/
- **Version**: 1.1.2 (as of Feb 2026)
