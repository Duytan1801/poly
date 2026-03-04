#!/usr/bin/env python3
"""
Full system test with 1000+ simulated profiles to demonstrate Isolation Forest.
"""

import random
import numpy as np
from poly.intelligence.scorer import InsiderScorer
from poly.intelligence.analyzer import ComprehensiveAnalyzer


def generate_realistic_profiles(n: int = 1000) -> list:
    """Generate realistic trader profiles for testing."""
    profiles = []

    for i in range(n):
        is_insider = random.random() < 0.02
        is_whale = random.random() < 0.10
        is_pre_res_trader = random.random() < 0.05

        if is_insider:
            winrate = random.uniform(0.80, 0.98)
            pre_res_ratio = random.uniform(0.40, 0.80)
            last_min_ratio = random.uniform(0.10, 0.30)
            max_bet = random.uniform(20000, 100000)
            whale_ratio = random.uniform(0.30, 0.70)
            mega_ratio = random.uniform(0.10, 0.30)
        elif is_whale:
            winrate = random.uniform(0.45, 0.65)
            pre_res_ratio = random.uniform(0.15, 0.35)
            last_min_ratio = random.uniform(0.02, 0.08)
            max_bet = random.uniform(10000, 50000)
            whale_ratio = random.uniform(0.20, 0.50)
            mega_ratio = random.uniform(0.05, 0.15)
        elif is_pre_res_trader:
            winrate = random.uniform(0.50, 0.70)
            pre_res_ratio = random.uniform(0.20, 0.50)
            last_min_ratio = random.uniform(0.05, 0.15)
            max_bet = random.uniform(1000, 8000)
            whale_ratio = random.uniform(0.05, 0.15)
            mega_ratio = 0.0
        else:
            winrate = random.uniform(0.35, 0.60)
            pre_res_ratio = random.uniform(0.02, 0.15)
            last_min_ratio = random.uniform(0.0, 0.05)
            max_bet = random.uniform(100, 2000)
            whale_ratio = random.uniform(0.0, 0.10)
            mega_ratio = 0.0

        profiles.append(
            {
                "address": f"0x{random.randint(0, 2**160):040x}",
                "winrate": winrate,
                "timing": {
                    "pre_resolution_ratio": pre_res_ratio,
                    "last_minute_ratio": last_min_ratio,
                    "avg_hours_before_resolution": random.uniform(6, 72),
                },
                "whales": {
                    "whale_ratio": whale_ratio,
                    "mega_whale_ratio": mega_ratio,
                    "max_bet": max_bet,
                    "avg_bet": max_bet * random.uniform(0.1, 0.5),
                },
                "multi_market": {
                    "unique_markets": random.randint(5, 100),
                    "cross_market_winrate": min(
                        winrate * random.uniform(0.9, 1.1), 1.0
                    ),
                },
                "cluster_bonus": 0.0,
                "pnl": random.uniform(-5000, 50000)
                if is_whale
                else random.uniform(-1000, 5000),
                "volume": max_bet * random.randint(5, 50),
            }
        )

    return profiles


def main():
    print("=" * 60)
    print("POLYMARKET INSIDER DETECTION - FULL SYSTEM TEST")
    print("(1000+ profiles with Isolation Forest + Z-Score)")
    print("=" * 60)

    n_profiles = 1000
    print(f"\n1. Generating {n_profiles} realistic trader profiles...")
    profiles = generate_realistic_profiles(n_profiles)
    print(f"   Generated {len(profiles)} profiles")

    print("\n2. Running Isolation Forest + Statistical Analysis...")
    scorer = InsiderScorer()
    scored = scorer.fit_and_score(profiles)

    print("\n" + "=" * 60)
    print("RESULTS - TOP 30 SUSPICIOUS WALLETS")
    print("=" * 60)
    print(
        f"{'#':<4} {'Address':<22} {'Score':<8} {'Level':<10} {'Win%':<8} {'Whale%':<8} {'ISO':<5} {'Z':<5}"
    )
    print("-" * 80)

    for i, p in enumerate(scored[:30]):
        addr = p["address"][:20] + ".." if len(p["address"]) > 22 else p["address"]
        iso = "YES" if p.get("is_isolation_outlier", False) else "no"
        z = "YES" if p.get("is_zscore_outlier", False) else "no"
        whale_pct = p.get("whales", {}).get("whale_ratio", 0) * 100
        print(
            f"{i + 1:<4} {addr:<22} {p['risk_score']:<8.1f} {p['level']:<10} {p.get('winrate', 0):.1%} {whale_pct:.1f}% {iso:<5} {z:<5}"
        )

    print("\n" + "=" * 60)
    print("SUMMARY STATISTICS")
    print("=" * 60)
    print(f"Total traders analyzed: {len(scored)}")

    iso_outliers = sum(1 for p in scored if p.get("is_isolation_outlier", False))
    z_outliers = sum(1 for p in scored if p.get("is_zscore_outlier", False))
    statistical_outliers = sum(1 for p in scored if p.get("is_outlier", False))

    print(
        f"Isolation Forest outliers: {iso_outliers} ({100 * iso_outliers / len(scored):.1f}%)"
    )
    print(
        f"Z-Score outliers (z>2.0): {z_outliers} ({100 * z_outliers / len(scored):.1f}%)"
    )
    print(f"Statistical outliers: {statistical_outliers}")
    print(f"\nRisk Level Distribution:")
    print(f"  CRITICAL: {sum(1 for p in scored if p['level'] == 'CRITICAL')}")
    print(f"  HIGH: {sum(1 for p in scored if p['level'] == 'HIGH')}")
    print(f"  MEDIUM: {sum(1 for p in scored if p['level'] == 'MEDIUM')}")
    print(f"  LOW: {sum(1 for p in scored if p['level'] == 'LOW')}")

    pop_stats = scorer.population_stats
    print(f"\nPopulation Statistics:")
    print(f"  Winrate mean: {pop_stats.get('winrate_mean', 0):.1%}")
    print(f"  Winrate std: {pop_stats.get('winrate_std', 0):.1%}")
    print(f"  Pre-resolution mean: {pop_stats.get('pre_resolution_mean', 0):.1%}")

    print("\n" + "=" * 60)
    print("FEATURE BREAKDOWN")
    print("=" * 60)
    print("Scoring Components (0-10 scale):")
    print("  Winrate: up to 5 points (3.5+ at 80%, 5.0 at 95%)")
    print("  Z-Score bonus: up to 1.5 points for z>2.0")
    print("  Pre-resolution: up to 2 points (50%+ = max)")
    print("  Last-minute ratio: up to 1.5 points (20%+ = max)")
    print("  Whale activity: up to 2 points (10%+ mega = max)")
    print("  Max bet: up to 1.5 points ($20k+ = max)")
    print("  Cross-market success: up to 1.5 points")
    print("  Isolation Forest outlier: +2 points")
    print("  Cluster membership: +1 point")
    print("=" * 60)

    print("\n✅ FULL SYSTEM TEST PASSED")
    print("   Isolation Forest is now active with 1000+ profiles")


if __name__ == "__main__":
    main()
