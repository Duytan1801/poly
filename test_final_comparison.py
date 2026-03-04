"""Final comprehensive test comparing old vs optimized CLI performance."""

import asyncio
import time
from poly.api.async_client import AsyncPolymarketClient
from poly.api.polymarket import PolymarketClient
from poly.intelligence.analyzer import ComprehensiveAnalyzer
from poly.intelligence.scorer import InsiderScorer


def test_old_cli_workflow(wallets=10):
    """Simulate the old CLI workflow (sequential)."""
    print("\n" + "=" * 80)
    print("OLD CLI WORKFLOW (Sequential)")
    print("=" * 80)

    import httpx

    client = PolymarketClient()
    analyzer = ComprehensiveAnalyzer()
    scorer = InsiderScorer()

    # Get sample addresses
    http = httpx.Client(timeout=30.0)
    resp = http.get("https://data-api.polymarket.com/trades", params={"limit": 100})
    addresses = list(set(t.get("proxyWallet") for t in resp.json()))[:wallets]
    http.close()

    print(f"\nAnalyzing {len(addresses)} wallets sequentially...")

    resolution_cache = {}
    market_metadata = {}
    total_trades = 0

    start = time.time()

    for i, addr in enumerate(addresses, 1):
        print(f"\n  [{i}/{len(addresses)}] Processing {addr[:20]}...")

        # 1. Fetch history (4 requests)
        trades = client.get_full_trader_history(addr, max_trades=200)
        total_trades += len(trades)
        print(f"    Fetched {len(trades)} trades")

        # 2. Fetch resolutions (N requests)
        cids = {t.get("conditionId") for t in trades if t.get("conditionId")}
        for cid in cids:
            if cid not in resolution_cache:
                res = client.get_market_resolution_state(cid)
                if res:
                    resolution_cache[cid] = res

        # 3. Fetch market metadata (N requests)
        for cid in cids:
            if cid not in market_metadata:
                info = client.get_market_info(cid)
                if info:
                    market_metadata[cid] = info

        # 4. Analyze & score
        profile = analyzer.analyze_trader(
            addr, trades, resolution_cache, market_metadata
        )
        scored = scorer.fit_and_score([profile])[0]

        if i == 1:
            print(f"    Sample score: {scored.get('total_score', 0):.2f}/10")

    elapsed = time.time() - start

    client.close()

    print(f"\n  Total time: {elapsed:.2f}s")
    print(f"  Total trades: {total_trades:,}")
    print(f"  Avg per wallet: {elapsed / len(addresses):.2f}s")

    return elapsed, total_trades


async def test_optimized_cli_workflow(wallets=10):
    """Simulate the optimized CLI workflow (batch)."""
    print("\n" + "=" * 80)
    print("OPTIMIZED CLI WORKFLOW (Batch + Async)")
    print("=" * 80)

    import httpx

    http = httpx.Client(timeout=30.0)
    resp = http.get("https://data-api.polymarket.com/trades", params={"limit": 100})
    addresses = list(set(t.get("proxyWallet") for t in resp.json()))[:wallets]
    http.close()

    print(f"\nAnalyzing {len(addresses)} wallets in parallel...")

    async with AsyncPolymarketClient() as client:
        analyzer = ComprehensiveAnalyzer()
        scorer = InsiderScorer()

        resolution_cache = {}
        market_metadata_cache = {}
        total_trades = 0

        start = time.time()

        # 1. BATCH: Fetch all histories
        print(f"\n  ⚡ Fetching histories for {len(addresses)} wallets...")
        histories = await client.fetch_trader_histories_batch(addresses, max_trades=200)
        total_trades = sum(len(h) for h in histories.values())
        print(f"     Fetched {total_trades:,} trades")

        # 2. BATCH: Collect and fetch resolutions
        all_cids = set()
        for trades in histories.values():
            all_cids.update(
                t.get("conditionId") for t in trades if t.get("conditionId")
            )

        print(f"\n  📊 Fetching {len(all_cids)} market resolutions...")
        await client.get_market_resolutions_batch(list(all_cids), resolution_cache)
        print(f"     Cached {len(resolution_cache)} resolutions")

        # 3. BATCH: Fetch market metadata
        new_cids = [cid for cid in all_cids if cid not in market_metadata_cache]
        print(f"\n  📁 Fetching {len(new_cids)} market metadata...")
        new_metadata = await client.get_market_info_batch(new_cids)
        market_metadata_cache.update(new_metadata)
        print(f"     Cached {len(market_metadata_cache)} metadata")

        # 4. Analyze all traders
        print(f"\n  🧠 Analyzing {len(addresses)} traders...")
        profiles = []
        for addr in addresses:
            trades = histories.get(addr, [])
            if not trades:
                continue

            profile = analyzer.analyze_trader(
                addr, trades, resolution_cache, market_metadata_cache
            )

            # Calculate winrate
            res_trades = [
                tr for tr in trades if tr.get("conditionId") in resolution_cache
            ]
            wins = sum(
                1
                for tr in res_trades
                if tr.get("outcomeIndex")
                == resolution_cache.get(tr["conditionId"], {}).get("winner_idx")
            )

            # Calculate PnL
            pnl = 0
            for tr in res_trades:
                cid = tr.get("conditionId")
                if not cid or cid not in resolution_cache:
                    continue
                size = float(tr.get("size", 0))
                price = float(tr.get("price", 0))
                outcome_idx = tr.get("outcomeIndex")
                winner_idx = resolution_cache[cid].get("winner_idx")

                if outcome_idx is None or winner_idx is None:
                    continue
                if int(outcome_idx) == int(winner_idx):
                    pnl += size * (1 - price)
                else:
                    pnl -= size * price

            profile.update(
                {
                    "total_trades": len(trades),
                    "winrate": wins / len(res_trades) if res_trades else 0,
                    "pnl": pnl,
                    "volume": sum(
                        float(t.get("size", 0)) * float(t.get("price", 0))
                        for t in trades
                    ),
                }
            )

            scored = scorer.fit_and_score([profile])[0]
            profiles.append(scored)

        elapsed = time.time() - start

        print(f"\n  Total time: {elapsed:.2f}s")
        print(f"  Total trades: {total_trades:,}")
        print(f"  Avg per wallet: {elapsed / len(addresses):.2f}s")

        if profiles:
            print(f"\n  Sample scores:")
            for i, p in enumerate(profiles[:3], 1):
                print(
                    f"    {i}. {p['address'][:20]}... Score: {p.get('total_score', 0):.2f}/10"
                )

        return elapsed, total_trades


if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("COMPREHENSIVE CLI PERFORMANCE COMPARISON")
    print("=" * 80)

    NUM_WALLETS = 10

    # Test old workflow
    old_time, old_trades = test_old_cli_workflow(NUM_WALLETS)

    # Test optimized workflow
    new_time, new_trades = asyncio.run(test_optimized_cli_workflow(NUM_WALLETS))

    # Calculate speedup
    speedup = old_time / new_time if new_time > 0 else 0

    print("\n" + "=" * 80)
    print("FINAL RESULTS")
    print("=" * 80)

    print(f"\n📊 Performance Comparison ({NUM_WALLETS} wallets):")
    print(f"  Old CLI:     {old_time:.2f}s ({old_trades:,} trades)")
    print(f"  Optimized:   {new_time:.2f}s ({new_trades:,} trades)")
    print(f"\n  🚀 SPEEDUP: {speedup:.1f}x FASTER")

    time_saved = old_time - new_time
    print(f"  ⏱️  Time saved: {time_saved:.2f}s per batch")

    # Extrapolate to larger workloads
    print(f"\n📈 Estimated Performance (100 wallets):")
    print(f"  Old CLI:     ~{old_time * 10:.1f}s")
    print(f"  Optimized:   ~{new_time * 10:.1f}s")
    print(f"  Time saved:  ~{time_saved * 10:.1f}s")

    if speedup >= 10:
        print(f"\n✅ SUCCESS! Achieved {speedup:.1f}x speedup (target: 10x)")
    elif speedup >= 5:
        print(f"\n✅ GREAT! Achieved {speedup:.1f}x speedup (target: 10x)")
    else:
        print(f"\n⚠️  Speedup is {speedup:.1f}x (target: 10x)")

    print("\n" + "=" * 80)
