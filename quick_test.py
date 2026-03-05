#!/usr/bin/env python3
"""
Quick test to verify all components work together with 1000+ profiles.
"""

from poly.api.polymarket import PolymarketClient
from poly.intelligence.analyzer import ComprehensiveAnalyzer
from poly.intelligence.scorer import InsiderScorer
from poly.intelligence.clustering import SybilClusterer


def fetch_all_traders(client: PolymarketClient, target: int = 1000) -> list:
    """Fetch 1000+ traders from multiple categories."""
    categories = ["OVERALL", "CRYPTO", "POLITICS", "SPORTS", "BUSINESS", "ECONOMY"]
    periods = ["WEEK", "MONTH", "ALL"]
    all_traders = []
    seen = set()

    for cat in categories:
        if len(all_traders) >= target:
            break
        for period in periods:
            if len(all_traders) >= target:
                break
            try:
                traders = client.get_leaderboard(category=cat, period=period, limit=50)
                for t in traders:
                    addr = t.get("proxyWallet")
                    if addr and addr not in seen:
                        seen.add(addr)
                        all_traders.append(t)
            except Exception as e:
                print(f"   Error fetching {cat}/{period}: {e}")
                continue
    return all_traders[:target]


def main():
    print("=" * 60)
    print("POLYMARKET INTELLIGENCE HUB - FULL TEST (1000+ profiles)")
    print("=" * 60)

    client = PolymarketClient()
    analyzer = ComprehensiveAnalyzer()
    scorer = InsiderScorer()
    clusterer = SybilClusterer()

    print("\n1. Fetching 1000+ traders from Polymarket...")
    traders = fetch_all_traders(client, target=1000)
    print(f"   Found {len(traders)} traders")

    if not traders:
        print("No traders found - API may be rate limited")
        return

    print("\n2. Fetching trader histories...")
    test_traders = []
    for i, t in enumerate(traders):
        addr = t.get("proxyWallet")
        if addr:
            try:
                trades = client.get_trader_history(addr, limit=100)
                if trades:
                    test_traders.append(
                        {
                            "address": addr,
                            "trades": trades,
                            "pnl": t.get("pnl", 0),
                            "volume": t.get("vol", 0),
                        }
                    )
                if len(test_traders) % 100 == 0:
                    print(f"   Processed {len(test_traders)} traders...")
            except Exception:
                continue

    print(f"   Fetched histories for {len(test_traders)} traders")

    if len(test_traders) < 10:
        print("Not enough traders for Isolation Forest")
        return

    print("\n3. Collecting market resolutions...")
    all_cids = set()
    for t in test_traders:
        for tr in t["trades"]:
            if tr.get("conditionId"):
                all_cids.add(tr["conditionId"])

    print(f"   Found {len(all_cids)} unique markets")

    resolutions = {}
    for cid in list(all_cids)[:200]:
        try:
            res = client.get_market_resolution_state(cid)
            if res:
                resolutions[cid] = res
        except Exception:
            continue
    print(f"   Resolved {len(resolutions)} markets")

    print("\n4. Analyzing traders...")
    profiles = []
    for t in test_traders:
        try:
            profile = analyzer.analyze_trader(
                address=t["address"],
                trades=t["trades"],
                market_resolutions=resolutions,
            )
            profile["pnl"] = t.get("pnl", 0)
            profile["volume"] = t.get("volume", 0)

            res_trades = [
                tr for tr in t["trades"] if tr.get("conditionId") in resolutions
            ]
            wins = sum(
                1
                for tr in res_trades
                if tr.get("outcomeIndex")
                == resolutions.get(tr["conditionId"], {}).get("winner_idx")
            )
            profile["winrate"] = wins / len(res_trades) if res_trades else 0
            profile["total_trades"] = len(t["trades"])

            profiles.append(profile)
        except Exception:
            continue

    print(f"   Analyzed {len(profiles)} traders")

    if len(profiles) < 10:
        print("Not enough profiles for analysis")
        return

    print("\n5. Clustering wallets...")
    profiles = clusterer.detect_clusters(profiles)

    print("\n6. Scoring traders (with Isolation Forest + Z-Score)...")
    scored = scorer.fit_and_score(profiles)

    print("\n" + "=" * 60)
    print("RESULTS - TOP 20 SUSPICIOUS WALLETS")
    print("=" * 60)
    print(
        f"{'#':<4} {'Address':<22} {'Score':<8} {'Level':<10} {'Win%':<8} {'Trades':<8} {'ISO':<5} {'Z':<5}"
    )
    print("-" * 80)

    for i, p in enumerate(scored[:20]):
        addr = p["address"][:20] + ".." if len(p["address"]) > 22 else p["address"]
        iso = "YES" if p.get("is_isolation_outlier", False) else "no"
        z = "YES" if p.get("is_zscore_outlier", False) else "no"
        print(
            f"{i + 1:<4} {addr:<22} {p['risk_score']:<8.1f} {p['level']:<10} {p.get('winrate', 0):.1%} {p.get('total_trades', 0):<8} {iso:<5} {z:<5}"
        )

    print("\n" + "=" * 60)
    print("SUMMARY STATISTICS")
    print("=" * 60)
    print(f"Total traders analyzed: {len(scored)}")
    print(
        f"Isolation Forest outliers: {sum(1 for p in scored if p.get('is_isolation_outlier', False))}"
    )
    print(
        f"Z-Score outliers: {sum(1 for p in scored if p.get('is_zscore_outlier', False))}"
    )
    print(f"CRITICAL: {sum(1 for p in scored if p['level'] == 'CRITICAL')}")
    print(f"HIGH: {sum(1 for p in scored if p['level'] == 'HIGH')}")
    print(f"MEDIUM: {sum(1 for p in scored if p['level'] == 'MEDIUM')}")
    print(f"LOW: {sum(1 for p in scored if p['level'] == 'LOW')}")

    print("=" * 60)

    client.close()


if __name__ == "__main__":
    main()
