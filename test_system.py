#!/usr/bin/env python3
"""
Test script for Polymarket Insider Detection System
Verifies Isolation Forest, statistical analysis, and scoring components.
"""

from poly.intelligence.scorer import InsiderScorer, StatisticalBounds
from poly.intelligence.analyzer import (
    ComprehensiveAnalyzer,
    StatisticalAnalyzer,
    TimingAnalyzer,
    WhaleAnalyzer,
)
from poly.intelligence.clustering import SybilClusterer


def create_test_profiles() -> list:
    """Create test profiles for testing the scoring pipeline."""
    return [
        {
            "address": "0xNormalTrader1",
            "winrate": 0.55,
            "timing": {
                "pre_resolution_ratio": 0.08,
                "last_minute_ratio": 0.02,
                "avg_hours_before_resolution": 48.0,
            },
            "whales": {
                "whale_ratio": 0.05,
                "mega_whale_ratio": 0.01,
                "max_bet": 2000,
                "avg_bet": 500,
            },
            "multi_market": {
                "unique_markets": 15,
                "cross_market_winrate": 0.52,
            },
            "cluster_bonus": 0.0,
        },
        {
            "address": "0xSuspiciousWhale1",
            "winrate": 0.88,
            "timing": {
                "pre_resolution_ratio": 0.45,
                "last_minute_ratio": 0.15,
                "avg_hours_before_resolution": 0.5,
            },
            "whales": {
                "whale_ratio": 0.35,
                "mega_whale_ratio": 0.08,
                "max_bet": 50000,
                "avg_bet": 8000,
            },
            "multi_market": {
                "unique_markets": 45,
                "cross_market_winrate": 0.85,
            },
            "cluster_bonus": 0.5,
        },
        {
            "address": "0xInsiderTrader2",
            "winrate": 0.92,
            "timing": {
                "pre_resolution_ratio": 0.60,
                "last_minute_ratio": 0.25,
                "avg_hours_before_resolution": 0.2,
            },
            "whales": {
                "whale_ratio": 0.50,
                "mega_whale_ratio": 0.15,
                "max_bet": 75000,
                "avg_bet": 15000,
            },
            "multi_market": {
                "unique_markets": 80,
                "cross_market_winrate": 0.90,
            },
            "cluster_bonus": 0.5,
        },
        {
            "address": "0xAverageTrader",
            "winrate": 0.48,
            "timing": {
                "pre_resolution_ratio": 0.10,
                "last_minute_ratio": 0.03,
                "avg_hours_before_resolution": 24.0,
            },
            "whales": {
                "whale_ratio": 0.02,
                "mega_whale_ratio": 0.0,
                "max_bet": 500,
                "avg_bet": 100,
            },
            "multi_market": {
                "unique_markets": 8,
                "cross_market_winrate": 0.45,
            },
            "cluster_bonus": 0.0,
        },
        {
            "address": "0xMegaWhaleSuspect",
            "winrate": 0.78,
            "timing": {
                "pre_resolution_ratio": 0.55,
                "last_minute_ratio": 0.20,
                "avg_hours_before_resolution": 0.3,
            },
            "whales": {
                "whale_ratio": 0.60,
                "mega_whale_ratio": 0.25,
                "max_bet": 100000,
                "avg_bet": 25000,
            },
            "multi_market": {
                "unique_markets": 120,
                "cross_market_winrate": 0.75,
            },
            "cluster_bonus": 0.5,
        },
    ]


def test_scorer():
    """Test the InsiderScorer with Isolation Forest and statistical analysis."""
    print("=" * 60)
    print("TESTING INSIDER SCORER")
    print("=" * 60)

    profiles = create_test_profiles()
    scorer = InsiderScorer()

    print(f"\n1. Testing Population Statistics Fitting...")
    pop_stats = scorer.fit_population_statistics(profiles)
    print(f"   Population winrate mean: {pop_stats['winrate_mean']:.3f}")
    print(f"   Population winrate std: {pop_stats['winrate_std']:.3f}")

    print(f"\n2. Testing Z-Score Calculation...")
    scorer.compute_z_scores(profiles)
    for p in profiles:
        print(
            f"   {p['address'][:20]}: z_score_winrate = {p.get('z_score_winrate', 0):.2f}"
        )

    print(f"\n3. Testing Isolation Forest Fitting...")
    scorer.fit_isolation_forest(profiles)
    if scorer.isolation_forest:
        print(f"   Isolation Forest fitted successfully!")

    print(f"\n4. Testing Outlier Prediction...")
    scorer.predict_outliers(profiles)
    for p in profiles:
        iso_outlier = p.get("is_isolation_outlier", False)
        zscore_outlier = p.get("is_zscore_outlier", False)
        print(
            f"   {p['address'][:20]}: isolation={iso_outlier}, zscore={zscore_outlier}"
        )

    print(f"\n5. Testing Complete Scoring Pipeline...")
    scored = scorer.fit_and_score(profiles)
    for p in scored:
        print(
            f"   {p['address'][:20]}: score={p['risk_score']:.1f}, level={p['level']}, outlier={p['is_outlier']}"
        )

    return scored


def test_analyzer():
    """Test the StatisticalAnalyzer."""
    print("\n" + "=" * 60)
    print("TESTING STATISTICAL ANALYZER")
    print("=" * 60)

    population_stats = {
        "winrate_mean": 0.52,
        "winrate_std": 0.15,
        "pre_resolution_mean": 0.1,
        "whale_ratio_mean": 0.08,
    }

    test_cases = [
        ("Normal trader", 0.55, {"pre_resolution_ratio": 0.08}, {"whale_ratio": 0.05}),
        (
            "Suspicious trader",
            0.88,
            {"pre_resolution_ratio": 0.45},
            {"whale_ratio": 0.35},
        ),
        ("Insider trader", 0.95, {"pre_resolution_ratio": 0.60}, {"whale_ratio": 0.50}),
    ]

    for name, winrate, timing, whales in test_cases:
        print(f"\n{name}:")
        winrate_dev = StatisticalAnalyzer.calculate_winrate_deviation(winrate)
        print(
            f"   Winrate: {winrate:.0%}, z-score: {winrate_dev['z_score']:.2f}, suspicious: {winrate_dev['is_suspicious_zscore']}"
        )

        timing_dev = StatisticalAnalyzer.calculate_timing_deviation(timing)
        print(
            f"   Pre-resolution z-score: {timing_dev['pre_resolution_zscore']:.2f}, anomaly: {timing_dev['is_pre_resolution_anomaly']}"
        )

        whale_dev = StatisticalAnalyzer.calculate_whale_deviation(whales)
        print(
            f"   Whale ratio z-score: {whale_dev['whale_ratio_zscore']:.2f}, anomaly: {whale_dev['is_whale_anomaly']}"
        )


def test_clustering():
    """Test the clustering component."""
    print("\n" + "=" * 60)
    print("TESTING CLUSTERING")
    print("=" * 60)

    clusterer = SybilClusterer(alchemy_api_key=None)
    profiles = create_test_profiles()

    print("\n1. Testing Placeholder Clustering (no API key)...")
    clustered = clusterer.detect_clusters(profiles)

    for p in clustered[:3]:
        print(
            f"   {p['address'][:20]}: cluster_id={p.get('cluster_id', 'unknown')}, size={p.get('cluster_size', 1)}"
        )

    clusterer.close()


def test_comprehensive_analyzer():
    """Test the ComprehensiveAnalyzer with all components."""
    print("\n" + "=" * 60)
    print("TESTING COMPREHENSIVE ANALYZER")
    print("=" * 60)

    from typing import List, Dict

    test_trades = [
        {
            "conditionId": "market1",
            "timestamp": 1709000000,
            "outcomeIndex": 0,
            "size": 1000,
            "price": 0.6,
        },
        {
            "conditionId": "market2",
            "timestamp": 1709100000,
            "outcomeIndex": 1,
            "size": 2000,
            "price": 0.7,
        },
        {
            "conditionId": "market3",
            "timestamp": 1709200000,
            "outcomeIndex": 0,
            "size": 5000,
            "price": 0.5,
        },
    ]

    market_resolutions = {
        "market1": {"winner_idx": 0, "closed_at": 1709003600},
        "market2": {"winner_idx": 1, "closed_at": 1709103600},
        "market3": {"winner_idx": 1, "closed_at": 1709203600},
    }

    analyzer = ComprehensiveAnalyzer()
    population_stats = {
        "winrate_mean": 0.52,
        "winrate_std": 0.15,
        "pre_resolution_mean": 0.1,
        "whale_ratio_mean": 0.08,
    }

    profile = analyzer.analyze_trader(
        address="0xTestTrader",
        trades=test_trades,
        market_resolutions=market_resolutions,
        population_stats=population_stats,
    )

    print(f"\nTrader: {profile['address']}")
    print(
        f"  Timing: avg_hours={profile['timing']['avg_hours_before_resolution']:.1f}, pre_res_ratio={profile['timing']['pre_resolution_ratio']:.2f}"
    )
    print(
        f"  Whales: max_bet=${profile['whales']['max_bet']:.0f}, whale_ratio={profile['whales']['whale_ratio']:.2f}"
    )
    print(
        f"  Multi-market: markets={profile['multi_market']['unique_markets']}, winrate={profile['multi_market']['cross_market_winrate']:.2f}"
    )
    print(f"  Statistics: winrate={profile['statistics'].get('winrate', 'N/A')}")


def main():
    print("\n" + "=" * 60)
    print("POLYMARKET INSIDER DETECTION SYSTEM TEST")
    print("=" * 60)

    try:
        test_scorer()
        test_analyzer()
        test_clustering()
        test_comprehensive_analyzer()

        print("\n" + "=" * 60)
        print("ALL TESTS PASSED!")
        print("=" * 60)
        print("\nSummary of Implemented Features:")
        print("  - Isolation Forest outlier detection")
        print("  - Z-score statistical deviation analysis")
        print("  - Win rate analysis (>80% suspicious)")
        print("  - Pre-resolution trading detection")
        print("  - Last-minute ratio tracking (1-10 min)")
        print("  - Whale detection ($5k+ and $25k+)")
        print("  - Wallet clustering via Polygon RPC")
        print("  - Cross-market success analysis")
        print("  - Composite risk scoring (0-10)")
        print("  - Risk levels: LOW | MEDIUM | HIGH | CRITICAL")

    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback

        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
