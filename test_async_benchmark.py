"""Benchmark async client vs synchronous client."""

import asyncio
import time
import sys
from poly.api.async_client import AsyncPolymarketClient, SyncWrapper
from poly.api.polymarket import PolymarketClient


def get_sample_addresses(n=10):
    """Get n sample addresses from recent trades."""
    import httpx

    client = httpx.Client(timeout=30.0)
    resp = client.get("https://data-api.polymarket.com/trades", params={"limit": 100})
    trades = resp.json()
    addresses = list(set(t.get("proxyWallet") for t in trades if t.get("proxyWallet")))
    client.close()
    return addresses[:n]


def test_sync_client(addresses):
    """Test synchronous client (baseline)."""
    print("\n" + "=" * 80)
    print("TEST: Synchronous Client (Baseline)")
    print("=" * 80)

    client = PolymarketClient()

    print(f"\nFetching histories for {len(addresses)} wallets sequentially...")
    start = time.time()

    histories = {}
    for addr in addresses:
        trades = client.get_full_trader_history(addr, max_trades=100)
        histories[addr] = trades

    elapsed = time.time() - start

    total_trades = sum(len(h) for h in histories.values())
    print(f"  Time: {elapsed:.2f}s")
    print(f"  Total trades fetched: {total_trades}")
    print(f"  Average per wallet: {elapsed / len(addresses):.2f}s")

    client.close()
    return elapsed, total_trades


def test_async_client(addresses):
    """Test async client with parallel fetching."""
    print("\n" + "=" * 80)
    print("TEST: Async Client with Parallel Fetching")
    print("=" * 80)

    async def fetch_all():
        async with AsyncPolymarketClient() as client:
            print(f"\nFetching histories for {len(addresses)} wallets in parallel...")
            start = time.time()

            histories = await client.fetch_trader_histories_batch(
                addresses, max_trades=100
            )

            elapsed = time.time() - start

            total_trades = sum(len(h) for h in histories.values())
            print(f"  Time: {elapsed:.2f}s")
            print(f"  Total trades fetched: {total_trades}")
            print(f"  Average per wallet: {elapsed / len(addresses):.2f}s")

            return elapsed, total_trades

    return asyncio.run(fetch_all())


def test_market_info_batch():
    """Test batch market metadata fetching."""
    print("\n" + "=" * 80)
    print("TEST: Batch Market Metadata Fetching")
    print("=" * 80)

    # Get some condition IDs
    import httpx

    sync_client = PolymarketClient()

    # Get trades to extract condition IDs
    trades = sync_client.get_trader_history(
        "0x56687bf447db6ffa42ffe2204a05edaa20f55839",  # Top trader
        limit=50,
    )
    condition_ids = list(
        set(t.get("conditionId") for t in trades if t.get("conditionId"))
    )[:20]

    print(f"\nFetching metadata for {len(condition_ids)} markets...")

    # Sync version
    print("\n1. Synchronous (baseline):")
    start = time.time()
    metadata_sync = {}
    for cid in condition_ids:
        info = sync_client.get_market_info(cid)
        if info:
            metadata_sync[cid] = info
    sync_time = time.time() - start
    print(f"  Time: {sync_time:.2f}s")
    print(f"  Markets fetched: {len(metadata_sync)}")

    # Async version
    async def fetch_batch():
        async with AsyncPolymarketClient() as client:
            start = time.time()
            metadata_async = await client.get_market_info_batch(condition_ids)
            async_time = time.time() - start
            return async_time, metadata_async

    print("\n2. Async parallel:")
    async_time, metadata_async = asyncio.run(fetch_batch())
    print(f"  Time: {async_time:.2f}s")
    print(f"  Markets fetched: {len(metadata_async)}")

    sync_client.close()

    speedup = sync_time / async_time if async_time > 0 else 0
    print(f"\n  Speedup: {speedup:.1f}x faster")

    return sync_time, async_time


def test_resolutions_batch():
    """Test batch resolution fetching."""
    print("\n" + "=" * 80)
    print("TEST: Batch Resolution Fetching")
    print("=" * 80)

    sync_client = PolymarketClient()

    # Get closed markets
    trades = sync_client.get_trader_history(
        "0x56687bf447db6ffa42ffe2204a05edaa20f55839", limit=100
    )
    condition_ids = list(
        set(t.get("conditionId") for t in trades if t.get("conditionId"))
    )[:20]

    print(f"\nFetching resolutions for {len(condition_ids)} markets...")

    # Sync version
    print("\n1. Synchronous (baseline):")
    cache = {}
    start = time.time()
    for cid in condition_ids:
        res = sync_client.get_market_resolution_state(cid)
        if res:
            cache[cid] = res
    sync_time = time.time() - start
    print(f"  Time: {sync_time:.2f}s")
    print(f"  Resolutions fetched: {len(cache)}")

    # Async version
    async def fetch_batch():
        async with AsyncPolymarketClient() as client:
            start = time.time()
            cache_async = await client.get_market_resolutions_batch(condition_ids)
            async_time = time.time() - start
            return async_time, cache_async

    print("\n2. Async parallel:")
    async_time, cache_async = asyncio.run(fetch_batch())
    print(f"  Time: {async_time:.2f}s")
    print(f"  Resolutions fetched: {len(cache_async)}")

    sync_client.close()

    speedup = sync_time / async_time if async_time > 0 else 0
    print(f"\n  Speedup: {speedup:.1f}x faster")

    return sync_time, async_time


if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("ASYNC CLIENT PERFORMANCE BENCHMARKS")
    print("=" * 80)

    # Test 1: Compare wallet history fetching
    num_wallets = 10
    print(f"\nFetching sample addresses (n={num_wallets})...")
    addresses = get_sample_addresses(num_wallets)
    print(f"Got {len(addresses)} addresses")

    sync_time, sync_trades = test_sync_client(addresses)
    async_time, async_trades = test_async_client(addresses)

    speedup_wallets = sync_time / async_time if async_time > 0 else 0

    print(f"\n📊 Wallet History Speedup: {speedup_wallets:.1f}x faster")
    print(f"   Sync: {sync_time:.2f}s | Async: {async_time:.2f}s")

    # Test 2: Market metadata batch
    sync_meta_time, async_meta_time = test_market_info_batch()
    speedup_meta = sync_meta_time / async_meta_time if async_meta_time > 0 else 0

    print(f"\n📊 Market Metadata Speedup: {speedup_meta:.1f}x faster")
    print(f"   Sync: {sync_meta_time:.2f}s | Async: {async_meta_time:.2f}s")

    # Test 3: Resolutions batch
    sync_res_time, async_res_time = test_resolutions_batch()
    speedup_res = sync_res_time / async_res_time if async_res_time > 0 else 0

    print(f"\n📊 Resolutions Speedup: {speedup_res:.1f}x faster")
    print(f"   Sync: {sync_res_time:.2f}s | Async: {async_res_time:.2f}s")

    # Overall summary
    print("\n" + "=" * 80)
    print("OVERALL PERFORMANCE SUMMARY")
    print("=" * 80)

    avg_speedup = (speedup_wallets + speedup_meta + speedup_res) / 3
    print(f"\n🎯 Average Speedup: {avg_speedup:.1f}x faster")

    if avg_speedup >= 10:
        print("\n✅ EXCELLENT! Async client achieves 10x+ speedup target!")
    elif avg_speedup >= 5:
        print("\n✅ GREAT! Async client achieves 5x+ speedup!")
    else:
        print("\n⚠️  Needs optimization to reach 10x speedup target")

    print(f"\nEstimated time for 100 wallets:")
    print(f"  Sync:  ~{sync_time * 10:.1f}s")
    print(f"  Async: ~{async_time * 10:.1f}s")
    print(f"  Time saved: ~{(sync_time - async_time) * 10:.1f}s")
