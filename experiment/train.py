"""
Insider Trading Detection Model - Neural Network

Trains on collected trade data to predict which traders are likely insiders.
Analyzes trading patterns: timing, win rate, volume, consistency.
"""

import os
import sys
import json
import argparse
import logging
from typing import Dict, List, Tuple
from datetime import datetime

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class InsiderDataset(Dataset):
    def __init__(self, features: np.ndarray, labels: np.ndarray):
        self.features = torch.FloatTensor(features)
        self.labels = torch.FloatTensor(labels)

    def __len__(self):
        return len(self.labels)

    def __getitem__(self, idx):
        return self.features[idx], self.labels[idx]


class InsiderDetector(nn.Module):
    def __init__(self, input_dim: int, hidden_dims: List[int] = [128, 64, 32]):
        super().__init__()

        layers = []
        prev_dim = input_dim

        for hidden_dim in hidden_dims:
            layers.extend(
                [
                    nn.Linear(prev_dim, hidden_dim),
                    nn.BatchNorm1d(hidden_dim),
                    nn.ReLU(),
                    nn.Dropout(0.3),
                ]
            )
            prev_dim = hidden_dim

        layers.append(nn.Linear(prev_dim, 1))
        layers.append(nn.Sigmoid())

        self.network = nn.Sequential(*layers)

    def forward(self, x):
        return self.network(x)


def load_data(json_file: str) -> pd.DataFrame:
    """Load collected trade data from JSON."""
    with open(json_file, "r") as f:
        data = json.load(f)

    trades = data.get("trades", [])
    logger.info(f"Loaded {len(trades)} trades")

    return pd.DataFrame(trades)


def engineer_trader_features(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate trade-level data into trader-level features."""

    logger.info("Engineering trader features...")

    address_col = "proxyWallet" if "proxyWallet" in df.columns else "address"

    trader_features = []

    for trader, group in df.groupby(address_col):
        group = group.sort_values("time_before_resolution_min")

        features = {
            "trader": trader,
            "total_trades": len(group),
            "win_rate": group["won_trade"].mean() if len(group) > 0 else 0,
            "wins": group["won_trade"].sum(),
            "losses": len(group) - group["won_trade"].sum(),
            "avg_trade_size": group["size"].mean() if "size" in group else 0,
            "max_trade_size": group["size"].max() if "size" in group else 0,
            "min_trade_size": group["size"].min() if "size" in group else 0,
            "std_trade_size": group["size"].std() if len(group) > 1 else 0,
            "avg_time_before_res_min": group["time_before_resolution_min"].mean(),
            "min_time_before_res_min": group["time_before_resolution_min"].min(),
            "max_time_before_res_min": group["time_before_resolution_min"].max(),
            "std_time_before_res_min": group["time_before_resolution_min"].std()
            if len(group) > 1
            else 0,
            "trades_10min": len(group[group["time_before_resolution_min"] <= 10]),
            "trades_30min": len(group[group["time_before_resolution_min"] <= 30]),
            "trades_1hr": len(group[group["time_before_resolution_min"] <= 60]),
            "trades_1day": len(group[group["time_before_resolution_min"] <= 1440]),
            "pct_10min": len(group[group["time_before_resolution_min"] <= 10])
            / len(group)
            if len(group) > 0
            else 0,
            "pct_30min": len(group[group["time_before_resolution_min"] <= 30])
            / len(group)
            if len(group) > 0
            else 0,
            "pct_1hr": len(group[group["time_before_resolution_min"] <= 60])
            / len(group)
            if len(group) > 0
            else 0,
            "unique_markets": group["market_condition_id"].nunique()
            if "market_condition_id" in group
            else 0,
            "avg_volume": group["volume"].mean() if "volume" in group else 0,
        }

        group_10min = group[group["time_before_resolution_min"] <= 10]
        if len(group_10min) > 0:
            features["win_rate_10min"] = group_10min["won_trade"].mean()
        else:
            features["win_rate_10min"] = 0

        group_30min = group[group["time_before_resolution_min"] <= 30]
        if len(group_30min) > 0:
            features["win_rate_30min"] = group_30min["won_trade"].mean()
        else:
            features["win_rate_30min"] = 0

        group_1hr = group[group["time_before_resolution_min"] <= 60]
        if len(group_1hr) > 0:
            features["win_rate_1hr"] = group_1hr["won_trade"].mean()
        else:
            features["win_rate_1hr"] = 0

        trader_features.append(features)

    return pd.DataFrame(trader_features)


def create_labels(
    df: pd.DataFrame, threshold_time_min: int = 10, threshold_winrate: float = 0.6
) -> np.ndarray:
    """
    Create labels for insider detection.

    Insider = someone who:
    1. Trades very close to resolution (< threshold_time_min)
    2. Has high win rate (> threshold_winrate)
    """
    labels = []

    for _, row in df.iterrows():
        is_insider = 0

        if (
            row["min_time_before_res_min"] <= threshold_time_min
            and row["win_rate"] >= threshold_winrate
        ):
            is_insider = 1
        elif row["min_time_before_res_min"] <= 5 and row["win_rate"] >= 0.55:
            is_insider = 1
        elif (
            row["min_time_before_res_min"] <= threshold_time_min
            and row["win_rate"] >= 0.7
        ):
            is_insider = 1

        labels.append(is_insider)

    return np.array(labels)


def train_model(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    hidden_dims: List[int] = [128, 64, 32],
    epochs: int = 100,
    batch_size: int = 64,
    lr: float = 0.001,
    device: str = "cpu",
) -> Tuple[InsiderDetector, Dict]:
    train_dataset = InsiderDataset(X_train, y_train)
    val_dataset = InsiderDataset(X_val, y_val)

    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False)

    input_dim = X_train.shape[1]
    model = InsiderDetector(input_dim, hidden_dims).to(device)

    criterion = nn.BCELoss()
    optimizer = optim.Adam(model.parameters(), lr=lr, weight_decay=1e-5)
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode="min", patience=10, factor=0.5
    )

    best_val_loss = float("inf")
    best_model_state = None
    history = {"train_loss": [], "val_loss": [], "val_acc": []}

    for epoch in range(epochs):
        model.train()
        train_loss = 0

        for batch_x, batch_y in train_loader:
            batch_x, batch_y = batch_x.to(device), batch_y.to(device)

            optimizer.zero_grad()
            outputs = model(batch_x).squeeze()
            loss = criterion(outputs, batch_y)
            loss.backward()
            optimizer.step()

            train_loss += loss.item()

        train_loss /= len(train_loader)

        model.eval()
        val_loss = 0
        correct = 0
        total = 0

        with torch.no_grad():
            for batch_x, batch_y in val_loader:
                batch_x, batch_y = batch_x.to(device), batch_y.to(device)
                outputs = model(batch_x).squeeze()
                loss = criterion(outputs, batch_y)
                val_loss += loss.item()

                predicted = (outputs > 0.5).float()
                total += batch_y.size(0)
                correct += (predicted == batch_y).sum().item()

        val_loss /= len(val_loader)
        val_acc = correct / total

        scheduler.step(val_loss)

        history["train_loss"].append(train_loss)
        history["val_loss"].append(val_loss)
        history["val_acc"].append(val_acc)

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_model_state = model.state_dict().copy()

        if (epoch + 1) % 10 == 0:
            logger.info(
                f"Epoch {epoch + 1}/{epochs} - Train Loss: {train_loss:.4f}, Val Loss: {val_loss:.4f}, Val Acc: {val_acc:.4f}"
            )

    model.load_state_dict(best_model_state)

    return model, history


def evaluate_model(
    model: InsiderDetector, X_test: np.ndarray, y_test: np.ndarray, device: str = "cpu"
):
    """Evaluate model performance."""
    model.eval()

    test_dataset = InsiderDataset(X_test, y_test)
    test_loader = DataLoader(test_dataset, batch_size=64, shuffle=False)

    all_preds = []
    all_probs = []
    all_labels = []

    with torch.no_grad():
        for batch_x, batch_y in test_loader:
            batch_x = batch_x.to(device)
            outputs = model(batch_x).squeeze()
            probs = outputs.cpu().numpy()
            preds = (probs > 0.5).astype(int)

            all_probs.extend(probs)
            all_preds.extend(preds)
            all_labels.extend(batch_y.numpy())

    all_probs = np.array(all_probs)
    all_preds = np.array(all_preds)
    all_labels = np.array(all_labels)

    tp = np.sum((all_preds == 1) & (all_labels == 1))
    tn = np.sum((all_preds == 0) & (all_labels == 0))
    fp = np.sum((all_preds == 1) & (all_labels == 0))
    fn = np.sum((all_preds == 0) & (all_labels == 1))

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = (
        2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
    )
    accuracy = (tp + tn) / (tp + tn + fp + fn)

    return {
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn,
        "probabilities": all_probs,
        "predictions": all_preds,
        "labels": all_labels,
    }


def predict_insiders(
    model: InsiderDetector,
    df: pd.DataFrame,
    scaler: StandardScaler,
    device: str = "cpu",
    threshold: float = 0.5,
) -> pd.DataFrame:
    """Predict insider probability for each trader."""
    feature_cols = [c for c in df.columns if c != "trader"]
    X = df[feature_cols].fillna(0).values

    X_scaled = scaler.transform(X)
    X_tensor = torch.FloatTensor(X_scaled).to(device)

    model.eval()
    with torch.no_grad():
        probs = model(X_tensor).squeeze().cpu().numpy()

    df = df.copy()
    df["insider_probability"] = probs
    df["predicted_insider"] = (probs >= threshold).astype(int)

    return df.sort_values("insider_probability", ascending=False)


def main():
    parser = argparse.ArgumentParser(
        description="Train insider trading detection model"
    )
    parser.add_argument("data_file", help="Path to collected trades JSON file")
    parser.add_argument(
        "--output", "-o", help="Output model path", default="insider_model.pt"
    )
    parser.add_argument("--epochs", type=int, default=100, help="Training epochs")
    parser.add_argument("--batch-size", type=int, default=64, help="Batch size")
    parser.add_argument("--lr", type=float, default=0.001, help="Learning rate")
    parser.add_argument("--test-size", type=float, default=0.2, help="Test split ratio")
    parser.add_argument(
        "--threshold-time",
        type=int,
        default=10,
        help="Time threshold for insider (minutes)",
    )
    parser.add_argument(
        "--threshold-winrate",
        type=float,
        default=0.6,
        help="Win rate threshold for insider",
    )

    args = parser.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    logger.info(f"Using device: {device}")

    logger.info(f"Loading data from {args.data_file}")
    df_trades = load_data(args.data_file)

    logger.info("Engineering features...")
    df_traders = engineer_trader_features(df_trades)
    logger.info(f"Created features for {len(df_traders)} traders")

    logger.info(
        f"Creating labels (threshold: {args.threshold_time}min, {args.threshold_winrate * 100}% winrate)"
    )
    labels = create_labels(df_traders, args.threshold_time, args.threshold_winrate)
    logger.info(
        f"Label distribution: {np.sum(labels)} insiders, {len(labels) - np.sum(labels)} non-insiders"
    )

    feature_cols = [c for c in df_traders.columns if c != "trader"]
    X = df_traders[feature_cols].fillna(0).values
    y = labels

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=args.test_size, random_state=42, stratify=y
    )

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    logger.info("Training model...")
    model, history = train_model(
        X_train_scaled,
        y_train,
        X_test_scaled,
        y_test,
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
        device=device,
    )

    logger.info("Evaluating model...")
    metrics = evaluate_model(model, X_test_scaled, y_test, device)

    logger.info(f"\n=== Model Evaluation ===")
    logger.info(f"Accuracy:  {metrics['accuracy']:.4f}")
    logger.info(f"Precision: {metrics['precision']:.4f}")
    logger.info(f"Recall:    {metrics['recall']:.4f}")
    logger.info(f"F1 Score:  {metrics['f1']:.4f}")
    logger.info(
        f"TP: {metrics['tp']}, TN: {metrics['tn']}, FP: {metrics['fp']}, FN: {metrics['fn']}"
    )

    logger.info("\n=== Top 10 Potential Insiders ===")
    df_results = predict_insiders(model, df_traders, scaler, device)
    top_insiders = df_results.head(10)
    for _, row in top_insiders.iterrows():
        logger.info(
            f"  {row['trader'][:20]}... | Prob: {row['insider_probability']:.3f} | Win Rate: {row['win_rate']:.2%} | Time: {row['min_time_before_res_min']:.0f}min"
        )

    torch.save(
        {
            "model_state_dict": model.state_dict(),
            "scaler": scaler,
            "feature_cols": feature_cols,
            "metrics": metrics,
        },
        args.output,
    )

    logger.info(f"Model saved to {args.output}")

    df_results.to_csv("insider_predictions.csv", index=False)
    logger.info("Predictions saved to insider_predictions.csv")


if __name__ == "__main__":
    main()
