"""
Train Perpetual ML Model for Insider Trading Detection.

Loads collected trader profiles and trains a classifier to predict insiders.
"""

import os
import sys
import json
import argparse
import logging
from datetime import datetime
from typing import List, Dict, Optional

import numpy as np

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

DATA_DIR = "training_data"
OUTPUT_DIR = "models"
os.makedirs(OUTPUT_DIR, exist_ok=True)


def load_training_data(combined_file: str) -> tuple:
    """Load training data from JSON."""
    logger.info(f"Loading data from {combined_file}")

    with open(combined_file, "r") as f:
        data = json.load(f)

    logger.info(f"Loaded {len(data)} profiles")

    # Extract features and labels
    profiles = []
    labels = []

    for item in data:
        profile = item.copy()
        label = profile.pop("label", 0)  # Remove label from profile
        profiles.append(profile)
        labels.append(label)

    labels = np.array(labels, dtype=np.int32)

    # Log distribution
    insider_count = sum(labels)
    normal_count = len(labels) - insider_count
    logger.info(f"Insiders: {insider_count}, Normal: {normal_count}")

    return profiles, labels


def extract_features(profile: Dict) -> np.ndarray:
    """Extract features from profile for ML model."""
    features = []

    # Basic metrics
    winrate = profile.get("winrate", 0.5)
    features.append(winrate)

    trades = profile.get("total_trades_actual", profile.get("total_trades", 0))
    features.append(trades)

    pnl = profile.get("pnl", 0)
    features.append(pnl)

    # Multi-market
    mm = profile.get("multi_market", {})
    unique_markets = mm.get("unique_markets", 0)
    features.append(unique_markets)

    # Value-weighted accuracy
    vwa = profile.get("value_weighted_accuracy", winrate)
    features.append(vwa)

    # New scoring features
    first_ts = profile.get("first_trade_timestamp", 0)
    last_ts = profile.get("last_trade_timestamp", 0)
    avg_trade_size = profile.get("avg_trade_size", 0)
    max_trade_size = profile.get("max_trade_size", 0)
    total_volume = profile.get("total_volume", 0)

    # Fresh wallet score (simplified)
    if trades < 5 and avg_trade_size >= 1000:
        fresh_wallet = 2.5
    elif trades < 10 and avg_trade_size >= 500:
        fresh_wallet = 2.0
    elif trades < 20 and avg_trade_size >= 250:
        fresh_wallet = 1.5
    else:
        fresh_wallet = 0.0
    features.append(fresh_wallet)

    # Position sizing score
    if total_volume > 0 and max_trade_size > 0:
        concentration = max_trade_size / total_volume
        if concentration >= 0.60:
            position_sizing = 2.0
        elif concentration >= 0.40:
            position_sizing = 1.5
        elif concentration >= 0.25:
            position_sizing = 1.0
        else:
            position_sizing = 0.0
    else:
        position_sizing = 0.0
    features.append(position_sizing)

    # Early entry (placeholder - needs market creation time)
    features.append(0.0)

    # Off-hours (placeholder - needs timestamps)
    features.append(0.0)

    # Volume impact (placeholder)
    features.append(0.0)

    # Cluster score
    cluster_size = profile.get("cluster_size", 1)
    related_wallets = len(profile.get("related_wallets", []))
    coordinated_trades = profile.get("coordinated_trades", 0)

    if related_wallets >= 5 and coordinated_trades > 0:
        cluster = 2.5
    elif related_wallets >= 3:
        cluster = 2.0
    elif related_wallets >= 2:
        cluster = 1.5
    elif related_wallets >= 1:
        cluster = 1.0
    else:
        cluster = 0.0
    features.append(cluster)

    # Timing features
    t = profile.get("timing", {})
    features.append(t.get("last_minute_ratio", 0))
    features.append(t.get("pre_resolution_ratio", 0))
    features.append(t.get("avg_hours_before_resolution", 48))

    # Account age
    current_ts = int(datetime.now().timestamp())
    account_age_days = (current_ts - first_ts) / 86400 if first_ts else 0
    days_since = (current_ts - last_ts) / 86400 if last_ts else 0
    features.append(account_age_days)
    features.append(days_since)

    # Size features
    features.append(avg_trade_size)
    features.append(max_trade_size)

    # Efficiency
    pnl_per_trade = pnl / trades if trades > 0 else 0
    features.append(pnl_per_trade)

    # Winrate vs category (placeholder)
    features.append(0.0)

    return np.array(features, dtype=np.float64)


def train_model(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    budget: float = 0.5,
) -> "PerpetualClassifier":
    """Train Perpetual classifier."""
    from perpetual import PerpetualClassifier

    logger.info(f"Training Perpetual model (budget={budget})...")
    logger.info(f"Training samples: {len(X_train)}, Validation: {len(X_val)}")

    model = PerpetualClassifier(
        objective="LogLoss",
        budget=budget,
        num_threads=4,
        feature_importance_method="Gain",
        log_iterations=10,
    )

    model.fit(X_train, y_train)

    # Evaluate
    train_acc = model.score(X_train, y_train)
    val_acc = model.score(X_val, y_val)

    logger.info(f"Train accuracy: {train_acc:.4f}")
    logger.info(f"Validation accuracy: {val_acc:.4f}")

    # Feature importance
    importance = model.feature_importances_
    feature_names = [
        "winrate",
        "total_trades",
        "pnl",
        "unique_markets",
        "value_weighted_accuracy",
        "fresh_wallet",
        "position_sizing",
        "early_entry",
        "off_hours",
        "volume_impact",
        "cluster",
        "late_ratio",
        "pre_res_ratio",
        "avg_hours",
        "account_age",
        "days_since",
        "avg_size",
        "max_size",
        "pnl_per_trade",
        "category_winrate",
    ]

    logger.info("\nFeature Importances:")
    sorted_idx = np.argsort(importance)[::-1]
    for i in sorted_idx[:10]:
        logger.info(f"  {feature_names[i]}: {importance[i]:.4f}")

    return model


def calibrate_model(model, X_train, y_train, X_cal, y_cal, alpha: float = 0.1):
    """Calibrate model for better probability estimates."""
    logger.info("Calibrating model...")

    # First fit on training data
    model.fit(X_train, y_train)

    # Then calibrate
    model.calibrate(X_cal, y_cal, alpha)

    logger.info("Calibration complete!")

    return model


def main():
    parser = argparse.ArgumentParser(
        description="Train Perpetual insider detection model"
    )

    parser.add_argument(
        "data_file",
        help="Path to combined training data JSON",
    )
    parser.add_argument(
        "--budget",
        type=float,
        default=0.5,
        help="Perpetual model budget (default: 0.5)",
    )
    parser.add_argument(
        "--test-size",
        type=float,
        default=0.2,
        help="Test set fraction (default: 0.2)",
    )
    parser.add_argument(
        "--calibrate",
        action="store_true",
        help="Calibrate model for probability estimates",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output model path (default: auto-generated)",
    )

    args = parser.parse_args()

    # Load data
    profiles, labels = load_training_data(args.data_file)

    # Extract features
    logger.info("Extracting features...")
    X = np.array([extract_features(p) for p in profiles])

    # Handle NaN/Inf
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

    # Split data
    n = len(X)
    indices = np.random.permutation(n)
    test_count = int(n * args.test_size)
    val_count = int((n - test_count) * args.test_size)

    test_idx = indices[:test_count]
    val_idx = indices[test_count : test_count + val_count]
    train_idx = indices[test_count + val_count :]

    X_train, y_train = X[train_idx], labels[train_idx]
    X_val, y_val = X[val_idx], labels[val_idx]
    X_test, y_test = X[test_idx], labels[test_idx]

    logger.info(f"Train: {len(X_train)}, Val: {len(X_val)}, Test: {len(X_test)}")

    # Train model
    model = train_model(X_train, y_train, X_val, y_val, budget=args.budget)

    # Calibrate if requested
    if args.calibrate:
        # Use first 20% for calibration (out-of-sample)
        calibrate_count = int(len(X_train) * 0.2)
        X_cal = X_train[:calibrate_count]
        y_cal = y_train[:calibrate_count]
        X_train_cal = X_train[calibrate_count:]
        y_train_cal = y_train[calibrate_count:]

        model = calibrate_model(model, X_train_cal, y_train_cal, X_cal, y_cal)

    # Final evaluation
    test_acc = model.score(X_test, y_test)
    logger.info(f"\nFinal Test Accuracy: {test_acc:.4f}")

    # Get predictions
    proba = model.predict_proba(X_test)
    if proba.ndim > 1:
        proba = proba[:, 1]

    predictions = (proba >= 0.5).astype(int)

    # Calculate metrics
    tp = np.sum((predictions == 1) & (y_test == 1))
    tn = np.sum((predictions == 0) & (y_test == 0))
    fp = np.sum((predictions == 1) & (y_test == 0))
    fn = np.sum((predictions == 0) & (y_test == 1))

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = (
        2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
    )

    logger.info(f"\nTest Metrics:")
    logger.info(f"  Accuracy: {test_acc:.4f}")
    logger.info(f"  Precision: {precision:.4f}")
    logger.info(f"  Recall: {recall:.4f}")
    logger.info(f"  F1 Score: {f1:.4f}")
    logger.info(f"  TP: {tp}, TN: {tn}, FP: {fp}, FN: {fn}")

    # Save model
    if args.output:
        model_path = args.output
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        model_path = os.path.join(OUTPUT_DIR, f"insider_model_{timestamp}.perpetual")

    model.save_model(model_path)
    logger.info(f"\nModel saved to: {model_path}")

    # Save training report
    report = {
        "timestamp": datetime.now().isoformat(),
        "model_path": model_path,
        "config": {
            "budget": args.budget,
            "test_size": args.test_size,
            "calibrated": args.calibrate,
        },
        "data": {
            "total_samples": n,
            "train_samples": len(X_train),
            "val_samples": len(X_val),
            "test_samples": len(X_test),
            "insiders": int(np.sum(labels)),
            "normal": int(len(labels) - np.sum(labels)),
        },
        "metrics": {
            "test_accuracy": float(test_acc),
            "precision": float(precision),
            "recall": float(recall),
            "f1_score": float(f1),
            "tp": int(tp),
            "tn": int(tn),
            "fp": int(fp),
            "fn": int(fn),
        },
    }

    report_path = os.path.join(OUTPUT_DIR, "training_report.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    logger.info(f"Training report: {report_path}")


if __name__ == "__main__":
    main()
