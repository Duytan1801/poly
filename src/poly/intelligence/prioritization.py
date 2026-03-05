"""
Market prioritization utilities.
Prioritizes markets by signal strength for insider detection.
"""

from typing import List, Dict, Tuple


def categorize_market_insider_probability(category: str) -> float:
    """
    Score market categories by insider trading probability.
    Higher score = more likely to have insider activity.
    """
    category_scores = {
        "politics": 0.9,  # High insider probability (polls, internal info)
        "crypto": 0.7,  # Medium-high (whale movements, exchange data)
        "sports": 0.6,  # Medium (injury reports, team info)
        "business": 0.8,  # High (earnings, M&A, insider info)
        "entertainment": 0.4,  # Lower (public info)
        "science": 0.5,  # Medium (research results)
        "pop culture": 0.3,  # Lower (public sentiment)
    }

    category_lower = category.lower() if category else ""

    for key, score in category_scores.items():
        if key in category_lower:
            return score

    return 0.5  # Default medium probability


def prioritize_markets(
    condition_ids: List[str], metadata_cache: Dict[str, Dict], top_percent: float = 0.7
) -> List[str]:
    """
    Prioritize markets by signal strength.

    Returns top N% of markets ranked by:
    - Liquidity (50% weight) - Higher liquidity = more reliable
    - Volume (30% weight) - Higher volume = more active
    - Category insider score (20% weight) - Insider-prone categories

    Args:
        condition_ids: List of condition IDs to prioritize
        metadata_cache: Cache of market metadata
        top_percent: Percentage of markets to return (0.7 = top 70%)

    Returns:
        List of prioritized condition IDs
    """
    scored_markets: List[Tuple[str, float]] = []

    for cid in condition_ids:
        meta = metadata_cache.get(cid, {})

        # Skip if no metadata
        if not meta:
            continue

        liquidity = float(meta.get("liquidity", 0))
        volume = float(meta.get("volume", 0))
        category = meta.get("category", "")

        # Calculate composite score
        liquidity_score = liquidity * 0.5
        volume_score = volume * 0.3
        category_score = categorize_market_insider_probability(category) * 100000 * 0.2

        total_score = liquidity_score + volume_score + category_score

        scored_markets.append((cid, total_score))

    # Sort by score descending
    scored_markets.sort(key=lambda x: x[1], reverse=True)

    # Return top N%
    cutoff = int(len(scored_markets) * top_percent)
    if cutoff == 0 and scored_markets:
        cutoff = 1  # At least return 1 market

    return [cid for cid, _ in scored_markets[:cutoff]]


def filter_by_liquidity(
    condition_ids: List[str],
    metadata_cache: Dict[str, Dict],
    min_liquidity: float = 50000.0,
) -> List[str]:
    """
    Filter markets by minimum liquidity threshold.

    Args:
        condition_ids: List of condition IDs to filter
        metadata_cache: Cache of market metadata
        min_liquidity: Minimum liquidity in USD (default: $50k)

    Returns:
        List of condition IDs meeting liquidity threshold
    """
    filtered = []

    for cid in condition_ids:
        meta = metadata_cache.get(cid, {})
        liquidity = float(meta.get("liquidity", 0))

        if liquidity >= min_liquidity:
            filtered.append(cid)

    return filtered
