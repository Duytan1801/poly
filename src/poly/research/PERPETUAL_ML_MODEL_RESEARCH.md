# Perpetual ML - Deep Research Documentation

## Executive Summary

Perpetual is a self-generalizing gradient boosting machine (GBM) developed by Mutlu Simsek, Serkan Korkmaz, and Pieter Pel. Its defining innovation is eliminating the need for hyperparameter optimization through a single `budget` parameter, making it significantly easier to use while delivering state-of-the-art predictive performance.

**Version**: 1.9.2  
**Core Technology**: Rust-based implementation with Python/R bindings  
**Primary Use Cases**: Classification, Regression, Ranking, Causal Inference

---

## 1. Core Architecture

### 1.1 System Overview

Perpetual employs a two-layer architecture optimized for performance and usability:

```
┌─────────────────────────────────────────────────┐
│         Python Interface (py-perpetual)         │
│    Built with PyO3, provides clean API surface  │
├─────────────────────────────────────────────────┤
│         Rust Core (perpetual-rs)                │
│  Histogram-based learning, tree building,       │
│  parallelism via Rayon                          │
└─────────────────────────────────────────────────┘
```

### 1.2 Rust Core Components

**Key Rust Modules** (`src/` directory):

| Component | File | Purpose |
|-----------|------|---------|
| PerpetualBooster | `booster/core.rs` | Manages ensemble of decision trees, training loop |
| Histogram | `binning.rs` | Discretizes continuous features for efficient splits |
| Objective | `objective/core.rs` | Generic loss function interface |
| Parallelism | Rayon | Data parallelism for histogram building, predictions |

**Supported Objectives**:
- **Classification**: LogLoss, BrierLoss, HingeLoss, CrossEntropyLoss
- **Regression**: SquaredLoss, QuantileLoss, HuberLoss, PoissonLoss, GammaLoss, TweedieLoss
- **Ranking**: ListNetLoss
- **Custom**: Tuple of (loss, gradient, initial_value) functions

### 1.3 Python Interface

**PyO3 Bindings**:
- Direct method forwarding from Python to Rust
- Zero-copy data transfer for Polars DataFrames
- Standard NumPy/Pandas support with memory layout considerations

**Data Interface**:
```python
# Zero-copy (Polars)
model.fit(polars_df)  # fit_columnar path

# Copy required (NumPy/Pandas)
model.fit(numpy_array)  # C-contiguous required
```

---

## 2. Key Innovation: Self-Generalization via Budget

### 2.1 The Budget Parameter

Instead of tuning multiple hyperparameters (learning rate, tree depth, regularization), Perpetual uses a single `budget` parameter:

```
Learning Rate (η) = 10^(-budget)
```

**How it works**:
1. Higher budget → more trees, potentially better fit
2. Lower budget → faster training, better generalization for simpler data
3. Algorithm monitors generalization error during training
4. Early stopping when trees start overfitting

### 2.2 Automatic Generalization Strategy

```
Training Process:
1. Start with initial predictions
2. Add trees iteratively
3. Monitor generalization error at each step
4. Stop when generalization capability drops below threshold
5. Result: Optimal number of trees determined automatically
```

**Advantages**:
- No validation set needed for early stopping
- Single hyperparameter to tune
- Guaranteed optimal complexity for given budget

---

## 3. Supported Task Types

### 3.1 Classification

```python
from perpetual import PerpetualBooster

model = PerpetualBooster(objective="LogLoss")
model.fit(X_train, y_train)
predictions = model.predict(X_test)
probs = model.predict_proba(X_test)
```

**Features**:
- Binary and multi-class support
- Probability calibration via PAVA (Pool Adjacent Violators Algorithm)
- Conformal prediction sets

### 3.2 Regression

```python
model = PerpetualBooster(objective="SquaredLoss")
model.fit(X_train, y_train)
predictions = model.predict(X_test)
```

**Quantile Regression**:
```python
model = PerpetualBooster(objective="QuantileLoss", quantile=0.9)
```

### 3.3 Learning-to-Rank

```python
import numpy as np
from perpetual import PerpetualBooster

# 100 queries, each with 10 documents
n_queries = 100
n_docs_per_query = 10

X = np.random.rand(n_queries * n_docs_per_query, 5)
y = np.random.rand(n_queries * n_docs_per_query)
group = np.full(n_queries, n_docs_per_query)

model = PerpetualBooster(objective="ListNetLoss")
model.fit(X, y, group=group)
```

---

## 4. Advanced Tree Features

### 4.1 Categorical Feature Handling

```python
model = PerpetualBooster(
    categorical_features=[0, 2, 5],  # Feature indices
    max_cat=1000  # Max categories before treating as numerical
)
```

**Capabilities**:
- Native categorical variable support
- Optimal split finding for categorical features
- Automatic detection (`categorical_features='auto'`)

### 4.2 Missing Value Handling

```python
model = PerpetualBooster(
    missing=np.nan,              # Value to consider missing
    allow_missing_splits=True,   # Allow splits separating missing/non-missing
    create_missing_branch=False, # Ternary tree support
    missing_node_treatment='None'  # Options: None, AssignToParent, AverageLeafWeight
)
```

### 4.3 Monotonic Constraints

```python
model = PerpetualBooster(
    monotone_constraints={
        'age': 1,           # Positive relationship
        'debt_ratio': -1,   # Negative relationship
        'income': 0         # No constraint
    }
)
```

### 4.4 Interaction Constraints

```python
model = PerpetualBooster(
    interaction_constraints=[
        [0, 1],    # Feature 0 can only interact with feature 1
        [2, 3, 4]  # Features 2, 3, 4 can interact with each other
    ]
)
```

---

## 5. Built-in Causal ML

Perpetual provides comprehensive causal inference capabilities:

### 5.1 Double Machine Learning (DML)

Estimates Conditional Average Treatment Effect (CATE) using Neyman-orthogonal score:

```python
from perpetual.dml import DMLEstimator

model = DMLEstimator(
    budget=0.5,
    n_folds=2,
    objective="SquaredLoss"
)
model.fit(X, w, y)  # w: treatment, y: outcome
cate_pred = model.predict(X_test)
```

### 5.2 Uplift Modeling

Identifies treatment-responsive individuals:

```python
from perpetual.uplift import UpliftBooster

model = UpliftBooster(budget=0.5)
model.fit(X, treatment, outcome)
uplift_scores = model.predict(X_test)
```

**Use Cases**:
- Marketing campaign optimization
- Customer retention
- Medical treatment selection

### 5.3 Policy Learning

Learns optimal treatment assignment policies:

```python
from perpetual.policy import PolicyLearner

model = PolicyLearner(budget=0.5)
model.fit(X, treatment, outcome)
optimal_policy = model.predict(X_test)
```

### 5.4 Instrumental Variables (BoostIV)

Handles endogenous treatment variables:

```python
from perpetual.iv import BraidedBooster

model = BraidedBooster(budget=0.5)
model.fit(X, treatment, outcome, instruments)
causal_effect = model.predict(X_test)
```

### 5.5 Meta-Learners

| Learner | Use Case |
|---------|----------|
| SLearner | Single model with treatment as feature |
| TLearner | Separate models for treated/control |
| XLearner | Two-stage approach with imputed effects |
| DRLearner | Doubly robust estimation |

### 5.6 Fairness and Bias Mitigation

```python
from perpetual.fairness import FairClassifier

model = FairClassifier(
    budget=0.5,
    sensitive_attribute='gender',
    fairness_constraint='demographic_parity'
)
model.fit(X, y)
fair_predictions = model.predict(X_test)
```

### 5.7 Regulatory Risk and Interpretability

```python
from perpetual.risk import PerpetualRiskEngine

risk_engine = PerpetualRiskEngine(model)
reason_codes = risk_engine.generate_reason_codes(X)
# Provides feature contributions for regulatory compliance
```

---

## 6. Calibration and Uncertainty Quantification

### 6.1 Post-Hoc Calibration Advantage

```
Traditional Approach:
├── Quantile Regression → Multiple models needed
├── CV-based Calibration → K× training time increase
└── Conformal Wrappers → External tools, complexity

Perpetual Approach:
├── Train once
├── Apply calibration post-hoc
└── Supports multiple alpha levels without retraining
```

### 6.2 Classification Calibration

```python
model = PerpetualBooster(objective="LogLoss", save_node_stats=True)
model.fit(X_train, y_train)
model.calibrate(X_cal, y_cal, alpha=[0.01, 0.05, 0.1])

probs = model.predict_proba(X_test, calibrated=True)
sets = model.predict_sets(X_test)  # Conformal prediction sets
```

**Methods**:
- **Conformal**: Standard isotonic regression
- **WeightVariance**: Confidence-weighted calibration
- **GRP/MinMax**: Proprietary high-efficiency methods

### 6.3 Regression Uncertainty Quantification

```python
model.calibrate(X_cal, y_cal, alpha=[0.1, 0.2], method="GRP")
intervals = model.predict_intervals(X_test)
# Returns: {'0.1': {'lower': [...], 'upper': [...]}, '0.2': ...}
```

**Methods**:
| Method | Description | Requires save_node_stats |
|--------|-------------|-------------------------|
| Conformal | Split conformal/CQR | No |
| MinMax | Leaf value ranges | Yes |
| WeightVariance | Fold weight scaling | Yes |
| GRP | Log-odds percentiles | Yes |

### 6.4 Raw Prediction Distributions

```python
# Generate uncalibrated simulation distribution
dist = model.predict_distribution(X_test, n=100)
# Shape: (n_samples, 100)
```

---

## 7. Drift Detection

### 7.1 Data Drift Detection

```python
model = PerpetualBooster(save_node_stats=True)
model.fit(X_train, y_train)

data_drift = model.calculate_drift(X_new, drift_type="data")
print(f"Data Drift Score: {data_drift:.4f}")
# Higher = more significant distribution shift
```

**Method**: Average Chi-squared statistic across all internal nodes

### 7.2 Concept Drift Detection

```python
concept_drift = model.calculate_drift(X_new, drift_type="concept")
print(f"Concept Drift Score: {concept_drift:.4f}")
```

**Method**: Focuses on parent-of-leaf nodes to detect prediction pattern shifts

### 7.3 Drift Interpretation

| Score Range | Interpretation |
|-------------|----------------|
| ~0 | No drift detected |
| Low (0-1) | Minor drift, monitor |
| Medium (1-5) | Moderate drift, investigate |
| High (>5) | Significant drift, action needed |

---

## 8. Continual Learning

### 8.1 Problem Statement

Traditional GBM retraining has O(n²) complexity as data grows. Perpetual's continual learning reduces this to O(n).

### 8.2 Implementation

```python
# Enable continual learning
model = PerpetualBooster(objective="SquaredLoss", budget=1.0, reset=False)

# First batch
model.fit(X_batch1, y_batch1)

# Subsequent batches - use CUMULATIVE data
X_cumulative = pd.concat([X_batch1, X_batch2])
y_cumulative = pd.concat([y_batch1, y_batch2])
model.fit(X_cumulative, y_cumulative)
```

**Critical Requirement**: Always provide cumulative data to prevent catastrophic forgetting.

### 8.3 Complexity Comparison

| Approach | Complexity | Use Case |
|----------|------------|----------|
| Retrain (reset=True) | O(n²) | Full retraining |
| Continual (reset=False) | O(n) | Streaming/batch updates |

### 8.4 Performance Trade-offs

```
Continual Learning:
├── Maintains same MSE as retraining
├── Significantly faster for growing datasets
└── Preserves knowledge from previous data

Retraining:
├── Re-learns all patterns
├── O(n²) scaling issue
└── Simple, no data management needed
```

---

## 9. Explainability

### 9.1 Feature Importance

```python
importance = model.calculate_feature_importance(
    method="Gain",  # Options: Weight, Cover, TotalGain, TotalCover
    normalize=True
)
```

### 9.2 Partial Dependence Plots

```python
pd_values = model.partial_dependence(
    X,
    feature="feature_name",
    samples=100,  # Number of evenly spaced points
    percentile_bounds=(0.2, 0.98)
)
# Returns: ndarray where col 0 = feature values, col 1 = PD values
```

### 9.3 SHAP-like Prediction Contributions

```python
contributions = model.predict_contributions(
    X_sample,
    method="Shapley"  # Options: Average, Weight, BranchDifference, etc.
)
# Shape: (n_samples, n_features + 1)
# Last column is bias term
```

**Methods Available**:
| Method | Description |
|--------|-------------|
| Average | Internal node averages |
| Shapley | Exact tree SHAP values |
| Weight | Saabas-style leaf weights |
| BranchDifference | Chosen vs other branch |
| MidpointDifference | Weighted branch difference |
| ProbabilityChange | LogLoss-specific probability change |

---

## 10. Model IO and Export

### 10.1 Native Serialization

```python
# JSON export/import
model.save_model("model.json")
model = PerpetualBooster.from_json("model.json")

# Native format
model.save_booster("model.perp")
model = PerpetualBooster.load_booster("model.perp")
```

### 10.2 XGBoost Export

```python
model.save_as_xgboost("model.json")
```

### 10.3 ONNX Export

```python
model.save_as_onnx("model.onnx")
```

### 10.4 Sklearn Interface

```python
from perpetual.sklearn import PerpetualClassifier, PerpetualRegressor

# Drop-in replacement for sklearn
clf = PerpetualClassifier(budget=0.5)
clf.fit(X_train, y_train)
score = clf.score(X_test, y_test)
```

---

## 11. API Reference Summary

### 11.1 PerpetualBooster Constructor Parameters

```python
PerpetualBooster(
    objective='LogLoss',           # Loss function
    budget=0.5,                    # Complexity control
    num_threads=None,              # Parallel threads
    monotone_constraints=None,     # Monotonic constraints
    categorical_features='auto',   # Categorical handling
    save_node_stats=False,         # Enable calibration/drift
    missing=nan,                   # Missing value
    allow_missing_splits=True,
    create_missing_branch=False,
    log_iterations=0,
    feature_importance_method='Gain',
    max_bin=256,                   # Histogram bins
    max_cat=1000,                  # Max categories
    interaction_constraints=None
)
```

### 11.2 Key Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `fit(X, y)` | Self | Train model |
| `predict(X)` | ndarray | Point predictions |
| `predict_proba(X)` | ndarray | Class probabilities |
| `predict_intervals(X)` | dict | Prediction intervals |
| `predict_sets(X)` | dict | Conformal sets |
| `calibrate(X, y, alpha)` | Self | Post-hoc calibration |
| `calculate_drift(X, type)` | float | Drift detection |
| `partial_dependence(X, f)` | ndarray | PDP values |
| `predict_contributions(X)` | ndarray | SHAP values |
| `save_model(path)` | None | Export model |

---

## 12. Installation and Dependencies

### 12.1 Requirements

- Python 3.9+
- Rust toolchain (for building from source)

### 12.2 Installation

```bash
pip install perpetual
```

### 12.3 Optional Dependencies

- Polars: For zero-copy data transfer
- Scikit-learn: For sklearn interface compatibility
- ONNX Runtime: For ONNX export

---

## 13. Performance Characteristics

### 13.1 Training Complexity

| Operation | Complexity | Notes |
|-----------|------------|-------|
| Histogram building | O(n × features) | Binned features |
| Tree construction | O(trees × bins × features) | Rayon parallelism |
| Continual learning | O(n) | Vs O(n²) for retraining |

### 13.2 Memory Usage

- Configurable via `memory_limit` parameter
- Node statistics (if `save_node_stats=True`) increase memory
- Zero-copy Polars integration reduces overhead

### 13.3 Parallelism

- Automatic multi-threading via Rayon
- Configurable `num_threads`
- Parallel predictions support

---

## 14. Use Case Recommendations

### 14.1 When to Use Perpetual

✓ Need state-of-the-art GBM performance  
✓ Want to avoid hyperparameter tuning  
✓ Causal inference requirements  
✓ Production deployment needs calibration  
✓ Streaming/continual learning scenarios  
✓ Drift monitoring requirements  

### 14.2 When to Consider Alternatives

✗ Need GPU acceleration  
✗ Deep learning architectures required  
✗ Very small datasets (<100 samples)  

---

## 15. Comparison with Alternatives

| Feature | Perpetual | XGBoost | LightGBM | CatBoost |
|---------|-----------|---------|----------|----------|
| Single hyperparameter | ✓ | ✗ | ✗ | ✗ |
| Built-in calibration | ✓ | ✗ | ✗ | ✗ |
| Causal ML | ✓ | ✗ | ✗ | ✗ |
| Drift detection | ✓ | ✗ | ✗ | ✗ |
| Continual learning | ✓ | ✗ | ✗ | ✗ |
| Rust core | ✓ | ✗ | ✗ | ✗ |
| ONNX export | ✓ | ✓ | ✗ | ✗ |

---

## 16. Tutorial Resources

The documentation includes extensive tutorials:

1. **Basic**: Classification, Regression, Ranking
2. **Calibration**: Regression/Classification calibration deep-dives
3. **Causal**:
   - Uplift Modeling (Criteo dataset)
   - Double Machine Learning (Wage gap)
   - Policy Learning
   - Instrumental Variables
   - Fairness-aware modeling
4. **Advanced**:
   - Custom objectives
   - Drift detection
   - Continual learning

---

## 17. Limitations and Considerations

### 17.1 Current Limitations

- No native GPU support
- Smaller community vs XGBoost/LightGBM
- ONNX export may not support all features

### 17.2 Best Practices

1. Always use cumulative data for continual learning
2. Set `save_node_stats=True` for calibration/drift
3. Use appropriate budget based on dataset size
4. Monitor drift scores in production
5. Validate calibration on held-out data

---

## 18. References

- **Documentation**: https://perpetual-ml.github.io/perpetual/
- **GitHub**: https://github.com/perpetual-ml/perpetual
- **Blog**: https://perpetual-ml.com/blog/how-perpetual-works
- **PyPI**: https://pypi.org/project/perpetual/

---

## 19. Summary

Perpetual represents a significant advancement in gradient boosting machines by:

1. **Simplifying Usage**: Single budget parameter eliminates hyperparameter tuning
2. **Enhancing Reliability**: Built-in calibration, drift detection, continual learning
3. **Enabling Causal Inference**: Native DML, uplift modeling, policy learning
4. **Maintaining Performance**: Rust core ensures competitive speed
5. **Production Readiness**: XGBoost/ONNX export, serialization, sklearn compatibility

For practitioners seeking a modern, capable GBM with strong causal inference support and reduced operational overhead, Perpetual is an excellent choice.

---

*Research completed: February 27, 2026*  
*Source: Perpetual Documentation v1.9.2*
