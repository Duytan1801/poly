"""
Feature Engineering for Insider Trading Detection Model.

Extracts features from collected trade data for model training:
- Trade timing features (time before jump, window size)
- Volume features (trade size, cumulative volume)
- Price features (price movement, volatility)
- Trader behavior features (win rate, PnL, trade frequency)
"""

import os
import json
import argparse
import logging
from datetime import datetime
from typing import List, Dict, Optional
import pandas as pd
import numpy as np
from collections import defaultdict

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def load_raw_data(input_file: str) -> Dict:
    """Load raw collected trade data."""
    with open(input_file, "r") as f:
        return json.load(f)


def extract_trade_features(trade: Dict, jump: Dict) -> Dict:
    """Extract features from a single trade relative to a price jump."""

    trade_ts = trade.get("timestamp", 0)
    if isinstance(trade_ts, str):
        trade_ts = int(trade_ts)

    jump_ts = jump.get("timestamp", 0)
    if isinstance(jump_ts, str):
        jump_ts = int(jump_ts)

    time_before_jump_sec = jump_ts - trade_ts
    time_before_jump_min = time_before_jump_sec / 60

    features = {
        "trade_id": trade.get("id", ""),
        "trader": trade.get("address", "").lower(),
        "token_id": jump.get("token_id", ""),
        "jump_timestamp": jump_ts,
        "trade_timestamp": trade_ts,
        "time_before_jump_sec": time_before_jump_sec,
        "time_before_jump_min": time_before_jump_min,
        "time_window_min": trade.get("time_before_jump_min", 0),
        "jump_percent": jump.get("percent_change", 0),
        "price_before_jump": jump.get("price_before", 0),
        "price_after_jump": jump.get("price_after", 0),
        "is_insider": 1
        if time_before_jump_min <= 60 and abs(jump.get("percent_change", 0)) >= 0.10
        else 0,
    }

    size = trade.get("size", 0)
    if isinstance(size, str):
        try:
            size = float(size)
        except:
            size = 0
    features["trade_size"] = size

    price = trade.get("price", 0)
    if isinstance(price, str):
        try:
            price = float(price)
        except:
            price = 0
    features["trade_price"] = price

    features["trade_value"] = size * price if price else 0

    side = trade.get("side", "buy").lower()
    features["is_buy"] = 1 if side == "buy" else 0

    outcome = trade.get("outcomeIndex", 0)
    if isinstance(outcome, str):
        try:
            outcome = int(outcome)
        except:
            outcome = 0
    features["outcome_index"] = outcome

    jump_direction = 1 if jump.get("percent_change", 0) > 0 else -1
    features["trade_aligned_with_jump"] = (
        1
        if (features["is_buy"] and jump_direction > 0)
        or (not features["is_buy"] and jump_direction < 0)
        else 0
    )

    return features


def aggregate_trader_features(trades: List[Dict], trader: str) -> Dict:
    """Aggregate features for a specific trader across all their trades."""

    trader_trades = [
        t for t in trades if t.get("address", "").lower() == trader.lower()
    ]

    if not trader_trades:
        return {}

    sizes = [t.get("trade_size", 0) for t in trader_trades]
    values = [t.get("trade_value", 0) for t in trader_trades]
    times = [t.get("time_before_jump_min", 0) for t in trader_trades]
    aligned = [t.get("trade_aligned_with_jump", 0) for t in trader_trades]
    is_buy = [t.get("is_buy", 0) for t in trader_trades]

    features = {
        "trader": trader,
        "total_trades": len(trader_trades),
        "avg_trade_size": np.mean(sizes) if sizes else 0,
        "max_trade_size": max(sizes) if sizes else 0,
        "total_volume": sum(values),
        "avg_time_before_jump_min": np.mean(times) if times else 0,
        "min_time_before_jump_min": min(times) if times else 0,
        "percent_aligned_with_jump": np.mean(aligned) if aligned else 0,
        "buy_ratio": np.mean(is_buy) if is_buy else 0,
    }

    grouped_by_jump = defaultdict(list)
    for t in trader_trades:
        key = t.get("jump_timestamp", 0)
        grouped_by_jump[key].append(t)

    features["trades_per_jump"] = (
        np.mean([len(v) for v in grouped_by_jump.values()]) if grouped_by_jump else 0
    )
    features["unique_jumps_traded"] = len(grouped_by_jump)

    return features


def engineer_features(input_file: str, output_file: str = None) -> Dict:
    """Main feature engineering pipeline."""

    logger.info(f"Loading data from {input_file}")
    data = load_raw_data(input_file)

    trades_raw = data.get("trades", [])
    jumps = data.get("jumps", [])

    logger.info(f"Loaded {len(trades_raw)} trades and {len(jumps)} jumps")

    trade_features = []
    for trade in trades_raw:
        jump_ts = trade.get("jump_timestamp")
        matching_jumps = [j for j in jumps if j.get("timestamp") == jump_ts]

        if matching_jumps:
            jump = matching_jumps[0]
            features = extract_trade_features(trade, jump)
            trade_features.append(features)

    logger.info(f"Extracted features for {len(trade_features)} trades")

    df_trades = pd.DataFrame(trade_features)

    traders = df_trades["trader"].unique() if not df_trades.empty else []
    logger.info(f"Aggregating features for {len(traders)} unique traders")

    trader_features = []
    for trader in traders:
        agg = aggregate_trader_features(trade_features, trader)
        if agg:
            trader_features.append(agg)

    df_traders = pd.DataFrame(trader_features)

    if output_file is None:
        base = input_file.replace(".json", "")
        output_file = f"{base}_features.json"

    output = {
        "trade_features": trade_features,
        "trader_features": trader_features,
        "trade_dataframe": df_trades.to_dict("records") if not df_trades.empty else [],
        "trader_dataframe": df_traders.to_dict("records")
        if not df_traders.empty
        else [],
        "summary": {
            "total_trades": len(trade_features),
            "total_traders": len(trader_features),
            "insider_trades": sum(
                1 for t in trade_features if t.get("is_insider", 0) == 1
            ),
            "unique_tokens": len(set(t.get("token_id", "") for t in trade_features)),
        },
    }

    with open(output_file, "w") as f:
        json.dump(output, f, indent=2, default=str)

    logger.info(f"Saved features to {output_file}")

    return output["summary"]


def create_training_dataset(input_file: str, output_file: str = None) -> pd.DataFrame:
    """Create a training-ready dataset with labels."""

    logger.info("Creating training dataset...")
    data = load_raw_data(input_file)

    trades = data.get("trades", [])
    jumps = data.get("jumps", [])

    features = []
    for trade in trades:
        jump_ts = trade.get("jump_timestamp")
        matching_jumps = [j for j in jumps if j.get("timestamp") == jump_ts]

        if matching_jumps:
            jump = matching_jumps[0]
            feat = extract_trade_features(trade, jump)
            features.append(feat)

    df = pd.DataFrame(features)

    if df.empty:
        logger.warning("No features extracted!")
        return df

    label_col = "is_insider"

    feature_cols = [
        "trade_size",
        "trade_value",
        "time_before_jump_min",
        "jump_percent",
        "is_buy",
        "outcome_index",
        "trade_aligned_with_jump",
    ]

    available_cols = [c for c in feature_cols if c in df.columns]

    X = df[available_cols].fillna(0)
    y = df[label_col] if label_col in df.columns else None

    if output_file is None:
        base = input_file.replace(".json", "")
        output_file = f"{base}_train.csv"

    train_df = X.copy()
    if y is not None:
        train_df[label_col] = y

    train_df.to_csv(output_file, index=False)

    logger.info(f"Saved training dataset to {output_file}")
    logger.info(f"Shape: {train_df.shape}")
    logger.info(f"Label distribution:\n{train_df[label_col].value_counts()}")

    return train_df


def parse_args():
    parser = argparse.ArgumentParser(
        description="Feature engineering for insider trading detection"
    )

    parser.add_argument("input", help="Input JSON file from collector")
    parser.add_argument("--output", "-o", help="Output file (default: auto-generated)")
    parser.add_argument(
        "--train-only", action="store_true", help="Only create training dataset"
    )

    return parser.parse_args()


def main():
    args = parse_args()

    if args.train_only:
        create_training_dataset(args.input, args.output)
    else:
        summary = engineer_features(args.input, args.output)
        logger.info(f"Summary: {json.dumps(summary, indent=2)}")


if __name__ == "__main__":
    main()
